from flask import Blueprint, jsonify

from app.extensions import db
from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant
from app.models.audit import AuditEvent, AuditIntegrityCheck, compute_hash
from app.services.audit_service import verify_chain

bp = Blueprint("audit", __name__)


@bp.get("/audit/events")
def list_audit_events():
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    events = AuditEvent.query.filter_by(tenant_id=tenant.id).order_by(AuditEvent.created_at.asc()).all()
    return jsonify(events=[e.to_dict() for e in events])


@bp.get("/audit/events/<event_id>/verify")
def verify_audit_event(event_id: str):
    """Checks only this one event's own hash against its own recorded
    fields. This does NOT detect a deleted or forked event elsewhere in
    the chain — use /audit/verify-chain for that."""
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    event = AuditEvent.query.filter_by(id=event_id, tenant_id=tenant.id).first()
    if event is None:
        return jsonify(error="not_found"), 404

    expected_hash = compute_hash(
        event.prev_hash, event.event_type, event.entity_type, event.entity_id, event.payload, event.created_at
    )
    valid = expected_hash == event.hash

    check = AuditIntegrityCheck(
        tenant_id=tenant.id,
        checked_from_event_id=event.id,
        checked_to_event_id=event.id,
        valid=valid,
        details={"expected_hash": expected_hash, "stored_hash": event.hash},
    )
    db.session.add(check)
    db.session.commit()

    return jsonify(event_id=event.id, valid=valid, integrity_check_id=check.id)


@bp.get("/audit/integrity-status")
def get_latest_integrity_status():
    """The most recently recorded AuditIntegrityCheck, without triggering
    a fresh verification — for dashboard consumption (ERD Phase 6's
    "audit integrity status" KPI), where re-running a full chain walk on
    every page load would be wasteful and would write a new
    AuditIntegrityCheck row as a side effect of just looking at one.
    Trigger a real check via /audit/verify-chain or the periodic
    `flask audit verify-all-tenants` command; this only reports what the
    last one found, which may be stale."""
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    check = (
        AuditIntegrityCheck.query.filter_by(tenant_id=tenant.id)
        .order_by(AuditIntegrityCheck.created_at.desc())
        .first()
    )
    return jsonify(latest_check=check.to_dict() if check else None)


@bp.get("/audit/verify-chain")
def verify_audit_chain():
    """Verifies the tenant's entire audit chain — detects tamper,
    deletion, reordering (via timestamp tampering), and forks. See
    app/services/audit_service.py::verify_chain for what each failure
    reason means and this store's threat model."""
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    result = verify_chain(tenant.id)

    check = AuditIntegrityCheck(
        tenant_id=tenant.id,
        checked_from_event_id=result.first_event_id,
        checked_to_event_id=result.last_event_id,
        valid=result.valid,
        details={
            "events_checked": result.events_checked,
            "failures": [
                {"event_id": f.event_id, "reason": f.reason, **f.detail} for f in result.failures
            ],
        },
    )
    db.session.add(check)
    db.session.commit()

    return jsonify(
        valid=result.valid,
        events_checked=result.events_checked,
        first_event_id=result.first_event_id,
        last_event_id=result.last_event_id,
        failures=[{"event_id": f.event_id, "reason": f.reason, **f.detail} for f in result.failures],
        integrity_check_id=check.id,
    )
