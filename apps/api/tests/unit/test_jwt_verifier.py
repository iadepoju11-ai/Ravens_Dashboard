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
from cryptography.hazmat.primitives import serialization
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


def test_algorithm_none_token_is_rejected(app):
    """CHECKLIST.md Phase 7D: the classic "alg: none" forgery -- a token
    with no signature at all, claiming to need none. Only possible to
    reach this app's verification logic if something upstream failed to
    reject an unsigned token outright; PyJWT's own decode requires a key
    for every algorithm except "none", and jwt_verifier.py never passes
    "none" in its `algorithms=["RS256"]` allowlist, so this must fail
    before any claim in the forged token is trusted."""
    now = datetime.now(timezone.utc)
    header = jwt.utils.base64url_encode(b'{"alg":"none","typ":"JWT"}').decode()
    payload_bytes = jwt.utils.base64url_encode(
        (
            '{"sub":"attacker","iss":"%s","aud":"%s","tenant_id":"11111111-1111-1111-1111-111111111111",'
            '"iat":%d,"exp":%d}' % (ISSUER, AUDIENCE, int(now.timestamp()), int((now + timedelta(minutes=5)).timestamp()))
        ).encode()
    ).decode()
    forged_token = f"{header}.{payload_bytes}."  # empty signature segment

    with app.app_context(), pytest.raises(jwt_verifier.TokenValidationError):
        jwt_verifier.decode_access_token(forged_token)


def test_algorithm_confusion_hs256_signed_with_the_rsa_public_key_is_rejected(app):
    """CHECKLIST.md Phase 7D: the classic RS256-to-HS256 confusion attack
    -- if a verifier ever passed the RSA *public* key (which is not
    secret; it's published in the issuer's JWKS) to an HMAC verifier, an
    attacker who knows that public key could forge a validly-signed
    HS256 token. jwt_verifier.py's `algorithms=["RS256"]` allowlist
    (passed to jwt.decode, not inferred from the token's own header) is
    what prevents this -- an HS256 token must be rejected regardless of
    what "signed" it with, before signature verification is even
    attempted with the wrong algorithm.

    Built by hand with `hmac` rather than `jwt.encode(..., algorithm="HS256")`
    -- PyJWT's own *encoder* already refuses to HMAC-sign with a
    PEM-formatted key (a second, independent safeguard against this same
    attack), which would make the test pass for the wrong reason if it
    only proved PyJWT's encoder guards itself rather than that
    jwt_verifier.py's decoder rejects the algorithm."""
    import base64
    import hashlib
    import hmac
    import json

    public_pem = _public_key.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    now = datetime.now(timezone.utc)
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "sub": "attacker",
                "iss": ISSUER,
                "aud": AUDIENCE,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
                "tenant_id": "11111111-1111-1111-1111-111111111111",
            }
        ).encode()
    ).rstrip(b"=")
    signing_input = header + b"." + payload
    signature = base64.urlsafe_b64encode(hmac.new(public_pem, signing_input, hashlib.sha256).digest()).rstrip(b"=")
    forged_token = (signing_input + b"." + signature).decode()

    with app.app_context(), pytest.raises(jwt_verifier.TokenValidationError):
        jwt_verifier.decode_access_token(forged_token)
