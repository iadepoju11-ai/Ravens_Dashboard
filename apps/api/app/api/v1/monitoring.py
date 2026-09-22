from flask import Blueprint, jsonify

from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant_by_id
from app.models.decision import Decision
from app.models.model import Model, ModelVersion
from app.models.monitoring import MonitoringAlert
from app.observability.summary import build_observability_summary
from app.security.authentication import authenticate
from app.security.permissions import require_permission

bp = Blueprint("monitoring", __name__)


@bp.get("/monitoring/metrics")
def get_metrics():
    identity = authenticate()
    require_permission(identity, "monitoring:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
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
    identity = authenticate()
    require_permission(identity, "monitoring:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    # Real writers, not a placeholder: audit-chain verification failures
    # (app/cli.py), outbox publish failures, and fairness threshold
    # breaches (app/api/v1/fairness.py) all raise these — see each
    # MonitoringAlert( call site for exactly when.
    alerts = (
        MonitoringAlert.query.filter_by(tenant_id=tenant.id)
        .order_by(MonitoringAlert.created_at.desc())
        .all()
    )
    return jsonify(alerts=[a.to_dict() for a in alerts])


@bp.get("/monitoring/observability")
def get_observability():
    """Process-level operational metrics (HTTP throughput/latency/errors,
    scoring/model-inference/explanation duration, DB query stats, outbox
    publish outcomes, governance/review counts) — CHECKLIST.md Phase 7B.

    Deliberately NOT tenant-scoped data, unlike every other endpoint in
    this blueprint: these are in-process Prometheus counters for the
    whole running container (see app/observability/metrics.py), the same
    numbers any tenant's requests contribute to and that GET /metrics
    exposes in raw Prometheus format for a real Prometheus/Grafana
    scrape. Gated by monitoring:read (the same permission the
    tenant-scoped endpoints above use) because it's still operational
    visibility into "is the platform healthy", not a tenant data leak —
    no per-tenant breakdown is included or derivable from these numbers.
    """
    identity = authenticate()
    require_permission(identity, "monitoring:read")

    return jsonify(observability=build_observability_summary())
