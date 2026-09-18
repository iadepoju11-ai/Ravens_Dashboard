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
| Keycloak | 8080 | **8081** (admin console/manual use only — see below) |

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

## OIDC authentication (Keycloak)

`POST /score`, `/decisions`, `/models`, `/fairness/reports`, and `/audit`
are migrated to OIDC auth (CHECKLIST.md Phase 6,
`docs/architecture/oidc-rbac.md`) — `/datasets`, `/monitoring/*`,
`/tenants` still use the `X-Tenant-Id` header. `docker compose up` starts
a `keycloak` service that auto-imports
`infra/keycloak/creditguard-realm.json` on first boot: the realm, its
five roles, and two clients --

- **`creditguard-api`** — `directAccessGrantsEnabled`, for scripts/curl
  (the manual-testing recipe below). Never used by a browser.
- **`creditguard-web`** — `standardFlowEnabled` + PKCE, for the actual
  React app (`apps/web/src/services/authConfig.ts`). Never issued a
  client secret; it's a public SPA client by design.

Both carry the same protocol mappers: a `tenant_id` claim (from a user
attribute) and an `aud: creditguard-api` claim, so a token from either
client is valid against the API.

### One issuer, two network paths

A browser (`localhost:8081`) and the `api` container (which cannot resolve
`localhost:8081` to Keycloak) reach Keycloak differently, but a JWT's
`iss` claim is fixed at issuance and must match exactly on validation.
Keycloak is pinned via `KC_HOSTNAME=localhost`/`KC_HOSTNAME_PORT=8081`
(`docker-compose.yml`) to always claim `http://localhost:8081/realms/...`
as its issuer, regardless of which path asked — and the `api` service's
`OIDC_ISSUER` is set to that same string. Only the *JWKS fetch* address
needs to differ: `OIDC_JWKS_URL` points at
`http://host.docker.internal:8081/...`, which Docker Desktop resolves to
the host machine (an `extra_hosts` entry makes the same alias work on
Linux). If you ever see the API reject a token as invalid right after
changing anything Keycloak-related, check `OIDC_ISSUER` still matches
`http://localhost:8081/realms/creditguard` exactly.

### Using the real login flow (the React app)

`docker compose up web` (or `npm run dev` in `apps/web`) needs
`VITE_OIDC_AUTHORITY`, `VITE_OIDC_CLIENT_ID`, `VITE_OIDC_REDIRECT_URI`
(`.env.example` has working defaults). Visiting `http://localhost:5173`
redirects to Keycloak's real login page; nothing renders until
`useIdentity().isAuthenticated` is true (`apps/web/src/app/AuthGate.tsx`).
You need a real Keycloak user with a `tenant_id` attribute pointing at a
real row in the `tenants` table — create one with the same `kcadm.sh`
recipe below, then log in with it in the browser.

### Manual testing recipe (curl/scripts, not the browser)

```
# Admin console: http://localhost:8081 (admin/admin — dev-only creds)

docker compose exec keycloak /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080 --realm master --user admin --password admin

docker compose exec keycloak /opt/keycloak/bin/kcadm.sh create users -r creditguard \
  -s username=test-analyst -s enabled=true -s email=test-analyst@example.com \
  -s firstName=Test -s lastName=Analyst -s emailVerified=true \
  -s 'attributes.tenant_id=["<a real tenant UUID from the tenants table>"]'

docker compose exec keycloak /opt/keycloak/bin/kcadm.sh set-password -r creditguard \
  --username test-analyst --new-password test-pass-123

docker compose exec keycloak /opt/keycloak/bin/kcadm.sh add-roles -r creditguard \
  --uusername test-analyst --rolename credit_analyst

# From the host (this is the direct-grant creditguard-api client, not PKCE):
curl -s -X POST http://localhost:8081/realms/creditguard/protocol/openid-connect/token \
  -d grant_type=password -d client_id=creditguard-api \
  -d username=test-analyst -d password=test-pass-123
# use the returned access_token as `Authorization: Bearer <token>` against
# http://localhost:5000/api/v1/score
```

(On Windows/Git Bash, prefix `docker compose exec` commands above with
`MSYS_NO_PATHCONV=1` — otherwise Git Bash rewrites the container's
`/opt/keycloak/...` path as a Windows path and the command fails with
"no such file or directory".)

### Gotcha: a long-running `api` container can end up with a stale DB connection

Rebuilding the `creditguard_app` Postgres role (e.g. by running
`tests/test_migrations.py`'s base→head cycle against the same Postgres a
persistent `api` container is also connected to — see
`docs/database-migrations.md`) can leave that container's pooled
connection stale: it starts failing with `permission denied for table
...` even though the grants are actually fine. `docker compose restart
api` clears it. Not a bug, just a consequence of a schema-destructive test
suite and a long-running app sharing one database.

### Two Keycloak gotchas this realm config already works around

Both were found by actually running a real token through the real
container — a mocked-JWKS unit test can't catch either, since both are
about what Keycloak *puts in* a token, not whether the API validates it
correctly:

- **A new user needs `email`/`firstName`/`lastName`, or the password
  grant fails with `"Account is not fully set up"`.** Keycloak 25's
  "declarative user profile" runs a `VERIFY_PROFILE` check against
  whichever attributes the profile schema marks required (email/first/last
  name, by default) — an incomplete profile blocks login entirely, with an
  error message that doesn't mention which field is missing.
- **A custom claim (`tenant_id`, here) is silently dropped unless it's
  declared in the realm's user-profile schema — not just added by a
  protocol mapper.** Setting the attribute via the admin API/console
  *appears* to succeed, but the declarative user profile strips any
  attribute it doesn't recognize before the token is even built, so the
  claim just doesn't show up — no error anywhere. `infra/keycloak/creditguard-realm.json`'s
  `components` block declares `tenant_id` in the schema for exactly this
  reason.
- Related, less surprising: the `sub` claim itself comes from Keycloak's
  built-in **`basic`** client scope. A client's `defaultClientScopes` list
  needs `basic` in it (already set in the realm export) or every token is
  missing `sub` — the one claim `app/security/provisioning.py` cannot
  function without.

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

**One test is the exception, and it's a big one**: `test_migrations.py`
downgrades the entire database to `base` (dropping every table) and back
to `head` as part of what it verifies. Running the full suite therefore
wipes *all* data in that Postgres instance — any tenant, user, model, or
decision you created by hand (e.g. to click through the React app) is
gone afterward, not just test fixtures. This is correct and necessary for
what that test checks; it just means "run the full test suite" and "keep
manually-created demo data around" don't mix on the same Postgres
instance. Re-seed whatever you need afterward (see "OIDC authentication"
above for the tenant/user creation recipe), or point `MIGRATION_TEST_DATABASE_URL`
at a separate, disposable database if you want to avoid this entirely.

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
docker compose down          # stop containers, keep the postgres_data/keycloak_data volumes
docker compose down -v       # also delete the volumes (destroys local data, including Keycloak realm/users)
```
