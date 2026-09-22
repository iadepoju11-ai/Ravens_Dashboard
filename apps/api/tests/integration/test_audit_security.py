"""Audit chain security tests (CHECKLIST.md Phase 5): tamper, deletion,
reordering, and fork must all be detected by verify_chain. See
app/services/audit_service.py for exactly what "detected" means and this
store's threat model (tamper-evident, not immutable — a privileged
attacker who rewrites an event *and* every downstream hash/prev_hash to
stay internally consistent is explicitly out of scope).
"""

from datetime import timedelta

from app.extensions import db
from app.models.audit import AuditEvent, AuditIntegrityCheck
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


def test_verify_chain_endpoint_persists_an_integrity_check(client, app, auth_headers):
    tenant = _create_tenant("audit-endpoint-bank")
    _record_events(tenant.id, 2)

    response = client.get(
        "/api/v1/audit/verify-chain", headers=auth_headers(tenant.id, roles=("auditor",))
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["valid"] is True
    assert body["events_checked"] == 2
    assert body["integrity_check_id"]


def test_integrity_status_is_none_before_any_check_has_run(client, app, auth_headers):
    tenant = _create_tenant("audit-status-empty-bank")
    _record_events(tenant.id, 2)

    response = client.get(
        "/api/v1/audit/integrity-status", headers=auth_headers(tenant.id, roles=("auditor",))
    )

    assert response.status_code == 200
    assert response.get_json()["latest_check"] is None


def test_integrity_status_reports_the_last_check_without_running_a_new_one(client, app, auth_headers):
    tenant = _create_tenant("audit-status-bank")
    _record_events(tenant.id, 2)
    headers = auth_headers(tenant.id, roles=("auditor",))
    verify_response = client.get("/api/v1/audit/verify-chain", headers=headers)
    integrity_check_id = verify_response.get_json()["integrity_check_id"]

    response = client.get("/api/v1/audit/integrity-status", headers=headers)

    assert response.status_code == 200
    latest_check = response.get_json()["latest_check"]
    assert latest_check["id"] == integrity_check_id
    assert latest_check["valid"] is True

    # Reading the status again must not trigger another check.
    count_before = AuditIntegrityCheck.query.filter_by(tenant_id=tenant.id).count()
    client.get("/api/v1/audit/integrity-status", headers=headers)
    count_after = AuditIntegrityCheck.query.filter_by(tenant_id=tenant.id).count()
    assert count_after == count_before


def test_export_requires_the_audit_export_permission(client, app, auth_headers):
    tenant = _create_tenant("audit-export-perms-bank")
    _record_events(tenant.id, 2)

    response = client.get(
        "/api/v1/audit/export", headers=auth_headers(tenant.id, roles=("credit_analyst",))
    )

    assert response.status_code == 403


def test_export_returns_every_event_with_its_payload(client, app, auth_headers):
    tenant = _create_tenant("audit-export-bank")
    _record_events(tenant.id, 3)

    response = client.get(
        "/api/v1/audit/export", headers=auth_headers(tenant.id, roles=("auditor",))
    )

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["events"]) == 3
    # AuditEvent.to_dict() alone never includes payload (see
    # GET /audit/events) -- the export is the one place it's included,
    # since it's the actual audit content and is already free of raw
    # personal data by construction (record_event's own payloads never
    # carry raw applicant features).
    assert all("payload" in event for event in body["events"])
    assert body["meta"]["event_count"] == 3
    assert body["meta"]["exported_by"]


def test_export_scoped_by_date_range_excludes_events_outside_it(client, app, auth_headers):
    tenant = _create_tenant("audit-export-scoped-bank")
    events = _record_events(tenant.id, 3)

    # Push the first event's timestamp well into the past so a date_from
    # filter can genuinely exclude it.
    events[0].created_at = events[0].created_at - timedelta(days=30)
    db.session.commit()

    cutoff = (events[0].created_at + timedelta(days=1)).isoformat()
    response = client.get(
        f"/api/v1/audit/export?date_from={cutoff}", headers=auth_headers(tenant.id, roles=("auditor",))
    )

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["events"]) == 2
    assert events[0].id not in {event["id"] for event in body["events"]}
    assert body["meta"]["scope"]["date_from"] == cutoff


def test_export_rejects_an_invalid_date(client, app, auth_headers):
    tenant = _create_tenant("audit-export-bad-date-bank")
    _record_events(tenant.id, 1)

    response = client.get(
        "/api/v1/audit/export?date_from=not-a-date", headers=auth_headers(tenant.id, roles=("auditor",))
    )

    assert response.status_code == 400


def test_export_itself_is_recorded_as_a_chained_audit_event(client, app, auth_headers):
    tenant = _create_tenant("audit-export-self-log-bank")
    _record_events(tenant.id, 2)
    headers = auth_headers(tenant.id, roles=("auditor",))

    response = client.get("/api/v1/audit/export", headers=headers)
    export_event_id = response.get_json()["meta"]["export_event_id"]

    # The export action is itself part of the tamper-evident chain, not
    # a separate access log -- so verifying the chain must see it, and it
    # must not have appeared in its own export's results.
    assert export_event_id not in {event["id"] for event in response.get_json()["events"]}
    exported_event = AuditEvent.query.filter_by(id=export_event_id).first()
    assert exported_event is not None
    assert exported_event.event_type == "audit.export"

    verify_response = client.get("/api/v1/audit/verify-chain", headers=headers)
    assert verify_response.get_json()["valid"] is True
    assert verify_response.get_json()["events_checked"] == 3
