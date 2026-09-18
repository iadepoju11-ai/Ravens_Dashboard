"""Real Fairlearn-based fairness evaluation, computed against the reference
model's own eval split by the protected attribute already excluded from
its features (CODE_GENDER, see config.py — it is tracked for evaluation
only, never fed to the model).

Two standard group-fairness metrics are computed at the model's fixed
decision threshold (0.5, see evaluate.py): demographic parity difference
(gap in positive-prediction rate between groups) and equalized odds
difference (gap in true-positive/false-positive rates between groups).
Each is checked against a configurable threshold and reported with an
explicit passed/failed verdict.

This is a statistical check against one configured metric and threshold —
not a legal or ethical fairness verdict (see CLAUDE.md: fairness
monitoring, legal compliance, and policy review are different things).
Groups smaller than MIN_GROUP_SIZE are excluded from the comparison
(e.g. Home Credit's CODE_GENDER has a handful of "XNA" rows) and reported
separately rather than silently folded in or silently dropped.
"""

from __future__ import annotations

import pandas as pd
from fairlearn.metrics import demographic_parity_difference, equalized_odds_difference

DECISION_THRESHOLD = 0.5
MIN_GROUP_SIZE = 30
DEMOGRAPHIC_PARITY_THRESHOLD = 0.10
EQUALIZED_ODDS_THRESHOLD = 0.10


def evaluate_fairness(
    pipeline,
    eval_df: pd.DataFrame,
    numeric_columns: list[str],
    categorical_columns: list[str],
    target_column: str,
    protected_attribute_column: str,
) -> dict:
    X = eval_df[numeric_columns + categorical_columns]
    y_true_full = eval_df[target_column].to_numpy()
    sensitive_full = eval_df[protected_attribute_column].astype(str).to_numpy()
    y_score_full = pipeline.predict_proba(X)[:, 1]
    y_pred_full = (y_score_full >= DECISION_THRESHOLD).astype(int)

    group_sizes = pd.Series(sensitive_full).value_counts()
    included_groups = sorted(group_sizes[group_sizes >= MIN_GROUP_SIZE].index.tolist())
    excluded_groups = sorted(group_sizes[group_sizes < MIN_GROUP_SIZE].index.tolist())

    mask = pd.Series(sensitive_full).isin(included_groups).to_numpy()
    y_true, y_pred, sensitive = y_true_full[mask], y_pred_full[mask], sensitive_full[mask]

    result = {
        "protected_attribute": protected_attribute_column,
        "decision_threshold": DECISION_THRESHOLD,
        "min_group_size": MIN_GROUP_SIZE,
        "groups_included": included_groups,
        "groups_excluded_too_small": {g: int(group_sizes[g]) for g in excluded_groups},
        "n_included": int(mask.sum()),
        "metrics": [],
    }

    if len(included_groups) < 2:
        result["metrics"].append(
            {
                "protected_attribute": protected_attribute_column,
                "metric_name": "not_applicable",
                "metric_value": None,
                "threshold": None,
                "passed": None,
                "note": "fewer than two groups met min_group_size — cannot compare",
            }
        )
        return result

    dp_difference = float(demographic_parity_difference(y_true, y_pred, sensitive_features=sensitive))
    eo_difference = float(equalized_odds_difference(y_true, y_pred, sensitive_features=sensitive))

    result["metrics"] = [
        {
            "protected_attribute": protected_attribute_column,
            "metric_name": "demographic_parity_difference",
            "metric_value": dp_difference,
            "threshold": DEMOGRAPHIC_PARITY_THRESHOLD,
            "passed": dp_difference <= DEMOGRAPHIC_PARITY_THRESHOLD,
        },
        {
            "protected_attribute": protected_attribute_column,
            "metric_name": "equalized_odds_difference",
            "metric_value": eo_difference,
            "threshold": EQUALIZED_ODDS_THRESHOLD,
            "passed": eo_difference <= EQUALIZED_ODDS_THRESHOLD,
        },
    ]
    return result
