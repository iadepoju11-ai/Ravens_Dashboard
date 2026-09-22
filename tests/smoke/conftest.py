"""Shared fixtures for the staging smoke-test suite (CHECKLIST.md Phase
7A). Every value is overridable by environment variable so the same
suite can point at any reachable deployment, not just the local staging
stack's default ports -- see docs/runbooks/deployment.md.
"""

from __future__ import annotations

import os

import pytest
import requests

API_BASE_URL = os.environ.get("SMOKE_API_BASE_URL", "http://localhost:5100/api/v1")
WEB_BASE_URL = os.environ.get("SMOKE_WEB_BASE_URL", "http://localhost:8090")
KEYCLOAK_URL = os.environ.get("SMOKE_KEYCLOAK_URL", "http://localhost:8181")
REALM = os.environ.get("SMOKE_REALM", "creditguard")
CLIENT_ID = os.environ.get("SMOKE_CLIENT_ID", "creditguard-api")

ADMIN_USERNAME = os.environ.get("SMOKE_ADMIN_USERNAME", "smoke-admin")
ADMIN_PASSWORD = os.environ.get("SMOKE_ADMIN_PASSWORD", "SmokeTest123!")
OTHER_TENANT_USERNAME = os.environ.get("SMOKE_OTHER_TENANT_USERNAME", "smoke-other-tenant")
OTHER_TENANT_PASSWORD = os.environ.get("SMOKE_OTHER_TENANT_PASSWORD", "SmokeTest123!")

REQUEST_TIMEOUT = 10


def get_token(username: str, password: str) -> str:
    """A real direct-grant (password) request against Keycloak -- the same
    grant type `creditguard-api`'s client config allows for testing (see
    infra/keycloak/creditguard-realm.json), never used by the real
    frontend, which is Authorization Code + PKCE only."""
    response = requests.post(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "username": username,
            "password": password,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return API_BASE_URL


@pytest.fixture(scope="session")
def web_base_url() -> str:
    return WEB_BASE_URL


@pytest.fixture(scope="session")
def admin_token() -> str:
    """smoke-admin: tenant `staging-smoke-bank`, role `admin` (full
    permissions, see app/security/permissions.py) -- used for every
    workflow this suite exercises except proving tenant isolation."""
    return get_token(ADMIN_USERNAME, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def other_tenant_token() -> str:
    """smoke-other-tenant: tenant `staging-smoke-bank-b`, same `admin`
    role -- same permissions, different tenant, so any isolation failure
    is a real data-scoping bug, not a permissions difference."""
    return get_token(OTHER_TENANT_USERNAME, OTHER_TENANT_PASSWORD)
