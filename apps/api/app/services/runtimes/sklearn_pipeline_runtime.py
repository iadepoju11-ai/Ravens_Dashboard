"""A ModelRuntime adapter for a scikit-learn Pipeline (preprocessing +
model) serialized via joblib — the artifact format produced by
apps/workers/ml/train.py (see docs/model_cards/). Works for any
sklearn-compatible classifier exposing predict_proba, which covers
XGBoost's and LightGBM's sklearn-API classifiers too, not just plain
scikit-learn estimators — no separate adapter needed for those.

Training and serving stay fully decoupled: this module never imports
apps/workers/ml code. It only needs the serialized artifact plus the
feature-name lists already stored on ModelVersion.metrics at registration
time (see app/api/v1/models.py) — no side-car metadata file to keep in
sync.
"""

from __future__ import annotations

import joblib
import pandas as pd
import shap

from app.services.model_runtime import FeatureContribution, ModelExplanation, ModelPrediction


class SklearnPipelineRuntime:
    def __init__(self, artifact_path: str, numeric_columns: list[str], categorical_columns: list[str]):
        self._pipeline = joblib.load(artifact_path)
        self._numeric_columns = numeric_columns
        self._categorical_columns = categorical_columns
        self._feature_columns = numeric_columns + categorical_columns
        self._preprocessor = self._pipeline.named_steps["preprocess"]
        self._model = self._pipeline.named_steps["model"]
        # TreeExplainer only supports tree-based models. An artifact whose
        # "model" step isn't tree-based (e.g. the logistic regression
        # baseline) would need a different explainer — not handled here.
        self._explainer = shap.TreeExplainer(self._model)

    def predict(self, features: dict) -> ModelPrediction:
        row = self._row_from_features(features)
        score = float(self._pipeline.predict_proba(row)[0][1])
        return ModelPrediction(score=score)

    def explain(self, features: dict, prediction: ModelPrediction) -> ModelExplanation:
        row = self._row_from_features(features)
        transformed = self._preprocessor.transform(row)
        if hasattr(transformed, "toarray"):
            transformed = transformed.toarray()

        shap_values = self._explainer.shap_values(transformed)[0]
        base_value = float(self._explainer.expected_value)
        feature_names = self._preprocessor.get_feature_names_out()

        contributions = [
            FeatureContribution(feature_name=str(name), value=float(value))
            for name, value in zip(feature_names, shap_values)
        ]
        return ModelExplanation(base_value=base_value, contributions=contributions, method="shap-tree")

    def _row_from_features(self, features: dict) -> pd.DataFrame:
        row = {column: features.get(column) for column in self._feature_columns}
        frame = pd.DataFrame([row])
        # A single-row frame built from a dict can infer the wrong dtype
        # (e.g. object) for a numeric column, which breaks the fitted
        # preprocessor's numeric imputer/scaler — force it explicitly.
        for column in self._numeric_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        return frame
