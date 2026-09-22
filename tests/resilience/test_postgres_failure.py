"""Fault-injection: PostgreSQL becomes unreachable (CHECKLIST.md Phase
7C). Stops the real staging `postgres` container, proves the API
degrades safely -- a clean 5xx with no leaked internals, same
safe-error-response contract Phase 7B built for any unhandled exception
(app/__init__.py's global error handler), not a crash or a hung request
-- then restarts it and proves the API recovers **on its own**: no
restart of the `api` container is needed, since SQLAlchemy's connection
pool simply starts succeeding again once Postgres answers.

Destructive (see conftest.py): requires RUN_RESILIENCE_TESTS=1. Always
restarts postgres in a `finally` block, even if an assertion fails, so a
failed test never leaves the shared staging deployment down.
"""

from __future__ import annotations

import pytest
import requests

from conftest import REQUEST_TIMEOUT, auth_headers, compose, is_api_ready, wait_until

pytestmark = pytest.mark.destructive


def test_postgres_outage_degrades_safely_and_recovers_without_an_api_restart(api_base_url, admin_token):
    wait_until(lambda: is_api_ready(api_base_url), timeout=30, description="API to be ready before the test starts")

    compose("stop", "postgres")
    try:
        wait_until(
            lambda: requests.get(f"{api_base_url}/health/ready", timeout=5).status_code == 503,
            timeout=30,
            description="readiness to report the database as unavailable",
        )

        ready_response = requests.get(f"{api_base_url}/health/ready", timeout=REQUEST_TIMEOUT)
        assert ready_response.status_code == 503
        assert ready_response.json()["dependencies"]["database"] is False

        # A request that needs the database must fail safely, not crash or
        # leak internals (connection string, driver exception, traceback).
        score_response = requests.post(
            f"{api_base_url}/score",
            json={"application_reference": "resilience-pg-outage", "features": {"income": 0.5}},
            headers=auth_headers(admin_token),
            timeout=REQUEST_TIMEOUT,
        )
        assert score_response.status_code >= 500
        body_text = score_response.text.lower()
        assert "traceback" not in body_text
        assert "psycopg2" not in body_text
        assert "password" not in body_text
    finally:
        compose("start", "postgres")
        wait_until(lambda: is_api_ready(api_base_url), timeout=60, description="API to recover once postgres restarts")

    # Recovery is proven by real traffic succeeding again, not just the
    # readiness probe -- the api process was never restarted, so this also
    # proves the connection pool itself recovers, not just a fresh process.
    ready_after = requests.get(f"{api_base_url}/health/ready", timeout=REQUEST_TIMEOUT)
    assert ready_after.status_code == 200
    assert ready_after.json()["dependencies"]["database"] is True

    tenants_after = requests.get(f"{api_base_url}/tenants", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT)
    assert tenants_after.status_code == 200
