"""Unit tests for OIDC access-token verification (app/security/jwt_verifier.py).

Uses a locally generated RSA keypair standing in for the OIDC provider's
signing key, with the JWKS lookup monkeypatched out -- these test the
actual signature/issuer/audience/expiry validation logic without needing
a running Keycloak (see docs/local-development.md for the one manual
end-to-end verification against the real container).
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

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


def _make_token(**claim_overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "abc123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "realm_access": {"roles": ["credit_analyst"]},
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, _private_key, algorithm="RS256")


def test_valid_token_decodes_to_its_claims(app):
    with app.app_context():
        claims = jwt_verifier.decode_access_token(_make_token())

    assert claims["sub"] == "abc123"
    assert claims["tenant_id"] == "11111111-1111-1111-1111-111111111111"


def test_expired_token_is_rejected(app):
    now = datetime.now(timezone.utc)
    token = _make_token(iat=now - timedelta(hours=1), exp=now - timedelta(minutes=1))

    with app.app_context(), pytest.raises(jwt_verifier.TokenValidationError):
        jwt_verifier.decode_access_token(token)


def test_wrong_issuer_is_rejected(app):
    token = _make_token(iss="http://attacker.example/realms/creditguard")

    with app.app_context(), pytest.raises(jwt_verifier.TokenValidationError):
        jwt_verifier.decode_access_token(token)


def test_wrong_audience_is_rejected(app):
    token = _make_token(aud="some-other-client")

    with app.app_context(), pytest.raises(jwt_verifier.TokenValidationError):
        jwt_verifier.decode_access_token(token)


def test_signature_from_an_untrusted_key_is_rejected(app):
    forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    forged_token = jwt.encode(
        {
            "sub": "attacker",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "tenant_id": "11111111-1111-1111-1111-111111111111",
        },
        forged_key,
        algorithm="RS256",
    )

    with app.app_context(), pytest.raises(jwt_verifier.TokenValidationError):
        jwt_verifier.decode_access_token(forged_token)


def test_error_message_never_leaks_library_internals(app):
    with app.app_context(), pytest.raises(jwt_verifier.TokenValidationError) as exc_info:
        jwt_verifier.decode_access_token(_make_token(aud="some-other-client"))

    assert "Invalid or missing authentication token" == exc_info.value.message
