"""add restricted runtime db role

Revision ID: a4e71d2b014c
Revises: 43b3180ac4fc
Create Date: 2026-09-18 00:00:00.000000

CHECKLIST.md Phase 5: "Separate audit-write DB permissions from ordinary
CRUD." Creates a restricted `creditguard_app` Postgres role for the
running application to connect as day-to-day: it can read/write ordinary
business tables, but only INSERT (never UPDATE or DELETE) on
`audit_events`/`audit_integrity_checks`, and has no DDL rights at all
(no CREATE/ALTER/DROP, no CREATEDB/CREATEROLE/SUPERUSER). Migrations
still run as the owner role that already exists (`DATABASE_URL`) -- this
role is for the live app's `SQLALCHEMY_DATABASE_URI` instead.

Password comes from APP_DB_PASSWORD (falls back to a fixed dev-only
default, same convention as the owner role's hardcoded dev credentials
everywhere else in this project) -- a real deployment would override it
via that environment variable, not by editing this file.

If a future migration adds another audit/evidence-style table (anything
where a client should never be able to alter or erase a row after it's
written), that migration must explicitly REVOKE UPDATE, DELETE ON
<table> FROM creditguard_app -- the ALTER DEFAULT PRIVILEGES below grants
full CRUD to every *new* table by default, same as ordinary business
tables get. See docs/database-migrations.md.
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "a4e71d2b014c"
down_revision = "43b3180ac4fc"
branch_labels = None
depends_on = None

APP_ROLE = "creditguard_app"
AUDIT_TABLES = ("audit_events", "audit_integrity_checks")
DEFAULT_APP_DB_PASSWORD = "creditguard_app_dev_password"  # noqa: S105 -- dev-only, documented above


def _role_exists(connection, role_name: str) -> bool:
    return bool(
        connection.execute(
            sa.text("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :role"), {"role": role_name}
        ).scalar()
    )


def upgrade():
    connection = op.get_bind()
    database_name = connection.engine.url.database

    if not _role_exists(connection, APP_ROLE):
        password = os.environ.get("APP_DB_PASSWORD", DEFAULT_APP_DB_PASSWORD)
        connection.execute(
            sa.text(
                f"CREATE ROLE {APP_ROLE} WITH LOGIN PASSWORD :password "  # noqa: S608
                "NOSUPERUSER NOCREATEDB NOCREATEROLE"
            ),
            {"password": password},
        )

    connection.execute(sa.text(f"GRANT CONNECT ON DATABASE {database_name} TO {APP_ROLE}"))
    connection.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
    connection.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))

    audit_tables_list = ", ".join(AUDIT_TABLES)
    connection.execute(sa.text(f"REVOKE UPDATE, DELETE ON {audit_tables_list} FROM {APP_ROLE}"))

    # Applies to tables the *current user* (the owner role running this
    # migration) creates from now on -- keeps future migrations from
    # needing to remember an explicit grant for ordinary tables.
    connection.execute(
        sa.text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}")
    )


def downgrade():
    connection = op.get_bind()
    database_name = connection.engine.url.database

    connection.execute(
        sa.text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}")
    )
    connection.execute(sa.text(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}"))
    connection.execute(sa.text(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}"))
    connection.execute(sa.text(f"REVOKE CONNECT ON DATABASE {database_name} FROM {APP_ROLE}"))

    if _role_exists(connection, APP_ROLE):
        connection.execute(sa.text(f"DROP OWNED BY {APP_ROLE}"))
        connection.execute(sa.text(f"DROP ROLE {APP_ROLE}"))
