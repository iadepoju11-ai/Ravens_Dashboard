"""End-to-end security-hardening checks (CHECKLIST.md Phase 7D) that need
a real authenticated request against a real tenant to prove anything --
see tests/unit/test_security_hardening.py for the checks that don't
(headers, CORS, the production-secret startup guard).
"""

from __future__ import annotations

from app.extensions import db
from app.models.tenant import Tenant


def test_an_oversized_request_body_is_rejected_with_413(app, client, auth_headers):
    # A request that's rejected on size must never even reach
    # ScoringService -- the auth/tenant checks that run before
    # request.get_json() (app/api/v1/decisions.py) don't read the body,
    # so this needs a fully valid, authenticated call reaching the point
    # where the body is actually parsed for the cap to trigger at all.
    tenant = Tenant(name="Oversized Body Bank", slug="oversized-body-bank")
    db.session.add(tenant)
    db.session.commit()

    app.config["MAX_CONTENT_LENGTH"] = 100
    response = client.post(
        "/api/v1/score",
        data=b'{"application_reference": "' + b"x" * 200 + b'"}',
        content_type="application/json",
        headers=auth_headers(tenant.id),
    )
    assert response.status_code == 413
