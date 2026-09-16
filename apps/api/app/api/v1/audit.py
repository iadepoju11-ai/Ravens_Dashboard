from flask import Blueprint, jsonify

from app.extensions import db
from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant
from app.models.audit import AuditEvent, AuditIntegrityCheck, compute_hash

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
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    event = AuditEvent.query.filter_by(id=event_id, tenant_id=tenant.id).first()
    if event is None:
        return jsonify(error="not_found"), 404

    expected_hash = compute_hash(
        event.prev_hash, event.event_type, event.entity_type, event.entity_id, event.payload
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
