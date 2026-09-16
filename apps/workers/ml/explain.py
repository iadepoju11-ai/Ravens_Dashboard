"""SHAP explanation fidelity check (CHECKLIST.md Phase 4: "SHAP
explanation test") against the trained XGBoost model. Verifies that, for a
sample of applicants, base_value + sum(shap_values) reconstructs the
model's own raw margin output within a small numerical tolerance — i.e.
the explanation is faithful to what the model actually predicted, not
just plausible-looking numbers.
"""

from __future__ import annotations

import numpy as np
import shap


def run_shap_fidelity_check(
    pipeline, sample_df, numeric_columns, categorical_columns, tolerance: float = 1e-3
) -> dict:
    preprocessor = pipeline.named_steps["preprocess"]
    model = pipeline.named_steps["model"]

    X_raw = sample_df[numeric_columns + categorical_columns]
    X_transformed = preprocessor.transform(X_raw)
    if hasattr(X_transformed, "toarray"):
        X_transformed = X_transformed.toarray()

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_transformed)
    base_value = explainer.expected_value

    raw_margin = model.predict(X_transformed, output_margin=True)
    reconstructed = base_value + shap_values.sum(axis=1)
    max_abs_error = float(np.max(np.abs(reconstructed - raw_margin)))

    return {
        "n_sampled": int(X_transformed.shape[0]),
        "max_reconstruction_error": max_abs_error,
        "tolerance": tolerance,
        "passed": max_abs_error <= tolerance,
    }
