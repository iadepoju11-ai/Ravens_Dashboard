"""The interface between the scoring workflow and a concrete model.

`ScoringService` depends only on this Protocol — it never imports a
specific model library. Swapping the placeholder arithmetic in
`PlaceholderRuntime` for a real trained model (ERD Phase 4's reference
model milestone) means writing a new class that satisfies this Protocol
and wiring it in; nothing in `ScoringService` or the API routes changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelPrediction:
    # Calibrated probability in [0, 1] that ScoringService thresholds into
    # an outcome. Model score, not the approval decision itself — see
    # CLAUDE.md: "model score ≠ approval decision ≠ policy outcome".
    score: float


@dataclass(frozen=True)
class FeatureContribution:
    feature_name: str
    value: float


@dataclass(frozen=True)
class ModelExplanation:
    base_value: float
    contributions: list[FeatureContribution]
    # e.g. "shap-tree", "shap-kernel", "placeholder" — persisted onto
    # Explanation.method so every explanation is traceable to how it was
    # produced.
    method: str


class ModelRuntime(Protocol):
    def predict(self, features: dict) -> ModelPrediction: ...

    def explain(self, features: dict, prediction: ModelPrediction) -> ModelExplanation: ...
