"""Security-hardening regression tests (CHECKLIST.md Phase 7D) for the
controls that don't have a more specific home elsewhere: security
response headers, CORS origin allow-listing, and the fail-fast startup
guard against a default secret in production. Rate limiting has its own
file (test_rate_limiting.py) since it needs a dedicated app instance with
limiting re-enabled; the request-body size cap is in
tests/integration/test_security_hardening.py since proving it end-to-end
needs a real authenticated request, not just a route with no setup.
"""

from __future__ import annotations

import pytest

from app import create_app
from app.config import CONFIG_BY_NAME


def test_responses_carry_the_standard_security_headers(client):
    response = client.get("/api/v1/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Content-Security-Policy"] == "default-src 'none'"
    assert "max-age" in response.headers["Strict-Transport-Security"]


def test_cors_echoes_the_allowed_origin(client):
    # TestingConfig inherits CORS_ALLOWED_ORIGINS from Config's own default
    # (http://localhost:5173, the dev Vite origin) -- no override needed.
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"


def test_cors_does_not_echo_an_unlisted_origin(client):
    response = client.get("/api/v1/health", headers={"Origin": "http://evil.example.com"})
    assert "Access-Control-Allow-Origin" not in response.headers


def test_production_config_refuses_to_start_with_the_default_secret(monkeypatch):
    monkeypatch.setattr(CONFIG_BY_NAME["production"], "SECRET_KEY", "change-me")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production", database_uri="sqlite:///:memory:")


def test_production_config_starts_fine_with_a_real_secret(monkeypatch):
    monkeypatch.setattr(CONFIG_BY_NAME["production"], "SECRET_KEY", "a-real-generated-secret")
    # Must not raise -- this is the "someone actually did the setup step" case.
    create_app("production", database_uri="sqlite:///:memory:")
