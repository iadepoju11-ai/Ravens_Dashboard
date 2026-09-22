from flask import Blueprint, jsonify, request

from app.extensions import db
from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant_by_id
from app.models.decision import Decision
from app.models.review import ReviewCase
from app.security.authentication import authenticate
from app.security.permissions import require_permission

bp = Blueprint("reviews", __name__)

_REVIEW_STATUSES = ("open", "in_review", "closed")
# A real, ordered workflow, not a free-form status field: a case is
# claimed (open -> in_review) before it's resolved (-> closed), or
# resolved directly from open. Re-opening a closed case, or any other
# transition, is rejected.
_VALID_TRANSITIONS = {("open", "in_review"), ("open", "closed"), ("in_review", "closed")}


def _review_case_dict(review_case: ReviewCase, decision: Decision | None) -> dict:
    return {
        **review_case.to_dict(),
        "decision": (
            {
                "id": decision.id,
                "application_reference": decision.application_reference,
                "score": decision.score,
                "outcome": decision.outcome,
                "model_version_id": decision.model_version_id,
                "created_at": decision.created_at.isoformat(),
            }
            if decision
            else None
        ),
    }


@bp.get("/reviews")
def list_reviews():
    identity = authenticate()
    require_permission(identity, "review:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    query = ReviewCase.query.filter_by(tenant_id=tenant.id)

    status = request.args.get("status")
    if status:
        if status not in _REVIEW_STATUSES:
            return jsonify(error=f"status must be one of {list(_REVIEW_STATUSES)}"), 400
        query = query.filter_by(status=status)

    review_cases = query.order_by(ReviewCase.created_at.desc()).all()
    decisions_by_id = {
        decision.id: decision
        for decision in Decision.query.filter(
            Decision.id.in_([rc.decision_id for rc in review_cases])
        ).all()
    }
    return jsonify(
        reviews=[_review_case_dict(rc, decisions_by_id.get(rc.decision_id)) for rc in review_cases]
    )


@bp.get("/reviews/<review_id>")
def get_review(review_id: str):
    identity = authenticate()
    require_permission(identity, "review:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    review_case = ReviewCase.query.filter_by(id=review_id, tenant_id=tenant.id).first()
    if review_case is None:
        return jsonify(error="not_found"), 404

    decision = Decision.query.filter_by(id=review_case.decision_id).first()
    return jsonify(review=_review_case_dict(review_case, decision))


@bp.post("/reviews/<review_id>/resolve")
def resolve_review(review_id: str):
    """Moves a review case forward one workflow step: `status: "in_review"`
    claims it (records the caller as `assigned_to`); `status: "closed"`
    resolves it (records `resolved_at`, and `assigned_to` too if nobody
    had claimed it yet). Any other requested transition — including
    re-opening a closed case — is rejected with 409, not silently applied.
    """
    identity = authenticate()
    require_permission(identity, "review:resolve")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    review_case = ReviewCase.query.filter_by(id=review_id, tenant_id=tenant.id).first()
    if review_case is None:
        return jsonify(error="not_found"), 404

    body = request.get_json(silent=True) or {}
    new_status = body.get("status")
    if new_status not in ("in_review", "closed"):
        return jsonify(error="status must be 'in_review' or 'closed'"), 400

    if (review_case.status, new_status) not in _VALID_TRANSITIONS:
        return jsonify(error=f"Cannot move a '{review_case.status}' review case to '{new_status}'"), 409

    review_case.status = new_status
    if new_status == "in_review":
        review_case.assigned_to = identity.user_id
    else:
        review_case.resolved_at = db.func.now()
        if review_case.assigned_to is None:
            review_case.assigned_to = identity.user_id

    db.session.commit()
    return jsonify(review=review_case.to_dict())
