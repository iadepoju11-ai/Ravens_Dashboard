# Audit evidence: threat model

Per `CLAUDE.md`: **"append-only" means the app only ever adds events.
"Tamper-evident" means alteration is detectable. "Immutable" is reserved
for storage/controls that genuinely prevent alteration under a defined
threat model — this system does not currently have those controls, so it
must never be described as immutable.**

## What this protects against

Each `AuditEvent` is chained to the previous one via a SHA-256 hash over
its own fields *and* the previous event's hash (`app/models/audit.py`,
`compute_hash`). `app/services/audit_service.py::verify_chain` walks the
whole chain by following hash pointers (not by trusting `created_at`
ordering) and detects:

| Attack | Detected as | Test |
| --- | --- | --- |
| Editing an event's payload/type without recomputing its hash | `hash_mismatch` | `test_tamper_is_detected` |
| Editing an event's timestamp without recomputing its hash (`created_at` is part of the hash input) | `hash_mismatch` | `test_reordering_via_timestamp_tampering_is_detected` |
| Deleting an event from the middle of the chain | `orphaned_or_unreachable` (everything downstream of the gap is unreachable from genesis) | `test_deletion_is_detected` |
| Inserting a forged event claiming the same predecessor as a real one | `duplicate_predecessor` | `test_fork_is_detected` |

This is a real, useful property: it catches the common cases — a manual
`UPDATE`/`DELETE`, a buggy migration, an operator "fixing" a record by
hand — none of which require deep DB access to attempt, and all of which
are easy to attempt *without* also recomputing every downstream hash.

## What this does NOT protect against

**A privileged attacker with full DB write access can defeat this.** If
they edit event N *and* recompute N's hash *and* update event N+1's
`prev_hash` to match *and* recompute N+1's hash, and so on for every
downstream event, the chain stays internally consistent and
`verify_chain` reports `valid: true` — because nothing outside the
database itself holds an independent record of what the chain *should*
look like. This is not a bug to fix later; it is the fundamental limit of
a self-contained hash chain. Closing it requires an **independently
protected commitment** — periodically publishing the chain's current tip
hash somewhere the same attacker can't also rewrite (e.g. a separate
system, a write-once external log, a signed/timestamped external
service). That infrastructure does not exist yet (see "Not yet built"
below) — until it does, this store's actual guarantee is *tamper-evident
against low-effort/partial tampering*, not against a privileged attacker,
and it must not be marketed as more than that.

Also out of scope for a hash chain by design:
- **Confidentiality** — hashing doesn't hide the payload; `payload` is
  stored in plaintext JSON. Sensitive data in decision inputs is still
  sensitive data at rest.
- **Availability** — the chain proves *if* data was altered, not that
  it's backed up or recoverable. See "Not yet built" (backup/restore).
- **Write authorization** — anyone who can write to `audit_events` today
  writes through the same DB credentials as ordinary application CRUD
  (see "Not yet built").

## Verification granularity

- `GET /audit/events/<id>/verify` — checks **one event's own hash**
  against its own recorded fields. Cheap, but does not detect a deleted
  or forked event elsewhere in the chain.
- `GET /audit/verify-chain` — checks the **entire chain** (all four attack
  types above). Use this one for actual integrity assurance; the
  single-event endpoint is a narrower spot-check.

Both persist an `AuditIntegrityCheck` row recording what was checked and
whether it passed — but nothing runs either of them automatically today
(see "Not yet built").

## Not yet built (tracked in `CHECKLIST.md` Phase 5)

- **Independently protected integrity commitments** — as described above,
  the actual defense against a privileged/full-DB attacker. Requires an
  external system this app doesn't control.
- **Periodic verification + alerting** — `flask audit verify-all-tenants`
  (`app/cli.py`) runs `verify_chain` for every tenant and writes a
  `MonitoringAlert` on failure, but nothing calls it on a schedule yet.
  Any external scheduler (cron, a Kubernetes CronJob, a scheduled CI job)
  can; choosing one is a real architecture decision, not folded into this
  work.
- **Separate audit-write DB permissions from ordinary CRUD** — the app
  connects to Postgres with one role that can read/write everything,
  including `audit_events`. A compromised app process can currently both
  serve requests *and* tamper with audit evidence using the same
  credentials.
- **Permission-controlled audit export** — no `/audit/export` endpoint
  exists yet, and building one before real authentication/RBAC (ERD Phase
  6) exists would mean "permission-controlled" in name only.
- **Backup/restore testing** — not yet exercised against this schema.
- **Postgres Row-Level Security** — deliberately not enabled. RLS is only
  as trustworthy as the session variable that sets the tenant context, and
  today that context comes from a client-supplied `X-Tenant-Id` header
  with no verification behind it (see `app/infrastructure/security/tenant_context.py`).
  Enabling RLS on top of that would create a false sense of enforcement
  without one. Revisit once real authenticated tenant identity propagation
  exists.
