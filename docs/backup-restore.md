# Backup and restore

Verified manually on 2026-09-17 against the local dockerized Postgres
(`docker-compose.yml`'s `postgres` service): seeded a tenant with a
3-event audit chain, backed up, dropped and recreated the database,
restored, and confirmed both the data and the audit hash chain
(`verify_chain`) were intact afterward. This documents that procedure so
it's repeatable, not a one-off terminal session.

**What this is**: a manual drill proving `pg_dump`/`pg_restore` round-trip
this schema correctly, including the timestamp precision the audit hash
chain depends on. **What this is not**: an automated backup schedule or
a disaster-recovery runbook — see "Not yet built" below and
`docs/runbooks/disaster-recovery.md` (CHECKLIST.md Phase 7F), which
takes this same drill to the staging deployment (scripted, retention-
pruned backups, a real automated backup→destroy→restore→verify test,
RPO/RTO targets, and application/migration rollback drills).

## Taking a backup

```
docker compose exec -T postgres pg_dump -U creditguard -F c -d creditguard > creditguard.dump
```

`-F c` (custom format) is required for `pg_restore` below — it's
compressed and allows selective/parallel restore, unlike plain SQL dumps.

## Restoring

**Into an empty database** (disaster recovery — the database was lost or
corrupted):

```
docker compose exec -T postgres psql -U creditguard -d postgres -c "DROP DATABASE creditguard;"
docker compose exec -T postgres psql -U creditguard -d postgres -c "CREATE DATABASE creditguard OWNER creditguard;"
cat creditguard.dump | docker compose exec -T postgres pg_restore -U creditguard -d creditguard --no-owner
```

`--no-owner` avoids failures if the restoring role's name doesn't
exactly match what was dumped (not an issue in this dev setup, but
harmless to always include).

## Verifying a restore actually worked

Don't just check that tables exist — confirm the data is real and the
audit chain still verifies:

```
docker compose run --rm -e DATABASE_URL=postgresql://creditguard:creditguard@postgres:5432/creditguard \
  api python -c "
from app import create_app
app = create_app('development')
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://creditguard:creditguard@postgres:5432/creditguard'
with app.app_context():
    from app.services.audit_service import verify_chain
    result = verify_chain('<a-tenant-id-that-should-have-data>')
    print('valid:', result.valid, 'events:', result.events_checked)
"
```

This matters specifically for the audit chain: `compute_hash` includes
each event's `created_at` (see `docs/architecture/audit-threat-model.md`),
so a restore path that doesn't preserve timestamp precision exactly would
silently break every event's hash. This was worth checking, not assuming
— an earlier bug in this same hash-chain work was exactly a timestamp
round-trip losing precision (through SQLite, not Postgres/`pg_restore` —
but the same category of risk).

## Not yet built

- **No automated/scheduled backups.** `scripts/staging-backup.sh`
  (Phase 7F) is still manually triggered — nothing runs it on a
  schedule. See `docs/runbooks/disaster-recovery.md`'s RPO target for
  what a scheduler would achieve.
- **Retention exists at the staging level, not here.** Phase 7F's
  `scripts/staging-backup.sh` prunes to the N most recent backups
  (host-local only — no off-host/encrypted-at-rest copy; see that
  runbook's "Known limitations").
- **A disaster-recovery runbook now exists**: `docs/runbooks/disaster-recovery.md`
  — RTO/RPO targets, a real automated backup/restore drill, application
  and migration rollback drills. Who's on call and how a
  restore-into-production is authorized remain organizational decisions
  it deliberately doesn't make.
- **Not tested against a production-scale database** — this drill (and
  Phase 7F's staging-level equivalent) used a handful of rows; restore
  time and behavior at real data volumes is unverified.

These are real operational gaps, tracked in `CHECKLIST.md`, not silently
assumed solved by one successful drill.
