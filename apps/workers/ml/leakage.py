"""Automated leakage checks, replacing the manual paragraph that used to
be the whole of docs/model_cards/credit-risk-v1.md's "Leakage review"
section with actual, regenerated-every-run checks.

Three checks, of two different kinds:

- `check_split_overlap` is a hard pass/fail: if the same applicant id
  appears in more than one of train/val/holdout, that's unambiguously a
  bug (data.py::stratified_split is a deterministic partition and should
  never produce this) -- this check exists to catch a future regression
  in the splitting logic automatically, not because it's expected to fail.
- `scan_target_correlation` and `scan_suspicious_column_names` are
  advisory: a real, strongly predictive feature can legitimately have
  high correlation with the target without being leaked (that's what a
  good feature looks like), so these are reported for a human to review,
  not treated as failures on their own.

Dataset-agnostic (all inputs are parameters) so the same functions serve
both the Home Credit pipeline and the German Credit benchmark comparison.
"""

from __future__ import annotations

import pandas as pd

CORRELATION_REVIEW_THRESHOLD = 0.95

# Column-name substrings that would suggest a field was recorded *after*
# a credit decision was made (and so wouldn't have been available at
# scoring time) -- a heuristic prompt for human review, not a definitive
# leakage determination on its own.
SUSPICIOUS_NAME_SUBSTRINGS = (
    "DECISION",
    "APPROVED",
    "APPROVAL",
    "OUTCOME",
    "STATUS_AFTER",
    "POST_DECISION",
)


def check_split_overlap(
    train_df: pd.DataFrame, val_df: pd.DataFrame, holdout_df: pd.DataFrame, id_column: str
) -> dict:
    train_ids = set(train_df[id_column])
    val_ids = set(val_df[id_column])
    holdout_ids = set(holdout_df[id_column])

    overlaps = {
        "train_val": sorted(train_ids & val_ids)[:10],
        "train_holdout": sorted(train_ids & holdout_ids)[:10],
        "val_holdout": sorted(val_ids & holdout_ids)[:10],
    }
    overlap_counts = {
        "train_val": len(train_ids & val_ids),
        "train_holdout": len(train_ids & holdout_ids),
        "val_holdout": len(val_ids & holdout_ids),
    }

    return {
        "passed": all(count == 0 for count in overlap_counts.values()),
        "overlap_counts": overlap_counts,
        # A sample of the actual overlapping ids (capped at 10), not just
        # the count, so a real failure is immediately actionable.
        "overlap_id_samples": overlaps,
    }


def scan_target_correlation(
    df: pd.DataFrame, numeric_columns: list[str], target_column: str, threshold: float = CORRELATION_REVIEW_THRESHOLD
) -> dict:
    correlations = df[numeric_columns].corrwith(df[target_column]).abs()
    flagged = correlations[correlations > threshold].sort_values(ascending=False)

    return {
        "threshold": threshold,
        "flagged_for_review": {column: float(value) for column, value in flagged.items()},
    }


def scan_suspicious_column_names(columns: list[str], target_column: str) -> list[str]:
    return [
        column
        for column in columns
        if column != target_column and any(substring in column.upper() for substring in SUSPICIOUS_NAME_SUBSTRINGS)
    ]


def run_leakage_checks(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    holdout_df: pd.DataFrame,
    numeric_columns: list[str],
    target_column: str,
    id_column: str,
) -> dict:
    split_overlap = check_split_overlap(train_df, val_df, holdout_df, id_column)
    target_correlation = scan_target_correlation(train_df, numeric_columns, target_column)
    suspicious_names = scan_suspicious_column_names(list(train_df.columns), target_column)

    return {
        # Only the hard check determines this -- the two scans below are
        # advisory and never flip this to False on their own (see module
        # docstring).
        "passed": split_overlap["passed"],
        "split_overlap": split_overlap,
        "target_correlation_scan": target_correlation,
        "suspicious_column_names": suspicious_names,
    }
