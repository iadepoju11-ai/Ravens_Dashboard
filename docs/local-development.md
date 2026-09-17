# Local development

## Prerequisites

- Docker Desktop (or another Docker Engine + Compose v2 — check with `docker compose version`)
- Python 3.12 only if you want to run the API outside Docker (see "Running
  outside Docker" below); not required for the Docker workflow

## Why Docker, not a local Python venv, for Postgres work

The API's Postgres driver, `psycopg2-binary`, does not yet ship a prebuilt
wheel for very new Python versions (e.g. 3.14) on Windows, and building it
from source requires `pg_config`/PostgreSQL dev headers that most machines
don't have installed. The `Dockerfile` targets `python:3.12-slim`, where
`psycopg2-binary` wheels exist — so anything that touches Postgres (running
the API for real, Alembic migrations, the migration smoke test) should go
through Docker. A local venv is still useful for fast iteration against
SQLite (see `apps/api/tests/`), which doesn't need `psycopg2` at all.

## Ports

This stack deliberately does **not** use Postgres/Kafka's default ports, so
it can run alongside another local Postgres/Kafka instance (e.g. a different
project) without colliding:

| Service | Default port | This stack's host port |
| --- | --- | --- |
| Postgres | 5432 | **5433** |
| Kafka | 9092 | **9093** |

Inside the Docker network, containers talk to each other on the *default*
ports via service name (`postgres:5432`, `kafka:9092`) — the remapping only
affects access from your host machine (e.g. `psql`, or running the Flask
app outside Docker).

## First-time setup

```
cp .env.example .env
docker compose up -d postgres
docker compose build api
docker compose run --rm -e DATABASE_URL=postgresql://creditguard:creditguard@postgres:5432/creditguard api flask db upgrade
docker compose up --build
```

The explicit `DATABASE_URL` override on the `flask db upgrade` step is
required, not optional, and it's the *owner* role (`creditguard`), not the
one the running app connects as — see "Database roles: owner vs runtime
app" below. `docker compose run` for one-off commands doesn't resolve the
`api` service's own `environment:` block the way `docker compose up` does,
so it must be passed explicitly here.

## Database roles: owner vs runtime app

CHECKLIST.md Phase 5 ("Separate audit-write DB permissions from ordinary
CRUD") splits DB access into two Postgres roles, provisioned by the
`a4e71d2b014c_add_restricted_runtime_db_role` migration:

- **`creditguard` (owner)** — full DDL rights. Runs migrations
  (`flask db upgrade`/`downgrade`) and nothing else. Never used by the
  running app.
- **`creditguard_app` (runtime)** — what the app actually connects as day
  to day. Ordinary CRUD on most tables, but only `INSERT` (no `UPDATE`/
  `DELETE`) on `audit_events` and `audit_integrity_checks`, and no DDL
  rights at all. This is what makes the audit trail append-only at the
  database level, not just by application convention — see
  `docs/architecture/audit-threat-model.md`.

Two connection strings, two purposes:

| Variable | Role | Used by |
| --- | --- | --- |
| `DATABASE_URL` | owner (`creditguard`) when you override it explicitly for `flask db upgrade`/`downgrade`; otherwise the **`api` service in `docker-compose.yml` overrides it to the runtime role** for normal container operation | migrations (explicit override) / the running app (compose default) |
| `APP_DATABASE_URL` | runtime (`creditguard_app`), always | `tests/integration/test_db_permissions.py` only |

`APP_DATABASE_URL` is defined twice on purpose: `.env` has a host-side
value (`localhost:5433`, for anything run directly on your machine), and
`docker-compose.yml`'s `api` service overrides it to the container-internal
address (`postgres:5432`) so `docker compose run api pytest ...` always
exercises the real permission checks instead of silently skipping them.
Both must use the same password — `APP_DB_PASSWORD` (default
`creditguard_app_dev_password` for local dev; the migration reads this same
variable when creating the role, so if you change one you must change both
and re-run the migration).

The permission-separation tests are skipped, not failed, when
`APP_DATABASE_URL` isn't set or `psycopg2` isn't installed (e.g. the bare
SQLite-only local venv) — see the module docstring in
`tests/integration/test_db_permissions.py`.

## Kafka & the transactional outbox

Business writes and the event that describes them are committed in the
same DB transaction (`app/services/outbox_service.py`, an `outbox_events`
table) — a disabled or unreachable Kafka broker can never lose or roll back
business data. Publishing to Kafka is a separate, explicitly-invoked step:

```
flask events publish-outbox
```

This is not wired to a scheduler yet (see `app/cli.py`'s module docstring —
picking Celery/RQ/cron is a real decision, not something to bolt on here);
run it manually, or from cron/a CI schedule/a Kubernetes CronJob.

Relevant config (`apps/api/app/config.py`):

- `KAFKA_ENABLED` (default `false`) — outbox rows are always created
  regardless of this flag; only the *publish* step is gated by it. With it
  `false`, `publish-outbox` is a no-op and rows stay `pending` forever
  until it's turned on.
- `KAFKA_BOOTSTRAP_SERVERS` (default `localhost:9093`, the host-side port;
  `docker-compose.yml` overrides this to `kafka:9092` — the internal port —
  for the `api` service).

Currently published event types, all versioned (`decision.created.v1`,
`decision.completed.v1`, `explanation.created.v1`), sharing one envelope:
`event_id`, `event_type`, `schema_version`, `tenant_id`, `aggregate_type`,
`aggregate_id`, `correlation_id` (the originating `/score` request's
`request_id` — ties all three events from one call together),
`occurred_at`, `payload`. A row's own id is reused as `event_id` on every
publish attempt, so a retry after a crash produces an identical message,
not a new one — a consumer deduplicating by `event_id` is unaffected.
Failed publishes retry automatically on the next `publish-outbox` run (up
to `MAX_ATTEMPTS`, after which the row is marked `failed` and a
`MonitoringAlert` is raised) with no separate backoff/scheduling logic
needed here.

To manually verify against the real dockerized broker:

```
docker compose run --rm -e DATABASE_URL=postgresql://creditguard:creditguard@postgres:5432/creditguard \
  -e KAFKA_ENABLED=true -e KAFKA_BOOTSTRAP_SERVERS=kafka:9092 api flask events publish-outbox

docker compose exec kafka kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic decision.created.v1 --from-beginning --max-messages 1
```

## Running tests

```
# Fast, SQLite-backed unit/integration tests (via a local venv — see below)
cd apps/api
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt   # or the equivalent excluding psycopg2-binary on Windows/py3.14
python -m pytest tests/unit tests/integration

# Full suite against real Postgres (needs Docker + migrations applied to
# head, since the permission-separation and outbox tests need real tables
# and roles): migration smoke test, DB permission separation
# (test_db_permissions.py, skips without APP_DATABASE_URL/psycopg2), and
# everything else, run together against the same instance
docker compose run --rm -e DATABASE_URL=postgresql://creditguard:creditguard@postgres:5432/creditguard api python -m pytest tests/ -v
```

Always invoke pytest as `python -m pytest`, not the bare `pytest` command —
the bare form doesn't add the working directory to `sys.path`, so
`tests/conftest.py`'s `from app import create_app` fails to resolve.

The Postgres-backed tests run against a real, persistent database (the
`postgres_data` volume), not a fresh instance per run — they're written to
clean up after themselves (see `test_db_permissions.py`'s and
`test_outbox_integration.py`'s use of unique/per-test identifiers and
explicit teardown) so the suite stays repeatable across runs without
`docker compose down -v` in between.

## Running outside Docker

If your local Python has a working `psycopg2` install (e.g. Python 3.12 on
Linux/macOS, or you built it from source on Windows), you can run the API
directly:

```
cd apps/api
pip install -r requirements.txt
export DATABASE_URL=postgresql://creditguard:creditguard@localhost:5433/creditguard  # host-side port
export FLASK_APP=app.main
flask db upgrade
python -m app.main
```

## Tearing down

```
docker compose down          # stop containers, keep the postgres_data volume
docker compose down -v       # also delete the volume (destroys local data)
```
