"""Entry point: python -m ml.relational_pipeline

Sprint E: does adding two of Home Credit's relational tables (credit
bureau history, this lender's own prior application history --
relational_features.py) improve on the application_train.csv-only
reference model (pipeline.py, credit-risk-v1)? Trains an XGBoost
comparison model on the merged feature set and reports its val/holdout
metrics next to a same-run application-only XGBoost baseline (same split,
same algorithm, same seed), so the delta reflects the relational features
alone, not train/split noise between separate runs.

Deliberately NOT registered as a ModelVersion and does NOT overwrite
credit-risk-v1.joblib -- this is a comparison, mirroring how
german_credit_pipeline.py treats German Credit as a benchmark, not a
candidate production model. Promoting the relational model to production
(if it wins) is a separate, deliberate step: re-running pipeline.py's own
data-quality checks against the expanded feature set, updating the model
card, and going through the same register/approve/deploy flow every other
model version does.

installments_payments.csv, POS_CASH_balance.csv, credit_card_balance.csv,
and bureau_balance.csv are out of scope for this comparison -- see
relational_features.py's module docstring.
"""

from __future__ import annotations

import json

from ml import relational_config as config
from ml.data import feature_columns, load_csv, stratified_split
from ml.evaluate import evaluate
from ml.leakage import run_leakage_checks
from ml.relational_features import (
    aggregate_bureau,
    aggregate_previous_application,
    merge_relational_features,
    relational_feature_columns,
)
from ml.train import save_pipeline, train_xgboost


def main() -> None:
    config.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    application_df = load_csv(config.APPLICATION_TRAIN_PATH)
    bureau_df = load_csv(config.BUREAU_PATH)
    previous_df = load_csv(config.PREVIOUS_APPLICATION_PATH)

    bureau_agg = aggregate_bureau(bureau_df)
    previous_agg = aggregate_previous_application(previous_df)
    merged_df = merge_relational_features(application_df, bureau_agg, previous_agg)

    print(
        f"application_train={len(application_df)} bureau_rows={len(bureau_df)} "
        f"previous_application_rows={len(previous_df)} merged={len(merged_df)}"
    )

    train_df, val_df, holdout_df = stratified_split(
        merged_df,
        config.TARGET_COLUMN,
        config.TRAIN_FRACTION,
        config.VALIDATION_FRACTION,
        config.HOLDOUT_FRACTION,
        config.RANDOM_SEED,
    )

    excluded = {config.ID_COLUMN, config.TARGET_COLUMN, config.PROTECTED_ATTRIBUTE_COLUMN}
    relational_numeric, relational_categorical = feature_columns(merged_df, excluded)
    application_only_numeric, application_only_categorical = feature_columns(application_df, excluded)

    print(
        f"application_only_features={len(application_only_numeric) + len(application_only_categorical)} "
        f"with_relational_features={len(relational_numeric) + len(relational_categorical)}"
    )

    leakage_report = run_leakage_checks(
        train_df, val_df, holdout_df, relational_numeric, config.TARGET_COLUMN, config.ID_COLUMN
    )
    config.LEAKAGE_REPORT_PATH.write_text(json.dumps(leakage_report, indent=2))
    if not leakage_report["passed"]:
        # Same hard stop as pipeline.py -- applicant ids overlapping
        # across splits would make every downstream metric unreliable.
        raise RuntimeError(
            f"Leakage check failed -- applicant ids overlap across splits: "
            f"{leakage_report['split_overlap']['overlap_counts']}"
        )

    relational_pipeline = train_xgboost(
        train_df, relational_numeric, relational_categorical, config.TARGET_COLUMN, config.RANDOM_SEED
    )
    application_only_pipeline = train_xgboost(
        train_df, application_only_numeric, application_only_categorical, config.TARGET_COLUMN, config.RANDOM_SEED
    )

    report = {
        "n_train": len(train_df),
        "n_validation": len(val_df),
        "n_holdout": len(holdout_df),
        "relational_feature_count": len(relational_feature_columns()),
        "application_only_validation": evaluate(
            application_only_pipeline,
            val_df,
            application_only_numeric,
            application_only_categorical,
            config.TARGET_COLUMN,
            config.PROTECTED_ATTRIBUTE_COLUMN,
        ),
        "application_only_holdout": evaluate(
            application_only_pipeline,
            holdout_df,
            application_only_numeric,
            application_only_categorical,
            config.TARGET_COLUMN,
            config.PROTECTED_ATTRIBUTE_COLUMN,
        ),
        "with_relational_features_validation": evaluate(
            relational_pipeline,
            val_df,
            relational_numeric,
            relational_categorical,
            config.TARGET_COLUMN,
            config.PROTECTED_ATTRIBUTE_COLUMN,
        ),
        "with_relational_features_holdout": evaluate(
            relational_pipeline,
            holdout_df,
            relational_numeric,
            relational_categorical,
            config.TARGET_COLUMN,
            config.PROTECTED_ATTRIBUTE_COLUMN,
        ),
    }

    save_pipeline(relational_pipeline, config.MODEL_PATH)
    metadata = {
        "model_name": "credit-risk-relational-comparison",
        "purpose": "Sprint E comparison only -- not registered as a ModelVersion, does not replace credit-risk-v1.",
        "algorithm": "xgboost.XGBClassifier",
        "tables_used": ["application_train.csv", "bureau.csv", "previous_application.csv"],
        "tables_deferred": [
            "bureau_balance.csv",
            "installments_payments.csv",
            "POS_CASH_balance.csv",
            "credit_card_balance.csv",
        ],
        "features": {"numeric": relational_numeric, "categorical": relational_categorical},
        "random_seed": config.RANDOM_SEED,
    }
    config.METADATA_PATH.write_text(json.dumps(metadata, indent=2))
    config.REPORT_PATH.write_text(json.dumps(report, indent=2))

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
