import uuid

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant
from app.models.decision import Decision
from app.models.explanation import Explanation
from app.models.model import ModelVersion
from app.services import audit_service, explanation_service, scoring_service

bp = Blueprint("decisions", __name__)


@bp.post("/score")
def score_application():
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    body = request.get_json(silent=True) or {}
    application_reference = body.get("application_reference")
    features = body.get("features")
    model_version_id = body.get("model_version_id")
    # Idempotency: schema-only for now (unique per tenant), see
    # app/models/decision.py. A client-supplied key is honoured when given;
    # otherwise one is generated so the NOT NULL/unique constraint is
    # satisfied. Look-before-write dedup enforcement is ERD Phase 3.
    request_id = body.get("request_id") or str(uuid.uuid4())

    if not application_reference or not isinstance(features, dict):
        return jsonify(error="application_reference and features are required"), 400

    if model_version_id:
        model_version = ModelVersion.query.filter_by(id=model_version_id).first()
        if model_version is None or model_version.model.tenant_id != tenant.id:
            return jsonify(error="Unknown model_version_id for this tenant"), 404
    else:
        model_version = (
            ModelVersion.query.join(ModelVersion.model)
            .filter(ModelVersion.model.has(tenant_id=tenant.id), ModelVersion.status == "deployed")
            .order_by(ModelVersion.created_at.desc())
            .first()
        )
        if model_version is None:
            return jsonify(error="No deployed model available for this tenant"), 409

    risk_score = scoring_service.score(features)
    outcome = scoring_service.decide_outcome(risk_score)

    decision = Decision(
        tenant_id=tenant.id,
        model_version_id=model_version.id,
        application_reference=application_reference,
        request_id=request_id,
        input_payload=features,
        score=risk_score,
        outcome=outcome,
    )
    db.session.add(decision)
    db.session.flush()

    base_value, attributions = explanation_service.explain(features, risk_score)
    explanation = Explanation(
        decision_id=decision.id,
        method="stub-shap",
        base_value=base_value,
        feature_attributions=attributions,
    )
    db.session.add(explanation)

    audit_service.record_event(
        tenant_id=tenant.id,
        event_type="decision.created",
        entity_type="decision",
        entity_id=decision.id,
        payload={"score": risk_score, "outcome": outcome, "model_version_id": model_version.id},
    )

    db.session.commit()

    return jsonify(decision=decision.to_dict(), explanation=explanation.to_dict()), 201


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
