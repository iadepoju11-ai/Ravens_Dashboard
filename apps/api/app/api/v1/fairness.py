from flask import Blueprint, jsonify

from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant
from app.models.fairness import FairnessEvaluation

bp = Blueprint("fairness", __name__)


@bp.get("/fairness/reports")
def list_fairness_reports():
    try:
        tenant = resolve_tenant()
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
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    evaluation = FairnessEvaluation.query.filter_by(id=report_id, tenant_id=tenant.id).first()
    if evaluation is None:
        return jsonify(error="not_found"), 404
    return jsonify(report=evaluation.to_dict())
