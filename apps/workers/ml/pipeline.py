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
from ml.data import feature_columns, load_csv, stratified_split
from ml.data_quality import profile as profile_data_quality
from ml.evaluate import evaluate
from ml.explain import run_shap_fidelity_check
from ml.fairness import evaluate_fairness
from ml.leakage import run_leakage_checks
from ml.train import save_pipeline, train_logistic_regression, train_xgboost


def main() -> None:
    config.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_csv(config.APPLICATION_TRAIN_PATH)

    data_quality_report = profile_data_quality(df, config.TARGET_COLUMN)
    config.DATA_QUALITY_REPORT_PATH.write_text(json.dumps(data_quality_report, indent=2))
    print(
        f"data quality: n_rows={data_quality_report['n_rows']} "
        f"n_duplicate_rows={data_quality_report['n_duplicate_rows']} "
        f"high_missingness_columns={len(data_quality_report['flags']['high_missingness']['columns'])}"
    )

    train_df, val_df, holdout_df = stratified_split(
        df,
        config.TARGET_COLUMN,
        config.TRAIN_FRACTION,
        config.VALIDATION_FRACTION,
        config.HOLDOUT_FRACTION,
        config.RANDOM_SEED,
    )
    excluded = {config.ID_COLUMN, config.TARGET_COLUMN, config.PROTECTED_ATTRIBUTE_COLUMN}
    numeric_columns, categorical_columns = feature_columns(df, excluded)

    print(
        f"train={len(train_df)} val={len(val_df)} holdout={len(holdout_df)} "
        f"numeric_features={len(numeric_columns)} categorical_features={len(categorical_columns)}"
    )

    leakage_report = run_leakage_checks(
        train_df, val_df, holdout_df, numeric_columns, config.TARGET_COLUMN, config.ID_COLUMN
    )
    config.LEAKAGE_REPORT_PATH.write_text(json.dumps(leakage_report, indent=2))
    if not leakage_report["passed"]:
        # A hard stop, not a warning: train_id/val_id/holdout_id overlap
        # means the model would be evaluated (in part) on data it was
        # trained on -- every downstream metric would be unreliable.
        raise RuntimeError(
            f"Leakage check failed -- applicant ids overlap across splits: "
            f"{leakage_report['split_overlap']['overlap_counts']}"
        )
    if leakage_report["target_correlation_scan"]["flagged_for_review"] or leakage_report["suspicious_column_names"]:
        print(
            "leakage scan flagged columns for manual review (not a hard failure): "
            f"{leakage_report['target_correlation_scan']['flagged_for_review']} "
            f"{leakage_report['suspicious_column_names']}"
        )

    logistic_pipeline = train_logistic_regression(
        train_df, numeric_columns, categorical_columns, config.TARGET_COLUMN, config.RANDOM_SEED
    )
    xgboost_pipeline = train_xgboost(
        train_df, numeric_columns, categorical_columns, config.TARGET_COLUMN, config.RANDOM_SEED
    )

    logistic_val_metrics = evaluate(
        logistic_pipeline, val_df, numeric_columns, categorical_columns,
        config.TARGET_COLUMN, config.PROTECTED_ATTRIBUTE_COLUMN,
    )
    xgboost_val_metrics = evaluate(
        xgboost_pipeline, val_df, numeric_columns, categorical_columns,
        config.TARGET_COLUMN, config.PROTECTED_ATTRIBUTE_COLUMN,
    )
    xgboost_holdout_metrics = evaluate(
        xgboost_pipeline, holdout_df, numeric_columns, categorical_columns,
        config.TARGET_COLUMN, config.PROTECTED_ATTRIBUTE_COLUMN,
    )

    shap_sample = holdout_df.sample(n=min(500, len(holdout_df)), random_state=config.RANDOM_SEED)
    shap_check = run_shap_fidelity_check(xgboost_pipeline, shap_sample, numeric_columns, categorical_columns)

    fairness_report = evaluate_fairness(
        xgboost_pipeline, holdout_df, numeric_columns, categorical_columns,
        config.TARGET_COLUMN, config.PROTECTED_ATTRIBUTE_COLUMN,
    )
    config.FAIRNESS_REPORT_PATH.write_text(json.dumps(fairness_report, indent=2))
    print(
        "fairness (holdout): "
        + ", ".join(f"{m['metric_name']}={m['metric_value']}" for m in fairness_report["metrics"])
    )

    save_pipeline(xgboost_pipeline, config.MODEL_PATH)
    save_pipeline(logistic_pipeline, config.BASELINE_MODEL_PATH)

    metadata = {
        "model_name": "credit-risk",
        "model_version": "1.0.0-dev",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "xgboost.XGBClassifier (comparison winner over logistic regression baseline)",
        "explainer": "shap-tree",
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
        "fairness_holdout": fairness_report,
    }

    config.METADATA_PATH.write_text(json.dumps(metadata, indent=2))
    config.REPORT_PATH.write_text(json.dumps(report, indent=2))

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
