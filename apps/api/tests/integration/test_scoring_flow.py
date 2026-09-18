from app.extensions import db
from app.models.decision import Decision
from app.models.model import Model, ModelVersion
from app.models.tenant import Tenant


def _create_tenant_and_model():
    tenant = Tenant(name="Acme Bank", slug="acme-bank")
    db.session.add(tenant)
    db.session.flush()

    model = Model(tenant_id=tenant.id, name="credit-risk")
    db.session.add(model)
    db.session.flush()

    model_version = ModelVersion(
        model_id=model.id,
        version="1.0.0",
        status="deployed",
        artifact_uri="file://./model_artifacts/credit-risk-1.0.0.pkl",
    )
    db.session.add(model_version)
    db.session.commit()
    return tenant, model_version


def test_score_application_creates_decision_and_explanation(client, app, auth_headers):
    tenant, model_version = _create_tenant_and_model()

    response = client.post(
        "/api/v1/score",
        json={
            "application_reference": "APP-1001",
            "features": {"income": 0.8, "debt_ratio": 0.2},
        },
        headers=auth_headers(tenant.id),
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["decision"]["model_version_id"] == model_version.id
    assert body["decision"]["outcome"] in ("approve", "refer", "decline")
    assert body["decision"]["request_id"]
    assert body["explanation"]["feature_attributions"]

    decision_id = body["decision"]["id"]
    get_response = client.get(f"/api/v1/decisions/{decision_id}", headers={"X-Tenant-Id": tenant.id})
    assert get_response.status_code == 200
    assert get_response.get_json()["decision"]["id"] == decision_id


def test_score_without_a_token_is_rejected(client):
    # This endpoint no longer trusts an X-Tenant-Id header at all (see
    # docs/architecture/oidc-rbac.md) -- what used to be "missing header"
    # is now "missing/invalid credential", covered thoroughly by
    # tests/integration/test_score_authorization.py. This is just the
    # smoke-test-level check that the happy-path suite's baseline
    # unauthenticated request is rejected.
    response = client.post("/api/v1/score", json={"application_reference": "APP-1", "features": {}})
    assert response.status_code == 401


def test_score_without_deployed_model_is_rejected(client, app, auth_headers):
    tenant = Tenant(name="No Model Bank", slug="no-model-bank")
    db.session.add(tenant)
    db.session.commit()

    response = client.post(
        "/api/v1/score",
        json={"application_reference": "APP-2", "features": {"income": 0.5}},
        headers=auth_headers(tenant.id),
    )
    assert response.status_code == 409


def test_audit_event_is_recorded_and_verifiable(client, app, auth_headers):
    tenant, _ = _create_tenant_and_model()

    score_response = client.post(
        "/api/v1/score",
        json={"application_reference": "APP-3", "features": {"income": 0.9}},
        headers=auth_headers(tenant.id),
    )
    decision_id = score_response.get_json()["decision"]["id"]

    events_response = client.get("/api/v1/audit/events", headers={"X-Tenant-Id": tenant.id})
    events = events_response.get_json()["events"]
    assert len(events) == 1
    assert events[0]["entity_id"] == decision_id

    verify_response = client.get(
        f"/api/v1/audit/events/{events[0]['id']}/verify", headers={"X-Tenant-Id": tenant.id}
    )
    verify_body = verify_response.get_json()
    assert verify_body["valid"] is True
    assert verify_body["integrity_check_id"]


def test_score_missing_application_reference_is_rejected(client, app, auth_headers):
    tenant, _ = _create_tenant_and_model()

    response = client.post(
        "/api/v1/score",
        json={"features": {"income": 0.5}},
        headers=auth_headers(tenant.id),
    )
    assert response.status_code == 400
    assert "application_reference" in response.get_json()["error"]


def test_score_empty_features_is_rejected(client, app, auth_headers):
    tenant, _ = _create_tenant_and_model()

    response = client.post(
        "/api/v1/score",
        json={"application_reference": "APP-4", "features": {}},
        headers=auth_headers(tenant.id),
    )
    assert response.status_code == 400
    assert "features" in response.get_json()["error"]


def test_score_unsupported_feature_type_is_rejected(client, app, auth_headers):
    tenant, _ = _create_tenant_and_model()

    response = client.post(
        "/api/v1/score",
        json={"application_reference": "APP-5", "features": {"income": {"nested": "object"}}},
        headers=auth_headers(tenant.id),
    )
    assert response.status_code == 400
    assert "income" in response.get_json()["error"]


def test_score_unknown_model_version_is_rejected(client, app, auth_headers):
    tenant, _ = _create_tenant_and_model()

    response = client.post(
        "/api/v1/score",
        json={
            "application_reference": "APP-6",
            "features": {"income": 0.5},
            "model_version_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=auth_headers(tenant.id),
    )
    assert response.status_code == 404


def test_score_non_deployed_model_version_is_rejected(client, app, auth_headers):
    tenant, deployed_version = _create_tenant_and_model()

    draft_version = ModelVersion(
        model_id=deployed_version.model_id,
        version="0.1.0-draft",
        status="draft",
        artifact_uri="file://./model_artifacts/credit-risk-0.1.0-draft.pkl",
    )
    db.session.add(draft_version)
    db.session.commit()

    response = client.post(
        "/api/v1/score",
        json={
            "application_reference": "APP-7",
            "features": {"income": 0.5},
            "model_version_id": draft_version.id,
        },
        headers=auth_headers(tenant.id),
    )
    assert response.status_code == 409


def test_score_replays_idempotently_by_request_id(client, app, auth_headers):
    tenant, _ = _create_tenant_and_model()

    payload = {
        "application_reference": "APP-8",
        "features": {"income": 0.5},
        "request_id": "client-key-123",
    }
    headers = auth_headers(tenant.id)

    first = client.post("/api/v1/score", json=payload, headers=headers)
    assert first.status_code == 201
    first_decision_id = first.get_json()["decision"]["id"]

    second = client.post("/api/v1/score", json=payload, headers=headers)
    assert second.status_code == 200
    assert second.get_json()["decision"]["id"] == first_decision_id

    # Only one decision and one audit event were actually created.
    assert Decision.query.filter_by(tenant_id=tenant.id).count() == 1


def test_deploying_a_model_version_supersedes_the_previous_deployment(client, app):
    tenant, first_version = _create_tenant_and_model()

    second_version = ModelVersion(
        model_id=first_version.model_id,
        version="2.0.0",
        status="approved",
        artifact_uri="file://./model_artifacts/credit-risk-2.0.0.pkl",
    )
    db.session.add(second_version)
    db.session.commit()

    response = client.post(
        f"/api/v1/models/{second_version.id}/deploy", headers={"X-Tenant-Id": tenant.id}
    )
    assert response.status_code == 200
    assert response.get_json()["model_version"]["status"] == "deployed"

    db.session.refresh(first_version)
    assert first_version.status == "archived"
