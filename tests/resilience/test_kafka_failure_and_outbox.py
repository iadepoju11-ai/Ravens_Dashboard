"""Fault-injection: Kafka becomes unreachable while outbox events are
pending (CHECKLIST.md Phase 7C). Kafka is deliberately not in the
critical scoring path (CLAUDE.md: "not in the critical scoring path
without justification") -- this test's central claim is that /score
keeps succeeding and the transactional outbox
(apps/api/app/services/outbox_service.py) keeps durably recording events
in Postgres even with the broker down, that publishing against a down
broker records retryable failures instead of losing or crashing on the
row, and that the same rows drain and publish once Kafka recovers -- the
retry-behaviour and duplicate-delivery-safety guarantees, proven here
against a real broker rather than the fake one
apps/api/tests/unit/test_outbox_service.py already covers at unit level.

.env.staging ships with KAFKA_ENABLED=false (nothing consumes these
topics yet -- see docs/runbooks/deployment.md's "Kafka" section), so
this test overrides it just for its own `flask events publish-outbox`
invocations via `docker compose exec -e`, without touching the
long-running api container's own configuration.

Destructive (see conftest.py): requires RUN_RESILIENCE_TESTS=1. Always
restarts kafka in a `finally` block.
"""

from __future__ import annotations

import subprocess

import pytest
import requests

from conftest import REQUEST_TIMEOUT, auth_headers, compose, is_api_ready, wait_until

pytestmark = pytest.mark.destructive


def _publish_outbox() -> subprocess.CompletedProcess:
    """`flask events publish-outbox` inside the running `api` container,
    with KAFKA_ENABLED forced on for just this one process -- cli.py
    exits 0 even when every event only retried (it only fails the command
    on a *permanent* failure, i.e. MAX_ATTEMPTS reached), so a zero exit
    code here proves nothing about whether Kafka was reachable; the
    stdout text is what this test actually asserts on."""
    return compose(
        "exec", "-T", "-e", "KAFKA_ENABLED=true", "api", "flask", "events", "publish-outbox", check=False, timeout=30
    )


def test_outbox_survives_a_kafka_outage_and_drains_once_kafka_recovers(
    api_base_url, admin_token, deployed_model_version_id
):
    wait_until(lambda: is_api_ready(api_base_url), timeout=30, description="API to be ready before the test starts")

    compose("stop", "kafka")
    try:
        # Scoring must keep working with the broker down.
        score_response = requests.post(
            f"{api_base_url}/score",
            json={
                "application_reference": "resilience-kafka-outage",
                "features": {"income": 0.2},
                "model_version_id": deployed_model_version_id,
            },
            headers=auth_headers(admin_token),
            timeout=REQUEST_TIMEOUT,
        )
        assert score_response.status_code == 201, score_response.text

        # The outbox rows for this decision were written in the same DB
        # transaction as the decision itself (app/services/scoring_service.py)
        # regardless of Kafka's availability. Publishing them now, with
        # Kafka down, must record retryable failures, not lose or crash on
        # the rows.
        publish_while_down = _publish_outbox()
        combined_output = publish_while_down.stdout + publish_while_down.stderr
        assert publish_while_down.returncode == 0, combined_output
        assert "retry" in publish_while_down.stdout, combined_output
    finally:
        compose("start", "kafka")

    # Kafka takes a few seconds to accept connections after `start` --
    # poll by actually trying to drain the outbox rather than sleeping a
    # fixed guess, until every previously-pending event has published.
    # (Safe to treat "no pending events left" as "published", not
    # "silently abandoned": events only leave "pending" by publishing
    # successfully or by exhausting MAX_ATTEMPTS=10 -- this test's outage
    # is a single attempt, nowhere near that ceiling.)
    def _drained() -> bool:
        result = _publish_outbox()
        return result.returncode == 0 and "no pending events" in result.stdout

    wait_until(_drained, timeout=90, interval=5, description="the outbox to drain once Kafka recovers")

    final_check = _publish_outbox()
    assert "no pending events" in final_check.stdout, final_check.stdout + final_check.stderr
