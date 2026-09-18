"""Covers POST /fairness/evaluate: the governance system of record for
fairness metrics computed offline by apps/workers/ml/fairness.py. The ML
worker has no database access (see apps/workers/requirements.txt — no
psycopg2/sqlalchemy), so this endpoint is how a computed report becomes a
real, queryable FairnessEvaluation row, exactly as POST /models is how a
trained artifact becomes a real ModelVersion row
(test_model_registration.py).
"""

from app.extensions import db
from app.models.fairness import FairnessEvaluation
from app.models.monitoring import MonitoringAlert
from app.models.tenant import Tenant


def _create_tenant(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.commit()
    return tenant


def _register_model_version(client, headers) -> str:
    response = client.post(
        "/api/v1/models",
        json={"name": "credit-risk", "version": "1.0.0-dev", "artifact_uri": "file://./does-not-matter.pkl"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.get_json()["model_version"]["id"]


def test_record_fairness_evaluation_persists_passing_and_failing_metrics(client, app, auth_headers):
    tenant = _create_tenant("fairness-eval-bank")
    headers = auth_headers(tenant.id, roles=("compliance_officer",))
    model_version_id = _register_model_version(client, headers)

    response = client.post(
        "/api/v1/fairness/evaluate",
        json={
            "model_version_id": model_version_id,
            "metrics": [
                {
                    "protected_attribute": "CODE_GENDER",
                    "metric_name": "demographic_parity_difference",
                    "metric_value": 0.03,
                    "threshold": 0.10,
                    "passed": True,
                },
                {
                    "protected_attribute": "CODE_GENDER",
                    "metric_name": "equalized_odds_difference",
                    "metric_value": 0.22,
                    "threshold": 0.10,
                    "passed": False,
                },
            ],
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.get_json()
    assert len(body["reports"]) == 2
    assert body["skipped_not_applicable"] == []

    stored = FairnessEvaluation.query.filter_by(tenant_id=tenant.id).order_by(FairnessEvaluation.metric_name).all()
    assert {e.metric_name for e in stored} == {"demographic_parity_difference", "equalized_odds_difference"}

    alerts = MonitoringAlert.query.filter_by(tenant_id=tenant.id, alert_type="fairness_threshold_breach").all()
    assert len(alerts) == 1
    assert alerts[0].severity == "high"
    assert "equalized_odds_difference" in alerts[0].message


def test_record_fairness_evaluation_skips_not_applicable_metrics(client, app, auth_headers):
    tenant = _create_tenant("fairness-eval-na-bank")
    headers = auth_headers(tenant.id, roles=("compliance_officer",))
    model_version_id = _register_model_version(client, headers)

    response = client.post(
        "/api/v1/fairness/evaluate",
        json={
            "model_version_id": model_version_id,
            "metrics": [
                {
                    "protected_attribute": "CODE_GENDER",
                    "metric_name": "not_applicable",
                    "metric_value": None,
                    "threshold": None,
                    "passed": None,
                }
            ],
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["reports"] == []
    assert body["skipped_not_applicable"] == ["not_applicable"]
    assert FairnessEvaluation.query.filter_by(tenant_id=tenant.id).count() == 0


def test_record_fairness_evaluation_requires_model_version_and_metrics(client, app, auth_headers):
    tenant = _create_tenant("fairness-eval-validation-bank")
    headers = auth_headers(tenant.id, roles=("compliance_officer",))

    response = client.post("/api/v1/fairness/evaluate", json={"metrics": []}, headers=headers)

    assert response.status_code == 400


def test_record_fairness_evaluation_rejects_unknown_model_version(client, app, auth_headers):
    tenant = _create_tenant("fairness-eval-unknown-model-bank")
    headers = auth_headers(tenant.id, roles=("compliance_officer",))

    response = client.post(
        "/api/v1/fairness/evaluate",
        json={
            "model_version_id": "00000000-0000-0000-0000-000000000000",
            "metrics": [
                {
                    "protected_attribute": "CODE_GENDER",
                    "metric_name": "demographic_parity_difference",
                    "metric_value": 0.03,
                    "threshold": 0.10,
                    "passed": True,
                }
            ],
        },
        headers=headers,
    )

    assert response.status_code == 404


def test_record_fairness_evaluation_requires_permission(client, app, auth_headers):
    tenant = _create_tenant("fairness-eval-perms-bank")
    model_version_id = _register_model_version(client, auth_headers(tenant.id, roles=("compliance_officer",)))

    response = client.post(
        "/api/v1/fairness/evaluate",
        json={
            "model_version_id": model_version_id,
            "metrics": [
                {
                    "protected_attribute": "CODE_GENDER",
                    "metric_name": "demographic_parity_difference",
                    "metric_value": 0.03,
                    "threshold": 0.10,
                    "passed": True,
                }
            ],
        },
        headers=auth_headers(tenant.id, roles=("credit_analyst",)),
    )

    assert response.status_code == 403


def test_get_fairness_reports_lists_recorded_evaluations(client, app, auth_headers):
    tenant = _create_tenant("fairness-eval-list-bank")
    headers = auth_headers(tenant.id, roles=("compliance_officer",))
    model_version_id = _register_model_version(client, headers)
    client.post(
        "/api/v1/fairness/evaluate",
        json={
            "model_version_id": model_version_id,
            "metrics": [
                {
                    "protected_attribute": "CODE_GENDER",
                    "metric_name": "demographic_parity_difference",
                    "metric_value": 0.03,
                    "threshold": 0.10,
                    "passed": True,
                }
            ],
        },
        headers=headers,
    )

    response = client.get("/api/v1/fairness/reports", headers=headers)

    assert response.status_code == 200
    assert len(response.get_json()["reports"]) == 1
