"""Exercises the real ModelRuntime adapter against the actual trained
artifact from docs/model_cards/credit-risk-v1.md — not a toy/synthetic
model. Requires the ML dependencies (pandas/xgboost/shap) and the
artifact itself (`make ml-train`, or point CREDIT_RISK_V1_ARTIFACT_PATH /
CREDIT_RISK_V1_METADATA_PATH elsewhere); skipped otherwise, e.g. in the
local SQLite-only venv.
"""

import json
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
BASELINE_ARTIFACT_PATH = os.environ.get(
    "CREDIT_RISK_V1_BASELINE_ARTIFACT_PATH", "/app/model_artifacts/credit-risk-v1-baseline-logreg.joblib"
)

if not Path(ARTIFACT_PATH).exists():
    pytest.skip(
        f"real trained artifact not found at {ARTIFACT_PATH} — run `make ml-train` first",
        allow_module_level=True,
    )

from app.services.runtimes.sklearn_pipeline_runtime import (  # noqa: E402
    SklearnPipelineRuntime,
    UnsupportedModelTypeError,
)


def _load_feature_metadata() -> dict:
    metadata = json.loads(Path(METADATA_PATH).read_text())
    return metadata["features"]


def test_predict_returns_a_probability():
    features_metadata = _load_feature_metadata()
    runtime = SklearnPipelineRuntime(
        ARTIFACT_PATH, features_metadata["numeric"], features_metadata["categorical"]
    )

    prediction = runtime.predict(
        {"AMT_INCOME_TOTAL": 150000, "AMT_CREDIT": 500000, "NAME_CONTRACT_TYPE": "Cash loans"}
    )

    assert 0.0 <= prediction.score <= 1.0


def test_predict_handles_a_mostly_empty_feature_dict():
    # Exercises the imputer path for every unset column, not just a
    # happy path where every feature is populated.
    features_metadata = _load_feature_metadata()
    runtime = SklearnPipelineRuntime(
        ARTIFACT_PATH, features_metadata["numeric"], features_metadata["categorical"]
    )

    prediction = runtime.predict({})

    assert 0.0 <= prediction.score <= 1.0


def test_explain_returns_shap_tree_contributions():
    features_metadata = _load_feature_metadata()
    runtime = SklearnPipelineRuntime(
        ARTIFACT_PATH, features_metadata["numeric"], features_metadata["categorical"]
    )
    features = {"AMT_INCOME_TOTAL": 150000, "AMT_CREDIT": 500000, "NAME_CONTRACT_TYPE": "Cash loans"}
    prediction = runtime.predict(features)

    explanation = runtime.explain(features, prediction)

    assert explanation.method == "shap-tree"
    assert len(explanation.contributions) > 0
    assert all(isinstance(c.value, float) for c in explanation.contributions)


@pytest.mark.skipif(
    not Path(BASELINE_ARTIFACT_PATH).exists(),
    reason=f"baseline artifact not found at {BASELINE_ARTIFACT_PATH} — run `make ml-train` first",
)
def test_a_non_tree_model_fails_fast_with_a_clear_error():
    # The logistic regression baseline this project also trains isn't
    # tree-based — shap.TreeExplainer can't explain it. This must fail
    # loudly and clearly at construction, not crash deep inside shap's
    # internals or silently produce a placeholder-like result.
    features_metadata = _load_feature_metadata()

    with pytest.raises(UnsupportedModelTypeError, match="LogisticRegression"):
        SklearnPipelineRuntime(
            BASELINE_ARTIFACT_PATH, features_metadata["numeric"], features_metadata["categorical"]
        )
