"""Concurrent-load generator for `POST /score` against a real deployed
stack (CHECKLIST.md Phase 7C) -- establishes a measured staging
performance baseline, not a pass/fail test, so it's a standalone script
rather than a pytest suite (see docs/performance/staging-baseline.md for
the numbers this produced against the local staging stack, and how to
read them).

Deliberately separate from tests/smoke/ and tests/resilience/ (own
requirements.txt) -- same reasoning as those two: an independently
runnable black-box tool against a deployed stack shouldn't share a
dependency tree or fixture module with what it's exercising.

Usage (see docs/runbooks/deployment.md / `make staging-load-test`):

    pip install -r tests/load/requirements.txt
    python tests/load/load_test_score.py --concurrency 20 --total-requests 200

Every request carries a fresh, unique `request_id` -- this measures the
cost of *creating* new decisions, not idempotent-replay lookups (that
path is a single indexed SELECT, a very different and much cheaper
profile; see ScoringService._find_existing).

Every URL/credential is overridable by environment variable, matching
tests/smoke/conftest.py's convention (SMOKE_API_BASE_URL, ...).
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

API_BASE_URL = os.environ.get("SMOKE_API_BASE_URL", "http://localhost:5100/api/v1")
KEYCLOAK_URL = os.environ.get("SMOKE_KEYCLOAK_URL", "http://localhost:8181")
REALM = os.environ.get("SMOKE_REALM", "creditguard")
CLIENT_ID = os.environ.get("SMOKE_CLIENT_ID", "creditguard-api")
ADMIN_USERNAME = os.environ.get("SMOKE_ADMIN_USERNAME", "smoke-admin")
ADMIN_PASSWORD = os.environ.get("SMOKE_ADMIN_PASSWORD", "SmokeTest123!")

REQUEST_TIMEOUT = 30


def get_token() -> str:
    response = requests.post(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": CLIENT_ID, "username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def deploy_load_test_model(token: str, run_id: str) -> str:
    """Registers/approves/deploys a dedicated model version for this run
    -- resolves to PlaceholderRuntime, same as every other test suite in
    this repo (no trained artifact needed to measure API-layer overhead)."""
    headers = {"Authorization": f"Bearer {token}"}

    register = requests.post(
        f"{API_BASE_URL}/models",
        json={"name": f"load-test-model-{run_id}", "version": "1.0.0", "artifact_uri": "file://load-test-placeholder.pkl"},
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    register.raise_for_status()
    model_version_id = register.json()["model_version"]["id"]

    requests.post(f"{API_BASE_URL}/models/{model_version_id}/approve", headers=headers, timeout=REQUEST_TIMEOUT).raise_for_status()
    requests.post(f"{API_BASE_URL}/models/{model_version_id}/deploy", headers=headers, timeout=REQUEST_TIMEOUT).raise_for_status()
    return model_version_id


@dataclass
class RequestResult:
    status_code: int
    latency_seconds: float
    error: str | None = None


def _score_once(token: str, model_version_id: str, index: int) -> RequestResult:
    body = {
        "application_reference": f"load-test-{index}-{uuid.uuid4().hex[:8]}",
        "features": {"income": (index % 100) / 100.0},
        "model_version_id": model_version_id,
        "request_id": str(uuid.uuid4()),
    }
    start = time.perf_counter()
    try:
        response = requests.post(
            f"{API_BASE_URL}/score",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT,
        )
        latency = time.perf_counter() - start
        return RequestResult(status_code=response.status_code, latency_seconds=latency)
    except requests.RequestException as exc:
        latency = time.perf_counter() - start
        return RequestResult(status_code=0, latency_seconds=latency, error=str(exc))


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(round(pct / 100 * (len(sorted_values) - 1))))
    return sorted_values[index]


def fetch_observability(token: str) -> dict | None:
    try:
        response = requests.get(
            f"{API_BASE_URL}/monitoring/observability",
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()["observability"]
    except requests.RequestException:
        return None


def run(concurrency: int, total_requests: int, warmup_requests: int) -> None:
    print(f"API base URL: {API_BASE_URL}")
    print(f"Concurrency: {concurrency}, total requests: {total_requests}, warmup: {warmup_requests}")

    token = get_token()
    run_id = uuid.uuid4().hex[:10]
    model_version_id = deploy_load_test_model(token, run_id)
    print(f"Deployed model_version_id={model_version_id} for this run")

    if warmup_requests:
        print(f"Warming up with {warmup_requests} sequential request(s)...")
        for i in range(warmup_requests):
            _score_once(token, model_version_id, index=-1 - i)

    observability_before = fetch_observability(token)

    print("Running timed load...")
    wall_clock_start = time.perf_counter()
    results: list[RequestResult] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_score_once, token, model_version_id, i) for i in range(total_requests)]
        for future in as_completed(futures):
            results.append(future.result())
    wall_clock_seconds = time.perf_counter() - wall_clock_start

    observability_after = fetch_observability(token)

    successes = [r for r in results if r.status_code in (200, 201)]
    failures = [r for r in results if r.status_code not in (200, 201)]
    latencies = sorted(r.latency_seconds for r in successes)

    print()
    print("=== Client-observed results ===")
    print(f"Total requests:     {len(results)}")
    print(f"Successful (2xx):   {len(successes)}")
    print(f"Failed:             {len(failures)}")
    print(f"Wall-clock time:    {wall_clock_seconds:.2f}s")
    print(f"Throughput:         {len(successes) / wall_clock_seconds:.1f} req/s (successful requests / wall clock)")
    if latencies:
        print(f"Latency mean:       {statistics.mean(latencies) * 1000:.1f} ms")
        print(f"Latency p50:        {_percentile(latencies, 50) * 1000:.1f} ms")
        print(f"Latency p90:        {_percentile(latencies, 90) * 1000:.1f} ms")
        print(f"Latency p95:        {_percentile(latencies, 95) * 1000:.1f} ms")
        print(f"Latency p99:        {_percentile(latencies, 99) * 1000:.1f} ms")
        print(f"Latency max:        {max(latencies) * 1000:.1f} ms")
    if failures:
        sample_errors = {(r.status_code, r.error) for r in failures[:5]}
        print(f"Sample failures (status, error): {sample_errors}")

    if observability_before and observability_after:
        before_scoring = observability_before.get("scoring", {}).get("duration", {})
        after_scoring = observability_after.get("scoring", {}).get("duration", {})
        delta_count = (after_scoring.get("count") or 0) - (before_scoring.get("count") or 0)
        print()
        print("=== Server-observed results (GET /monitoring/observability, this run's delta) ===")
        print(f"Scoring calls recorded server-side during this run: {delta_count}")
        print(f"Server-side p50 (all-time, includes this run):      {after_scoring.get('p50_ms')} ms")
        print(f"Server-side p95 (all-time, includes this run):      {after_scoring.get('p95_ms')} ms")
        print(
            "Note: server-side duration excludes network/TLS/auth overhead the client-observed "
            "numbers above include -- server-side should read lower, and did in every run recorded "
            "in docs/performance/staging-baseline.md; a client-side number lower than server-side "
            "would indicate a measurement bug, not a real result."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--total-requests", type=int, default=200)
    parser.add_argument("--warmup-requests", type=int, default=5)
    args = parser.parse_args()
    run(concurrency=args.concurrency, total_requests=args.total_requests, warmup_requests=args.warmup_requests)


if __name__ == "__main__":
    main()
