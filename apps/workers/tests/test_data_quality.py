import numpy as np
import pandas as pd
import pytest

from ml.data_quality import profile

TARGET_COLUMN = "TARGET"


@pytest.fixture()
def toy_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "AMT_INCOME_TOTAL": [50000.0, 60000.0, None, 70000.0, 55000.0],
            "NAME_CONTRACT_TYPE": ["Cash loans", "Cash loans", "Revolving loans", "Cash loans", None],
            "ALWAYS_SAME": [1, 1, 1, 1, 1],
            TARGET_COLUMN: [0, 1, 0, 0, 1],
        }
    )


def test_profile_reports_shape_and_duplicates(toy_df):
    report = profile(toy_df, TARGET_COLUMN)

    assert report["n_rows"] == 5
    assert report["n_columns"] == 4
    assert report["n_duplicate_rows"] == 0


def test_profile_computes_missingness_per_column(toy_df):
    report = profile(toy_df, TARGET_COLUMN)

    assert report["columns"]["AMT_INCOME_TOTAL"]["missing_count"] == 1
    assert report["columns"]["AMT_INCOME_TOTAL"]["missing_fraction"] == pytest.approx(0.2)
    assert report["columns"]["NAME_CONTRACT_TYPE"]["missing_count"] == 1


def test_profile_computes_numeric_summary_stats(toy_df):
    report = profile(toy_df, TARGET_COLUMN)

    numeric = report["columns"]["AMT_INCOME_TOTAL"]
    assert numeric["min"] == 50000.0
    assert numeric["max"] == 70000.0
    assert numeric["mean"] is not None


def test_profile_computes_categorical_top_value(toy_df):
    report = profile(toy_df, TARGET_COLUMN)

    categorical = report["columns"]["NAME_CONTRACT_TYPE"]
    assert categorical["top_value"] == "Cash loans"


def test_profile_flags_constant_columns(toy_df):
    report = profile(toy_df, TARGET_COLUMN)

    assert "ALWAYS_SAME" in report["flags"]["constant_columns"]
    assert "AMT_INCOME_TOTAL" not in report["flags"]["constant_columns"]


def test_profile_flags_high_missingness_columns():
    df = pd.DataFrame({"MOSTLY_MISSING": [None, None, None, 1.0, 2.0], TARGET_COLUMN: [0, 1, 0, 1, 0]})
    report = profile(df, TARGET_COLUMN)

    assert "MOSTLY_MISSING" in report["flags"]["high_missingness"]["columns"]


def test_profile_flags_high_cardinality_categorical_columns():
    rng = np.random.default_rng(1)
    df = pd.DataFrame(
        {
            "HIGH_CARDINALITY": [f"value-{i}" for i in range(100)],
            TARGET_COLUMN: rng.integers(0, 2, 100),
        }
    )
    report = profile(df, TARGET_COLUMN)

    assert "HIGH_CARDINALITY" in report["flags"]["high_cardinality_categorical"]["columns"]


def test_profile_reports_target_class_balance(toy_df):
    report = profile(toy_df, TARGET_COLUMN)

    assert report["target"]["column"] == TARGET_COLUMN
    assert report["target"]["class_counts"] == {"0": 3, "1": 2}
    assert report["target"]["positive_rate"] == pytest.approx(0.4)


def test_profile_without_target_column_omits_target_section(toy_df):
    report = profile(toy_df, target_column=None)

    assert "target" not in report
