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
    ],
)
def test_role_has_its_own_permissions(role, permission):
    assert has_permission(_identity(role), permission)


@pytest.mark.parametrize(
    ("role", "permission"),
    [
        (CREDIT_ANALYST, "audit:verify"),
        (CREDIT_ANALYST, "models:approve"),
        (AUDITOR, "decisions:create"),
        (COMPLIANCE_OFFICER, "decisions:create"),
        (DATA_PROTECTION_OFFICER, "decisions:create"),
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
