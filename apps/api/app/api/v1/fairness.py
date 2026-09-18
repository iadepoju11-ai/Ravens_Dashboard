from flask import Blueprint, jsonify, request

from app.extensions import db
from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant_by_id
from app.models.fairness import FairnessEvaluation
from app.models.model import ModelVersion
from app.models.monitoring import MonitoringAlert
from app.security.authentication import authenticate
from app.security.permissions import require_permission

bp = Blueprint("fairness", __name__)

_REQUIRED_METRIC_FIELDS = ("protected_attribute", "metric_name", "metric_value", "threshold", "passed")


@bp.get("/fairness/reports")
def list_fairness_reports():
    identity = authenticate()
    require_permission(identity, "fairness:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    evaluations = (
        FairnessEvaluation.query.filter_by(tenant_id=tenant.id)
        .order_by(FairnessEvaluation.created_at.desc())
        .all()
    )
    return jsonify(reports=[e.to_dict() for e in evaluations])


@bp.get("/fairness/reports/<report_id>")
def get_fairness_report(report_id: str):
    identity = authenticate()
    require_permission(identity, "fairness:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    evaluation = FairnessEvaluation.query.filter_by(id=report_id, tenant_id=tenant.id).first()
    if evaluation is None:
        return jsonify(error="not_found"), 404
    return jsonify(report=evaluation.to_dict())


@bp.post("/fairness/evaluate")
def record_fairness_evaluation():
    """Persists fairness metrics computed offline by the ML pipeline
    (apps/workers/ml/fairness.py) against a specific model version, and
    raises a MonitoringAlert for any metric that failed its threshold —
    tying fairness monitoring into the same alert mechanism the audit
    chain already uses (see app/cli.py). Mirrors POST /models: the real
    computation happens in the ML worker (which has no direct database
    access), this endpoint is the governance system of record.

    A metric with metric_value=None (evaluate_fairness's "not_applicable"
    case, e.g. too few groups met the minimum sample size) is reported
    back but not persisted -- there is nothing to compare against a
    threshold, and a bare "fair"/"unfair" row would misrepresent that.
    """
    identity = authenticate()
    require_permission(identity, "fairness:review")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    body = request.get_json(silent=True) or {}
    model_version_id = body.get("model_version_id")
    metrics = body.get("metrics")

    if not model_version_id or not isinstance(metrics, list) or not metrics:
        return jsonify(error="model_version_id and a non-empty metrics list are required"), 400

    model_version = ModelVersion.query.filter_by(id=model_version_id).first()
    if model_version is None or model_version.model.tenant_id != tenant.id:
        return jsonify(error="Unknown model_version_id for this tenant"), 404

    for metric in metrics:
        if not isinstance(metric, dict) or not all(field in metric for field in _REQUIRED_METRIC_FIELDS):
            return jsonify(error=f"Each metric requires: {', '.join(_REQUIRED_METRIC_FIELDS)}"), 400

    created = []
    skipped_not_applicable = []
    for metric in metrics:
        if metric["metric_value"] is None:
            skipped_not_applicable.append(metric["metric_name"])
            continue

        evaluation = FairnessEvaluation(
            tenant_id=tenant.id,
            model_version_id=model_version.id,
            protected_attribute=metric["protected_attribute"],
            metric_name=metric["metric_name"],
            metric_value=metric["metric_value"],
            threshold=metric["threshold"],
            passed=bool(metric["passed"]),
        )
        db.session.add(evaluation)
        created.append(evaluation)

        if not evaluation.passed:
            db.session.add(
                MonitoringAlert(
                    tenant_id=tenant.id,
                    alert_type="fairness_threshold_breach",
                    severity="high",
                    message=(
                        f"Fairness metric '{evaluation.metric_name}' for "
                        f"{evaluation.protected_attribute}={evaluation.metric_value:.4f} "
                        f"exceeds threshold {evaluation.threshold}"
                    ),
                    source_entity_type="model_version",
                    source_entity_id=model_version.id,
                )
            )

    db.session.commit()
    return (
        jsonify(reports=[e.to_dict() for e in created], skipped_not_applicable=skipped_not_applicable),
        201,
    )
