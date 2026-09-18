"""The application's own view of "who is making this request" -- built
once per request from a verified token plus the matching `User` row, then
read everywhere else via `get_current_identity()`. Nothing downstream of
this (routes, services) ever looks at a raw JWT claim or an HTTP header
again; it only ever sees an `Identity`.
"""

from __future__ import annotations

from dataclasses import dataclass

from flask import g


@dataclass(frozen=True)
class Identity:
    user_id: str
    tenant_id: str
    oidc_subject: str
    email: str | None
    roles: frozenset[str]


class IdentityNotSetError(Exception):
    """Raised if get_current_identity() is called on a route that never
    ran authentication -- a programming error (a missing `authenticate()`
    call), not a client-facing 401."""


def set_current_identity(identity: Identity) -> None:
    g.identity = identity


def get_current_identity() -> Identity:
    identity = g.get("identity")
    if identity is None:
        raise IdentityNotSetError("No authenticated identity on this request")
    return identity
