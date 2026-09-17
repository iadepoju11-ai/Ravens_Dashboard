"""Proves ScoringService enqueues the right outbox events for a real
/score request, and — critically — does not re-enqueue them on an
idempotent replay (CHECKLIST.md "Kafka & events": duplicate-delivery
safety starts with not creating duplicate outbox rows in the first place).
"""

from app.extensions import db
from app.models.model import Model, ModelVersion
from app.models.outbox import OutboxEvent
from app.models.tenant import Tenant


def _create_tenant_and_model() -> tuple[Tenant, ModelVersion]:
    tenant = Tenant(name="outbox-integration-bank", slug="outbox-integration-bank")
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


def test_score_enqueues_the_three_expected_outbox_events(client, app):
    tenant, model_version = _create_tenant_and_model()

    response = client.post(
        "/api/v1/score",
        json={
            "application_reference": "APP-1",
            "features": {"income": 0.5},
            "request_id": "req-outbox-1",
        },
        headers={"X-Tenant-Id": tenant.id},
    )
    assert response.status_code == 201
    decision_id = response.get_json()["decision"]["id"]
    explanation_id = response.get_json()["explanation"]["id"]

    events = OutboxEvent.query.filter_by(tenant_id=tenant.id).order_by(OutboxEvent.event_type).all()
    by_type = {e.event_type: e for e in events}

    assert set(by_type) == {"decision.created.v1", "decision.completed.v1", "explanation.created.v1"}
    assert all(e.status == "pending" for e in events)
    assert all(e.correlation_id == "req-outbox-1" for e in events)
    assert by_type["decision.created.v1"].aggregate_id == decision_id
    assert by_type["decision.completed.v1"].aggregate_id == decision_id
    assert by_type["explanation.created.v1"].aggregate_id == explanation_id


def test_idempotent_replay_does_not_enqueue_duplicate_events(client, app):
    tenant, _ = _create_tenant_and_model()
    payload = {
        "application_reference": "APP-2",
        "features": {"income": 0.5},
        "request_id": "req-outbox-replay",
    }

    first = client.post("/api/v1/score", json=payload, headers={"X-Tenant-Id": tenant.id})
    assert first.status_code == 201

    second = client.post("/api/v1/score", json=payload, headers={"X-Tenant-Id": tenant.id})
    assert second.status_code == 200  # replay, not a new decision

    events = OutboxEvent.query.filter_by(tenant_id=tenant.id).all()
    assert len(events) == 3  # still just the first call's events
