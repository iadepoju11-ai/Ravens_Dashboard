import numpy as np
import pandas as pd
import pytest

from ml.evaluate import evaluate
from ml.explain import run_shap_fidelity_check
from ml.train import train_lightgbm, train_logistic_regression, train_xgboost

NUMERIC_COLUMNS = ["AMT_INCOME_TOTAL", "AMT_CREDIT"]
CATEGORICAL_COLUMNS = ["NAME_CONTRACT_TYPE"]
TARGET_COLUMN = "TARGET"
RANDOM_SEED = 42


@pytest.fixture()
def toy_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 200
    return pd.DataFrame(
        {
            "AMT_INCOME_TOTAL": rng.normal(50000, 10000, n),
            "AMT_CREDIT": rng.normal(20000, 5000, n),
            "NAME_CONTRACT_TYPE": rng.choice(["Cash loans", "Revolving loans"], n),
            "TARGET": rng.integers(0, 2, n),
        }
    )


def test_train_and_evaluate_logistic_regression(toy_df):
    pipeline = train_logistic_regression(
        toy_df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN, RANDOM_SEED
    )
    metrics = evaluate(pipeline, toy_df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN)

    assert metrics["n_observations"] == len(toy_df)
    assert 0.0 <= metrics["roc_auc"] <= 1.0
    assert 0.0 <= metrics["pr_auc"] <= 1.0
    assert metrics["drift"] == "not_applicable_no_deployed_baseline_yet"


def test_train_and_evaluate_xgboost(toy_df):
    pipeline = train_xgboost(toy_df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN, RANDOM_SEED)
    metrics = evaluate(pipeline, toy_df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN)

    assert 0.0 <= metrics["roc_auc"] <= 1.0
    confusion = metrics["confusion_matrix_at_threshold"]
    assert sum(confusion.values()) == len(toy_df)


def test_train_and_evaluate_lightgbm(toy_df):
    pipeline = train_lightgbm(toy_df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN, RANDOM_SEED)
    metrics = evaluate(pipeline, toy_df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN)

    assert 0.0 <= metrics["roc_auc"] <= 1.0


def test_shap_fidelity_check_passes_on_a_freshly_trained_model(toy_df):
    pipeline = train_xgboost(toy_df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN, RANDOM_SEED)
    result = run_shap_fidelity_check(pipeline, toy_df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS)

    assert result["passed"] is True
    assert result["n_sampled"] == len(toy_df)


def test_evaluate_reports_subgroup_performance_when_column_given(toy_df):
    toy_df = toy_df.assign(sex=np.random.default_rng(1).choice(["a", "b"], len(toy_df)))
    pipeline = train_xgboost(toy_df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN, RANDOM_SEED)

    metrics = evaluate(
        pipeline, toy_df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN, protected_attribute_column="sex"
    )

    assert "subgroup_performance" in metrics
    assert set(metrics["subgroup_performance"]) == {"a", "b"}
