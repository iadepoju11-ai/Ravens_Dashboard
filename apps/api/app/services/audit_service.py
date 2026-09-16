"""Append-only audit evidence.

Chains each event to the previous one's hash (per tenant) so the sequence
is tamper-evident: recomputing the hash of any event and comparing it to
the stored value detects edits, and a break in the prev_hash chain detects
deletions or reordering. See ERD Section 1.1 ("persist decision evidence")
and the "tamper-evident audit evidence" replacement for the prototype's
basic audit logger. Publishing events onto the Kafka audit topic for
downstream consumers is handled by the audit worker, not this service.
"""

from __future__ import annotations

from app.extensions import db
from app.models.audit import AuditEvent, compute_hash


def record_event(tenant_id: str, event_type: str, entity_type: str, entity_id: str, payload: dict) -> AuditEvent:
    last_event = (
        AuditEvent.query.filter_by(tenant_id=tenant_id).order_by(AuditEvent.created_at.desc()).first()
    )
    prev_hash = last_event.hash if last_event else None

    event = AuditEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, event_type, entity_type, entity_id, payload),
    )
    db.session.add(event)
    return event
