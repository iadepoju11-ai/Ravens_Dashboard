from app.extensions import db
from app.models.model import Model, ModelVersion
from app.models.tenant import Tenant


_tenant_counter = 0


def _create_tenant_and_model() -> tuple[Tenant, ModelVersion]:
    global _tenant_counter
    _tenant_counter += 1
    slug = f"decisions-list-bank-{_tenant_counter}"
    tenant = Tenant(name=slug, slug=slug)
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


def _score(client, tenant, application_reference, income, request_id):
    return client.post(
        "/api/v1/score",
        json={"application_reference": application_reference, "features": {"income": income}, "request_id": request_id},
        headers={"X-Tenant-Id": tenant.id},
    )


def test_list_decisions_returns_recent_decisions_newest_first(client, app):
    tenant, _ = _create_tenant_and_model()
    _score(client, tenant, "APP-1", 0.1, "req-1")
    _score(client, tenant, "APP-2", 0.9, "req-2")

    response = client.get("/api/v1/decisions", headers={"X-Tenant-Id": tenant.id})

    assert response.status_code == 200
    decisions = response.get_json()["decisions"]
    assert [d["application_reference"] for d in decisions] == ["APP-2", "APP-1"]


def test_list_decisions_filters_by_outcome(client, app):
    tenant, _ = _create_tenant_and_model()
    _score(client, tenant, "APP-LOW", 0.1, "req-low")  # approve
    _score(client, tenant, "APP-HIGH", 0.9, "req-high")  # decline

    response = client.get("/api/v1/decisions?outcome=decline", headers={"X-Tenant-Id": tenant.id})

    assert response.status_code == 200
    decisions = response.get_json()["decisions"]
    assert [d["application_reference"] for d in decisions] == ["APP-HIGH"]


def test_list_decisions_rejects_an_invalid_outcome(client, app):
    tenant, _ = _create_tenant_and_model()

    response = client.get("/api/v1/decisions?outcome=not_a_real_outcome", headers={"X-Tenant-Id": tenant.id})

    assert response.status_code == 400


def test_list_decisions_filters_by_model_version(client, app):
    tenant, model_version = _create_tenant_and_model()
    _score(client, tenant, "APP-1", 0.1, "req-1")

    response = client.get(
        f"/api/v1/decisions?model_version_id={model_version.id}", headers={"X-Tenant-Id": tenant.id}
    )
    assert response.status_code == 200
    assert len(response.get_json()["decisions"]) == 1

    response = client.get(
        "/api/v1/decisions?model_version_id=00000000-0000-0000-0000-000000000000",
        headers={"X-Tenant-Id": tenant.id},
    )
    assert response.status_code == 200
    assert response.get_json()["decisions"] == []


def test_list_decisions_rejects_an_unparseable_date(client, app):
    tenant, _ = _create_tenant_and_model()

    response = client.get("/api/v1/decisions?date_from=not-a-date", headers={"X-Tenant-Id": tenant.id})

    assert response.status_code == 400


def test_list_decisions_limit_is_clamped(client, app):
    tenant, _ = _create_tenant_and_model()
    for i in range(3):
        _score(client, tenant, f"APP-{i}", 0.1, f"req-{i}")

    response = client.get("/api/v1/decisions?limit=1", headers={"X-Tenant-Id": tenant.id})

    assert response.status_code == 200
    assert len(response.get_json()["decisions"]) == 1


def test_list_decisions_does_not_leak_other_tenants(client, app):
    tenant_a, _ = _create_tenant_and_model()
    tenant_b, _ = _create_tenant_and_model()
    _score(client, tenant_a, "APP-A", 0.1, "req-a")
    _score(client, tenant_b, "APP-B", 0.1, "req-b")

    response = client.get("/api/v1/decisions", headers={"X-Tenant-Id": tenant_a.id})

    decisions = response.get_json()["decisions"]
    assert [d["application_reference"] for d in decisions] == ["APP-A"]
