from app.extensions import db
from app.models.model import Model, ModelVersion
from app.models.tenant import Tenant


def _create_tenant(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.commit()
    return tenant


def test_metrics_report_no_data_explicitly_rather_than_zero(client, app):
    tenant = _create_tenant("monitoring-empty-bank")

    response = client.get("/api/v1/monitoring/metrics", headers={"X-Tenant-Id": tenant.id})

    assert response.status_code == 200
    metrics = response.get_json()["metrics"]
    assert metrics["decision_count"] == 0
    # None, not 0 — "no decisions yet" and "0% approval rate" are
    # different facts.
    assert metrics["approval_rate"] is None
    assert metrics["current_model_version"] is None


def test_metrics_report_approval_rate_and_current_model_version(client, app):
    tenant = _create_tenant("monitoring-data-bank")
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

    client.post(
        "/api/v1/score",
        json={"application_reference": "APP-1", "features": {"income": 0.1}, "request_id": "req-1"},
        headers={"X-Tenant-Id": tenant.id},
    )
    client.post(
        "/api/v1/score",
        json={"application_reference": "APP-2", "features": {"income": 0.9}, "request_id": "req-2"},
        headers={"X-Tenant-Id": tenant.id},
    )

    response = client.get("/api/v1/monitoring/metrics", headers={"X-Tenant-Id": tenant.id})

    metrics = response.get_json()["metrics"]
    assert metrics["decision_count"] == 2
    assert metrics["approved_count"] == 1
    assert metrics["approval_rate"] == 0.5
    assert metrics["current_model_version"] == {
        "model_id": model.id,
        "model_name": "credit-risk",
        "model_version_id": model_version.id,
        "version": "1.0.0",
    }
