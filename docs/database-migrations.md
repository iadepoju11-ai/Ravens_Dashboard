# Database migrations

Schema changes are managed with Alembic via Flask-Migrate. `apps/api/migrations/`
holds the migration environment (`env.py`) and history (`versions/`).

## Why generate migrations against real Postgres, not SQLite

`flask db migrate` (autogenerate) diffs the SQLAlchemy models against
whatever database `SQLALCHEMY_DATABASE_URI`/`DATABASE_URL` currently points
to. If that's SQLite, Alembic renders SQLite's batch-mode `ALTER TABLE`
workarounds into the migration, which don't apply cleanly to Postgres later.
Always generate migrations with `DATABASE_URL` pointing at a real Postgres —
in this project, the dockerized one on host port 5433 (`postgres:5432`
inside the Docker network). See `docs/local-development.md` for why the API
container (Python 3.12) is used rather than a local venv for this.

## Creating a new migration

```
docker compose up -d postgres
docker compose run --rm -e DATABASE_URL=postgresql://creditguard:creditguard@postgres:5432/creditguard \
  api flask db migrate -m "describe the change"
```

**Always hand-review the generated file** in
`apps/api/migrations/versions/` before applying it — autogenerate gets
close but not perfect. Specifically check:

- **All expected tables/columns are present** — autogenerate can silently
  miss a table if a model wasn't imported into `app/models/__init__.py`
  before migration discovery ran.
- **Custom column types are imported.** This project's UUID primary/foreign
  keys use a custom `GUID` type (`app/models/base.py` — native `uuid` on
  Postgres, `CHAR(36)` on SQLite). Alembic renders these as
  `app.models.base.GUID(...)` in the migration body but does **not**
  automatically add the corresponding `import app.models.base` at the top
  of the file — this was caught by hand on the very first migration in this
  project and would otherwise crash with `NameError` on `flask db upgrade`.
  Add the import yourself if it's missing.
- **Primary/foreign keys, nullability, unique constraints, check
  constraints, indexes, and `ondelete` cascade behavior** match intent —
  diff the rendered `op.create_table(...)`/`op.add_column(...)` calls
  against the model definitions, don't just skim for "looks about right."
- **The `downgrade()` function is sane** — autogenerate produces one, but
  verify it actually reverses `upgrade()` (this matters for the migration
  smoke test below, which downgrades to `base` as part of getting a clean
  slate).
- **A new audit/evidence table needs its own permission migration.** The
  restricted runtime role (`creditguard_app`, see
  `docs/local-development.md` "Database roles: owner vs runtime app") gets
  full CRUD on new tables automatically via `ALTER DEFAULT PRIVILEGES`
  (set up once in `a4e71d2b014c_add_restricted_runtime_db_role`) — that's
  correct for ordinary tables, but wrong for anything that must be
  append-only (audit trails, integrity check results, evidence records). A
  table like that needs an explicit follow-up migration that
  `REVOKE UPDATE, DELETE ON <table> FROM creditguard_app`, the same way
  `audit_events`/`audit_integrity_checks` are locked down. This is easy to
  forget precisely because the default-privileges grant makes the new table
  "just work" without it.

## Applying migrations

```
docker compose run --rm -e DATABASE_URL=postgresql://creditguard:creditguard@postgres:5432/creditguard \
  api flask db upgrade
```

(Or `make api-db-upgrade` if you're running the API outside Docker with a
working local Postgres driver — see `docs/local-development.md`.)

## Migration smoke test

`apps/api/tests/test_migrations.py` guards against the "tests pass on
`create_all()` but real deploy fails on incomplete migrations" trap: the
rest of the test suite uses `db.create_all()` against in-memory SQLite
(fast, no Postgres dependency), which will happily create tables even if
the actual Alembic migration is broken or incomplete. This test instead:

1. Downgrades the target Postgres database to `base` (empty).
2. Runs every migration forward to `head`.
3. Asserts all expected tables exist.
4. Exercises a full workflow through the ORM (tenant → model → model
   version → decision) to confirm the applied schema actually works, not
   just that the DDL ran without error.

It requires a real, reachable Postgres and `psycopg2` and is skipped
otherwise (e.g. in a local SQLite-only venv):

```
docker compose run --rm -e DATABASE_URL=postgresql://creditguard:creditguard@postgres:5432/creditguard \
  api python -m pytest tests/test_migrations.py -v
```

Run this after every migration change, not just the SQLite-backed suite —
it is the only test that exercises the real migration path end to end.

Its fixture restores the database to `head` in teardown (downgrade to
`base`, then back up to `head`), not just downgrading to `base` and
stopping there — this suite runs against a real, persistent Postgres
shared with other integration tests in the same run (e.g.
`test_db_permissions.py`), and those depend on migration-provisioned state
like the `creditguard_app` role. Leaving the database at `base` after this
test would drop that role out from under any test that happens to run
afterward.

Running it while a *persistent* `api` container (`docker compose up -d
api`) is also connected to the same Postgres has a related, milder
symptom: this test's `downgrade` step drops and recreates the
`creditguard_app` role entirely (same role name, new Postgres role
underneath), but a connection already pooled by the long-running api
process keeps working against whatever grants existed at the time it was
opened. The next request through that stale pooled connection can fail
with `permission denied for table ...` even though `\dp <table>` shows
the grant is fine — `docker compose restart api` (fresh connection pool)
clears it. Not a bug in the migration or the app; just a real consequence
of running a schema-destructive test suite against a database something
else is actively connected to.

## Gotcha: overriding `SQLALCHEMY_DATABASE_URI` after `create_app()` does nothing

Flask-SQLAlchemy 3.x builds the engine for the default bind **inside**
`db.init_app()` and never re-reads `app.config` afterwards (this is
documented behavior, not a bug in that library). Code like this looks
reasonable but silently keeps using whichever URI `create_app()`'s config
class defaulted to:

```python
app = create_app("testing")
app.config["SQLALCHEMY_DATABASE_URI"] = some_other_url  # no effect — too late
```

This bit both `test_migrations.py` and `test_db_permissions.py`, which need
a real Postgres URL rather than `TestingConfig`'s SQLite default. The fix
is `create_app`'s `database_uri` parameter (`app/__init__.py`), which sets
the config **before** calling `db.init_app()`:

```python
app = create_app("testing", database_uri=some_other_url)
```

Any future fixture that needs a Flask app bound to a non-default database
must go through this parameter, not a post-hoc config assignment.
