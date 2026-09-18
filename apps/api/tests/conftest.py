from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import create_app
from app.extensions import db as _db
from app.security import jwt_verifier

TEST_OIDC_ISSUER = "http://keycloak:8080/realms/creditguard"
TEST_OIDC_AUDIENCE = "creditguard-api"

# One keypair for the whole test session, standing in for Keycloak's own
# signing key -- see tests/unit/test_jwt_verifier.py and
# tests/integration/test_score_authorization.py for tests that exercise
# validation failures (wrong issuer/audience/signature) directly; this
# fixture only needs to mint tokens that *pass* validation, for the many
# other tests that call an authenticated endpoint incidentally.
_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_public_key)


@pytest.fixture()
def app():
    flask_app = create_app("testing")
    flask_app.config["OIDC_ISSUER"] = TEST_OIDC_ISSUER
    flask_app.config["OIDC_AUDIENCE"] = TEST_OIDC_AUDIENCE
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(autouse=True)
def _fake_jwk_client(monkeypatch):
    monkeypatch.setattr(jwt_verifier, "_jwk_client", lambda: _FakeJWKClient())


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def make_token():
    """Mints a token that passes app/security/jwt_verifier.py's
    validation, for a given tenant/roles/subject. Use for tests that need
    *a* valid, authorized caller rather than testing auth itself."""

    def _make_token(tenant_id: str, roles: tuple[str, ...] = ("credit_analyst",), sub: str = "test-user") -> str:
        now = datetime.now(timezone.utc)
        claims = {
            "sub": sub,
            "iss": TEST_OIDC_ISSUER,
            "aud": TEST_OIDC_AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "email": f"{sub}@example.com",
            "tenant_id": tenant_id,
            "realm_access": {"roles": list(roles)},
        }
        return jwt.encode(claims, _private_key, algorithm="RS256")

    return _make_token


@pytest.fixture()
def auth_headers(make_token):
    """`headers={**auth_headers(tenant.id), ...}` for a quick valid
    credit_analyst bearer token -- the common case in existing tests that
    aren't specifically about authorization."""

    def _auth_headers(tenant_id: str, roles: tuple[str, ...] = ("credit_analyst",), sub: str = "test-user") -> dict:
        return {"Authorization": f"Bearer {make_token(tenant_id, roles=roles, sub=sub)}"}

    return _auth_headers
