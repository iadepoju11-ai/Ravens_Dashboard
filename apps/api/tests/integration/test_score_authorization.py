"""Proves POST /score -- the first endpoint migrated off the
X-Tenant-Id-header trust model onto OIDC auth (CHECKLIST.md Phase 6) --
actually enforces authentication, permission, and tenant isolation, not
just that the happy path still works. See docs/architecture/oidc-rbac.md.

Uses a locally generated RSA keypair standing in for Keycloak, with the
JWKS lookup monkeypatched out (same approach as
tests/unit/test_jwt_verifier.py) so this runs fast against SQLite without
a live Keycloak; docs/local-development.md documents the one manual
end-to-end run against the real container.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.extensions import db
from app.models.model import Model, ModelVersion
from app.models.outbox import OutboxEvent
from app.models.tenant import Tenant
from app.models.user import User
from app.security import jwt_verifier

ISSUER = "http://keycloak:8080/realms/creditguard"
AUDIENCE = "creditguard-api"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_public_key)


@pytest.fixture(autouse=True)
def _fake_jwk_client(app, monkeypatch):
    app.config["OIDC_ISSUER"] = ISSUER
    app.config["OIDC_AUDIENCE"] = AUDIENCE
    monkeypatch.setattr(jwt_verifier, "_jwk_client", lambda: _FakeJWKClient())


def _token(*, sub="user-1", tenant_id=None, roles=("credit_analyst",), **overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": sub,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "email": f"{sub}@example.com",
        "realm_access": {"roles": list(roles)},
    }
    if tenant_id is not None:
        claims["tenant_id"] = tenant_id
    claims.update(overrides)
    return jwt.encode(claims, _private_key, algorithm="RS256")


def _create_tenant_with_deployed_model(slug: str) -> tuple[Tenant, ModelVersion]:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.flush()

    model = Model(tenant_id=tenant.id, name="credit-risk")
    db.session.add(model)
    db.session.flush()

    model_version = ModelVersion(
        model_id=model.id,
        version="1.0.0",
        status="deployed",
        artifact_uri="file://./model_artifacts/credit-risk-1.0.0.pkl",
    )
    db.session.add(model_version)
    db.session.commit()
    return tenant, model_version


def _score(client, token=None, **body):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {"application_reference": "APP-1", "features": {"income": 0.5}}
    payload.update(body)
    return client.post("/api/v1/score", json=payload, headers=headers)


def test_missing_token_is_rejected(client, app):
    with app.app_context():
        _create_tenant_with_deployed_model("no-token-bank")

    response = _score(client)
    assert response.status_code == 401


def test_garbage_token_is_rejected(client, app):
    with app.app_context():
        _create_tenant_with_deployed_model("garbage-token-bank")

    response = _score(client, token="not-a-real-jwt")
    assert response.status_code == 401


def test_expired_token_is_rejected(client, app):
    with app.app_context():
        tenant, _ = _create_tenant_with_deployed_model("expired-token-bank")
        tenant_id = tenant.id

    now = datetime.now(timezone.utc)
    token = _token(tenant_id=tenant_id, iat=now - timedelta(hours=1), exp=now - timedelta(minutes=1))
    response = _score(client, token=token)
    assert response.status_code == 401


def test_valid_token_without_decisions_create_permission_is_forbidden(client, app):
    with app.app_context():
        tenant, _ = _create_tenant_with_deployed_model("wrong-role-bank")
        tenant_id = tenant.id

    token = _token(sub="auditor-1", tenant_id=tenant_id, roles=("auditor",))
    response = _score(client, token=token)
    assert response.status_code == 403


def test_cross_tenant_model_version_is_not_found_not_leaked(client, app):
    with app.app_context():
        tenant_a, _ = _create_tenant_with_deployed_model("tenant-a-bank")
        _tenant_b, model_version_b = _create_tenant_with_deployed_model("tenant-b-bank")
        tenant_a_id = tenant_a.id
        model_version_b_id = model_version_b.id

    # Authenticated as tenant A, but the request names a model version that
    # belongs to tenant B -- must not score against another tenant's model,
    # and must not distinguish "exists but not yours" from "doesn't exist".
    token = _token(sub="analyst-a", tenant_id=tenant_a_id, roles=("credit_analyst",))
    response = _score(client, token=token, model_version_id=model_version_b_id)
    assert response.status_code == 404


def test_valid_request_scores_and_uses_the_identitys_tenant_not_a_header(client, app):
    with app.app_context():
        tenant, _ = _create_tenant_with_deployed_model("valid-request-bank")
        tenant_id = tenant.id
        other_tenant, _ = _create_tenant_with_deployed_model("decoy-header-bank")
        other_tenant_id = other_tenant.id

    token = _token(sub="analyst-1", tenant_id=tenant_id, roles=("credit_analyst",))
    # A stale/forged X-Tenant-Id header naming a *different* tenant must be
    # ignored entirely now that this endpoint trusts the verified identity.
    response = client.post(
        "/api/v1/score",
        json={"application_reference": "APP-1", "features": {"income": 0.5}, "request_id": "req-auth-1"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Id": other_tenant_id},
    )

    assert response.status_code == 201
    decision = response.get_json()["decision"]
    assert decision["tenant_id"] == tenant_id
    assert decision["tenant_id"] != other_tenant_id

    with app.app_context():
        events = OutboxEvent.query.filter_by(tenant_id=tenant_id).all()
        assert len(events) == 3
        assert OutboxEvent.query.filter_by(tenant_id=other_tenant_id).count() == 0


def test_first_login_provisions_a_user_and_second_login_reuses_it(client, app):
    with app.app_context():
        tenant, _ = _create_tenant_with_deployed_model("provisioning-bank")
        tenant_id = tenant.id

    token = _token(sub="new-user-1", tenant_id=tenant_id, roles=("credit_analyst",))
    first = _score(client, token=token, request_id="req-provision-1")
    assert first.status_code == 201

    with app.app_context():
        matching_users = User.query.filter_by(oidc_subject="new-user-1").all()
        assert len(matching_users) == 1
        provisioned_user_id = matching_users[0].id

    second = _score(client, token=token, request_id="req-provision-2")
    assert second.status_code == 201

    with app.app_context():
        matching_users = User.query.filter_by(oidc_subject="new-user-1").all()
        assert len(matching_users) == 1
        assert matching_users[0].id == provisioned_user_id
