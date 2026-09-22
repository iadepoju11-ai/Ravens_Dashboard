from datetime import datetime

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant_by_id
from app.models.audit import AuditEvent, AuditIntegrityCheck, compute_hash
from app.security.authentication import authenticate
from app.security.permissions import require_permission
from app.services.audit_service import record_event, verify_chain

bp = Blueprint("audit", __name__)


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@bp.get("/audit/events")
def list_audit_events():
    identity = authenticate()
    require_permission(identity, "audit:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    events = AuditEvent.query.filter_by(tenant_id=tenant.id).order_by(AuditEvent.created_at.asc()).all()
    return jsonify(events=[e.to_dict() for e in events])


@bp.get("/audit/events/<event_id>/verify")
def verify_audit_event(event_id: str):
    """Checks only this one event's own hash against its own recorded
    fields. This does NOT detect a deleted or forked event elsewhere in
    the chain — use /audit/verify-chain for that."""
    identity = authenticate()
    require_permission(identity, "audit:verify")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
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
    identity = authenticate()
    require_permission(identity, "audit:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
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
    identity = authenticate()
    require_permission(identity, "audit:verify")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
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


@bp.get("/audit/export")
def export_audit_events():
    """Permission-controlled export of a tenant's audit events, optionally
    scoped by `date_from`/`date_to` (same ISO-8601 convention as
    GET /decisions) so a caller isn't forced into a full-history dump.

    Personal data is minimised by construction, not by filtering here:
    record_event()'s own payloads (see e.g. scoring_service.py's
    "decision.created" event) never carry raw applicant features, only
    derived values like score/outcome/model_version_id -- so there is no
    raw personal data in an AuditEvent's payload to strip in the first
    place.

    Records who/when/scope: the export itself is written as a new
    AuditEvent (event_type "audit.export"), chained into the same
    tamper-evident sequence as everything else it exports -- "who
    exported what, when" is real audit evidence, not a separate access
    log that could be edited independently of it. That event is recorded
    after the export query runs, so it never includes itself.
    """
    identity = authenticate()
    require_permission(identity, "audit:export")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    query = AuditEvent.query.filter_by(tenant_id=tenant.id)

    date_from = request.args.get("date_from")
    if date_from:
        parsed = _parse_iso_datetime(date_from)
        if parsed is None:
            return jsonify(error="date_from must be an ISO-8601 date/datetime"), 400
        query = query.filter(AuditEvent.created_at >= parsed)

    date_to = request.args.get("date_to")
    if date_to:
        parsed = _parse_iso_datetime(date_to)
        if parsed is None:
            return jsonify(error="date_to must be an ISO-8601 date/datetime"), 400
        query = query.filter(AuditEvent.created_at <= parsed)

    events = query.order_by(AuditEvent.created_at.asc()).all()

    export_event = record_event(
        tenant_id=tenant.id,
        event_type="audit.export",
        entity_type="tenant",
        entity_id=tenant.id,
        payload={
            "exported_by": identity.user_id,
            "date_from": date_from,
            "date_to": date_to,
            "event_count": len(events),
        },
    )
    db.session.commit()

    return jsonify(
        events=[{**event.to_dict(), "payload": event.payload} for event in events],
        meta={
            "exported_by": identity.user_id,
            "exported_at": export_event.created_at.isoformat(),
            "scope": {"date_from": date_from, "date_to": date_to},
            "event_count": len(events),
            "export_event_id": export_event.id,
        },
    )
