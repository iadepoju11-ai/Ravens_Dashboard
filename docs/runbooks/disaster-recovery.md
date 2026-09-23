# Disaster recovery

CHECKLIST.md Phase 7F. Complements `docs/runbooks/deployment.md` (normal
deploy/rollback) and `docs/backup-restore.md` (the original dev-level
`pg_dump`/`pg_restore` round-trip drill this document builds on). Scope
is deliberately narrow, per the project's own current deployment shape:
**prove the system can be backed up, restored, rolled back, and
recovered using the infrastructure it actually has** — a single Docker
host running `docker-compose.staging.yml`, no cloud account, no managed
database, no Kubernetes. Not a claim that this is enterprise-grade
production DR; see "Known limitations" at the bottom for exactly what
that would still need.

Every number and every procedure below is from a real drill run against
the real staging deployment while writing this document, not assumed
correct from reading a script.

## Failure scenarios this runbook covers

| Scenario | Section |
| --- | --- |
| PostgreSQL data loss/corruption | Backup and restore |
| A bad application deploy | Application rollback |
| A migration that shouldn't have shipped | Migration rollback |
| Kafka broker outage | Kafka recovery |
| Keycloak data loss | Keycloak recovery |

Out of scope for this pass (see "Known limitations"): total host loss
requiring provisioning new hardware, multi-region failover, and anything
assuming infrastructure this project doesn't have yet.

## Backup and restore

### Mechanism

`scripts/staging-backup.sh` — a timestamped, custom-format `pg_dump`
(`-F c`: compressed, supports selective/parallel restore, required for
`pg_restore`), written to `backups/staging/` (gitignored — dumps contain
real tenant/decision data) and only renamed into place once the dump
actually succeeds, so an interrupted run never leaves a file that looks
like a valid backup but isn't. `make staging-backup`.

`scripts/staging-restore.sh <backup-file>` — stops the `api` container
(a real, load-bearing step: the first version of this script didn't, and
`DROP DATABASE` failed outright with "database ... is being accessed by
other users" against the api container's own live connection pool — a
production restore needs the application offline for exactly this
reason regardless), drops and recreates the database, restores from the
given dump with `--no-owner`, then restarts `api`. `make staging-restore
FILE=backups/staging/creditguard-staging-<timestamp>.dump`. Does **not**
run `flask db upgrade` itself — the caller does that explicitly, since a
backup might predate migrations the current app expects (see "Migration
rollback" below for why that's a separate, deliberate step, not folded
in silently).

### Retention

Host-local only, `BACKUP_RETENTION_COUNT` most recent backups (default
7) — the script prunes older ones after each successful run. There is no
off-host or cloud copy; see "Known limitations."

### Encryption

**Not implemented at the application level.** Backup files are plain
`pg_dump` custom-format archives on local disk, exactly as sensitive as
the database itself. A real deployment would want encryption at rest
(disk-level, or an encrypted object-storage destination) and encryption
in transit if backups ever leave the host — neither exists here. Stated
honestly as a gap, not silently assumed solved.

### Backup success/failure signal

The script exits non-zero on `pg_dump` failure (and removes the partial
`.tmp` file first) and echoes a timestamped success/failure line to
stdout — the same convention `flask audit verify-all-tenants` and `flask
events publish-outbox` (`app/cli.py`) already use, so this is safe to
wire into whichever scheduler eventually runs it (none does yet — see
"Known limitations").

### The real recovery drill

`tests/resilience/test_backup_restore_drill.py` (`make staging-dr-drill`,
or `RUN_RESILIENCE_TESTS=1 pytest test_backup_restore_drill.py` directly
— same opt-in as every other destructive test in that directory; this is
the single most destructive one, since it drops the database):

```
score a decision ("before")
  → backup
    → score another decision ("after" — must NOT survive the restore)
      → stop api, DROP DATABASE, recreate, pg_restore, restart api
        → flask db upgrade (proves a safe no-op when already at head)
          → API healthy again
            → "before" decision readable
            → "after" decision returns 404 (proves a genuine
              point-in-time restore, not a no-op)
            → audit chain still verifies (GET /audit/verify-chain)
```

**Passed for real** (2026-09-23, against the live staging deployment):
backup took 2.5s, restore+migrate+recovery took 10.3s, total drill time
12.8s. The `finally` block re-seeds staging regardless of pass/fail, so
a failed drill never leaves the shared deployment unusable.

**Caveat on those numbers**: this staging database has a handful of
tenants/decisions from smoke/resilience test runs, not production data
volume. `docs/backup-restore.md` already flagged this same limitation
for its own drill — restore time at real data volumes is genuinely
untested, not assumed to scale linearly.

## Recovery objectives

Targets appropriate to this deployment's actual shape (single host,
manual operator-triggered backups, no scheduler) — not invented
enterprise numbers:

- **RPO (Recovery Point Objective)**: **currently unbounded** — nothing
  runs `staging-backup.sh` automatically, so the true RPO today is "however
  long it's been since a human last ran it." **Target, if a scheduler is
  added** (cron / a Kubernetes CronJob / GitHub Actions on a schedule —
  see `app/cli.py`'s own docstring for why none is wired up yet):
  **≤ 1 hour**, via an hourly backup job. This is a reasonable target for
  this system's actual write volume and single-host shape, not a
  five-nines claim.
- **RTO (Recovery Time Objective)**: **target ≤ 15 minutes** for a
  database-only incident (corruption/data loss, Postgres volume intact
  or a recent backup available) — the real drill above took under 15
  seconds end-to-end at current data volume, leaving generous headroom
  for realistic production data volumes and a human actually executing
  the runbook rather than a test harness. For a **total host loss**
  (redeploying the entire `docker-compose.staging.yml` stack from
  nothing, including Keycloak realm import and Postgres/Kafka cold
  start), the realistic figure observed repeatedly during this project's
  own development — bringing the full stack from `down -v` to every
  service reporting healthy — is on the order of **1–2 minutes** for
  container/service startup, plus however long `staging-restore.sh`
  takes against the most recent available backup. No formal target is
  set for this broader scenario yet; it's bounded by the numbers above,
  not independently measured end-to-end.

## Application rollback

**Real drill performed** (2026-09-23): rolled back from the current
release to the commit before Phase 7D's security-hardening pass
(`bb8818f`), while leaving the database at head (no migrations exist
between those two commits, so this also specifically tested "does an
older release tolerate the current schema").

```
git worktree add <path> bb8818f   # isolated checkout, doesn't disturb the working tree
docker build -t <old-image> <path>/apps/api
docker compose -f docker-compose.staging.yml --env-file .env.staging stop api
docker run -d --network creditguard-staging_default -p <port>:5000 \
  -e DATABASE_URL=<the same connection string the compose api service uses> \
  -e SECRET_KEY=... -e OIDC_ISSUER=... -e OIDC_JWKS_URL=... -e OIDC_AUDIENCE=... \
  <old-image>
```

**Result**: the older release started cleanly against the current
(head) database, `/health` and `/health/ready` both passed, and a real
authenticated `POST /score` call against a currently-deployed model
version succeeded (`201`, real decision + explanation returned) — full
functional compatibility, not just a health check. As an extra
confirmation the rollback was genuine (not just a relabeled current
image): the pre-7D build's `/api/v1/health` echoed `Access-Control-Allow-Origin`
back for an arbitrary `Origin` header (CORS was unrestricted before
Phase 7D) and carried none of Phase 7D's security response headers —
exactly the expected old behavior, for the reasons that behavior was
itself flagged and fixed in `docs/architecture/security-hardening.md`.

**Why this is safe by construction, not just this one drill**: every
migration in this repository's history so far only adds columns/tables
(nullable columns, new tables) — nothing has ever dropped or renamed a
column an older app version depends on. An older release simply doesn't
reference what it doesn't know about. This is not a guarantee for *all
possible future migrations* — a migration that drops or renames a
column an in-flight older release still reads would break this
assumption, which is exactly why "migration rollback" below is a
separate concern from "application rollback."

**Mechanics recap**: to actually perform this in a real incident,
rebuild/pull the previous release's image, `docker compose ... stop
api`, then either `docker compose up -d api` after retagging the
previous image as the one the compose file's `api` service builds/refers
to, or run it standalone joined to the same Docker network as this drill
did. This repo has no image-tag-pinning in `docker-compose.staging.yml`
today (it always builds `./apps/api` fresh) — pinning to a specific
`ghcr.io/.../api:<sha>` tag (CHECKLIST.md Phase 7E publishes these) would
make this a `docker compose pull && up -d` operation instead of a manual
rebuild; not wired up yet, tracked as a known limitation below.

## Migration rollback

CI already exercises the mechanical upgrade → downgrade → upgrade
regression (`tests/test_migrations.py`, `main-checks.yml`'s
`api-migration-regression` job, CHECKLIST.md Phase 7E). The operational
question this runbook adds is the one CI can't answer by itself: **can
the previous application version safely operate against the database
after a migration is rolled back?**

This already has a real, documented answer — not hypothetical. From
`docs/runbooks/deployment.md`'s "Rollback" section (Phase 7A/7B):
downgrading past `e15b4aad7f27` (adds `users.oidc_subject`) and then
upgrading back does **not** restore the `oidc_subject` value on users
that already existed — the column comes back `NULL` for any row that
existed across the round trip. The *old* application code (before the
Phase 7B fix) looked users up by `oidc_subject` only, found nothing, and
tried to `INSERT` a new row that collided with the existing one on
`uq_user_tenant_email`, producing an unhandled `IntegrityError` — a
concrete, reproduced case of "the app didn't tolerate a migration
rollback cleanly." Fixed in `app/security/provisioning.py::_provision_user`
(falls back to a `(tenant_id, email)` lookup and re-links instead of
inserting), regression-tested
(`apps/api/tests/unit/test_provisioning.py`), and re-verified live at
the time by downgrading staging past that revision, upgrading back, and
confirming a real affected user authenticates successfully with exactly
one row, not two.

**The operational procedure**, generalized from that incident:

1. **Always take a backup before downgrading** (see "Backup and
   restore" above) — a generated migration's `downgrade()` isn't always
   as carefully hand-verified as its `upgrade()`, and a downgrade that
   drops a column is real, unrecoverable data loss for that column.
2. Downgrade: `docker compose -f docker-compose.staging.yml --env-file
   .env.staging run --rm -e DATABASE_URL=... migrate flask db downgrade
   -- -1` (the `--` before `-1` is required, verified in Phase 7A — Click
   otherwise parses `-1` as an unknown option).
3. **Check whether the application code still deployed expects the
   column/table the downgrade just removed or emptied.** If it does
   (the oidc_subject case), either roll the *application* back too
   (previous section) or patch the application to tolerate the gap, as
   `_provision_user` now does.
4. If in doubt, restore the pre-downgrade backup instead of downgrading
   forward-then-back — the safer, always-available fallback.

## Kafka recovery

Already built and verified (CHECKLIST.md Phase 7C,
`tests/resilience/test_kafka_failure_and_outbox.py`) — this section
documents the recovery semantics for the DR runbook's sake rather than
re-proving them:

```
API scores normally throughout
  → Postgres/outbox: every event still written in the same DB
    transaction as the business row it describes (app/services/scoring_service.py)
      → Kafka unavailable: publish-outbox attempts record retryable
        failures (attempts/last_error), rows stay "pending" — nothing is
        lost, nothing blocks /score (Kafka is not in the critical
        scoring path — CLAUDE.md)
          → Kafka restored: the next `flask events publish-outbox` run
            (no scheduler wired up yet — see app/cli.py) drains every
            pending row and publishes it, verified against a real broker
            outage/recovery cycle, not just a fake producer
```

No Kafka consumer exists in this codebase (explicit constraint across
every Phase 7 pass) — recovery here means the *producer/outbox* side
survives an outage without data loss, which is the entire current scope.
`tests/integration/test_kafka_integration.py` (Phase 7E) separately
proves a real broker round-trip (publish + consumer readback) works at
all; combined, the outbox durability guarantee and the real-broker
publish path are both independently verified, not just asserted.

## Keycloak recovery

Documented in `docs/runbooks/deployment.md`'s "Redeploying" section
already: Keycloak only imports `infra/keycloak/creditguard-realm.json`
on first boot of a fresh `staging_keycloak_data` volume — if that volume
is lost or corrupted, recreate it and redeploy:

```
docker compose -f docker-compose.staging.yml --env-file .env.staging down
docker volume rm creditguard-staging_staging_keycloak_data
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
```

This resets Keycloak back to exactly what the realm JSON describes (the
two seeded smoke-test users, the `creditguard-web`/`creditguard-api`
clients) — any user or role created by hand outside that file is lost.
Postgres application data (`staging_postgres_data`) is untouched by this
— the two volumes are independent, and this procedure doesn't require a
Postgres restore. Not independently drilled this pass (the realm import
is deterministic, file-driven, and has already been exercised
repeatedly across every phase's redeploys in this project without
issue) — noted here for completeness, not re-verified with a fresh
drill.

## Verification checklist

After any real recovery action (backup restore, application rollback,
migration rollback), confirm all of the following before calling the
incident resolved — this is exactly what the automated drill above
checks, restated as a manual checklist for when the drill script itself
isn't what's being run:

- [ ] `GET /api/v1/health` and `GET /api/v1/health/ready` both `200`
- [ ] A real user can authenticate (Keycloak token exchange succeeds)
- [ ] `POST /score` against a real deployed model version succeeds and
      returns a decision + explanation
- [ ] Previously-existing decisions are still readable
      (`GET /decisions/<id>`)
- [ ] `GET /api/v1/audit/verify-chain` reports `valid: true`
- [ ] The staging smoke suite passes in full (`make staging-smoke-test`)
- [ ] Frontend loads and can log in (manual check — not part of the
      automated drill)

## Known limitations

Deliberately out of scope for this pass — this runbook proves recovery
using the infrastructure this project actually has, not a claim that
infrastructure is sufficient for a real production deployment:

- **No off-host/cloud backup storage.** Backups live on the same host
  as the database they're backing up — a total host loss loses both
  simultaneously. A real deployment needs an off-host destination
  (object storage, a second host, etc.).
- **No backup encryption.** Plain files on local disk; see "Encryption"
  above.
- **No scheduler.** Backups are manually triggered
  (`make staging-backup`); nothing runs on a timer. The RPO target above
  is what a scheduler *would* achieve, not what exists today.
- **Not tested at production data volume.** The real drill numbers above
  are from a small staging dataset; restore time at real volume is
  unverified.
- **No image-tag pinning in `docker-compose.staging.yml`.** The
  application-rollback drill worked by building an old commit by hand;
  pinning the compose file to a specific `ghcr.io/.../api:<sha>` tag
  (images already published there since Phase 7E) would make this a
  `docker compose pull` operation instead — not wired up yet.
- **No formal on-call/incident-command process.** Who is authorized to
  trigger a production restore, how an incident is declared and
  communicated, and escalation paths are organizational decisions this
  document doesn't make.
- **No multi-region/multi-host failover, no managed database, no
  Kubernetes.** All explicitly out of scope for this pass — see this
  document's opening paragraph. These are future deployment-architecture
  decisions, not gaps in what was tested here.
