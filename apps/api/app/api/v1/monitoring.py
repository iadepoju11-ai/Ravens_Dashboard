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
    deployed_model_count = (
        ModelVersion.query.join(Model)
        .filter(Model.tenant_id == tenant.id, ModelVersion.status == "deployed")
        .count()
    )

    return jsonify(
        metrics={
            "decision_count": decision_count,
            "deployed_model_count": deployed_model_count,
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
