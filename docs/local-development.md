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

The explicit `DATABASE_URL` override on the `flask db upgrade` step isn't
needed once you're running through `docker compose up` — the `api` service
in `docker-compose.yml` sets it automatically. It's shown here because
`docker compose run` for one-off commands doesn't always resolve
`depends_on`-driven environment overrides the same way `up` does.

## Running tests

```
# Fast, SQLite-backed unit/integration tests (via a local venv — see below)
cd apps/api
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt   # or the equivalent excluding psycopg2-binary on Windows/py3.14
python -m pytest tests/unit tests/integration

# Postgres-backed migration smoke test (needs Docker; see database-migrations.md)
docker compose run --rm -e DATABASE_URL=postgresql://creditguard:creditguard@postgres:5432/creditguard api python -m pytest tests/test_migrations.py -v
```

Always invoke pytest as `python -m pytest`, not the bare `pytest` command —
the bare form doesn't add the working directory to `sys.path`, so
`tests/conftest.py`'s `from app import create_app` fails to resolve.

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
