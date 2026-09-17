"""Computes the evaluation metrics required by CHECKLIST.md Phase 4's
reference model milestone: ROC-AUC, PR-AUC, precision/recall, Brier score,
a calibration curve, a confusion matrix, an illustrative expected-cost
figure, and subgroup performance.

Drift and out-of-time stability are deliberately NOT computed here: drift
needs a previously-deployed baseline to compare against (none exists yet
for this first reference model), and out-of-time stability needs a
genuine calendar date field neither Home Credit's application_train.csv
nor German Credit has. Both are reported as explicit "not applicable"
rather than silently omitted or faked.

Dataset-agnostic (target_column/protected_attribute_column are
parameters) so the same function serves both the Home Credit pipeline and
the German Credit benchmark comparison.
"""

from __future__ import annotations

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)

DECISION_THRESHOLD = 0.5
# An explicit, configurable, illustrative cost assumption — not a
# validated business cost model. A false negative (predicted repay,
# actually defaults) is assumed to cost 10x a false positive (predicted
# default, actually would have repaid).
COST_FALSE_NEGATIVE = 10.0
COST_FALSE_POSITIVE = 1.0


def evaluate(
    pipeline,
    eval_df,
    numeric_columns,
    categorical_columns,
    target_column: str,
    protected_attribute_column: str | None = None,
) -> dict:
    X = eval_df[numeric_columns + categorical_columns]
    y_true = eval_df[target_column].to_numpy()
    y_score = pipeline.predict_proba(X)[:, 1]
    y_pred = (y_score >= DECISION_THRESHOLD).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    expected_cost = (fn * COST_FALSE_NEGATIVE + fp * COST_FALSE_POSITIVE) / len(y_true)
    fraction_positive, mean_predicted = calibration_curve(y_true, y_score, n_bins=10, strategy="quantile")

    metrics = {
        "n_observations": int(len(y_true)),
        "positive_rate": float(y_true.mean()),
        "roc_auc": float(roc_auc_score(y_true, y_score)),
        "pr_auc": float(average_precision_score(y_true, y_score)),
        "brier_score": float(brier_score_loss(y_true, y_score)),
        "decision_threshold": DECISION_THRESHOLD,
        "precision_at_threshold": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall_at_threshold": float(recall_score(y_true, y_pred, zero_division=0)),
        "confusion_matrix_at_threshold": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
        "expected_cost_per_applicant": float(expected_cost),
        "cost_assumption": {
            "false_negative": COST_FALSE_NEGATIVE,
            "false_positive": COST_FALSE_POSITIVE,
            "note": "Illustrative, not a validated business cost model.",
        },
        "calibration_curve": {
            "mean_predicted": mean_predicted.tolist(),
            "fraction_positive": fraction_positive.tolist(),
        },
        "drift": "not_applicable_no_deployed_baseline_yet",
        "out_of_time_stability": "not_applicable_no_calendar_date_field_in_application_train",
    }

    if protected_attribute_column and protected_attribute_column in eval_df.columns:
        metrics["subgroup_performance"] = _subgroup_performance(eval_df, y_true, y_score, protected_attribute_column)

    return metrics


def _subgroup_performance(eval_df, y_true, y_score, protected_attribute_column: str) -> dict:
    subgroup_metrics = {}
    groups = eval_df[protected_attribute_column].to_numpy()
    for group in np.unique(groups):
        mask = groups == group
        if mask.sum() < 30:
            subgroup_metrics[str(group)] = {"n": int(mask.sum()), "note": "sample too small to report reliably"}
            continue
        subgroup_metrics[str(group)] = {
            "n": int(mask.sum()),
            "positive_rate": float(y_true[mask].mean()),
            "roc_auc": (
                float(roc_auc_score(y_true[mask], y_score[mask])) if len(np.unique(y_true[mask])) > 1 else None
            ),
        }
    return subgroup_metrics
