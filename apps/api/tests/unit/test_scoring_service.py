import pytest

from app.extensions import db
from app.models.decision import Decision
from app.models.model import Model, ModelVersion
from app.models.tenant import Tenant
from app.services.model_runtime import FeatureContribution, ModelExplanation, ModelPrediction
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


class _BrokenRuntime:
    def predict(self, features):
        raise RuntimeError("model artefact path: /secret/internal/path.pkl")

    def explain(self, features, prediction):
        raise AssertionError("explain() must not be called when predict() fails")


class _FixedRuntime:
    """A fake ModelRuntime, unrelated to the placeholder or any real model
    library — demonstrates that ScoringService works with any object
    satisfying the Protocol, not just PlaceholderRuntime."""

    def predict(self, features):
        return ModelPrediction(score=0.9)

    def explain(self, features, prediction):
        return ModelExplanation(
            base_value=0.1,
            contributions=[FeatureContribution(feature_name="income", value=0.8)],
            method="fixed-fake",
        )


def test_runtime_failure_raises_explicit_error_and_creates_no_decision(app):
    tenant = _create_tenant_and_deployed_model()

    with pytest.raises(ScoringRuntimeError) as exc_info:
        ScoringService(runtime=_BrokenRuntime()).score(
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


def test_scoring_service_is_unaware_of_the_concrete_runtime(app):
    tenant = _create_tenant_and_deployed_model()

    result = ScoringService(runtime=_FixedRuntime()).score(
        tenant=tenant,
        application_reference="APP-FIXED-RUNTIME",
        features={"income": 0.5},
        request_id="fixed-runtime-1",
    )

    assert result.decision.score == 0.9
    assert result.decision.outcome == "decline"
    assert result.explanation.method == "fixed-fake"
    assert result.explanation.feature_attributions == {"income": 0.8}
