"""Placeholder risk-scoring logic.

Stands in for the real model runtime (ERD Section 3.1, "Model service" —
loading an approved model artifact and running inference) until the model
registry and runtime are built. Exists so the decision workflow
(score -> explain -> govern -> audit) can be exercised end-to-end.
"""

from __future__ import annotations


def score(features: dict) -> float:
    numeric_values = [v for v in features.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not numeric_values:
        return 0.5
    raw = sum(numeric_values) / len(numeric_values)
    return max(0.0, min(1.0, raw))


def decide_outcome(risk_score: float) -> str:
    if risk_score < 0.33:
        return "approve"
    if risk_score < 0.66:
        return "refer"
    return "decline"
