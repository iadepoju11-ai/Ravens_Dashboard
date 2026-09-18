"""Roles map to permissions; application code checks permissions, never
role names directly -- so a bank asking for a slightly different
permission model later is a change to ROLE_PERMISSIONS, not a grep across
every route for `if role == "..."`.

Roles are carried as claims on the verified OIDC token (Keycloak's
`realm_access.roles`, see jwt_verifier.py/provisioning.py) -- there is no
separate source of truth for role assignment in this application's own
database. The pre-existing `roles`/`user_roles` tables (see
app/models/role.py) predate this design and stay schema-only for now;
see CHECKLIST.md.
"""

from __future__ import annotations

from app.security.identity import Identity

ADMIN = "admin"
CREDIT_ANALYST = "credit_analyst"
COMPLIANCE_OFFICER = "compliance_officer"
AUDITOR = "auditor"
DATA_PROTECTION_OFFICER = "data_protection_officer"

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ADMIN: frozenset(
        {
            "users:manage",
            "tenant:manage",
        }
    ),
    CREDIT_ANALYST: frozenset(
        {
            "decisions:create",
            "decisions:read",
        }
    ),
    COMPLIANCE_OFFICER: frozenset(
        {
            "decisions:read",
            "models:read",
            "models:approve",
            "fairness:read",
            "fairness:review",
        }
    ),
    AUDITOR: frozenset(
        {
            "audit:read",
            "audit:export",
            "audit:verify",
        }
    ),
    DATA_PROTECTION_OFFICER: frozenset(
        {
            "datasets:read",
            "audit:read",
        }
    ),
}


class AuthorizationError(Exception):
    """The caller is authenticated but lacks the permission this route
    requires. Always maps to 403 -- the identity is real, it just isn't
    allowed to do this."""

    def __init__(self, message: str = "You do not have permission to perform this action"):
        super().__init__(message)
        self.message = message
        self.status_code = 403


def permissions_for(roles: frozenset[str]) -> frozenset[str]:
    granted: set[str] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)


def has_permission(identity: Identity, permission: str) -> bool:
    return permission in permissions_for(identity.roles)


def require_permission(identity: Identity, permission: str) -> None:
    if not has_permission(identity, permission):
        raise AuthorizationError()
