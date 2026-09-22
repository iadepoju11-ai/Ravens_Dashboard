"""Shared fixtures for the staging resilience/chaos-test suite
(CHECKLIST.md Phase 7C). Deliberately separate from tests/smoke/ (own
conftest.py, own requirements.txt) for the same reason smoke is separate
from apps/api and from tests/load/: an independently-runnable black-box
suite against a real deployed stack shouldn't share a dependency tree or
fixture module with what it's testing.

Unlike tests/smoke/ (safe to run anytime, never mutates the deployment's
own infrastructure), most tests here stop and restart real staging
containers (Postgres, Kafka, the API) -- disruptive to anything else
relying on that staging deployment being up while a test runs. Every such
test is marked `pytestmark = pytest.mark.destructive` at module level and
requires RUN_RESILIENCE_TESTS=1 to even run (see
`_require_resilience_opt_in` below) so it's never triggered by a plain
`pytest` invocation or an unrelated CI job by accident. Tests that don't
touch any container (e.g. duplicate-request-safety, pure HTTP
concurrency) are not marked and always run.

Every destructive test restores the container(s) it stopped before
returning, in a `finally` block, so a failing assertion never leaves the
shared staging deployment down for the next test or for a human.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests

API_BASE_URL = os.environ.get("SMOKE_API_BASE_URL", "http://localhost:5100/api/v1")
KEYCLOAK_URL = os.environ.get("SMOKE_KEYCLOAK_URL", "http://localhost:8181")
REALM = os.environ.get("SMOKE_REALM", "creditguard")
CLIENT_ID = os.environ.get("SMOKE_CLIENT_ID", "creditguard-api")
ADMIN_USERNAME = os.environ.get("SMOKE_ADMIN_USERNAME", "smoke-admin")
ADMIN_PASSWORD = os.environ.get("SMOKE_ADMIN_PASSWORD", "SmokeTest123!")

REQUEST_TIMEOUT = 15

# tests/resilience/conftest.py -> tests/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.staging.yml"
ENV_FILE = REPO_ROOT / ".env.staging"
_COMPOSE_BASE = ["docker", "compose", "-f", str(COMPOSE_FILE), "--env-file", str(ENV_FILE)]


def get_token(username: str, password: str) -> str:
    response = requests.post(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": CLIENT_ID, "username": username, "password": password},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def compose(*args: str, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
    """Runs `docker compose -f docker-compose.staging.yml --env-file
    .env.staging <args>` against this repo's staging stack, regardless of
    which directory pytest was invoked from."""
    return subprocess.run([*_COMPOSE_BASE, *args], capture_output=True, text=True, timeout=timeout, check=check)


def wait_until(predicate, timeout: float = 60.0, interval: float = 2.0, description: str = "condition") -> None:
    """Polls `predicate()` until it returns truthy or `timeout` elapses.
    Any exception a probe raises (e.g. a connection error while a
    container is down) just means "not ready yet", not a hard failure --
    the loop keeps going until the deadline."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except Exception as exc:  # noqa: BLE001 -- a probe failing is an expected mid-outage state, not a bug
            last_error = exc
        time.sleep(interval)
    suffix = f" (last probe error: {last_error})" if last_error else ""
    raise TimeoutError(f"timed out after {timeout}s waiting for {description}{suffix}")


def is_api_ready(api_base_url: str) -> bool:
    response = requests.get(f"{api_base_url}/health/ready", timeout=5)
    return response.status_code == 200


@pytest.fixture(autouse=True)
def _require_docker():
    if shutil.which("docker") is None:
        pytest.skip("docker not available to this test runner")


@pytest.fixture(autouse=True)
def _require_resilience_opt_in(request):
    if request.node.get_closest_marker("destructive") and os.environ.get("RUN_RESILIENCE_TESTS") != "1":
        pytest.skip("set RUN_RESILIENCE_TESTS=1 to run tests that stop/restart real staging containers")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "destructive: stops/restarts a real staging container; requires RUN_RESILIENCE_TESTS=1"
    )


@pytest.fixture(scope="session")
def run_id() -> str:
    return uuid.uuid4().hex[:10]


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return API_BASE_URL


@pytest.fixture(scope="session")
def admin_token() -> str:
    return get_token(ADMIN_USERNAME, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def deployed_model_version_id(api_base_url, admin_token, run_id) -> str:
    """Registers/approves/deploys a dedicated model version for this test
    session, same PlaceholderRuntime-resolving pattern as
    tests/smoke/test_staging_smoke.py's fixture of the same name -- kept
    separate rather than imported across suites (see module docstring)."""
    headers = auth_headers(admin_token)

    register = requests.post(
        f"{api_base_url}/models",
        json={
            "name": f"resilience-model-{run_id}",
            "version": "1.0.0",
            "artifact_uri": "file://resilience-placeholder.pkl",
        },
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    assert register.status_code == 201, register.text
    model_version_id = register.json()["model_version"]["id"]

    approve = requests.post(f"{api_base_url}/models/{model_version_id}/approve", headers=headers, timeout=REQUEST_TIMEOUT)
    assert approve.status_code == 200, approve.text

    deploy = requests.post(f"{api_base_url}/models/{model_version_id}/deploy", headers=headers, timeout=REQUEST_TIMEOUT)
    assert deploy.status_code == 200, deploy.text

    return model_version_id
