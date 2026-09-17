"""Append-only audit evidence.

Chains each event to the previous one's hash (per tenant) so the sequence
is tamper-evident: recomputing the hash of any event and comparing it to
the stored value detects edits (including a tampered timestamp, since
created_at is part of the hash input — see compute_hash), and a break in
the prev_hash chain detects deletions or forks. See ERD Section 1.1
("persist decision evidence") and the "tamper-evident audit evidence"
replacement for the prototype's basic audit logger. Publishing events onto
the Kafka audit topic for downstream consumers is handled by the audit
worker, not this service.

Threat model, per CLAUDE.md: "tamper-evident" means alteration is
detectable, not that it's prevented — a privileged attacker with DB write
access could rewrite an event *and* every downstream hash/prev_hash to
keep the chain internally consistent. This module cannot detect that; it
detects the far more common case of an edit that doesn't also rewrite the
rest of the chain (e.g. a manual UPDATE, or a deleted row). Never describe
this store as "immutable".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.extensions import db
from app.models.audit import AuditEvent, compute_hash
from app.models.base import utcnow


def record_event(tenant_id: str, event_type: str, entity_type: str, entity_id: str, payload: dict) -> AuditEvent:
    last_event = (
        AuditEvent.query.filter_by(tenant_id=tenant_id).order_by(AuditEvent.created_at.desc()).first()
    )
    prev_hash = last_event.hash if last_event else None
    # Generated explicitly (rather than left to the created_at column
    # default) so the exact value covered by the hash is the exact value
    # persisted — see compute_hash's docstring.
    created_at = utcnow()

    event = AuditEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, event_type, entity_type, entity_id, payload, created_at),
        created_at=created_at,
    )
    db.session.add(event)
    return event


@dataclass(frozen=True)
class ChainFailure:
    event_id: str
    reason: str  # "hash_mismatch" | "orphaned_or_unreachable" | "duplicate_predecessor"
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ChainVerificationResult:
    valid: bool
    events_checked: int
    first_event_id: str | None
    last_event_id: str | None
    failures: list[ChainFailure]


def verify_chain(tenant_id: str) -> ChainVerificationResult:
    """Verifies a tenant's entire audit chain, not just one event.

    Walks the chain by following hash pointers from the genesis event
    (prev_hash is None) forward — not by trusting `created_at` ordering,
    since a tampered timestamp shouldn't be able to fool the walk itself
    (it's still caught separately, as a hash_mismatch on that event).

    Detects:
    - **Tamper**: an event's stored hash doesn't match recomputing it from
      its own recorded fields -> "hash_mismatch".
    - **Deletion**: the event that should follow a given hash is missing,
      so nothing downstream of the deletion is reachable from genesis ->
      "orphaned_or_unreachable".
    - **Reordering** (via timestamp tampering): covered by "hash_mismatch",
      since created_at is part of the hash input.
    - **Fork**: two events both claim the same prev_hash ->
      "duplicate_predecessor" on the extra one(s).
    """
    events = AuditEvent.query.filter_by(tenant_id=tenant_id).order_by(AuditEvent.created_at.asc()).all()

    by_prev_hash: dict[str | None, list[AuditEvent]] = {}
    for event in events:
        by_prev_hash.setdefault(event.prev_hash, []).append(event)

    failures: list[ChainFailure] = []
    ordered: list[AuditEvent] = []
    current_prev_hash: str | None = None

    while True:
        candidates = by_prev_hash.get(current_prev_hash, [])
        if not candidates:
            break

        event, *extra = candidates
        for duplicate in extra:
            failures.append(
                ChainFailure(event_id=duplicate.id, reason="duplicate_predecessor", detail={"prev_hash": current_prev_hash})
            )

        ordered.append(event)
        recomputed = compute_hash(
            event.prev_hash, event.event_type, event.entity_type, event.entity_id, event.payload, event.created_at
        )
        if recomputed != event.hash:
            failures.append(ChainFailure(event_id=event.id, reason="hash_mismatch"))

        current_prev_hash = event.hash

    reached_ids = {event.id for event in ordered}
    for event in events:
        if event.id not in reached_ids:
            failures.append(ChainFailure(event_id=event.id, reason="orphaned_or_unreachable"))

    return ChainVerificationResult(
        valid=not failures,
        events_checked=len(events),
        first_event_id=ordered[0].id if ordered else None,
        last_event_id=ordered[-1].id if ordered else None,
        failures=failures,
    )
