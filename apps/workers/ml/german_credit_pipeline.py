"""Entry point: python -m ml.german_credit_pipeline

Trains the same baseline-vs-comparison approach used for Home Credit
(pipeline.py) against German Credit — kept as a benchmark comparison
point against the academic prototype's own dataset
(docs/architecture/data-strategy.md Phase A), not a candidate production
model in its own right; results are not registered as a Model/ModelVersion.

Also trains a THIRD algorithm, LightGBM, alongside logistic regression and
XGBoost — CHECKLIST.md previously flagged "no second [boosting] library
proven" as a gap for the ModelRuntime adapter (apps/api), which only ever
calls predict_proba() and was asserted, not demonstrated, to work for any
sklearn-API classifier. This gives that assertion actual evidence.
"""

from __future__ import annotations

import json

import pandas as pd

from ml import german_credit_config as config
from ml.data import feature_columns, stratified_split
from ml.evaluate import evaluate
from ml.train import train_lightgbm, train_logistic_regression, train_xgboost


def _load_and_recode() -> pd.DataFrame:
    df = pd.read_csv(config.DATA_PATH)
    # Recode so 1 consistently means elevated credit risk (bad credit),
    # matching Home Credit's TARGET polarity — see german_credit_config.py.
    df[config.TARGET_COLUMN] = (df[config.TARGET_COLUMN] != config.RAW_TARGET_GOOD_CREDIT_VALUE).astype(int)
    return df


def main() -> None:
    config.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    df = _load_and_recode()
    train_df, val_df, holdout_df = stratified_split(
        df,
        config.TARGET_COLUMN,
        config.TRAIN_FRACTION,
        config.VALIDATION_FRACTION,
        config.HOLDOUT_FRACTION,
        config.RANDOM_SEED,
    )
    excluded = {config.TARGET_COLUMN, *config.PROTECTED_ATTRIBUTE_COLUMNS}
    numeric_columns, categorical_columns = feature_columns(df, excluded)

    print(
        f"train={len(train_df)} val={len(val_df)} holdout={len(holdout_df)} "
        f"numeric_features={len(numeric_columns)} categorical_features={len(categorical_columns)}"
    )

    models = {
        "logistic_regression": train_logistic_regression(
            train_df, numeric_columns, categorical_columns, config.TARGET_COLUMN, config.RANDOM_SEED
        ),
        "xgboost": train_xgboost(
            train_df, numeric_columns, categorical_columns, config.TARGET_COLUMN, config.RANDOM_SEED
        ),
        "lightgbm": train_lightgbm(
            train_df, numeric_columns, categorical_columns, config.TARGET_COLUMN, config.RANDOM_SEED
        ),
    }

    report = {"n_rows": int(len(df)), "n_train": len(train_df), "n_validation": len(val_df), "n_holdout": len(holdout_df)}
    for name, pipeline in models.items():
        report[f"{name}_validation"] = evaluate(
            pipeline, val_df, numeric_columns, categorical_columns, config.TARGET_COLUMN, config.SUBGROUP_COLUMN
        )
        report[f"{name}_holdout"] = evaluate(
            pipeline, holdout_df, numeric_columns, categorical_columns, config.TARGET_COLUMN, config.SUBGROUP_COLUMN
        )

    config.REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
