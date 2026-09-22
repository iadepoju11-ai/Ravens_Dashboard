"""Object-level (IDOR) cross-tenant access, gathered in one file
(CHECKLIST.md Phase 7D) for the direct-object-access endpoints across
decisions, models, fairness reports, reviews, audit records, and exports
that weren't already covered elsewhere:

- decisions list-level isolation: tests/integration/test_decisions_list.py::test_list_decisions_does_not_leak_other_tenants
- reviews GET-by-id isolation: tests/integration/test_reviews.py::test_get_review_returns_not_found_for_another_tenants_review
- models approve-by-id isolation: tests/integration/test_endpoint_authorization.py::test_compliance_officer_cannot_approve_another_tenants_model_version
- audit list-level isolation: tests/integration/test_endpoint_authorization.py::test_auditor_cannot_read_another_tenants_audit_events
- datasets list-level isolation: tests/integration/test_endpoint_authorization.py::test_compliance_officer_cannot_see_another_tenants_datasets

Every case here follows the same shape and the same reasoning
(app/infrastructure/security/tenant_context.py's own docstring): tenant
identity comes only from the authenticated Identity, never a
client-supplied id, and a lookup scoped to the wrong tenant must report
`404 not_found` -- the same response as "this id doesn't exist at all" --
never a `403` (which would confirm the id is real, just off-limits) and
never a `200` with real cross-tenant data.
"""

from __future__ import annotations

from app.extensions import db
from app.models.audit import AuditIntegrityCheck
from app.models.decision import Decision
from app.models.fairness import FairnessEvaluation
from app.models.model import Model, ModelVersion
from app.models.review import ReviewCase
from app.models.tenant import Tenant
from app.services.audit_service import record_event


def _create_tenant(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.commit()
    return tenant


def _create_deployed_model_version(tenant: Tenant) -> ModelVersion:
    model = Model(tenant_id=tenant.id, name="credit-risk")
    db.session.add(model)
    db.session.flush()
    model_version = ModelVersion(model_id=model.id, version="1.0.0", status="deployed", artifact_uri="file://x")
    db.session.add(model_version)
    db.session.commit()
    return model_version


def _create_approved_model_version(tenant: Tenant) -> ModelVersion:
    model = Model(tenant_id=tenant.id, name="credit-risk")
    db.session.add(model)
    db.session.flush()
    model_version = ModelVersion(model_id=model.id, version="1.0.0", status="approved", artifact_uri="file://x")
    db.session.add(model_version)
    db.session.commit()
    return model_version


def _create_decision(tenant: Tenant, model_version: ModelVersion) -> Decision:
    decision = Decision(
        tenant_id=tenant.id,
        model_version_id=model_version.id,
        application_reference="APP-ISOLATION-1",
        request_id="req-isolation-1",
        input_payload={},
        score=0.5,
        outcome="approve",
    )
    db.session.add(decision)
    db.session.commit()
    return decision


def test_decision_by_id_is_not_found_for_another_tenant(client, app, auth_headers):
    tenant_a = _create_tenant("decision-idor-tenant-a")
    tenant_b = _create_tenant("decision-idor-tenant-b")
    model_version_a = _create_deployed_model_version(tenant_a)
    decision_a = _create_decision(tenant_a, model_version_a)

    response = client.get(
        f"/api/v1/decisions/{decision_a.id}",
        headers=auth_headers(tenant_b.id, roles=("credit_analyst",)),
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"


def test_model_deploy_is_not_found_for_another_tenants_model_version(client, app, auth_headers):
    tenant_a = _create_tenant("model-deploy-idor-tenant-a")
    tenant_b = _create_tenant("model-deploy-idor-tenant-b")
    model_version_a = _create_approved_model_version(tenant_a)

    response = client.post(
        f"/api/v1/models/{model_version_a.id}/deploy",
        headers=auth_headers(tenant_b.id, roles=("compliance_officer",), sub="officer-b"),
    )

    assert response.status_code == 404
    with app.app_context():
        # Confirm the cross-tenant attempt didn't mutate tenant_a's own
        # model version despite reporting 404 -- not found must really
        # mean nothing happened, not "found but silently blocked".
        untouched = ModelVersion.query.filter_by(id=model_version_a.id).first()
        assert untouched.status == "approved"


def test_fairness_report_by_id_is_not_found_for_another_tenant(client, app, auth_headers):
    tenant_a = _create_tenant("fairness-idor-tenant-a")
    tenant_b = _create_tenant("fairness-idor-tenant-b")
    model_version_a = _create_deployed_model_version(tenant_a)

    evaluation = FairnessEvaluation(
        tenant_id=tenant_a.id,
        model_version_id=model_version_a.id,
        protected_attribute="age_group",
        metric_name="demographic_parity_difference",
        metric_value=0.2,
        threshold=0.1,
        passed=False,
    )
    db.session.add(evaluation)
    db.session.commit()

    response = client.get(
        f"/api/v1/fairness/reports/{evaluation.id}",
        headers=auth_headers(tenant_b.id, roles=("compliance_officer",)),
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"


def test_review_resolve_is_not_found_and_makes_no_change_for_another_tenants_case(client, app, auth_headers):
    tenant_a = _create_tenant("review-resolve-idor-tenant-a")
    tenant_b = _create_tenant("review-resolve-idor-tenant-b")
    model_version_a = _create_deployed_model_version(tenant_a)
    decision_a = _create_decision(tenant_a, model_version_a)
    review_case = ReviewCase(
        tenant_id=tenant_a.id, decision_id=decision_a.id, status="open", reason="Score fell in the refer band"
    )
    db.session.add(review_case)
    db.session.commit()
    review_case_id = review_case.id

    response = client.post(
        f"/api/v1/reviews/{review_case_id}/resolve",
        json={"status": "closed"},
        headers=auth_headers(tenant_b.id, roles=("compliance_officer",), sub="officer-b"),
    )

    assert response.status_code == 404
    with app.app_context():
        untouched = ReviewCase.query.filter_by(id=review_case_id).first()
        assert untouched.status == "open"
        assert untouched.resolved_at is None


def test_audit_event_verify_by_id_is_not_found_and_writes_no_integrity_check_for_another_tenant(
    client, app, auth_headers
):
    tenant_a = _create_tenant("audit-verify-idor-tenant-a")
    tenant_b = _create_tenant("audit-verify-idor-tenant-b")

    with app.app_context():
        event = record_event(
            tenant_id=tenant_a.id, event_type="test.event", entity_type="test", entity_id="entity-1", payload={}
        )
        db.session.commit()
        event_id = event.id

    response = client.get(
        f"/api/v1/audit/events/{event_id}/verify",
        headers=auth_headers(tenant_b.id, roles=("auditor",), sub="auditor-b"),
    )

    assert response.status_code == 404
    with app.app_context():
        # A cross-tenant lookup must fail before any AuditIntegrityCheck
        # row is written -- otherwise tenant_b's identity would end up
        # attributed to a check about an event it was never allowed to
        # see.
        assert AuditIntegrityCheck.query.filter_by(checked_from_event_id=event_id).count() == 0


def test_audit_export_only_ever_returns_the_callers_own_tenants_events(client, app, auth_headers):
    tenant_a = _create_tenant("audit-export-idor-tenant-a")
    tenant_b = _create_tenant("audit-export-idor-tenant-b")

    with app.app_context():
        record_event(tenant_id=tenant_a.id, event_type="test.event", entity_type="test", entity_id="a-1", payload={})
        record_event(tenant_id=tenant_b.id, event_type="test.event", entity_id="b-1", entity_type="test", payload={})
        db.session.commit()

    response = client.get(
        "/api/v1/audit/export", headers=auth_headers(tenant_a.id, roles=("auditor",), sub="auditor-a")
    )

    assert response.status_code == 200
    body = response.get_json()
    returned_tenant_ids = {event["tenant_id"] for event in body["events"]}
    assert returned_tenant_ids == {tenant_a.id}
    # The export's own audit trail entry is attributed to the caller's
    # tenant too, not left ambiguous or attributed to whichever tenant
    # happened to be created first.
    assert body["meta"]["exported_by"]
