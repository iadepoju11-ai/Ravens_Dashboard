import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.extensions import limiter
from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant_by_id
from app.models.decision import DECISION_OUTCOMES, Decision
from app.models.explanation import Explanation
from app.security.authentication import authenticate
from app.security.permissions import require_permission
from app.services.reason_codes import generate_reason_codes
from app.services.scoring_service import ScoringRuntimeError, ScoringService, ScoringValidationError

bp = Blueprint("decisions", __name__)

_DEFAULT_LIST_LIMIT = 20
_MAX_LIST_LIMIT = 100


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _explanation_dict(explanation: Explanation | None) -> dict | None:
    if explanation is None:
        return None
    return {
        **explanation.to_dict(),
        "reason_codes": generate_reason_codes(explanation.feature_attributions),
    }


@bp.post("/score")
# Stricter than the app-wide default (app/config.py's RATELIMIT_DEFAULT) --
# this is the most expensive request in the system (model inference,
# explanation generation, an audit write, three outbox writes) and the
# one most worth bounding per caller (CHECKLIST.md Phase 7D).
@limiter.limit("30 per minute")
def score_application():
    identity = authenticate()
    require_permission(identity, "decisions:create")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
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
            explanation=_explanation_dict(result.explanation),
        ),
        status_code,
    )


@bp.get("/decisions")
def list_decisions():
    """Filterable by decision status (`outcome`), model version
    (`model_version_id`), and time period (`date_from`/`date_to`, ISO-8601).
    "Lending product" filtering (ERD Phase 6) isn't listed — the schema
    doesn't model a lending-product concept yet, so there's nothing to
    filter by.
    """
    identity = authenticate()
    require_permission(identity, "decisions:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    query = Decision.query.filter_by(tenant_id=tenant.id)

    outcome = request.args.get("outcome")
    if outcome:
        if outcome not in DECISION_OUTCOMES:
            return jsonify(error=f"outcome must be one of {list(DECISION_OUTCOMES)}"), 400
        query = query.filter_by(outcome=outcome)

    model_version_id = request.args.get("model_version_id")
    if model_version_id:
        query = query.filter_by(model_version_id=model_version_id)

    date_from = request.args.get("date_from")
    if date_from:
        parsed = _parse_iso_datetime(date_from)
        if parsed is None:
            return jsonify(error="date_from must be an ISO-8601 date/datetime"), 400
        query = query.filter(Decision.created_at >= parsed)

    date_to = request.args.get("date_to")
    if date_to:
        parsed = _parse_iso_datetime(date_to)
        if parsed is None:
            return jsonify(error="date_to must be an ISO-8601 date/datetime"), 400
        query = query.filter(Decision.created_at <= parsed)

    try:
        limit = int(request.args.get("limit", _DEFAULT_LIST_LIMIT))
    except ValueError:
        return jsonify(error="limit must be an integer"), 400
    limit = max(1, min(limit, _MAX_LIST_LIMIT))

    decisions = query.order_by(Decision.created_at.desc()).limit(limit).all()
    return jsonify(decisions=[d.to_dict() for d in decisions])


@bp.get("/decisions/<decision_id>")
def get_decision(decision_id: str):
    identity = authenticate()
    require_permission(identity, "decisions:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    decision = Decision.query.filter_by(id=decision_id, tenant_id=tenant.id).first()
    if decision is None:
        return jsonify(error="not_found"), 404

    explanation = Explanation.query.filter_by(decision_id=decision.id).first()

    return jsonify(
        decision=decision.to_dict(),
        explanation=_explanation_dict(explanation),
    )
