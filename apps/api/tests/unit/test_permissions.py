"""Unit tests for role -> permission mapping (app/security/permissions.py).
Roles map to permissions, not the other way around -- these tests pin
down exactly what each of the five CreditGuard roles can and can't do."""

import pytest

from app.security.identity import Identity
from app.security.permissions import (
    ADMIN,
    AUDITOR,
    COMPLIANCE_OFFICER,
    CREDIT_ANALYST,
    DATA_PROTECTION_OFFICER,
    ROLE_PERMISSIONS,
    AuthorizationError,
    has_permission,
    require_permission,
)


def _identity(*roles: str) -> Identity:
    return Identity(
        user_id="u1",
        tenant_id="t1",
        oidc_subject="sub1",
        email="a@b.com",
        roles=frozenset(roles),
    )


@pytest.mark.parametrize(
    ("role", "permission"),
    [
        (CREDIT_ANALYST, "decisions:create"),
        (CREDIT_ANALYST, "decisions:read"),
        (COMPLIANCE_OFFICER, "models:approve"),
        (COMPLIANCE_OFFICER, "fairness:review"),
        (AUDITOR, "audit:verify"),
        (DATA_PROTECTION_OFFICER, "datasets:read"),
        (ADMIN, "tenant:manage"),
        (ADMIN, "decisions:read"),
        (ADMIN, "audit:read"),
        (ADMIN, "fairness:read"),
        (ADMIN, "monitoring:read"),
        (COMPLIANCE_OFFICER, "datasets:read"),
        (COMPLIANCE_OFFICER, "datasets:create"),
        (COMPLIANCE_OFFICER, "monitoring:read"),
    ],
)
def test_role_has_its_own_permissions(role, permission):
    assert has_permission(_identity(role), permission)


@pytest.mark.parametrize("role", [ADMIN, CREDIT_ANALYST, COMPLIANCE_OFFICER, AUDITOR, DATA_PROTECTION_OFFICER])
def test_every_role_can_read_its_own_tenant(role):
    # tenant:read carries no cross-tenant risk (see app/api/v1/tenants.py)
    # -- it's the one permission every role holds, unlike everything else
    # in this file, which is deliberately scoped to one workflow.
    assert has_permission(_identity(role), "tenant:read")


def test_admin_has_access_to_every_page_and_feature():
    # By explicit request (2026-09-18): admin is a superset of every other
    # role's permissions, not read-only-dashboard-plus-management. Checked
    # against the *other* roles' actual permission sets, not a hand-copied
    # literal list, so this can't silently drift out of sync with them.
    identity = _identity(ADMIN)
    all_other_permissions = (
        ROLE_PERMISSIONS[CREDIT_ANALYST]
        | ROLE_PERMISSIONS[COMPLIANCE_OFFICER]
        | ROLE_PERMISSIONS[AUDITOR]
        | ROLE_PERMISSIONS[DATA_PROTECTION_OFFICER]
    )
    for permission in all_other_permissions:
        assert has_permission(identity, permission), f"admin is missing {permission}"
    assert has_permission(identity, "users:manage")
    assert has_permission(identity, "tenant:manage")


@pytest.mark.parametrize(
    ("role", "permission"),
    [
        (CREDIT_ANALYST, "audit:verify"),
        (CREDIT_ANALYST, "models:approve"),
        (AUDITOR, "decisions:create"),
        (COMPLIANCE_OFFICER, "decisions:create"),
        (DATA_PROTECTION_OFFICER, "decisions:create"),
        (CREDIT_ANALYST, "monitoring:read"),
        (AUDITOR, "monitoring:read"),
        (DATA_PROTECTION_OFFICER, "datasets:create"),
        (CREDIT_ANALYST, "datasets:create"),
    ],
)
def test_role_does_not_have_other_roles_permissions(role, permission):
    assert not has_permission(_identity(role), permission)


def test_unknown_role_grants_nothing():
    assert not has_permission(_identity("some_role_the_idp_invented"), "decisions:create")


def test_no_roles_grants_nothing():
    assert not has_permission(_identity(), "decisions:create")


def test_multiple_roles_union_their_permissions():
    identity = _identity(CREDIT_ANALYST, AUDITOR)
    assert has_permission(identity, "decisions:create")
    assert has_permission(identity, "audit:verify")


def test_require_permission_raises_when_missing():
    with pytest.raises(AuthorizationError):
        require_permission(_identity(AUDITOR), "decisions:create")


def test_require_permission_is_silent_when_granted():
    require_permission(_identity(CREDIT_ANALYST), "decisions:create")
