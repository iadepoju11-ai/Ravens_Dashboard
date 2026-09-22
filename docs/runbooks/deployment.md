# Deployment: staging environment

CHECKLIST.md Phase 7A. Covers `docker-compose.staging.yml` — a
reproducible, deploy-from-the-repository staging stack (API, React
frontend, PostgreSQL, Kafka, Keycloak) — how to deploy it, how to verify
it, and how to roll it back. Everything below was run for real against a
fresh stack while writing this, not assumed correct from reading the
compose file.

## What this is, and isn't

**Is**: a reproducible, config-driven deployment of the full stack,
runnable on any machine with Docker — built images (no bind-mounted
source, unlike the dev `docker-compose.yml`), migrations run as an
explicit deploy step, secrets separated from dev's well-known values,
health/readiness-gated startup ordering, and a smoke-test suite that
exercises the deployed system over real HTTP.

**Isn't**: a real cloud/production target. There is no cloud account,
container registry, or CD pipeline in this project — "staging" here
means "the same Docker images and deploy sequence a real target would
use, run locally or on any Docker host you point it at", not a hosted
environment with its own domain and TLS. See "Known limitations" at the
bottom for exactly what a real production deployment would still need on
top of this.

## Topology

| Service | Image | Staging port | Purpose |
| --- | --- | --- | --- |
| `postgres` | `postgres:16` | 5533 | Primary database |
| `zookeeper` | `confluentinc/cp-zookeeper` | — | Kafka coordination |
| `kafka` | `confluentinc/cp-kafka` | 9193 | Event bus (producers only — see "Kafka" below) |
| `keycloak` | `quay.io/keycloak/keycloak:25.0` | 8181 | OIDC provider |
| `migrate` | built from `apps/api` | — | One-shot: runs `flask db upgrade`, then exits |
| `api` | built from `apps/api` | 5100 | Flask API (gunicorn) |
| `web` | built from `apps/web` | 8090 | React SPA, built + served by nginx |

Different ports than `docker-compose.yml`'s dev stack throughout, and a
separate Compose project name (`creditguard-staging`, set in the compose
file's top-level `name:`) — the two stacks can run side by side on one
machine without any port or volume collision.

## First-time setup

```
cp .env.staging.example .env.staging
```

Then edit `.env.staging` and replace every `CHANGE_ME` with a real,
generated secret (e.g. `python3 -c "import secrets; print(secrets.token_hex(16))"`
per value). `.env.staging` is gitignored — never commit it. See the
comments in `.env.staging.example` for what each variable does and which
ones must match between two lines (`APP_DB_PASSWORD` in particular).

If staging runs on a different host than the one you're deploying from,
also replace every `localhost` in `.env.staging` with that host's real
address (see the file's own header comment for why there's no single
place to change this).

## Deploying

```
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
```

(`make staging-up` is the same command, if `make` is available — it
isn't in every environment, e.g. this project's own Windows/Git-Bash dev
setup, which is why every command in this doc is also given in full.)

This builds the `api` and `web` images fresh and starts everything in
dependency order:

1. `postgres` starts, compose waits for its healthcheck (`pg_isready`).
2. `keycloak` starts and imports `infra/keycloak/creditguard-realm.json`
   (only on first boot of the `staging_keycloak_data` volume — re-running
   `up` against an existing volume does **not** re-import or update an
   already-imported realm; see "Redeploying" below for what that means
   in practice).
3. `migrate` runs `flask db upgrade` against `postgres` (owner role) and
   exits. This is what makes migrations part of deployment rather than a
   documented manual step — `api` will not start until this container
   **exits with code 0**, not just starts.
4. `api` starts once `migrate` has succeeded and `keycloak` is healthy,
   and is itself healthchecked via `GET /api/v1/health/ready` (confirms
   real DB connectivity from inside the container, not just that the
   process is up).
5. `web` (built by nginx serving the production Vite build) starts once
   `api` is healthy.

Watch it come up:

```
docker compose -f docker-compose.staging.yml --env-file .env.staging ps
```

Every service should reach `Up ... (healthy)` (or plain `Up` for
`zookeeper`/`kafka`, which don't have healthchecks defined — see "Kafka"
below). `migrate` will show `Exited (0)` — that's success, not a crash.

### Seeding (first deploy only, or after a volume reset)

A fresh database has a schema but no data — no tenants exist yet, and
neither Keycloak nor Postgres knows about the other without one more
step. The realm file seeds two Keycloak users (`smoke-admin`,
`smoke-other-tenant`, see "Smoke-test identities" below) with fixed
`tenant_id` attributes; this command creates the matching tenants in
Postgres:

```
docker compose -f docker-compose.staging.yml --env-file .env.staging exec api flask seed staging
```

(`make staging-seed`.) Idempotent — safe to run again after every
`staging-up`; it only creates a tenant that doesn't already exist by id,
never duplicates or updates.

### Verifying the deploy

```
curl -sf http://localhost:5100/api/v1/health
curl -sf http://localhost:5100/api/v1/health/ready
curl -sf http://localhost:8090/healthz
curl -sf http://localhost:8181/realms/creditguard
```

All four should return `200`. Then run the smoke-test suite (see below)
— it's the real end-to-end proof, not just that four processes answer a
ping.

## Smoke tests

`tests/smoke/` — black-box HTTP tests against the real deployed stack
(never Flask's in-process test client):

- `test_staging_smoke.py` — authentication, tenant isolation, scoring,
  decision retrieval, model operations, fairness, audit/export,
  monitoring, and review cases. See its module docstring for the full
  rationale (why it's sequential, why every record it creates is
  `run_id`-namespaced so repeated runs against a long-lived environment
  never collide).
- `test_staging_observability.py` (CHECKLIST.md Phase 7B) — proves the
  metrics and structured-logging paths actually work against the real
  deployment: `GET /metrics` is reachable and exposes the expected
  metric families, `GET /api/v1/monitoring/observability` reflects real
  accumulated activity (not stuck at zero), `X-Request-ID` is generated/
  echoed correctly, unhandled-exception responses never leak internals,
  and — skipped cleanly if Docker isn't reachable from wherever the
  suite runs, e.g. against a real remote host — the API container's
  actual log output parses as JSON and a specific request's log line can
  be found by its `request_id`.

```
pip install -r tests/smoke/requirements.txt
cd tests/smoke && python -m pytest . -v
```

(`make staging-smoke-test`, after `staging-up` + `staging-seed`.) 27
tests total, verified passing against a real fresh deploy and again
against the same still-running stack (repeatability check) while writing
this.

Every URL/credential the suite uses is overridable by environment
variable (`SMOKE_API_BASE_URL`, `SMOKE_KEYCLOAK_URL`, ...) — see
`tests/smoke/conftest.py` — so the same suite works against staging
running on a different host, not just `localhost`.

### Smoke-test identities

Two users are seeded into every fresh Keycloak realm import
(`infra/keycloak/creditguard-realm.json`), both role `admin` (full
permissions), in two different seeded tenants — same role deliberately,
so any test failure it catches is a real data-isolation bug, not a
permissions difference:

| Username | Password | Tenant |
| --- | --- | --- |
| `smoke-admin` | `SmokeTest123!` | `staging-smoke-bank` |
| `smoke-other-tenant` | `SmokeTest123!` | `staging-smoke-bank-b` |

These exist in every staging (and, if its Keycloak volume is ever reset,
dev) deployment by construction — not a manual setup step, and not
real credentials for anything sensitive (there is no real data behind
them in a fresh deploy).

## Redeploying (a normal code change)

```
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
```

The same command as the first deploy. Compose rebuilds any image whose
build context changed, recreates only the containers whose image or
config changed, and — because `api` depends on `migrate` completing
successfully — any new migration runs again automatically before the new
`api` container starts. Existing data in `staging_postgres_data` and
`staging_keycloak_data` (named volumes) survives a redeploy; only
`down -v` (below) removes them.

`make staging-redeploy` runs the full sequence — build+up, seed,
smoke test — in one command, useful as the single thing a CI job or a
human would run.

**If the Keycloak realm itself changed** (a new client, a new protocol
mapper, a new role) and staging already has an existing
`staging_keycloak_data` volume: the running Keycloak will **not**
re-import `creditguard-realm.json`, per Keycloak's own import semantics
(step 2 above). Recreate the volume to pick up realm changes:

```
docker compose -f docker-compose.staging.yml --env-file .env.staging down
docker volume rm creditguard-staging_staging_keycloak_data
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
```

This does not touch `staging_postgres_data` — application data survives;
only Keycloak's own state (realm config, any users created by hand
outside the JSON) is reset back to exactly what the file describes.

## Rollback

Two independent things can need rolling back: the application code, and
the database schema. Handle them separately — don't downgrade the schema
just because a code deploy needs reverting, or vice versa.

### Application rollback

There is no image registry or version tagging in this project yet (see
"Known limitations") — "rollback" today means redeploying from a
previous commit:

```
git checkout <previous-good-commit>
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
```

If the previous commit's schema differs from what's currently in the
database (i.e. the deploy being rolled back **added** a migration), see
"Database rollback" first — deploying old code against a newer schema
that added non-nullable columns or renamed tables will generally break
immediately in more confusing ways than downgrading first.

### Database rollback

**Take a backup before downgrading, always** — same procedure as
`docs/backup-restore.md`, pointed at the staging project/port:

```
docker compose -f docker-compose.staging.yml --env-file .env.staging exec -T postgres \
  pg_dump -U creditguard -F c -d creditguard > creditguard-staging-backup.dump
```

Then downgrade one migration (or to a specific revision — see
`docs/database-migrations.md`):

```
docker compose -f docker-compose.staging.yml --env-file .env.staging run --rm \
  -e DATABASE_URL=postgresql://creditguard:<DB_OWNER_PASSWORD from .env.staging>@postgres:5432/creditguard \
  migrate flask db downgrade -- -1
```

(The `--` before `-1` is required — without it, Click parses `-1` as an
unknown option rather than a relative-revision argument, and fails
before Alembic ever sees it. Verified for real; this is not a
theoretical gotcha.)

**This is a genuinely risky operation** — `docs/database-migrations.md`
already documents that a generated migration's `downgrade()` isn't
always hand-verified as carefully as its `upgrade()`, and a downgrade
that drops a column is real, unrecoverable data loss for that column
regardless of how careful the migration author was. If in doubt, restore
the pre-downgrade backup instead of downgrading forward-then-back.

After a database rollback, redeploy the application version that matches
the now-current (older) schema — see "Application rollback" above.

**Real failure mode, hit while writing this doc, fixed 2026-09-23**:
downgrading past `e15b4aad7f27` (which adds `users.oidc_subject`) and
then upgrading back does **not** restore the `oidc_subject` value on
users that already existed — the column comes back empty, not
repopulated, for any row that existed across the round trip. The next
request from a real user whose JIT-provisioned `User` row lost its
`oidc_subject` used to fail with a `psycopg2.errors.UniqueViolation` on
`uq_user_tenant_email`: `app/security/provisioning.py` looked the user up
by `oidc_subject` only, didn't find it (now `NULL`), and tried to
provision a new row that collided with the existing one on
`(tenant_id, email)`.

**Fixed**: `_provision_user` now falls back to a `(tenant_id, email)`
lookup when no user matches the token's subject, and re-links
(`oidc_subject = <new subject>`) instead of inserting a duplicate — a
disabled user found this way is still rejected, not silently
re-activated. Regression-tested in
`tests/unit/test_provisioning.py::test_a_user_whose_oidc_subject_was_lost_is_relinked_not_duplicated`,
and re-verified live: downgraded staging past `e15b4aad7f27`, upgraded
back, and confirmed `smoke-other-tenant` (whose `oidc_subject` the round
trip had wiped) now authenticates successfully instead of 500ing, with
exactly one `users` row for that `(tenant, email)` afterward, not two.

This still doesn't make the round trip itself safe for other columns —
**take a backup before downgrading, always** (above); this fix only
closes the one specific, reproduced failure mode for user identity
linkage.

## Kafka

`kafka`/`zookeeper` run in staging (matching the dev stack) so
`KAFKA_ENABLED=true` can be flipped on without a second deploy, but **no
consumer exists yet anywhere in this codebase** (CHECKLIST.md) — this
pass deliberately does not add one. `KAFKA_ENABLED=false` in
`.env.staging.example` by design: the transactional outbox
(`app/services/outbox_service.py`) records every event in Postgres
regardless, so nothing is lost with Kafka disabled, and there is no
consumer downstream to receive anything published anyway. Enable it only
once a real consumer exists to read from it.

## Observability (CHECKLIST.md Phase 7B)

Structured JSON logging and Prometheus-format metrics — vendor-neutral in
both cases: JSON lines to stdout are consumable by any log shipper
without a custom parser, and Prometheus's text exposition format is
scraped by Prometheus itself, Grafana Agent, Datadog, and most other
observability vendors alike. Nothing here imports a vendor-specific SDK.

- **Logs**: every line the API process writes to stdout is one JSON
  object (`timestamp`, `level`, `logger`, `message`, `request_id`,
  `tenant_id`, plus call-specific fields) — `LOG_LEVEL` in `.env.staging`
  controls verbosity (default `INFO`). `docker compose -f
  docker-compose.staging.yml --env-file .env.staging logs -f api` to
  tail them.
- **Metrics**: `GET /metrics` (not under `/api/v1` — Prometheus scraping
  convention) exposes the raw exposition format: HTTP request
  count/latency by route, scoring/model-inference/explanation duration,
  PostgreSQL query duration and error count, outbox publish outcomes, and
  governance/review-case counts. **Deliberately unauthenticated**, same
  as any real Prometheus scrape target — restrict who can reach it at the
  network/ingress level in a real deployment, not with a bearer token
  scrapers don't carry.
- **Same data, readable**: `GET /api/v1/monitoring/observability`
  (authenticated, `monitoring:read`) is a curated JSON summary of the
  identical underlying counters — what the frontend Monitoring page's
  "System health" section renders. p50/p95 are approximated from each
  histogram's bucket counts by linear interpolation (the same technique
  Prometheus's own `histogram_quantile()` uses), not computed
  differently between the two endpoints.
- **Single-worker assumption**: `apps/api/Dockerfile`'s gunicorn command
  has no `--workers` flag (defaults to one sync worker), so these
  in-process counters are accurate for the whole container today. Scaling
  to multiple workers per container would silently make `GET /metrics`
  report per-worker numbers instead of per-container — revisit with
  `prometheus_client`'s multiprocess mode if that ever changes.
- **Request correlation**: every response carries an `X-Request-ID`
  header (echoes a caller-supplied one, or generates a fresh one) — the
  same id tags every structured log line for that request, so a specific
  request's logs can be found by grepping for its id.
- **Safe error responses**: a global handler catches any exception not
  already handled more specifically, logs it in full (message, type,
  traceback) server-side, and returns a generic
  `{"error": "An unexpected error occurred", "meta": {"request_id": ...}}`
  — never a stack trace, DB detail, or internal path to the caller. Real
  `HTTPException`s (404, 405, ...) are handled separately and keep their
  normal status/behavior, not swallowed into this generic response.

## Resilience and load testing (CHECKLIST.md Phase 7C)

Two more independently-runnable suites against the real deployed stack,
alongside the smoke tests above — both verified for real against this
staging deployment while writing this, not assumed correct from reading
the code.

### Load testing

`tests/load/load_test_score.py` fires concurrent `POST /score` requests
at a real deployment and reports client-observed latency/throughput
alongside the server-observed numbers from
`GET /api/v1/monitoring/observability` (Phase 7B) for the same window —
proving the observability instrumentation itself captures load
accurately, not just that the API stays up under it.

```
pip install -r tests/load/requirements.txt
python tests/load/load_test_score.py --concurrency 10 --total-requests 200
```

(`make staging-load-test`, `ARGS="..."` to override flags.) See
`docs/performance/staging-baseline.md` for the measured baseline this
produced and — the more important part — what it reveals about this
stack's real concurrency ceiling (a single gunicorn worker, not
`ScoringService` itself).

### Resilience / fault-injection tests

`tests/resilience/` proves the system degrades safely and recovers
without manual intervention when a real dependency fails, and that
duplicate/concurrent requests are handled safely:

- `test_postgres_failure.py` — stops the real `postgres` container,
  confirms `/health/ready` reports `503` with no leaked internals and
  `/score` fails safely (not a crash or a hang), then restarts it and
  confirms the API recovers **without restarting the `api` container** —
  SQLAlchemy's own connection pool reconnects on its own.
- `test_kafka_failure_and_outbox.py` — stops `kafka`, confirms `/score`
  keeps succeeding (Kafka is not in the critical scoring path — CLAUDE.md)
  and that `flask events publish-outbox` records retryable failures
  instead of losing or crashing on the pending rows, then restarts kafka
  and confirms the same rows drain and publish once it recovers — retry
  behaviour and transactional-outbox persistence, proven against a real
  broker outage.
- `test_api_container_restart.py` — restarts the `api` container itself,
  confirms it comes back healthy on its own and that a decision scored
  before the restart is still readable afterward (Postgres, not the API
  process, is the system of record).
- `test_duplicate_request_safety.py` — fires N simultaneous client-side
  `/score` calls carrying the *same* idempotency key (`request_id`) at
  the real API and Postgres, and confirms exactly one decision is created
  and every racing call gets a safe response, never a 500. **Caveat,
  discovered while writing it**: this deployment's gunicorn runs a single
  worker (see "Observability" above and `docs/performance/staging-baseline.md`),
  so these requests are serialized before they reach `ScoringService` —
  this test cannot force the genuine race window a fix made in this same
  pass addresses. That fix — `ScoringService` could previously let two
  truly concurrent requests both pass its idempotency lookup before
  either committed, and the loser would 500 on the database's own
  `uq_decision_tenant_request_id` constraint instead of receiving the
  winner's decision — is proven deterministically instead, at the unit
  level: `apps/api/tests/unit/test_scoring_service.py::test_a_concurrent_duplicate_request_is_deduplicated_not_crashed`
  forces the exact race window directly. The staging test still verifies
  real, valuable end-to-end coverage (the dedup contract holds under load
  against the real stack); see the test's own docstring for the full
  reasoning.

The Postgres/Kafka/API-restart tests are **destructive** — they stop or
restart real containers in this deployment — so they're marked
`pytest.mark.destructive` and skip unless `RUN_RESILIENCE_TESTS=1` is
set, to make sure a plain `pytest` invocation (or an unrelated CI job)
never triggers them by accident. Every one restores the container(s) it
touched in a `finally` block, even on failure, so a failing assertion
never leaves the shared staging deployment down. The duplicate-request
test is not gated — it never touches a container, only ordinary
concurrent HTTP traffic.

```
pip install -r tests/resilience/requirements.txt
cd tests/resilience && RUN_RESILIENCE_TESTS=1 python -m pytest . -v
```

(`make staging-resilience-test`.) All 4 tests verified passing against
this staging deployment, individually and as a full sequential run, with
the stack confirmed fully healthy (`docker compose ... ps`, all services
`Up ... (healthy)`) immediately afterward both times.

## Security (CHECKLIST.md Phase 7D)

Full verification write-up, real findings, and what was and wasn't fixed:
`docs/architecture/security-hardening.md`. The deploy-relevant knobs it
adds, both already set correctly in the real `.env.staging`/`.env.example`:

- `CORS_ALLOWED_ORIGINS` — comma-separated list of origins allowed to
  make cross-origin requests to this API (the React app's own origin).
  flask-cors only ever echoes back CORS headers for a listed origin,
  never `*`.
- `RATELIMIT_DEFAULT` — the app-wide per-remote-address rate limit
  (`POST /score` has its own stricter, hardcoded override). In-memory
  storage — see the security doc's "known limitation" on what changes if
  this is ever scaled past one gunicorn worker.

Also new: `create_app()` refuses to start under `FLASK_ENV=production`
if `SECRET_KEY` is still the literal placeholder `"change-me"` — a
fail-fast check that someone actually did the secret-generation step
above, not a silent insecure default.

## Known limitations

- **No TLS anywhere.** Keycloak runs in `start-dev` mode
  (`sslRequired: none`), and `api`/`web` serve plain HTTP. A real
  internet-facing deployment needs a reverse proxy or load balancer
  terminating TLS in front of all three — out of scope for this pass
  (CHECKLIST.md Phase 7's "staging environment" item, not "production
  hardening", which is its own separate line).
- **No container registry or image versioning.** Images are built
  locally by `docker compose ... up --build`; there is no `docker push`
  anywhere and no tag beyond `latest`. "Rollback" (above) means
  rebuilding from an older commit, not pulling a previously-published
  image — a real CD pipeline would tag and retain images instead.
- **No secrets manager.** `.env.staging` is a local file. A real
  deployment target would pull these from Vault/AWS Secrets
  Manager/equivalent, not a `.env` file sitting on the host.
- **No CD pipeline.** Nothing in `.github/workflows/` deploys anywhere —
  there is no server or cloud account for it to deploy *to* yet. This
  doc's commands are what such a pipeline would eventually run; wiring
  them into CI is future work once a real target exists to point them
  at.
- **No load-balancing/scaling.** One `api` container, one `web`
  container. Horizontal scaling, and what that would mean for the
  outbox/audit-chain's per-tenant sequential-write assumptions, is
  unexamined.
