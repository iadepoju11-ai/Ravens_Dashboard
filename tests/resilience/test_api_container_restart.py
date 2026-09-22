"""Fault-injection: the API container itself is restarted mid-deployment
(CHECKLIST.md Phase 7C) -- the scenario a rolling deploy, an OOM kill, or
a host reboot all produce. Proves the container comes back healthy on its
own (docker-compose.staging.yml's healthcheck, not a manual intervention)
and that a decision scored before the restart is still readable
afterward -- Postgres, not the API process, is the system of record, so a
restart must never appear to lose data.

Destructive (see conftest.py): requires RUN_RESILIENCE_TESTS=1.
"""

from __future__ import annotations

import pytest
import requests

from conftest import REQUEST_TIMEOUT, auth_headers, compose, is_api_ready, wait_until

pytestmark = pytest.mark.destructive


def test_api_restart_recovers_and_preserves_previously_scored_decisions(
    api_base_url, admin_token, deployed_model_version_id
):
    wait_until(lambda: is_api_ready(api_base_url), timeout=30, description="API to be ready before the test starts")

    before = requests.post(
        f"{api_base_url}/score",
        json={
            "application_reference": "resilience-api-restart",
            "features": {"income": 0.15},
            "model_version_id": deployed_model_version_id,
        },
        headers=auth_headers(admin_token),
        timeout=REQUEST_TIMEOUT,
    )
    assert before.status_code == 201, before.text
    decision_id = before.json()["decision"]["id"]

    compose("restart", "api")
    wait_until(lambda: is_api_ready(api_base_url), timeout=60, description="API to become ready again after the restart")

    after = requests.get(
        f"{api_base_url}/decisions/{decision_id}", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
    )
    assert after.status_code == 200
    assert after.json()["decision"]["id"] == decision_id
    assert after.json()["decision"]["application_reference"] == "resilience-api-restart"

    # The restarted process must also serve genuinely new traffic
    # correctly, not just replay data written before it restarted.
    after_restart_score = requests.post(
        f"{api_base_url}/score",
        json={
            "application_reference": "resilience-api-restart-post",
            "features": {"income": 0.1},
            "model_version_id": deployed_model_version_id,
        },
        headers=auth_headers(admin_token),
        timeout=REQUEST_TIMEOUT,
    )
    assert after_restart_score.status_code == 201, after_restart_score.text
