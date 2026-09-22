"""Staging smoke tests for CHECKLIST.md Phase 7B: proves the metrics and
structured-logging paths work against a REAL running deployment, the
same "real HTTP, real deployed stack" spirit as test_staging_smoke.py.

The metrics/request-id checks are pure HTTP and portable to any reachable
deployment (SMOKE_API_BASE_URL, see conftest.py). The one log-format
check additionally shells out to `docker logs` against the local staging
container, and skips cleanly (not a failure) when Docker isn't reachable
from wherever this suite is running — e.g. against a real remote staging
host with no local Docker access to it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid

import pytest
import requests

from conftest import REQUEST_TIMEOUT, auth_headers

DOCKER_AVAILABLE = shutil.which("docker") is not None
STAGING_API_CONTAINER = os.environ.get("SMOKE_STAGING_API_CONTAINER", "creditguard-staging-api-1")


class TestMetricsEndpoint:
    def test_metrics_is_reachable_without_authentication(self, api_base_url):
        response = requests.get(f"{api_base_url.removesuffix('/api/v1')}/metrics", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")

    def test_metrics_exposes_the_expected_metric_families(self, api_base_url):
        response = requests.get(f"{api_base_url.removesuffix('/api/v1')}/metrics", timeout=REQUEST_TIMEOUT)
        body = response.text
        for expected in [
            "http_requests_total",
            "http_request_duration_seconds",
            "scoring_requests_total",
            "model_inference_duration_seconds",
            "db_query_duration_seconds",
            "outbox_events_published_total",
            "governance_results_total",
            "review_cases_opened_total",
        ]:
            assert expected in body, f"{expected} missing from /metrics"


class TestObservabilityJsonEndpoint:
    def test_requires_authentication(self, api_base_url):
        response = requests.get(f"{api_base_url}/monitoring/observability", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 401

    def test_returns_the_expected_shape_and_reflects_real_activity(self, api_base_url, admin_token):
        response = requests.get(
            f"{api_base_url}/monitoring/observability", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 200
        observability = response.json()["observability"]
        for key in ["http", "scoring", "model_inference", "explanation", "database", "outbox", "governance", "review_cases"]:
            assert key in observability
        # This very request, and every health check the compose
        # healthcheck has already run against a persistent staging
        # deployment, are real HTTP traffic against the same process --
        # these counters should be real, not stuck at zero placeholders.
        assert observability["http"]["total_requests"] > 0
        assert observability["database"]["query_duration"]["count"] > 0


class TestRequestIdPropagation:
    def test_a_supplied_request_id_is_echoed_back(self, api_base_url, admin_token):
        request_id = uuid.uuid4().hex
        response = requests.get(
            f"{api_base_url}/tenants",
            headers={**auth_headers(admin_token), "X-Request-ID": request_id},
            timeout=REQUEST_TIMEOUT,
        )
        assert response.headers.get("X-Request-ID") == request_id

    def test_a_request_id_is_generated_when_none_supplied(self, api_base_url, admin_token):
        response = requests.get(f"{api_base_url}/tenants", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT)
        assert response.headers.get("X-Request-ID")


class TestSafeErrorResponses:
    def test_an_invalid_bearer_token_never_leaks_internals(self, api_base_url):
        response = requests.get(
            f"{api_base_url}/decisions", headers={"Authorization": "Bearer not-a-real-token"}, timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 401
        assert "traceback" not in response.text.lower()
        assert "Exception" not in response.text


@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="docker not available to this test runner")
class TestStructuredLogging:
    def test_the_api_container_emits_valid_json_log_lines(self):
        result = subprocess.run(
            ["docker", "logs", "--tail", "100", STAGING_API_CONTAINER],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert lines, f"no log output found for container {STAGING_API_CONTAINER}"

        parsed_count = 0
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            parsed_count += 1
            assert "timestamp" in record
            assert "level" in record
            assert "message" in record
            # request_id/tenant_id keys must always be present (null
            # outside a request context), never silently omitted.
            assert "request_id" in record
            assert "tenant_id" in record

        assert parsed_count > 0, "no line in the recent log output parsed as JSON"

    def test_a_real_request_produces_a_log_line_carrying_its_request_id(self, api_base_url, admin_token):
        request_id = uuid.uuid4().hex
        response = requests.get(
            f"{api_base_url}/tenants",
            headers={**auth_headers(admin_token), "X-Request-ID": request_id},
            timeout=REQUEST_TIMEOUT,
        )
        assert response.status_code == 200

        result = subprocess.run(
            ["docker", "logs", "--tail", "200", STAGING_API_CONTAINER],
            capture_output=True,
            text=True,
            timeout=10,
        )
        matching = [line for line in result.stdout.splitlines() if request_id in line]
        assert matching, f"no log line found carrying request_id {request_id}"
        record = json.loads(matching[-1])
        assert record["request_id"] == request_id
