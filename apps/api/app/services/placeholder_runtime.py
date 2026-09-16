"""Stands in for the real model runtime (ERD Phase 4) until the reference
model milestone (Home Credit training pipeline, see
docs/architecture/data-strategy.md) lands. Implements `ModelRuntime` so
`ScoringService` can be exercised end-to-end today and swapped to a real
adapter later without any change to the service or API routes.
"""

from __future__ import annotations

from app.services.model_runtime import FeatureContribution, ModelExplanation, ModelPrediction


class PlaceholderRuntime:
    def predict(self, features: dict) -> ModelPrediction:
        numeric_values = [v for v in features.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if not numeric_values:
            return ModelPrediction(score=0.5)
        raw = sum(numeric_values) / len(numeric_values)
        return ModelPrediction(score=max(0.0, min(1.0, raw)))

    def explain(self, features: dict, prediction: ModelPrediction) -> ModelExplanation:
        numeric_features = {
            k: v for k, v in features.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        base_value = 0.5
        if not numeric_features:
            return ModelExplanation(base_value=base_value, contributions=[], method="placeholder")

        delta = prediction.score - base_value
        share = delta / len(numeric_features)
        contributions = [FeatureContribution(feature_name=name, value=share) for name in numeric_features]
        return ModelExplanation(base_value=base_value, contributions=contributions, method="placeholder")
