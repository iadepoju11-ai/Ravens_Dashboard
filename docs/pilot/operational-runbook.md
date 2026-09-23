# Operational runbook

Part of the pilot package (`docs/pilot/README.md`). Day-to-day operation
of a running deployment — the authoritative, exact-command procedures
live in `docs/runbooks/deployment.md` and
`docs/runbooks/disaster-recovery.md`; this document is the operator-facing
summary of when to use which.

## Health and readiness

Two endpoints, checked continuously by the deployment's own container
healthchecks: `GET /api/v1/health` (the process is up) and `GET
/api/v1/health/ready` (the database is actually reachable — the one that
matters for "can this serve real traffic"). Both are unauthenticated and
exempt from rate limiting, by design, so a healthcheck can never itself
become the thing that fails.

## Observing the system

- **Structured logs**: every line the API writes to stdout is one JSON
  object (timestamp, level, message, a request correlation id, and the
  tenant id for authenticated requests) — consumable by any log shipper
  without a custom parser.
- **Metrics**: `GET /metrics` (Prometheus text format, unauthenticated —
  the standard scrape convention; restrict network access to it at the
  ingress/firewall level, not with a bearer token a scraper doesn't
  carry) exposes HTTP/scoring/model-inference/explanation/database/outbox
  timing and counts. `GET /api/v1/monitoring/observability`
  (authenticated) is the same data as curated JSON, for the frontend's
  "System health" panel.
- **Business metrics**: `GET /api/v1/monitoring/metrics` (decision
  counts, approval rate — `null`, never `0`, when there's no data yet)
  and `GET /api/v1/monitoring/alerts` (real alerts: audit-chain
  verification failures, outbox publish failures, fairness threshold
  breaches).
- **Request correlation**: every response carries an `X-Request-Id`
  header, echoed from the caller if supplied — the same id tags every
  structured log line for that request.

## Scoring and reviewing decisions

Day-to-day use is the frontend: score an application, see the decision
with its explanation and reason codes, and — for a `refer` outcome or a
failed governance check — a review case is opened automatically and
appears on the Reviews page for a `compliance_officer`/`admin` to claim
and resolve. No manual step is needed to route a borderline decision to
a human; it happens as part of the same `/score` call.

## Rate limits, if a caller reports being blocked

`POST /score` is limited to 30 requests/minute per remote address; every
other endpoint defaults to 300/minute per remote address (health checks
and metrics scraping are exempt). This is currently per-IP, not
per-tenant or per-user — a shared corporate NAT could in principle share
a limit across multiple real users. See `known-limitations.md`.

## Backups

Scripted, not automatic (no scheduler is wired up yet — see
`known-limitations.md`): `make staging-backup` (or
`scripts/staging-backup.sh` directly) takes a timestamped, compressed
Postgres dump, retained locally with the most recent N kept
automatically. **Decide and operationalize a real backup cadence before
a pilot goes live** — the mechanism is real and drilled, the schedule is
not yet automated.

## Restoring from a backup

`make staging-restore FILE=<path>` — stops the API first (a real,
load-bearing step: an earlier version of this script didn't, and the
restore failed outright against the API's own live database
connections), drops and recreates the database, restores, and restarts
the API. Run `flask db upgrade` afterward if the restored backup might
predate migrations the currently-deployed application expects. Full
procedure and the real, timed drill that proved this works end-to-end
(not just that the restore command exits `0`):
`docs/runbooks/disaster-recovery.md`.

## Incident response — the shape of it

1. **Detect**: a `MonitoringAlert` (fairness breach, outbox failure,
   audit-chain integrity failure), a failed healthcheck, or a report
   from a user.
2. **Assess**: is this an application issue (roll back the release — see
   below) or a data issue (restore from backup)? Don't do both at once;
   handle them separately.
3. **Application rollback**: this repository publishes images tagged by
   exact commit SHA once they pass the full CI gate — rolling back means
   redeploying a known-good previous tag. A real drill confirmed an
   older release works correctly against the *current* database schema
   (every migration so far only adds columns/tables, nothing an older
   release chokes on) — not a guarantee for every conceivable future
   migration, a verified fact about this repository's actual history so
   far.
4. **Database rollback**: always back up before downgrading a migration
   — a generated migration's `downgrade()` isn't as carefully verified
   as its `upgrade()`, and some downgrades are genuinely destructive
   (a dropped column doesn't come back). If in doubt, restore the
   pre-downgrade backup instead of downgrading forward-then-back.
5. **Verify recovery**: health/readiness both green, a real user can
   authenticate, `POST /score` succeeds against a real deployed model,
   previously-existing decisions are still readable, the audit chain
   still verifies, and the smoke-test suite passes in full. This exact
   checklist is in `docs/runbooks/disaster-recovery.md` — restated here
   because it's what "the incident is resolved" actually means, not just
   "the container restarted."

## What to escalate, and to whom

Not defined by this document — who is authorized to trigger a
production restore, how an incident is declared, and escalation paths
are organizational decisions specific to whoever operates a pilot
deployment, not something this codebase can decide on their behalf. See
`known-limitations.md`.
