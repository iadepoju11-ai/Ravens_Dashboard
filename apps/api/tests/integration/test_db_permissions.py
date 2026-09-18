"""Proves the Postgres permission separation actually holds (CHECKLIST.md
Phase 5): the restricted `creditguard_app` role can do normal application
work — including writing audit events — but cannot modify or delete an
existing audit event, and has no DDL rights at all. See
docs/architecture/audit-threat-model.md and the
a4e71d2b014c_add_restricted_runtime_db_role migration.

Requires a reachable Postgres with that migration applied and
APP_DATABASE_URL pointing at the provisioned creditguard_app role —
skipped otherwise, e.g. the local SQLite-only venv.
"""

import os
import uuid

import pytest

pytest.importorskip("psycopg2")

import sqlalchemy as sa  # noqa: E402

APP_DATABASE_URL = os.environ.get("APP_DATABASE_URL")

if not APP_DATABASE_URL:
    pytest.skip(
        "APP_DATABASE_URL not set — requires a Postgres instance with the "
        "restricted creditguard_app role provisioned",
        allow_module_level=True,
    )

from app import create_app  # noqa: E402
from app.extensions import db as _db  # noqa: E402
from app.models.model import Model, ModelVersion  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402


@pytest.fixture()
def app_role_app():
    application = create_app("testing", database_uri=APP_DATABASE_URL)
    with application.app_context():
        yield application
        _db.session.remove()


@pytest.fixture()
def app_role_client(app_role_app):
    return app_role_app.test_client()


def test_app_role_can_perform_a_normal_scoring_workflow(app_role_client, app_role_app, auth_headers):
    # Unlike the SQLite unit-test suite (a fresh in-memory DB per test), this
    # runs against a real, persistent Postgres instance -- a fixed slug
    # would collide with leftover rows from a previous run of this same
    # test, so cleanup below (via the owner role, since the app role can't
    # delete its own audit_events) is not optional.
    slug = f"perm-sep-bank-{uuid.uuid4().hex[:12]}"
    owner_url = os.environ.get("DATABASE_URL")
    with app_role_app.app_context():
        tenant = Tenant(name=slug, slug=slug)
        _db.session.add(tenant)
        _db.session.flush()
        model = Model(tenant_id=tenant.id, name="credit-risk")
        _db.session.add(model)
        _db.session.flush()
        model_version = ModelVersion(
            model_id=model.id,
            version="1.0.0",
            status="deployed",
            artifact_uri="file://./model_artifacts/credit-risk-1.0.0.pkl",
        )
        _db.session.add(model_version)
        _db.session.commit()
        tenant_id = tenant.id

    try:
        # Proves INSERT works on ordinary tables *and* on audit_events (the
        # scoring flow writes an audit event as part of the same request) —
        # not just that the connection succeeds. Also exercises the
        # OIDC-authenticated path (app/security/), which JIT-provisions a
        # User row -- another ordinary-table INSERT the app role must be
        # able to do.
        response = app_role_client.post(
            "/api/v1/score",
            json={"application_reference": "APP-1", "features": {"income": 0.5}},
            headers=auth_headers(tenant_id),
        )
        assert response.status_code == 201
    finally:
        if owner_url:
            owner_engine = sa.create_engine(owner_url)
            with owner_engine.begin() as conn:
                conn.execute(sa.text("DELETE FROM decisions WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
                conn.execute(
                    sa.text("DELETE FROM outbox_events WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id}
                )
                conn.execute(
                    sa.text("DELETE FROM audit_events WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id}
                )
                conn.execute(sa.text("DELETE FROM models WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
                conn.execute(sa.text("DELETE FROM users WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
                conn.execute(sa.text("DELETE FROM tenants WHERE id = :tenant_id"), {"tenant_id": tenant_id})
            owner_engine.dispose()


def test_app_role_cannot_update_audit_events():
    engine = sa.create_engine(APP_DATABASE_URL)
    with engine.connect() as conn, pytest.raises(sa.exc.DBAPIError, match="permission denied"):
        conn.execute(sa.text("UPDATE audit_events SET payload = '{}' WHERE 1=0"))
        conn.commit()
    engine.dispose()


def test_app_role_cannot_delete_audit_events():
    engine = sa.create_engine(APP_DATABASE_URL)
    with engine.connect() as conn, pytest.raises(sa.exc.DBAPIError, match="permission denied"):
        conn.execute(sa.text("DELETE FROM audit_events WHERE 1=0"))
        conn.commit()
    engine.dispose()


def test_app_role_cannot_update_audit_integrity_checks():
    engine = sa.create_engine(APP_DATABASE_URL)
    with engine.connect() as conn, pytest.raises(sa.exc.DBAPIError, match="permission denied"):
        conn.execute(sa.text("UPDATE audit_integrity_checks SET valid = false WHERE 1=0"))
        conn.commit()
    engine.dispose()


def test_app_role_can_insert_into_audit_events():
    # The whole point of the restriction is append-only, not no-access.
    # Cleanup must go through the *owner* connection -- the app role
    # can't DELETE from audit_events, which is exactly the thing being
    # tested here.
    engine = sa.create_engine(APP_DATABASE_URL)
    owner_url = os.environ.get("DATABASE_URL")
    tenant_id = None
    try:
        with engine.begin() as conn:
            tenant_id = conn.execute(
                sa.text(
                    "INSERT INTO tenants (id, name, slug, is_active, created_at) "
                    "VALUES (gen_random_uuid(), 'perm-insert-check', 'perm-insert-check', true, now()) "
                    "RETURNING id"
                )
            ).scalar()
            conn.execute(
                sa.text(
                    "INSERT INTO audit_events "
                    "(id, tenant_id, event_type, entity_type, entity_id, payload, prev_hash, hash, created_at) "
                    "VALUES (gen_random_uuid(), :tenant_id, 'test.event', 'test', gen_random_uuid(), "
                    "'{}', NULL, 'deadbeef', now())"
                ),
                {"tenant_id": tenant_id},
            )
    finally:
        engine.dispose()
        if tenant_id is not None and owner_url:
            owner_engine = sa.create_engine(owner_url)
            with owner_engine.begin() as conn:
                conn.execute(sa.text("DELETE FROM audit_events WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
                conn.execute(sa.text("DELETE FROM tenants WHERE id = :tenant_id"), {"tenant_id": tenant_id})
            owner_engine.dispose()


def test_app_role_cannot_create_tables():
    engine = sa.create_engine(APP_DATABASE_URL)
    with engine.connect() as conn, pytest.raises(sa.exc.DBAPIError, match="permission denied"):
        conn.execute(sa.text("CREATE TABLE ddl_should_be_denied (id int)"))
        conn.commit()
    engine.dispose()
