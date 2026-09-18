"""Verifies OIDC access tokens: signature (via the issuer's published
JWKS), issuer, audience, and expiry. Deliberately provider-agnostic --
nothing here knows it's talking to Keycloak specifically, only that it's
talking to *an* OIDC-compliant issuer (CLAUDE.md: portable between the
dev-time provider and whatever an enterprise customer brings).

Never trust claims from a token that failed any of these checks -- a
caller only ever gets an `Identity` (see identity.py) after every check
here has passed.
"""

from __future__ import annotations

import jwt
from flask import current_app

_jwk_clients: dict[str, jwt.PyJWKClient] = {}


class TokenValidationError(Exception):
    """The token is missing, malformed, unsigned by a trusted key, expired,
    or issued for a different issuer/audience. Always maps to 401 -- at
    this point there is no identity to reason about yet, valid or not."""

    def __init__(self, message: str = "Invalid or missing authentication token"):
        super().__init__(message)
        self.message = message
        self.status_code = 401


def _jwk_client() -> jwt.PyJWKClient:
    # Cached per JWKS URL (not just a single module-level client) so tests
    # can point different Flask app configs at different fake JWKS
    # endpoints without cross-contaminating a shared client.
    jwks_url = current_app.config["OIDC_JWKS_URL"]
    client = _jwk_clients.get(jwks_url)
    if client is None:
        client = jwt.PyJWKClient(jwks_url)
        _jwk_clients[jwks_url] = client
    return client


def decode_access_token(token: str) -> dict:
    """Returns the token's claims if -- and only if -- the signature,
    issuer, audience, and expiry all check out. Raises
    TokenValidationError otherwise; never returns claims from a token
    that failed any check."""
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=current_app.config["OIDC_ISSUER"],
            audience=current_app.config["OIDC_AUDIENCE"],
        )
    except jwt.PyJWTError:
        # Deliberately generic -- PyJWT's own exception text is safe today,
        # but never surface library/internal detail from an auth failure
        # to the caller (same reasoning as ScoringRuntimeError).
        raise TokenValidationError() from None
    return claims
