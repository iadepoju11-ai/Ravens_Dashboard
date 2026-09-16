"""Load the Home Credit application table and split it for training.

No genuine out-of-time split is possible from application_train.csv alone
(see config.py's note on DAYS_* fields) — stratified random splitting by
TARGET is used instead, and this is a documented limitation, not silently
presented as time-aware evaluation.
"""

from __future__ import annotations

import pandas as pd
from sklearn.model_selection import train_test_split

from ml.config import (
    APPLICATION_TRAIN_PATH,
    HOLDOUT_FRACTION,
    ID_COLUMN,
    PROTECTED_ATTRIBUTE_COLUMN,
    RANDOM_SEED,
    TARGET_COLUMN,
    TRAIN_FRACTION,
    VALIDATION_FRACTION,
)


def load_application_train() -> pd.DataFrame:
    return pd.read_csv(APPLICATION_TRAIN_PATH)


def split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    assert abs(TRAIN_FRACTION + VALIDATION_FRACTION + HOLDOUT_FRACTION - 1.0) < 1e-9

    train_df, remainder_df = train_test_split(
        df,
        train_size=TRAIN_FRACTION,
        stratify=df[TARGET_COLUMN],
        random_state=RANDOM_SEED,
    )
    relative_val_fraction = VALIDATION_FRACTION / (VALIDATION_FRACTION + HOLDOUT_FRACTION)
    val_df, holdout_df = train_test_split(
        remainder_df,
        train_size=relative_val_fraction,
        stratify=remainder_df[TARGET_COLUMN],
        random_state=RANDOM_SEED,
    )
    return train_df, val_df, holdout_df


def feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Numeric and categorical feature column names — excludes the id,
    target, and protected-attribute columns (see config.py)."""
    excluded = {ID_COLUMN, TARGET_COLUMN, PROTECTED_ATTRIBUTE_COLUMN}
    feature_df = df.drop(columns=[c for c in excluded if c in df.columns])

    numeric_columns = feature_df.select_dtypes(include="number").columns.tolist()
    categorical_columns = feature_df.select_dtypes(exclude="number").columns.tolist()
    return numeric_columns, categorical_columns
