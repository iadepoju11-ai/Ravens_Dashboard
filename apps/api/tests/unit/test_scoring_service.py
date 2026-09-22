import pytest

from app.extensions import db
from app.models.decision import Decision
from app.models.fairness import FairnessEvaluation
from app.models.governance import GovernanceResult
from app.models.model import Model, ModelVersion
from app.models.review import ReviewCase
from app.models.tenant import Tenant
from app.services.model_runtime import FeatureContribution, ModelExplanation, ModelPrediction
from app.services.scoring_service import ScoringRuntimeError, ScoringService, ScoringValidationError


def _create_tenant_and_deployed_model(metrics: dict | None = None):
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
        metrics=metrics,
    )
    db.session.add(model_version)
    db.session.commit()
    return tenant, model_version


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


class _ScoreRuntime:
    """A fake runtime returning a fixed, caller-chosen score -- used to hit
    a specific outcome band (approve/refer/decline) on demand."""

    def __init__(self, score: float):
        self._score = score

    def predict(self, features):
        return ModelPrediction(score=self._score)

    def explain(self, features, prediction):
        return ModelExplanation(base_value=0.0, contributions=[], method="score-runtime-fake")


def test_runtime_failure_raises_explicit_error_and_creates_no_decision(app):
    tenant, _model_version = _create_tenant_and_deployed_model()

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
    tenant, _model_version = _create_tenant_and_deployed_model()

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


def test_a_clean_decision_gets_a_passing_governance_result_and_no_review_case(app):
    tenant, _model_version = _create_tenant_and_deployed_model()

    result = ScoringService(runtime=_ScoreRuntime(0.1)).score(
        tenant=tenant,
        application_reference="APP-CLEAN-APPROVE",
        features={"income": 0.5},
        request_id="clean-approve-1",
    )

    assert result.decision.outcome == "approve"
    governance_result = GovernanceResult.query.filter_by(decision_id=result.decision.id).first()
    assert governance_result is not None
    assert governance_result.passed is True
    assert ReviewCase.query.filter_by(decision_id=result.decision.id).count() == 0


def test_a_refer_outcome_opens_a_review_case(app):
    tenant, _model_version = _create_tenant_and_deployed_model()

    result = ScoringService(runtime=_ScoreRuntime(0.5)).score(
        tenant=tenant,
        application_reference="APP-REFER",
        features={"income": 0.5},
        request_id="refer-1",
    )

    assert result.decision.outcome == "refer"
    review_case = ReviewCase.query.filter_by(decision_id=result.decision.id).first()
    assert review_case is not None
    assert review_case.status == "open"
    assert review_case.tenant_id == tenant.id
    assert "refer band" in review_case.reason


def test_a_failing_governance_check_opens_a_review_case_even_on_a_clean_approve(app):
    tenant, model_version = _create_tenant_and_deployed_model()
    db.session.add(
        FairnessEvaluation(
            tenant_id=tenant.id,
            model_version_id=model_version.id,
            protected_attribute="CODE_GENDER",
            metric_name="demographic_parity_difference",
            metric_value=0.3,
            threshold=0.10,
            passed=False,
        )
    )
    db.session.commit()

    result = ScoringService(runtime=_ScoreRuntime(0.1)).score(
        tenant=tenant,
        application_reference="APP-GOVERNANCE-FAIL",
        features={"income": 0.5},
        request_id="governance-fail-1",
    )

    assert result.decision.outcome == "approve"
    governance_result = GovernanceResult.query.filter_by(decision_id=result.decision.id).first()
    assert governance_result.passed is False
    review_case = ReviewCase.query.filter_by(decision_id=result.decision.id).first()
    assert review_case is not None
    assert "fairness evaluation" in review_case.reason


def test_unknown_feature_is_rejected_when_the_model_version_has_a_schema(app):
    tenant, _model_version = _create_tenant_and_deployed_model(
        metrics={"features": {"numeric": ["income"], "categorical": ["employment_type"]}}
    )

    with pytest.raises(ScoringValidationError, match="unexpected_feature"):
        ScoringService(runtime=_FixedRuntime()).score(
            tenant=tenant,
            application_reference="APP-UNKNOWN-FEATURE",
            features={"income": 0.5, "unexpected_feature": 1},
            request_id="unknown-feature-1",
        )


def test_wrong_type_for_a_numeric_feature_is_rejected(app):
    tenant, _model_version = _create_tenant_and_deployed_model(
        metrics={"features": {"numeric": ["income"], "categorical": []}}
    )

    with pytest.raises(ScoringValidationError, match="must be numeric"):
        ScoringService(runtime=_FixedRuntime()).score(
            tenant=tenant,
            application_reference="APP-WRONG-TYPE",
            features={"income": "not-a-number"},
            request_id="wrong-type-1",
        )


def test_a_model_version_without_a_recorded_schema_skips_validation(app):
    # Every fixture/test model registered without `metrics` (the common
    # case, and every test above this one) must keep working unchanged --
    # there is nothing to validate an unlisted feature name against.
    tenant, _model_version = _create_tenant_and_deployed_model(metrics=None)

    result = ScoringService(runtime=_FixedRuntime()).score(
        tenant=tenant,
        application_reference="APP-NO-SCHEMA",
        features={"anything_at_all": 1},
        request_id="no-schema-1",
    )

    assert result.decision.score == 0.9
