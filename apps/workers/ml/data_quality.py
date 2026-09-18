"""Generates a real data-quality report artifact instead of leaving
missingness/cardinality observations as prose in the model card (see
docs/model_cards/credit-risk-v1.md's "Missing data" note, which this
report now backs with actual numbers, regenerated on every training run
rather than hand-maintained).

Dataset-agnostic (target_column is optional) so the same function serves
both the Home Credit pipeline and the German Credit benchmark comparison.
"""

from __future__ import annotations

import pandas as pd

# Flags, not failures -- a data-quality report should surface what a
# human should look at, not silently drop columns or block training.
HIGH_MISSINGNESS_THRESHOLD = 0.30
HIGH_CARDINALITY_THRESHOLD = 50


def profile(df: pd.DataFrame, target_column: str | None = None) -> dict:
    n_rows = len(df)
    columns = {}
    high_missingness = []
    constant_columns = []
    high_cardinality_columns = []

    for column in df.columns:
        series = df[column]
        missing_count = int(series.isna().sum())
        missing_fraction = missing_count / n_rows if n_rows else 0.0
        n_unique = int(series.nunique(dropna=True))

        column_report: dict = {
            "dtype": str(series.dtype),
            "missing_count": missing_count,
            "missing_fraction": missing_fraction,
            "n_unique": n_unique,
        }

        if pd.api.types.is_numeric_dtype(series):
            non_null = series.dropna()
            column_report["min"] = float(non_null.min()) if len(non_null) else None
            column_report["max"] = float(non_null.max()) if len(non_null) else None
            column_report["mean"] = float(non_null.mean()) if len(non_null) else None
            column_report["std"] = float(non_null.std()) if len(non_null) > 1 else None
        else:
            mode = series.mode(dropna=True)
            if len(mode):
                column_report["top_value"] = str(mode.iloc[0])
                column_report["top_value_fraction"] = float((series == mode.iloc[0]).mean())
            if n_unique > HIGH_CARDINALITY_THRESHOLD:
                high_cardinality_columns.append(column)

        if missing_fraction > HIGH_MISSINGNESS_THRESHOLD:
            high_missingness.append(column)
        if n_unique <= 1:
            constant_columns.append(column)

        columns[column] = column_report

    report = {
        "n_rows": n_rows,
        "n_columns": len(df.columns),
        "n_duplicate_rows": int(df.duplicated().sum()),
        "columns": columns,
        "flags": {
            "high_missingness": {
                "threshold": HIGH_MISSINGNESS_THRESHOLD,
                "columns": high_missingness,
            },
            "constant_columns": constant_columns,
            "high_cardinality_categorical": {
                "threshold": HIGH_CARDINALITY_THRESHOLD,
                "columns": high_cardinality_columns,
            },
        },
    }

    if target_column and target_column in df.columns:
        target = df[target_column]
        report["target"] = {
            "column": target_column,
            "n_missing": int(target.isna().sum()),
            "class_counts": {str(k): int(v) for k, v in target.value_counts(dropna=True).items()},
            "positive_rate": float(target.mean()) if pd.api.types.is_numeric_dtype(target) else None,
        }

    return report
