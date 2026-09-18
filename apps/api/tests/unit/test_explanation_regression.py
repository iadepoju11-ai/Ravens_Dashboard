"""Explanation regression tests: pins expected explanation output for a
fixed input against the real trained `credit-risk-v1` artifact, so a
future change to the preprocessing pipeline, the explainer, or the
reason-code logic that silently degrades explanation quality gets caught
by a test, not just noticed by a human looking at the UI.

This is deliberately narrower than tests/unit/test_sklearn_pipeline_runtime.py
(which checks explanations are *well-formed*) and
apps/workers/ml/explain.py's SHAP fidelity check (which checks
base_value + sum(shap_values) reconstructs the model's own margin output
on a *sample* of holdout data) -- this pins *specific* values for one
fixed input, so a regression shows up as a failing assertion with the old
vs. new number, not just "still well-formed" or "still faithful on
average".

Requires the real trained artifact (`make ml-train`); skipped otherwise,
same convention as test_sklearn_pipeline_runtime.py.
"""

import json
import math
import os
from pathlib import Path

import pytest

pytest.importorskip("pandas")
pytest.importorskip("xgboost")
pytest.importorskip("shap")

ARTIFACT_PATH = os.environ.get("CREDIT_RISK_V1_ARTIFACT_PATH", "/app/model_artifacts/credit-risk-v1.joblib")
METADATA_PATH = os.environ.get(
    "CREDIT_RISK_V1_METADATA_PATH", "/app/model_artifacts/credit-risk-v1-metadata.json"
)

if not Path(ARTIFACT_PATH).exists():
    pytest.skip(
        f"real trained artifact not found at {ARTIFACT_PATH} — run `make ml-train` first",
        allow_module_level=True,
    )

from app.services.reason_codes import generate_reason_codes  # noqa: E402
from app.services.runtimes.sklearn_pipeline_runtime import SklearnPipelineRuntime  # noqa: E402

# A fixed, representative input -- the same one test_sklearn_pipeline_runtime.py
# and test_model_registration.py already use for the real-artifact happy
# path, so this pins the exact case those tests already exercise.
FIXED_FEATURES = {"AMT_INCOME_TOTAL": 150000, "AMT_CREDIT": 500000, "NAME_CONTRACT_TYPE": "Cash loans"}

# Pinned against the credit-risk-v1 artifact trained 2026-09-18 (see
# docs/model_cards/credit-risk-v1.md). If this model is retrained and
# these assertions start failing, that's expected -- update the pinned
# values deliberately, with a note about why, rather than loosening the
# tolerance to make the diff go away.
EXPECTED_SCORE = 0.5988212823867798
EXPECTED_BASE_VALUE = 0.01389046385884285
EXPECTED_TOP_REASON_FEATURE = "numeric__AMT_GOODS_PRICE"
EXPECTED_TOP_REASON_CONTRIBUTION = 0.20041246712207794
TOLERANCE = 1e-6


@pytest.fixture()
def runtime() -> SklearnPipelineRuntime:
    features_metadata = json.loads(Path(METADATA_PATH).read_text())["features"]
    return SklearnPipelineRuntime(ARTIFACT_PATH, features_metadata["numeric"], features_metadata["categorical"])


def test_score_is_stable_for_a_fixed_input(runtime):
    prediction = runtime.predict(FIXED_FEATURES)

    assert prediction.score == pytest.approx(EXPECTED_SCORE, abs=TOLERANCE)


def test_explanation_base_value_is_stable_for_a_fixed_input(runtime):
    prediction = runtime.predict(FIXED_FEATURES)
    explanation = runtime.explain(FIXED_FEATURES, prediction)

    assert explanation.base_value == pytest.approx(EXPECTED_BASE_VALUE, abs=TOLERANCE)


def test_top_reason_code_is_stable_for_a_fixed_input(runtime):
    prediction = runtime.predict(FIXED_FEATURES)
    explanation = runtime.explain(FIXED_FEATURES, prediction)
    attributions = {c.feature_name: c.value for c in explanation.contributions}

    reasons = generate_reason_codes(attributions, top_n=1)

    assert reasons[0]["feature"] == EXPECTED_TOP_REASON_FEATURE
    assert reasons[0]["contribution"] == pytest.approx(EXPECTED_TOP_REASON_CONTRIBUTION, abs=TOLERANCE)


def test_explaining_the_same_input_twice_produces_identical_output(runtime):
    # Determinism, not just stability against a hardcoded pin -- catches
    # any accidental nondeterminism (an unseeded random step, a
    # dict-ordering dependency) introduced anywhere in the predict/explain
    # path, independent of whether the pinned values above are current.
    prediction_a = runtime.predict(FIXED_FEATURES)
    explanation_a = runtime.explain(FIXED_FEATURES, prediction_a)

    prediction_b = runtime.predict(FIXED_FEATURES)
    explanation_b = runtime.explain(FIXED_FEATURES, prediction_b)

    assert prediction_a.score == prediction_b.score
    assert explanation_a.base_value == explanation_b.base_value
    assert [c.value for c in explanation_a.contributions] == [c.value for c in explanation_b.contributions]


def test_explanation_reconstructs_the_models_own_prediction(runtime):
    # The adapter-level version of apps/workers/ml/explain.py's fidelity
    # check: proves SklearnPipelineRuntime's explain() -- not just the
    # raw shap library in isolation -- produces an explanation faithful
    # to what predict() actually returned, for this specific input.
    prediction = runtime.predict(FIXED_FEATURES)
    explanation = runtime.explain(FIXED_FEATURES, prediction)

    reconstructed_margin = explanation.base_value + sum(c.value for c in explanation.contributions)
    reconstructed_score = 1 / (1 + math.exp(-reconstructed_margin))

    assert reconstructed_score == pytest.approx(prediction.score, abs=1e-4)
