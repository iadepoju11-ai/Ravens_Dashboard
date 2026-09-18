import numpy as np
import pandas as pd

from ml.leakage import check_split_overlap, run_leakage_checks, scan_suspicious_column_names, scan_target_correlation

ID_COLUMN = "SK_ID_CURR"
TARGET_COLUMN = "TARGET"


def _df(ids, target_values=None) -> pd.DataFrame:
    n = len(ids)
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            ID_COLUMN: ids,
            "AMT_INCOME_TOTAL": rng.normal(50000, 10000, n),
            TARGET_COLUMN: target_values if target_values is not None else rng.integers(0, 2, n),
        }
    )


def test_check_split_overlap_passes_for_disjoint_splits():
    train_df = _df(range(0, 100))
    val_df = _df(range(100, 150))
    holdout_df = _df(range(150, 200))

    result = check_split_overlap(train_df, val_df, holdout_df, ID_COLUMN)

    assert result["passed"] is True
    assert result["overlap_counts"] == {"train_val": 0, "train_holdout": 0, "val_holdout": 0}


def test_check_split_overlap_fails_when_an_id_appears_in_two_splits():
    train_df = _df(range(0, 100))
    val_df = _df(range(90, 150))  # ids 90-99 overlap with train
    holdout_df = _df(range(150, 200))

    result = check_split_overlap(train_df, val_df, holdout_df, ID_COLUMN)

    assert result["passed"] is False
    assert result["overlap_counts"]["train_val"] == 10
    assert len(result["overlap_id_samples"]["train_val"]) == 10


def test_scan_target_correlation_flags_a_near_perfect_predictor():
    n = 500
    target = np.random.default_rng(1).integers(0, 2, n)
    df = pd.DataFrame(
        {
            "TARGET": target,
            "LEAKED_COPY_OF_TARGET": target,  # perfectly correlated -- should be flagged
            "AMT_INCOME_TOTAL": np.random.default_rng(2).normal(50000, 10000, n),  # unrelated -- should not
        }
    )

    result = scan_target_correlation(df, ["LEAKED_COPY_OF_TARGET", "AMT_INCOME_TOTAL"], "TARGET")

    assert "LEAKED_COPY_OF_TARGET" in result["flagged_for_review"]
    assert "AMT_INCOME_TOTAL" not in result["flagged_for_review"]


def test_scan_suspicious_column_names_flags_post_decision_looking_fields():
    columns = ["AMT_INCOME_TOTAL", "LOAN_DECISION_DATE", "APPROVAL_STATUS", "NAME_CONTRACT_TYPE", "TARGET"]

    flagged = scan_suspicious_column_names(columns, target_column="TARGET")

    assert set(flagged) == {"LOAN_DECISION_DATE", "APPROVAL_STATUS"}


def test_run_leakage_checks_passes_on_clean_disjoint_data():
    train_df = _df(range(0, 200))
    val_df = _df(range(200, 250))
    holdout_df = _df(range(250, 300))

    result = run_leakage_checks(train_df, val_df, holdout_df, ["AMT_INCOME_TOTAL"], TARGET_COLUMN, ID_COLUMN)

    assert result["passed"] is True


def test_run_leakage_checks_fails_on_split_overlap_regardless_of_correlation_scan():
    train_df = _df(range(0, 100))
    val_df = _df(range(95, 150))  # deliberately overlapping with train

    result = run_leakage_checks(train_df, val_df, val_df, ["AMT_INCOME_TOTAL"], TARGET_COLUMN, ID_COLUMN)

    assert result["passed"] is False


def test_run_leakage_checks_does_not_fail_just_because_a_correlation_is_flagged():
    # A real, strongly predictive feature -- correlated with the target,
    # but not a split-overlap bug -- must not fail the hard check.
    n = 300
    target = np.random.default_rng(3).integers(0, 2, n)
    ids = range(n)
    train_df = pd.DataFrame({ID_COLUMN: ids, "STRONG_PREDICTOR": target, TARGET_COLUMN: target})
    val_df = _df(range(n, n + 50))
    holdout_df = _df(range(n + 50, n + 100))

    result = run_leakage_checks(train_df, val_df, holdout_df, ["STRONG_PREDICTOR"], TARGET_COLUMN, ID_COLUMN)

    assert result["passed"] is True
    assert "STRONG_PREDICTOR" in result["target_correlation_scan"]["flagged_for_review"]
