"""Maps a verified token's claims onto an application `User` and builds
the `Identity` the rest of the app works with.

Per CLAUDE.md: the OIDC provider owns authentication; this app owns
tenancy and authorization. That split shows up concretely here -- a
brand-new `sub` gets a `User` row created just-in-time (tenant taken from
the token, since there's nothing in our own DB yet to consult), but an
*existing* user's tenant comes from our own stored `User.tenant_id`, not
re-read from the token on every request. The token can't move a user
between tenants after the fact; only this application's own data can.
"""

from __future__ import annotations

from app.extensions import db
from app.models.tenant import Tenant
from app.models.user import User
from app.security.identity import Identity
from app.security.jwt_verifier import TokenValidationError
from app.security.permissions import AuthorizationError


def resolve_identity(claims: dict) -> Identity:
    subject = claims.get("sub")
    if not subject:
        raise TokenValidationError()

    user = User.query.filter_by(oidc_subject=subject).first()
    if user is None:
        user = _provision_user(subject, claims)
    elif not user.is_active:
        raise AuthorizationError("This account has been disabled")

    roles = frozenset(claims.get("realm_access", {}).get("roles", []))
    return Identity(
        user_id=user.id,
        tenant_id=user.tenant_id,
        oidc_subject=subject,
        email=user.email,
        roles=roles,
    )


def _provision_user(subject: str, claims: dict) -> User:
    tenant_id = claims.get("tenant_id")
    if not tenant_id:
        # The realm's protocol mapper (see infra/keycloak/) puts tenant_id
        # on every token; a token without one can't be provisioned into
        # any tenant, so there's no identity to establish.
        raise TokenValidationError()

    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None or not tenant.is_active:
        raise AuthorizationError("Unknown or inactive tenant")

    user = User(
        tenant_id=tenant.id,
        email=claims.get("email") or f"{subject}@oidc.local",
        full_name=claims.get("name"),
        oidc_subject=subject,
    )
    db.session.add(user)
    db.session.commit()
    return user
