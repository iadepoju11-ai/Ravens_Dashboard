# Backup and restore

Verified manually on 2026-09-17 against the local dockerized Postgres
(`docker-compose.yml`'s `postgres` service): seeded a tenant with a
3-event audit chain, backed up, dropped and recreated the database,
restored, and confirmed both the data and the audit hash chain
(`verify_chain`) were intact afterward. This documents that procedure so
it's repeatable, not a one-off terminal session.

**What this is**: a manual drill proving `pg_dump`/`pg_restore` round-trip
this schema correctly, including the timestamp precision the audit hash
chain depends on. **What this is not**: an automated backup schedule,
retention policy, or disaster-recovery runbook — see "Not yet built"
below.

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

- **No automated/scheduled backups.** This is a manual drill; nothing
  runs `pg_dump` on a schedule or ships the result anywhere.
- **No retention policy.** How many backups to keep, for how long, and
  where (encrypted at rest, off-host) isn't decided.
- **No disaster-recovery runbook** — RTO/RPO targets, who's on call, how
  a restore-into-production would actually be authorized and executed.
- **Not tested against a production-scale database** — this drill used a
  handful of rows; restore time and behavior at real data volumes is
  unverified.

These are real operational gaps, tracked in `CHECKLIST.md` Phase 7
(production engineering & pilot), not silently assumed solved by this
one successful drill.
