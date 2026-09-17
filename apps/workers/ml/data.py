"""Generic dataset loading/splitting helpers, parameterized by target
column and split fractions rather than hardcoded to one dataset — shared
by both the Home Credit pipeline (pipeline.py) and the German Credit
benchmark comparison (german_credit_pipeline.py).

Neither dataset has an absolute calendar date field usable for a genuine
out-of-time split (Home Credit's DAYS_* fields are relative offsets, not
sortable across applicants; German Credit has no date at all) —
stratified random splitting is used instead, and this is a documented
limitation, not silently presented as time-aware evaluation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def stratified_split(
    df: pd.DataFrame,
    target_column: str,
    train_fraction: float,
    validation_fraction: float,
    holdout_fraction: float,
    random_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    assert abs(train_fraction + validation_fraction + holdout_fraction - 1.0) < 1e-9

    train_df, remainder_df = train_test_split(
        df,
        train_size=train_fraction,
        stratify=df[target_column],
        random_state=random_seed,
    )
    relative_val_fraction = validation_fraction / (validation_fraction + holdout_fraction)
    val_df, holdout_df = train_test_split(
        remainder_df,
        train_size=relative_val_fraction,
        stratify=remainder_df[target_column],
        random_state=random_seed,
    )
    return train_df, val_df, holdout_df


def feature_columns(df: pd.DataFrame, excluded_columns: set[str]) -> tuple[list[str], list[str]]:
    """Numeric and categorical feature column names, excluding whatever
    id/target/protected-attribute columns the caller passes in."""
    feature_df = df.drop(columns=[c for c in excluded_columns if c in df.columns])

    numeric_columns = feature_df.select_dtypes(include="number").columns.tolist()
    categorical_columns = feature_df.select_dtypes(exclude="number").columns.tolist()
    return numeric_columns, categorical_columns
