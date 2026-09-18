import numpy as np
import pandas as pd

from ml.fairness import DEMOGRAPHIC_PARITY_THRESHOLD, EQUALIZED_ODDS_THRESHOLD, MIN_GROUP_SIZE, evaluate_fairness
from ml.train import train_xgboost

NUMERIC_COLUMNS = ["AMT_INCOME_TOTAL", "AMT_CREDIT"]
CATEGORICAL_COLUMNS = ["NAME_CONTRACT_TYPE"]
TARGET_COLUMN = "TARGET"
PROTECTED_ATTRIBUTE_COLUMN = "GROUP"
RANDOM_SEED = 42


def _df(n: int, group_values, rng_seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(rng_seed)
    return pd.DataFrame(
        {
            "AMT_INCOME_TOTAL": rng.normal(50000, 10000, n),
            "AMT_CREDIT": rng.normal(20000, 5000, n),
            "NAME_CONTRACT_TYPE": rng.choice(["Cash loans", "Revolving loans"], n),
            TARGET_COLUMN: rng.integers(0, 2, n),
            PROTECTED_ATTRIBUTE_COLUMN: group_values,
        }
    )


def test_evaluate_fairness_reports_both_metrics_for_two_balanced_groups():
    n = 400
    groups = np.array(["A"] * (n // 2) + ["B"] * (n // 2))
    df = _df(n, groups)
    pipeline = train_xgboost(df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN, RANDOM_SEED)

    result = evaluate_fairness(
        pipeline, df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN, PROTECTED_ATTRIBUTE_COLUMN
    )

    metric_names = {m["metric_name"] for m in result["metrics"]}
    assert metric_names == {"demographic_parity_difference", "equalized_odds_difference"}
    assert result["groups_included"] == ["A", "B"]
    assert result["groups_excluded_too_small"] == {}
    for metric in result["metrics"]:
        assert metric["metric_value"] >= 0.0
        assert metric["passed"] == (metric["metric_value"] <= metric["threshold"])


def test_evaluate_fairness_excludes_groups_below_min_group_size():
    n = 300
    groups = np.array(["A"] * (n - 5) + ["TINY"] * 5)
    df = _df(n, groups)
    pipeline = train_xgboost(df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN, RANDOM_SEED)

    result = evaluate_fairness(
        pipeline, df, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, TARGET_COLUMN, PROTECTED_ATTRIBUTE_COLUMN
    )

    assert "TINY" in result["groups_excluded_too_small"]
    assert result["groups_excluded_too_small"]["TINY"] == 5
    assert result["groups_included"] == ["A"]
    # Only one group meets the size bar -- a comparison is impossible, not
    # silently skipped or folded into a misleading single-group number.
    assert result["metrics"][0]["metric_name"] == "not_applicable"
    assert result["metrics"][0]["passed"] is None


def test_evaluate_fairness_thresholds_are_configurable_module_constants():
    # Locks the current defaults so a silent change doesn't slip through
    # without deliberately touching this test.
    assert DEMOGRAPHIC_PARITY_THRESHOLD == 0.10
    assert EQUALIZED_ODDS_THRESHOLD == 0.10
    assert MIN_GROUP_SIZE == 30
