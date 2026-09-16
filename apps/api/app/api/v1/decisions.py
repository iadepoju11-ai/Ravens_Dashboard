import uuid

from flask import Blueprint, jsonify, request

from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant
from app.models.decision import Decision
from app.models.explanation import Explanation
from app.services.scoring_service import ScoringRuntimeError, ScoringService, ScoringValidationError

bp = Blueprint("decisions", __name__)


@bp.post("/score")
def score_application():
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    body = request.get_json(silent=True) or {}
    # A client-supplied idempotency key is honoured when given; otherwise
    # one is generated. A generated key can never collide with a replay
    # (each call gets a fresh one), so only a client-supplied key can
    # actually trigger the dedup path in ScoringService.
    request_id = body.get("request_id") or str(uuid.uuid4())

    try:
        result = ScoringService().score(
            tenant=tenant,
            application_reference=body.get("application_reference"),
            features=body.get("features"),
            request_id=request_id,
            model_version_id=body.get("model_version_id"),
        )
    except (ScoringValidationError, ScoringRuntimeError) as exc:
        return jsonify(error=exc.message), exc.status_code

    status_code = 201 if result.created else 200
    return (
        jsonify(
            decision=result.decision.to_dict(),
            explanation=result.explanation.to_dict() if result.explanation else None,
        ),
        status_code,
    )


@bp.get("/decisions/<decision_id>")
def get_decision(decision_id: str):
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    decision = Decision.query.filter_by(id=decision_id, tenant_id=tenant.id).first()
    if decision is None:
        return jsonify(error="not_found"), 404

    explanation = Explanation.query.filter_by(decision_id=decision.id).first()

    return jsonify(
        decision=decision.to_dict(),
        explanation=explanation.to_dict() if explanation else None,
    )
