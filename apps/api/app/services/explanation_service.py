"""Placeholder explanation logic.

Stands in for the SHAP-based explanation service (ERD Section 3.1) until
the model runtime and a real explainer are wired in. Produces a naive,
evenly-weighted feature attribution so the API contract and persistence
path can be validated end-to-end.
"""

from __future__ import annotations


def explain(features: dict, risk_score: float) -> tuple[float, dict]:
    numeric_features = {
        k: v for k, v in features.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
    }
    base_value = 0.5
    if not numeric_features:
        return base_value, {}

    delta = risk_score - base_value
    share = delta / len(numeric_features)
    attributions = {name: share for name in numeric_features}
    return base_value, attributions
