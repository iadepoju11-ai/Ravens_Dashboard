"""Rate limiting (CHECKLIST.md Phase 7D, app/extensions.py's `limiter`).

Disabled in the shared `app`/`client` fixtures (TestingConfig's
RATELIMIT_ENABLED=False, app/config.py) so the rest of this suite's
hundreds of requests -- all sharing one "remote address" under Flask's
test client -- don't trip a limit meant for a single real caller. This
file re-enables it for its own app instances, so the mechanism itself is
still proven to work.

Flask-Limiter reads its config (RATELIMIT_ENABLED, RATELIMIT_DEFAULT)
from `app.config` at `init_app()` time, inside `create_app()` -- setting
`app.config[...]` *after* `create_app()` has already returned is too
late, the limiter has already captured the disabled state TestingConfig
sets by default. These tests instead monkeypatch the TestingConfig class
attribute itself before calling `create_app()`, so the override is in
place when `limiter.init_app(app)` actually runs.

Flask-Limiter enforces limits in a `before_request` hook, ahead of the
view function -- an unauthenticated call that would otherwise 401 still
counts against the limit, so these tests don't need a real tenant or
token, just repeated calls to any ordinary route.
"""

from __future__ import annotations

from app import create_app
from app.config import CONFIG_BY_NAME
from app.extensions import db as _db


def _build_client(monkeypatch, *, default_limit: str | None = None):
    monkeypatch.setattr(CONFIG_BY_NAME["testing"], "RATELIMIT_ENABLED", True)
    if default_limit is not None:
        monkeypatch.setattr(CONFIG_BY_NAME["testing"], "RATELIMIT_DEFAULT", default_limit)
    application = create_app("testing", database_uri="sqlite:///:memory:")
    with application.app_context():
        _db.create_all()
    return application.test_client()


def test_a_caller_exceeding_the_default_limit_gets_a_429(monkeypatch):
    client = _build_client(monkeypatch, default_limit="3 per minute")

    statuses = [client.get("/api/v1/tenants").status_code for _ in range(6)]
    assert statuses[:3] == [401, 401, 401]  # under the limit -- reach the view, fail auth normally
    assert 429 in statuses, statuses


def test_score_has_its_own_stricter_limit_than_the_app_wide_default(monkeypatch):
    # POST /score's own decorator (app/api/v1/decisions.py,
    # @limiter.limit("30 per minute")) is hardcoded, not config-driven --
    # set RATELIMIT_DEFAULT very generously here so a 429 within 32 calls
    # can only be /score's own tighter limit kicking in, not the app-wide
    # default.
    client = _build_client(monkeypatch, default_limit="1000 per minute")

    statuses = [
        client.post("/api/v1/score", json={"application_reference": "x", "features": {}}).status_code
        for _ in range(32)
    ]
    assert 429 in statuses, statuses


def test_metrics_and_health_are_exempt_from_rate_limiting(monkeypatch):
    client = _build_client(monkeypatch, default_limit="1 per minute")

    for _ in range(5):
        assert client.get("/metrics").status_code == 200
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/health/ready").status_code == 200


def test_rate_limiting_is_disabled_by_default_in_the_testing_config(client):
    # The shared fixture from conftest.py -- proves the opt-out this whole
    # file relies on is real, not just assumed.
    for _ in range(20):
        assert client.get("/api/v1/tenants").status_code == 401
