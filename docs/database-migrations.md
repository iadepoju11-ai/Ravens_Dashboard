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
