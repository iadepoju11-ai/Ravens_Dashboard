import pytest

from app.extensions import db
from app.models.decision import Decision
from app.models.model import Model, ModelVersion
from app.models.tenant import Tenant
from app.services.scoring_service import ScoringRuntimeError, ScoringService


def _create_tenant_and_deployed_model():
    tenant = Tenant(name="Runtime Failure Bank", slug="runtime-failure-bank")
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
    return tenant


def test_runtime_failure_raises_explicit_error_and_creates_no_decision(app, monkeypatch):
    tenant = _create_tenant_and_deployed_model()

    def _broken_predict(self, features):
        raise RuntimeError("model artefact path: /secret/internal/path.pkl")

    monkeypatch.setattr(ScoringService, "_predict", _broken_predict)

    with pytest.raises(ScoringRuntimeError) as exc_info:
        ScoringService().score(
            tenant=tenant,
            application_reference="APP-RUNTIME-FAIL",
            features={"income": 0.5},
            request_id="runtime-fail-1",
        )

    # The safe, generic message is exposed — never the original exception's
    # internals (e.g. a model artefact path).
    assert "secret" not in exc_info.value.message
    assert "path" not in exc_info.value.message.lower()

    # No half-written decision was left behind.
    assert Decision.query.filter_by(tenant_id=tenant.id).count() == 0
