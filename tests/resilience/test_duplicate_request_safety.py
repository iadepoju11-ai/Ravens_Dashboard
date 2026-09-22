"""Concurrency: duplicate-event / duplicate-request safety proven against
a real deployed stack (CHECKLIST.md Phase 7C) -- fires genuinely
concurrent /score calls carrying the *same* client-supplied idempotency
key (`request_id`) at the real staging API and Postgres, the scenario the
deterministic unit-level reproduction in
apps/api/app/services/scoring_service.py's
`test_a_concurrent_duplicate_request_is_deduplicated_not_crashed` can
only simulate, not genuinely race. That unit test also pins the fix this
one is proving end-to-end: two overlapping calls can both pass the
initial idempotency lookup before either commits, so the actual
arbitration happens at the database's `uq_decision_tenant_request_id`
constraint -- ScoringService now catches the resulting IntegrityError and
returns the winner's decision instead of surfacing a 500 to the loser.

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
