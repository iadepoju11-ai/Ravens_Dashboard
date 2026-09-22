"""Duplicate-request safety, exercised as N simultaneous client-side
`/score` calls carrying the *same* idempotency key (`request_id`) against
the real staging API and Postgres (CHECKLIST.md Phase 7C).

**Honest caveat, discovered while writing this test**: this staging
deployment's `api` container runs gunicorn with no `--workers` flag
(`apps/api/Dockerfile`), i.e. a single synchronous worker (see
docs/performance/staging-baseline.md) -- one process handling one
request at a time. That means these N client-side-simultaneous requests
are actually serialized by gunicorn itself before they ever reach
`ScoringService`, so this test cannot force the genuine race window
(`_find_existing` returning "not found" for two calls before either
commits) the way real concurrent execution could. Confirmed empirically:
this test passed even against a build of the API that did *not* yet have
the `IntegrityError` handling described below, because the race it's
meant to catch never actually opens under single-worker serialization.

The genuine, deterministic proof of that race and its fix lives in
`apps/api/tests/unit/test_scoring_service.py::test_a_concurrent_duplicate_request_is_deduplicated_not_crashed`,
which forces the race directly (no threads, no worker model to fight)
by making `_find_existing`'s first call report "not found" and then
committing a colliding row itself, standing in for a concurrent winner.
`ScoringService` catches the resulting `IntegrityError` on the losing
insert and returns the winner's decision instead of a 500.

This test still earns its place here: it proves the idempotency/dedup
contract holds end-to-end against the real deployed stack under N
simultaneous submissions -- exactly one decision created, every other
call replayed safely, nothing 500s -- which is real coverage even though
it cannot exercise the specific race window the unit test targets. If
this deployment is ever changed to run multiple gunicorn workers (see
the load-testing doc's capacity-planning notes), this test would then
also be capable of catching a regression of the fix itself.

Not marked destructive and not gated behind RUN_RESILIENCE_TESTS -- this
test doesn't touch any container, only ordinary concurrent HTTP traffic
the API is meant to handle correctly.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

from conftest import REQUEST_TIMEOUT, auth_headers

CONCURRENCY = 10


def test_n_concurrent_requests_with_the_same_idempotency_key_produce_exactly_one_decision(
    api_base_url, admin_token, deployed_model_version_id
):
    request_id = f"resilience-dup-{uuid.uuid4().hex}"
    body = {
        "application_reference": f"resilience-dup-app-{uuid.uuid4().hex}",
        "features": {"income": 0.4},
        "model_version_id": deployed_model_version_id,
        "request_id": request_id,
    }

    def _send(_index: int):
        return requests.post(
            f"{api_base_url}/score", json=body, headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        )

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        responses = list(pool.map(_send, range(CONCURRENCY)))

    # Every call must succeed -- none of the racing losers may surface as
    # a 500 (the exact failure mode the IntegrityError handling prevents).
    statuses = [r.status_code for r in responses]
    assert all(status in (200, 201) for status in statuses), list(zip(statuses, [r.text for r in responses]))

    decision_ids = {r.json()["decision"]["id"] for r in responses}
    assert len(decision_ids) == 1, f"expected exactly one decision across {CONCURRENCY} racing calls, got {decision_ids}"

    # Exactly one call created it (201); every other racing call -- winner
    # or loser of the underlying DB race -- must report a replay (200).
    assert statuses.count(201) == 1, statuses
    assert statuses.count(200) == CONCURRENCY - 1, statuses
