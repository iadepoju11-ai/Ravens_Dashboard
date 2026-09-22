"""Covers the review-case API: listing, reading one with its decision
context, and the claim/resolve workflow. Review cases themselves are
opened by ScoringService (see tests/unit/test_scoring_service.py) --
these tests focus on the API surface built on top of that, using
directly-constructed ReviewCase rows so they don't depend on hitting a
specific score band.
"""

from app.extensions import db
from app.models.decision import Decision
from app.models.model import Model, ModelVersion
from app.models.review import ReviewCase
from app.models.tenant import Tenant


def _create_tenant(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.commit()
    return tenant


def _create_decision(tenant: Tenant) -> Decision:
    model = Model(tenant_id=tenant.id, name="credit-risk")
    db.session.add(model)
    db.session.flush()
    model_version = ModelVersion(model_id=model.id, version="1.0.0", status="deployed", artifact_uri="file://x")
    db.session.add(model_version)
    db.session.flush()
    decision = Decision(
        tenant_id=tenant.id,
        model_version_id=model_version.id,
        application_reference="APP-REVIEW-1",
        request_id="req-review-1",
        input_payload={},
        score=0.5,
        outcome="refer",
    )
    db.session.add(decision)
    db.session.commit()
    return decision


def _create_review_case(tenant: Tenant, decision: Decision, status: str = "open") -> ReviewCase:
    review_case = ReviewCase(
        tenant_id=tenant.id, decision_id=decision.id, status=status, reason="Score fell in the refer band"
    )
    db.session.add(review_case)
    db.session.commit()
    return review_case


def test_list_reviews_requires_the_review_read_permission(client, app, auth_headers):
    tenant = _create_tenant("reviews-perms-bank")

    response = client.get("/api/v1/reviews", headers=auth_headers(tenant.id, roles=("credit_analyst",)))

    assert response.status_code == 403


def test_list_reviews_includes_decision_context(client, app, auth_headers):
    tenant = _create_tenant("reviews-list-bank")
    decision = _create_decision(tenant)
    _create_review_case(tenant, decision)

    response = client.get("/api/v1/reviews", headers=auth_headers(tenant.id, roles=("compliance_officer",)))

    assert response.status_code == 200
    reviews = response.get_json()["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["status"] == "open"
    assert reviews[0]["decision"]["application_reference"] == "APP-REVIEW-1"
    assert reviews[0]["decision"]["outcome"] == "refer"


def test_list_reviews_filters_by_status(client, app, auth_headers):
    tenant = _create_tenant("reviews-filter-bank")
    decision = _create_decision(tenant)
    _create_review_case(tenant, decision, status="open")
    _create_review_case(tenant, decision, status="closed")
    headers = auth_headers(tenant.id, roles=("compliance_officer",))

    response = client.get("/api/v1/reviews?status=closed", headers=headers)

    assert response.status_code == 200
    reviews = response.get_json()["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["status"] == "closed"


def test_list_reviews_rejects_an_invalid_status(client, app, auth_headers):
    tenant = _create_tenant("reviews-bad-status-bank")

    response = client.get(
        "/api/v1/reviews?status=nonsense", headers=auth_headers(tenant.id, roles=("compliance_officer",))
    )

    assert response.status_code == 400


def test_get_review_returns_not_found_for_another_tenants_review(client, app, auth_headers):
    tenant_a = _create_tenant("reviews-tenant-a-bank")
    tenant_b = _create_tenant("reviews-tenant-b-bank")
    decision = _create_decision(tenant_a)
    review_case = _create_review_case(tenant_a, decision)

    response = client.get(
        f"/api/v1/reviews/{review_case.id}", headers=auth_headers(tenant_b.id, roles=("compliance_officer",))
    )

    assert response.status_code == 404


def test_resolve_claims_an_open_case(client, app, auth_headers):
    tenant = _create_tenant("reviews-claim-bank")
    decision = _create_decision(tenant)
    review_case = _create_review_case(tenant, decision)

    response = client.post(
        f"/api/v1/reviews/{review_case.id}/resolve",
        json={"status": "in_review"},
        headers=auth_headers(tenant.id, roles=("compliance_officer",)),
    )

    assert response.status_code == 200
    body = response.get_json()["review"]
    assert body["status"] == "in_review"
    assert body["assigned_to"]
    assert body["resolved_at"] is None


def test_resolve_closes_a_case_directly_from_open(client, app, auth_headers):
    tenant = _create_tenant("reviews-direct-close-bank")
    decision = _create_decision(tenant)
    review_case = _create_review_case(tenant, decision)

    response = client.post(
        f"/api/v1/reviews/{review_case.id}/resolve",
        json={"status": "closed"},
        headers=auth_headers(tenant.id, roles=("compliance_officer",)),
    )

    assert response.status_code == 200
    body = response.get_json()["review"]
    assert body["status"] == "closed"
    assert body["resolved_at"]
    # Nobody had claimed it -- resolving directly still records who did.
    assert body["assigned_to"]


def test_resolve_rejects_reopening_a_closed_case(client, app, auth_headers):
    tenant = _create_tenant("reviews-reopen-bank")
    decision = _create_decision(tenant)
    review_case = _create_review_case(tenant, decision, status="closed")

    response = client.post(
        f"/api/v1/reviews/{review_case.id}/resolve",
        json={"status": "in_review"},
        headers=auth_headers(tenant.id, roles=("compliance_officer",)),
    )

    assert response.status_code == 409


def test_resolve_rejects_an_invalid_status_value(client, app, auth_headers):
    tenant = _create_tenant("reviews-bad-resolve-status-bank")
    decision = _create_decision(tenant)
    review_case = _create_review_case(tenant, decision)

    response = client.post(
        f"/api/v1/reviews/{review_case.id}/resolve",
        json={"status": "open"},
        headers=auth_headers(tenant.id, roles=("compliance_officer",)),
    )

    assert response.status_code == 400


def test_resolve_requires_the_review_resolve_permission(client, app, auth_headers):
    tenant = _create_tenant("reviews-resolve-perms-bank")
    decision = _create_decision(tenant)
    review_case = _create_review_case(tenant, decision)

    # auditor holds neither review:read nor review:resolve -- admin can't be
    # used here since it has every permission by design (2026-09-18).
    response = client.post(
        f"/api/v1/reviews/{review_case.id}/resolve",
        json={"status": "closed"},
        headers=auth_headers(tenant.id, roles=("auditor",)),
    )

    assert response.status_code == 403
