"""Covers registering a model version via the API, approving it, and —
where the real trained artifact is available (`make ml-train`) — a full
end-to-end register -> link dataset version -> approve -> deploy -> score
chain against it, proving the real ModelRuntime adapter is actually
reachable through the live API, not just unit-tested in isolation.
"""

import json
import os
from pathlib import Path

import pytest

from app.extensions import db
from app.models.model import ModelVersion
from app.models.tenant import Tenant

ARTIFACT_PATH = os.environ.get("CREDIT_RISK_V1_ARTIFACT_PATH", "/app/model_artifacts/credit-risk-v1.joblib")
METADATA_PATH = os.environ.get(
    "CREDIT_RISK_V1_METADATA_PATH", "/app/model_artifacts/credit-risk-v1-metadata.json"
)
REAL_ARTIFACT_AVAILABLE = Path(ARTIFACT_PATH).exists()


def _create_tenant(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.commit()
    return tenant


def test_register_model_version_creates_a_draft(client, app):
    tenant = _create_tenant("model-registration-bank")

    response = client.post(
        "/api/v1/models",
        json={"name": "credit-risk", "version": "1.0.0-dev", "artifact_uri": "file://./does-not-matter.pkl"},
        headers={"X-Tenant-Id": tenant.id},
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["model_version"]["status"] == "draft"
    assert body["model"]["name"] == "credit-risk"


def test_registering_the_same_model_version_twice_is_rejected(client, app):
    tenant = _create_tenant("model-registration-dup-bank")
    payload = {"name": "credit-risk", "version": "1.0.0-dev", "artifact_uri": "file://./does-not-matter.pkl"}

    first = client.post("/api/v1/models", json=payload, headers={"X-Tenant-Id": tenant.id})
    assert first.status_code == 201

    second = client.post("/api/v1/models", json=payload, headers={"X-Tenant-Id": tenant.id})
    assert second.status_code == 409


def test_register_model_version_requires_name_version_and_artifact_uri(client, app):
    tenant = _create_tenant("model-registration-validation-bank")

    response = client.post(
        "/api/v1/models",
        json={"name": "credit-risk"},
        headers={"X-Tenant-Id": tenant.id},
    )

    assert response.status_code == 400


def test_register_model_version_rejects_unknown_training_dataset_version(client, app):
    tenant = _create_tenant("model-registration-unknown-dataset-bank")

    response = client.post(
        "/api/v1/models",
        json={
            "name": "credit-risk",
            "version": "1.0.0-dev",
            "artifact_uri": "file://./does-not-matter.pkl",
            "training_dataset_version_id": "00000000-0000-0000-0000-000000000000",
        },
        headers={"X-Tenant-Id": tenant.id},
    )

    assert response.status_code == 404


def test_register_model_version_links_a_real_dataset_version(client, app):
    tenant = _create_tenant("model-registration-dataset-link-bank")

    dataset_response = client.post(
        "/api/v1/datasets",
        json={"name": "home-credit-application", "version": "kaggle-home-credit-default-risk", "uri": "s3://x"},
        headers={"X-Tenant-Id": tenant.id},
    )
    assert dataset_response.status_code == 201
    dataset_version_id = dataset_response.get_json()["version"]["id"]

    model_response = client.post(
        "/api/v1/models",
        json={
            "name": "credit-risk",
            "version": "1.0.0-dev",
            "artifact_uri": "file://./does-not-matter.pkl",
            "training_dataset_version_id": dataset_version_id,
        },
        headers={"X-Tenant-Id": tenant.id},
    )
    assert model_response.status_code == 201


def test_approve_draft_model_version(client, app):
    tenant = _create_tenant("model-approval-bank")
    register_response = client.post(
        "/api/v1/models",
        json={"name": "credit-risk", "version": "1.0.0-dev", "artifact_uri": "file://./does-not-matter.pkl"},
        headers={"X-Tenant-Id": tenant.id},
    )
    model_version_id = register_response.get_json()["model_version"]["id"]

    response = client.post(
        f"/api/v1/models/{model_version_id}/approve", headers={"X-Tenant-Id": tenant.id}
    )

    assert response.status_code == 200
    assert response.get_json()["model_version"]["status"] == "approved"


def test_approving_an_already_approved_version_is_rejected(client, app):
    tenant = _create_tenant("model-approval-dup-bank")
    register_response = client.post(
        "/api/v1/models",
        json={"name": "credit-risk", "version": "1.0.0-dev", "artifact_uri": "file://./does-not-matter.pkl"},
        headers={"X-Tenant-Id": tenant.id},
    )
    model_version_id = register_response.get_json()["model_version"]["id"]
    client.post(f"/api/v1/models/{model_version_id}/approve", headers={"X-Tenant-Id": tenant.id})

    response = client.post(
        f"/api/v1/models/{model_version_id}/approve", headers={"X-Tenant-Id": tenant.id}
    )

    assert response.status_code == 409


def test_approving_an_unknown_model_version_is_rejected(client, app):
    tenant = _create_tenant("model-approval-unknown-bank")

    response = client.post(
        "/api/v1/models/00000000-0000-0000-0000-000000000000/approve",
        headers={"X-Tenant-Id": tenant.id},
    )

    assert response.status_code == 404


@pytest.mark.skipif(
    not REAL_ARTIFACT_AVAILABLE,
    reason=f"real trained artifact not found at {ARTIFACT_PATH} — run `make ml-train` first",
)
def test_score_against_the_real_deployed_model_uses_shap_tree_explanations(client, app):
    tenant = _create_tenant("real-model-bank")
    metadata = json.loads(Path(METADATA_PATH).read_text())

    dataset_response = client.post(
        "/api/v1/datasets",
        json={
            "name": metadata["dataset"]["name"],
            "version": metadata["dataset"]["version"],
            "uri": metadata["dataset"]["source_file"],
            "row_count": metadata["dataset"]["n_rows"],
        },
        headers={"X-Tenant-Id": tenant.id},
    )
    assert dataset_response.status_code == 201
    dataset_version_id = dataset_response.get_json()["version"]["id"]

    register_response = client.post(
        "/api/v1/models",
        json={
            "name": "credit-risk",
            "version": "1.0.0-dev",
            "artifact_uri": f"file://{ARTIFACT_PATH}",
            "metrics": {"features": metadata["features"]},
            "training_dataset_version_id": dataset_version_id,
        },
        headers={"X-Tenant-Id": tenant.id},
    )
    assert register_response.status_code == 201
    model_version_id = register_response.get_json()["model_version"]["id"]
    assert register_response.get_json()["model_version"]["id"] == model_version_id

    approve_response = client.post(
        f"/api/v1/models/{model_version_id}/approve", headers={"X-Tenant-Id": tenant.id}
    )
    assert approve_response.status_code == 200

    deploy_response = client.post(
        f"/api/v1/models/{model_version_id}/deploy", headers={"X-Tenant-Id": tenant.id}
    )
    assert deploy_response.status_code == 200

    score_response = client.post(
        "/api/v1/score",
        json={
            "application_reference": "APP-REAL-MODEL-1",
            "features": {"AMT_INCOME_TOTAL": 150000, "AMT_CREDIT": 500000, "NAME_CONTRACT_TYPE": "Cash loans"},
        },
        headers={"X-Tenant-Id": tenant.id},
    )

    assert score_response.status_code == 201
    body = score_response.get_json()
    assert 0.0 <= body["decision"]["score"] <= 1.0
    assert body["explanation"]["method"] == "shap-tree"
    assert len(body["explanation"]["feature_attributions"]) > 0

    # The trained-on dataset version is traceable from the deployed model.
    model_version = db.session.get(ModelVersion, model_version_id)
    assert model_version.training_dataset_version_id == dataset_version_id
