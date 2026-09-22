"""Tests app/security/provisioning.py's just-in-time user provisioning,
including the real rollback-hazard regression documented in
docs/runbooks/deployment.md: downgrading past the migration that added
`users.oidc_subject` and upgrading back leaves existing users with a
NULL oidc_subject, so the next login for that user used to try to INSERT
a second row and crash with an IntegrityError on uq_user_tenant_email
instead of re-linking to the existing one.
"""

import pytest

from app.extensions import db
from app.models.tenant import Tenant
from app.models.user import User
from app.security.permissions import AuthorizationError
from app.security.provisioning import resolve_identity


def _create_tenant(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.commit()
    return tenant


def _claims(tenant_id: str, sub: str, email: str, roles: tuple[str, ...] = ("credit_analyst",)) -> dict:
    return {
        "sub": sub,
        "email": email,
        "tenant_id": tenant_id,
        "realm_access": {"roles": list(roles)},
    }


def test_a_brand_new_subject_provisions_a_new_user(app):
    tenant = _create_tenant("provisioning-new-user-bank")

    identity = resolve_identity(_claims(tenant.id, "sub-new", "new@example.com"))

    assert identity.tenant_id == tenant.id
    user = User.query.filter_by(oidc_subject="sub-new").first()
    assert user is not None
    assert user.email == "new@example.com"


def test_an_existing_subject_is_found_directly_without_reprovisioning(app):
    tenant = _create_tenant("provisioning-existing-bank")
    first = resolve_identity(_claims(tenant.id, "sub-existing", "existing@example.com"))

    second = resolve_identity(_claims(tenant.id, "sub-existing", "existing@example.com"))

    assert second.user_id == first.user_id
    assert User.query.filter_by(tenant_id=tenant.id, email="existing@example.com").count() == 1


def test_a_user_whose_oidc_subject_was_lost_is_relinked_not_duplicated(app):
    """The actual regression: simulates the post-downgrade/upgrade state
    (an existing row for this tenant+email, oidc_subject wiped to NULL by
    the round trip) directly, rather than by running real Alembic
    migrations in a unit test -- the effect on this function is identical
    either way: the by-oidc_subject lookup in resolve_identity finds
    nothing, so _provision_user is called for a subject that, from the
    IdP's point of view, belongs to an already-known account.
    """
    tenant = _create_tenant("provisioning-relink-bank")
    original = resolve_identity(_claims(tenant.id, "sub-original", "relink@example.com"))
    user = db.session.get(User, original.user_id)
    user.oidc_subject = None
    db.session.commit()

    # A new (or reissued) subject claim for the same tenant + email --
    # this used to raise sqlalchemy.exc.IntegrityError on
    # uq_user_tenant_email instead of returning an identity.
    relinked = resolve_identity(_claims(tenant.id, "sub-reissued", "relink@example.com"))

    assert relinked.user_id == original.user_id
    assert User.query.filter_by(tenant_id=tenant.id, email="relink@example.com").count() == 1
    refreshed = db.session.get(User, original.user_id)
    assert refreshed.oidc_subject == "sub-reissued"


def test_relinking_a_disabled_user_is_still_rejected(app):
    tenant = _create_tenant("provisioning-relink-disabled-bank")
    original = resolve_identity(_claims(tenant.id, "sub-original", "disabled@example.com"))
    user = db.session.get(User, original.user_id)
    user.oidc_subject = None
    user.is_active = False
    db.session.commit()

    with pytest.raises(AuthorizationError):
        resolve_identity(_claims(tenant.id, "sub-reissued", "disabled@example.com"))

    # Rejected, not silently re-linked -- the disabled account must not
    # come back to life just because its oidc_subject was cleared.
    refreshed = db.session.get(User, original.user_id)
    assert refreshed.oidc_subject is None


def test_an_already_disabled_user_found_by_oidc_subject_is_still_rejected(app):
    tenant = _create_tenant("provisioning-disabled-direct-bank")
    original = resolve_identity(_claims(tenant.id, "sub-direct", "direct-disabled@example.com"))
    user = db.session.get(User, original.user_id)
    user.is_active = False
    db.session.commit()

    with pytest.raises(AuthorizationError):
        resolve_identity(_claims(tenant.id, "sub-direct", "direct-disabled@example.com"))
