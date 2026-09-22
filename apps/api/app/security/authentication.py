"""The single entry point a route calls to turn an incoming request into
an `Identity`: extract the bearer token, verify it, resolve/provision the
user, and stash the result on the request (`set_current_identity`) so
`get_current_identity()` works for the rest of the request.

A route never inspects the Authorization header or a JWT claim itself --
only `authenticate()` here, `get_current_identity()`, and
`require_permission()` (permissions.py).
"""

from __future__ import annotations

from flask import request

from app.observability.context import set_tenant_id
from app.security.identity import Identity, set_current_identity
from app.security.jwt_verifier import TokenValidationError, decode_access_token
from app.security.provisioning import resolve_identity

_BEARER_PREFIX = "Bearer "


def authenticate() -> Identity:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith(_BEARER_PREFIX):
        raise TokenValidationError()

    token = auth_header[len(_BEARER_PREFIX) :].strip()
    if not token:
        raise TokenValidationError()

    claims = decode_access_token(token)
    identity = resolve_identity(claims)
    set_current_identity(identity)
    # The one choke point every authenticated route passes through --
    # setting it here means every structured log line for the rest of
    # this request carries tenant_id, without each route file doing it.
    set_tenant_id(identity.tenant_id)
    return identity
