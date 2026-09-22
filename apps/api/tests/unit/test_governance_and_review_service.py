from app.extensions import db
from app.models.fairness import FairnessEvaluation
from app.models.model import Model, ModelVersion
from app.models.tenant import Tenant
from app.services.governance_service import CHECK_NAME_FAIRNESS_STATUS, evaluate_governance
from app.services.review_service import REASON_GOVERNANCE_FAILURE, REASON_REFER_OUTCOME, maybe_open_review_case


def _create_deployed_model_version(tenant_slug: str) -> ModelVersion:
    tenant = Tenant(name=tenant_slug, slug=tenant_slug)
    db.session.add(tenant)
    db.session.flush()
    model = Model(tenant_id=tenant.id, name="credit-risk")
    db.session.add(model)
    db.session.flush()
    model_version = ModelVersion(model_id=model.id, version="1.0.0", status="deployed", artifact_uri="file://x")
    db.session.add(model_version)
    db.session.commit()
    return model_version


def test_evaluate_governance_passes_when_no_fairness_evaluations_exist(app):
    model_version = _create_deployed_model_version("governance-no-eval-bank")

    result = evaluate_governance(model_version.id, decision_id="00000000-0000-0000-0000-000000000001")

    assert result.check_name == CHECK_NAME_FAIRNESS_STATUS
    assert result.passed is True
    assert result.details["evaluations_considered"] == 0
    assert result.details["failing_metrics"] == []


def test_evaluate_governance_fails_when_a_fairness_metric_failed(app):
    model_version = _create_deployed_model_version("governance-failing-bank")
    db.session.add(
        FairnessEvaluation(
            tenant_id=model_version.model.tenant_id,
            model_version_id=model_version.id,
            protected_attribute="CODE_GENDER",
            metric_name="demographic_parity_difference",
            metric_value=0.25,
            threshold=0.10,
            passed=False,
        )
    )
    db.session.commit()

    result = evaluate_governance(model_version.id, decision_id="00000000-0000-0000-0000-000000000002")

    assert result.passed is False
    assert result.details["evaluations_considered"] == 1
    assert result.details["failing_metrics"][0]["metric_name"] == "demographic_parity_difference"


def test_evaluate_governance_passes_when_the_only_evaluation_passed(app):
    model_version = _create_deployed_model_version("governance-passing-bank")
    db.session.add(
        FairnessEvaluation(
            tenant_id=model_version.model.tenant_id,
            model_version_id=model_version.id,
            protected_attribute="CODE_GENDER",
            metric_name="demographic_parity_difference",
            metric_value=0.02,
            threshold=0.10,
            passed=True,
        )
    )
    db.session.commit()

    result = evaluate_governance(model_version.id, decision_id="00000000-0000-0000-0000-000000000003")

    assert result.passed is True
    assert result.details["evaluations_considered"] == 1


def test_maybe_open_review_case_returns_none_for_a_clean_approve():
    assert maybe_open_review_case("tenant-1", "decision-1", outcome="approve", governance_passed=True) is None


def test_maybe_open_review_case_opens_for_a_refer_outcome():
    review_case = maybe_open_review_case("tenant-1", "decision-1", outcome="refer", governance_passed=True)

    assert review_case is not None
    assert review_case.status == "open"
    assert review_case.reason == REASON_REFER_OUTCOME


def test_maybe_open_review_case_opens_for_a_governance_failure_even_on_approve():
    review_case = maybe_open_review_case("tenant-1", "decision-1", outcome="approve", governance_passed=False)

    assert review_case is not None
    assert review_case.reason == REASON_GOVERNANCE_FAILURE


def test_maybe_open_review_case_combines_both_reasons():
    review_case = maybe_open_review_case("tenant-1", "decision-1", outcome="refer", governance_passed=False)

    assert REASON_REFER_OUTCOME in review_case.reason
    assert REASON_GOVERNANCE_FAILURE in review_case.reason
