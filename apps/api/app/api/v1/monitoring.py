from flask import Blueprint, jsonify

from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant
from app.models.decision import Decision
from app.models.model import Model, ModelVersion
from app.models.monitoring import MonitoringAlert

bp = Blueprint("monitoring", __name__)


@bp.get("/monitoring/metrics")
def get_metrics():
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    decision_count = Decision.query.filter_by(tenant_id=tenant.id).count()
    approved_count = Decision.query.filter_by(tenant_id=tenant.id, outcome="approve").count()
    # None (not 0) when there's no data yet — a 0% approval rate and "we
    # don't know yet" are different facts, and the frontend must show them
    # differently (CHECKLIST.md Phase 6: never render 0 for missing data).
    approval_rate = (approved_count / decision_count) if decision_count else None

    deployed_versions = (
        ModelVersion.query.join(Model)
        .filter(Model.tenant_id == tenant.id, ModelVersion.status == "deployed")
        .order_by(ModelVersion.created_at.desc())
        .all()
    )
    current_model_version = None
    if deployed_versions:
        latest = deployed_versions[0]
        current_model_version = {
            "model_id": latest.model_id,
            "model_name": latest.model.name,
            "model_version_id": latest.id,
            "version": latest.version,
        }

    return jsonify(
        metrics={
            "decision_count": decision_count,
            "approved_count": approved_count,
            "approval_rate": approval_rate,
            "deployed_model_count": len(deployed_versions),
            "current_model_version": current_model_version,
        }
    )


@bp.get("/monitoring/alerts")
def list_alerts():
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    # Alerts are raised by the monitoring worker (ERD Section 3.1), not yet
    # implemented, so this will be empty until that worker exists.
    alerts = (
        MonitoringAlert.query.filter_by(tenant_id=tenant.id)
        .order_by(MonitoringAlert.created_at.desc())
        .all()
    )
    return jsonify(alerts=[a.to_dict() for a in alerts])
