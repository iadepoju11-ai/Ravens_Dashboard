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

_CREDIT_ANALYST_PERMISSIONS = frozenset(
    {
        "decisions:create",
        "decisions:read",
        "tenant:read",
    }
)

_COMPLIANCE_OFFICER_PERMISSIONS = frozenset(
    {
        "decisions:read",
        "models:read",
        # No dedicated data-scientist/model-ops role exists among the
        # five CreditGuard roles -- compliance_officer owns the whole
        # model lifecycle (register -> approve -> deploy) for now,
        # not just the approval step. Revisit if that changes. Same
        # reasoning extends to registering the training data those
        # models cite (datasets:create/read), and to model-risk
        # monitoring (monitoring:read) -- both are part of "Models,
        # governance and fairness", this role's stated remit.
        "models:create",
        "models:approve",
        "models:deploy",
        "datasets:read",
        "datasets:create",
        "monitoring:read",
        "fairness:read",
        "fairness:review",
        # Review cases are opened automatically for a "refer" outcome or
        # a failing governance/fairness check (review_service.py) --
        # resolving them is part of the same "Models, governance and
        # fairness" remit as fairness:review.
        "review:read",
        "review:resolve",
        "tenant:read",
    }
)

_AUDITOR_PERMISSIONS = frozenset(
    {
        "audit:read",
        "audit:export",
        "audit:verify",
        "tenant:read",
    }
)

_DATA_PROTECTION_OFFICER_PERMISSIONS = frozenset(
    {
        "datasets:read",
        "audit:read",
        "tenant:read",
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    # Full access to every page and feature, by explicit request (2026-09-18)
    # -- superset of every other role's permissions plus the two admin-only
    # ones (users:manage, tenant:manage), rather than a hand-maintained list.
    # Built as a union so a new permission added to any other role is
    # automatically granted to admin too, with nothing to keep in sync by
    # hand.
    ADMIN: (
        frozenset({"users:manage", "tenant:manage"})
        | _CREDIT_ANALYST_PERMISSIONS
        | _COMPLIANCE_OFFICER_PERMISSIONS
        | _AUDITOR_PERMISSIONS
        | _DATA_PROTECTION_OFFICER_PERMISSIONS
    ),
    CREDIT_ANALYST: _CREDIT_ANALYST_PERMISSIONS,
    COMPLIANCE_OFFICER: _COMPLIANCE_OFFICER_PERMISSIONS,
    AUDITOR: _AUDITOR_PERMISSIONS,
    DATA_PROTECTION_OFFICER: _DATA_PROTECTION_OFFICER_PERMISSIONS,
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
