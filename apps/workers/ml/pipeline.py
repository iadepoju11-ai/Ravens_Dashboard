"""Entry point: python -m ml.pipeline

Loads application_train.csv, splits it, trains the baseline and
comparison models, evaluates both on the validation split (plus a final
holdout check for the comparison model), runs the SHAP fidelity check,
and writes the artifact + metadata + validation report that
docs/model_cards/credit-risk-v1.md documents.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ml import config
from ml.data import feature_columns, load_application_train, split
from ml.evaluate import evaluate
from ml.explain import run_shap_fidelity_check
from ml.train import save_pipeline, train_logistic_regression, train_xgboost


def main() -> None:
    config.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_application_train()
    train_df, val_df, holdout_df = split(df)
    numeric_columns, categorical_columns = feature_columns(df)

    print(
        f"train={len(train_df)} val={len(val_df)} holdout={len(holdout_df)} "
        f"numeric_features={len(numeric_columns)} categorical_features={len(categorical_columns)}"
    )

    logistic_pipeline = train_logistic_regression(train_df, numeric_columns, categorical_columns)
    xgboost_pipeline = train_xgboost(train_df, numeric_columns, categorical_columns)

    logistic_val_metrics = evaluate(logistic_pipeline, val_df, numeric_columns, categorical_columns)
    xgboost_val_metrics = evaluate(xgboost_pipeline, val_df, numeric_columns, categorical_columns)
    xgboost_holdout_metrics = evaluate(xgboost_pipeline, holdout_df, numeric_columns, categorical_columns)

    shap_sample = holdout_df.sample(n=min(500, len(holdout_df)), random_state=config.RANDOM_SEED)
    shap_check = run_shap_fidelity_check(xgboost_pipeline, shap_sample, numeric_columns, categorical_columns)

    save_pipeline(xgboost_pipeline, config.MODEL_PATH)
    save_pipeline(logistic_pipeline, config.BASELINE_MODEL_PATH)

    metadata = {
        "model_name": "credit-risk",
        "model_version": "1.0.0-dev",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "xgboost.XGBClassifier (comparison winner over logistic regression baseline)",
        "dataset": {
            "name": "home-credit-application",
            "version": "kaggle-home-credit-default-risk",
            "source_file": config.APPLICATION_TRAIN_PATH.name,
            "n_rows": int(len(df)),
        },
        "features": {
            "numeric": numeric_columns,
            "categorical": categorical_columns,
            "excluded": [config.ID_COLUMN, config.TARGET_COLUMN, config.PROTECTED_ATTRIBUTE_COLUMN],
        },
        "random_seed": config.RANDOM_SEED,
    }

    report = {
        "logistic_regression_validation": logistic_val_metrics,
        "xgboost_validation": xgboost_val_metrics,
        "xgboost_holdout": xgboost_holdout_metrics,
        "shap_fidelity_check": shap_check,
    }

    config.METADATA_PATH.write_text(json.dumps(metadata, indent=2))
    config.REPORT_PATH.write_text(json.dumps(report, indent=2))

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
