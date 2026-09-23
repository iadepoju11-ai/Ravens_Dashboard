# Pilot deployment guide

Part of the pilot package (`docs/pilot/README.md`). This is a curated
overview for evaluating what deploying this product involves — the
authoritative, exact-command source of truth is
`docs/runbooks/deployment.md`; this document doesn't repeat every
command verbatim (to avoid the two drifting out of sync), it explains
the shape and points to the exact procedure.

## Topology

One Docker host, six containers (`docker-compose.staging.yml`):

| Service | What it is | Notes |
| --- | --- | --- |
| `postgres` | PostgreSQL 16 | Primary datastore. Two roles: an owner/DDL role for migrations, and a restricted runtime role the application actually connects as (full CRUD on business tables, append-only on audit tables, no DDL). |
| `keycloak` | OIDC identity provider | Swappable for any OIDC-compliant enterprise IdP without code changes — this app only ever talks standard OIDC (issuer/JWKS/audience), never a Keycloak-specific API. |
| `kafka` + `zookeeper` | Event bus | Producer-only today — see `docs/pilot/known-limitations.md`. Disabled by default (`KAFKA_ENABLED=false`); nothing is lost while disabled, since every event is also durably recorded in Postgres regardless. |
| `api` | Flask application (gunicorn) | The credit-decision, governance, and audit engine. Single worker process today — see the capacity note below. |
| `web` | React frontend, built and served by nginx | The dashboard: scoring, decisions, models, datasets, fairness, audit, monitoring, reviews. |
| `migrate` | One-shot migration runner | Runs `flask db upgrade` and exits before `api` is allowed to start — migrations are part of the deploy sequence itself, never a manual step someone has to remember. |

## Prerequisites

- Docker and Docker Compose on the target host.
- Real, generated secrets for `.env.staging` (never the placeholder
  values in `.env.staging.example`) — see `configuration-reference.md`.
- If deploying anywhere other than a single developer's machine: real
  TLS termination in front of the stack (this topology has none of its
  own — see `known-limitations.md`) and a real hostname/DNS setup for
  the OIDC issuer to match what both the browser and the API expect.

## First deploy

Build and start everything, in dependency order (Postgres healthy →
Keycloak imports its realm and becomes healthy → migrations run to
completion → the API starts and is health/readiness-checked → the
frontend starts) — the exact command and what each step confirms:
`docs/runbooks/deployment.md`'s "Deploying" section. Then seed the two
fixed-id demo/smoke-test tenants (idempotent, safe to re-run) and run
the smoke-test suite as the real proof the deployment works, not just
that six containers report "running."

## Redeploying (a normal update)

The same build+up command — Compose only rebuilds/recreates what
changed, and any new migration runs automatically before the new `api`
container starts. Existing data survives a normal redeploy; only an
explicit volume removal resets it. One caveat worth knowing up front: if
the OIDC realm configuration itself changes (a new client, a new role),
Keycloak does **not** re-import it into an already-initialized data
volume — that volume has to be explicitly recreated, which *does* reset
Keycloak's own state (not the application database). Exact procedure:
`docs/runbooks/deployment.md`'s "Redeploying" section.

## Reproducible, versioned images

Every push to the main branch that passes the full CI gate (real
Postgres tests, an isolated migration regression, a real Kafka broker
integration test, clean Docker builds, dependency/container/secret
scanning, and — the final gate — a full staging deployment passing both
the smoke and resilience test suites) publishes both the API and web
images tagged by the exact commit SHA that produced them, to GHCR. A
pilot deployment can pin to a specific, known-good SHA rather than
always building from source — see `docs/runbooks/deployment.md`'s CI/CD
section. This compose file doesn't pin to one of those tags by default
today (see `known-limitations.md`); doing so is a small, described
config change, not a re-architecture.

## Rollback and disaster recovery

Both are drilled, not theoretical: a real application-rollback (an older
release against the current database, full functional compatibility
confirmed) and a real, timed backup-destroy-restore-verify cycle.
`docs/runbooks/disaster-recovery.md` is the authoritative procedure;
`docs/pilot/operational-runbook.md` summarizes it for day-to-day
operational use.

## Capacity, honestly

`apps/api/Dockerfile` runs gunicorn with a single worker. A measured
load-test baseline against this exact topology
(`docs/performance/staging-baseline.md`) found a practical ceiling
around **~70 requests/second** for `/score` on a single host, with the
bottleneck identified as queueing behind that one worker — not
`ScoringService` itself, which has real headroom (server-side scoring
duration stayed flat at ~8ms even as client-observed latency grew under
load). Two independent, documented, **not yet implemented** levers exist
for more capacity: more gunicorn workers per container (which would need
`prometheus_client`'s multiprocess mode to keep metrics accurate — not
wired up), and horizontal scaling (no load balancer exists in this
topology today). Neither is a large change, but neither has been done —
know the real ceiling before committing to a pilot workload, and treat
"scale before it's needed" as a pre-pilot capacity-planning
conversation, not an assumption.
