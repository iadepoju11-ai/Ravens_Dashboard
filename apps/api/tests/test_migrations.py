"""Migration smoke test.

Guards against the "tests pass on create_all() but real deploy fails on
incomplete migrations" trap (CHECKLIST.md Phase 1): this test exercises the
actual Alembic migration path against a real Postgres database, not the
SQLite create_all() shortcut the rest of the suite uses.

Requires a reachable Postgres (MIGRATION_TEST_DATABASE_URL, falling back to
DATABASE_URL) and psycopg2 — skipped otherwise, e.g. in a local venv without
a Postgres driver. Run it via Docker, where both are available:

    docker compose run --rm \\
      -e DATABASE_URL=postgresql://creditguard:creditguard@postgres:5432/creditguard \\
      api pytest tests/test_migrations.py -v
"""

import os

import pytest

pytest.importorskip("psycopg2", reason="requires psycopg2 (Postgres driver) to exercise real migrations")

import sqlalchemy as sa  # noqa: E402

MIGRATION_DATABASE_URL = os.environ.get("MIGRATION_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

if not MIGRATION_DATABASE_URL or not MIGRATION_DATABASE_URL.startswith("postgresql"):
    pytest.skip(
        "Migration smoke test requires a Postgres DATABASE_URL "
        "(set MIGRATION_TEST_DATABASE_URL or DATABASE_URL)",
        allow_module_level=True,
    )

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db as _db  # noqa: E402

EXPECTED_TABLES = {
    "tenants",
    "users",
    "roles",
    "user_roles",
    "datasets",
    "dataset_versions",
    "models",
    "model_versions",
    "decisions",
    "explanations",
    "governance_results",
    "audit_events",
    "audit_integrity_checks",
    "fairness_evaluations",
    "monitoring_alerts",
    "review_cases",
    "model_deployments",
}


def _alembic_config(app) -> Config:
    migrations_dir = os.path.join(app.root_path, "..", "migrations")
    cfg = Config(os.path.join(migrations_dir, "alembic.ini"))
    cfg.set_main_option("script_location", migrations_dir)
    cfg.set_main_option("sqlalchemy.url", MIGRATION_DATABASE_URL)
    return cfg


@pytest.fixture()
def migrated_app():
    app = create_app("testing")
    app.config["SQLALCHEMY_DATABASE_URI"] = MIGRATION_DATABASE_URL

    cfg = _alembic_config(app)
    with app.app_context():
        # Start from an empty database regardless of what this Postgres
        # instance already had applied, then run every migration forward.
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
        yield app
        _db.session.remove()
        command.downgrade(cfg, "base")


def test_migration_creates_all_expected_tables(migrated_app):
    inspector = sa.inspect(_db.engine)
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))


def test_migration_supports_full_decision_workflow(migrated_app):
    from app.models.decision import Decision
    from app.models.model import Model, ModelVersion
    from app.models.tenant import Tenant

    tenant = Tenant(name="Migration Smoke Bank", slug="migration-smoke-bank")
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
    _db.session.flush()

    decision = Decision(
        tenant_id=tenant.id,
        model_version_id=model_version.id,
        application_reference="APP-MIGRATION-SMOKE",
        request_id="req-migration-smoke",
        input_payload={"income": 0.5},
        score=0.42,
        outcome="refer",
    )
    _db.session.add(decision)
    _db.session.commit()

    fetched = Decision.query.filter_by(id=decision.id).one()
    assert fetched.application_reference == "APP-MIGRATION-SMOKE"
    assert fetched.model_version_id == model_version.id
