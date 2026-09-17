"""Audit chain security tests (CHECKLIST.md Phase 5): tamper, deletion,
reordering, and fork must all be detected by verify_chain. See
app/services/audit_service.py for exactly what "detected" means and this
store's threat model (tamper-evident, not immutable — a privileged
attacker who rewrites an event *and* every downstream hash/prev_hash to
stay internally consistent is explicitly out of scope).
"""

from datetime import timedelta

from app.extensions import db
from app.models.audit import AuditEvent
from app.models.tenant import Tenant
from app.services import audit_service
from app.services.audit_service import verify_chain


def _create_tenant(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.commit()
    return tenant


def _record_events(tenant_id: str, count: int) -> list[AuditEvent]:
    events = [
        audit_service.record_event(
            tenant_id=tenant_id,
            event_type="decision.created",
            entity_type="decision",
            entity_id=f"00000000-0000-0000-0000-{i:012d}",
            payload={"index": i},
        )
        for i in range(count)
    ]
    db.session.commit()
    return events


def test_untampered_chain_verifies_as_valid(app):
    tenant = _create_tenant("audit-happy-path-bank")
    _record_events(tenant.id, 3)

    result = verify_chain(tenant.id)

    assert result.valid is True
    assert result.events_checked == 3
    assert result.failures == []


def test_tamper_is_detected(app):
    tenant = _create_tenant("audit-tamper-bank")
    events = _record_events(tenant.id, 3)

    # Modify a payload without recomputing the hash — simulates a manual
    # UPDATE, the exact case a hash chain exists to catch.
    tampered = events[1]
    tampered.payload = {"index": "TAMPERED"}
    db.session.commit()

    result = verify_chain(tenant.id)

    assert result.valid is False
    assert any(f.event_id == tampered.id and f.reason == "hash_mismatch" for f in result.failures)


def test_deletion_is_detected(app):
    tenant = _create_tenant("audit-deletion-bank")
    events = _record_events(tenant.id, 3)
    _first, middle, last = events

    db.session.delete(middle)
    db.session.commit()

    result = verify_chain(tenant.id)

    assert result.valid is False
    assert any(f.event_id == last.id and f.reason == "orphaned_or_unreachable" for f in result.failures)


def test_reordering_via_timestamp_tampering_is_detected(app):
    tenant = _create_tenant("audit-reorder-bank")
    events = _record_events(tenant.id, 3)

    # Move the first event's timestamp after the others, without
    # recomputing its hash — created_at is part of the hash input (see
    # compute_hash), so this must be caught the same way a payload tamper
    # is, not treated as a legitimate reorder.
    tampered = events[0]
    tampered.created_at = tampered.created_at + timedelta(hours=1)
    db.session.commit()

    result = verify_chain(tenant.id)

    assert result.valid is False
    assert any(f.event_id == tampered.id and f.reason == "hash_mismatch" for f in result.failures)


def test_fork_is_detected(app):
    tenant = _create_tenant("audit-fork-bank")
    events = _record_events(tenant.id, 2)
    first, _second = events

    # A forged event claiming the same predecessor as the real second
    # event — two events both claiming to be the immediate successor of
    # `first`.
    forked = AuditEvent(
        tenant_id=tenant.id,
        event_type="decision.created",
        entity_type="decision",
        entity_id="00000000-0000-0000-0000-000000000099",
        payload={"index": "forked"},
        prev_hash=first.hash,
        hash="0" * 64,
    )
    db.session.add(forked)
    db.session.commit()

    result = verify_chain(tenant.id)

    assert result.valid is False
    assert any(f.reason == "duplicate_predecessor" for f in result.failures)


def test_verify_chain_endpoint_persists_an_integrity_check(client, app):
    tenant = _create_tenant("audit-endpoint-bank")
    _record_events(tenant.id, 2)

    response = client.get("/api/v1/audit/verify-chain", headers={"X-Tenant-Id": tenant.id})

    assert response.status_code == 200
    body = response.get_json()
    assert body["valid"] is True
    assert body["events_checked"] == 2
    assert body["integrity_check_id"]
