import numpy as np
import pandas as pd

from ml.relational_features import (
    aggregate_bureau,
    aggregate_previous_application,
    merge_relational_features,
    relational_feature_columns,
)


def _bureau_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [1, 1, 1, 2],
            "SK_ID_BUREAU": [100, 101, 102, 200],
            "CREDIT_ACTIVE": ["Active", "Closed", "Active", "Closed"],
            "DAYS_CREDIT": [-100, -500, -50, -200],
            "CREDIT_DAY_OVERDUE": [0, 0, 5, 0],
            "AMT_CREDIT_SUM": [10000.0, 5000.0, 20000.0, 15000.0],
            "AMT_CREDIT_SUM_DEBT": [1000.0, 0.0, 2000.0, 500.0],
            "AMT_CREDIT_SUM_OVERDUE": [0.0, 0.0, 100.0, 0.0],
            "CREDIT_TYPE": ["Credit card", "Car loan", "Credit card", "Car loan"],
        }
    )


def _previous_application_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_PREV": [1000, 1001, 1002, 2000],
            "SK_ID_CURR": [1, 1, 1, 2],
            "NAME_CONTRACT_STATUS": ["Approved", "Refused", "Approved", "Refused"],
            "AMT_ANNUITY": [1000.0, np.nan, 1500.0, 800.0],
            "AMT_APPLICATION": [10000.0, 5000.0, 15000.0, 8000.0],
            "AMT_CREDIT": [10000.0, 0.0, 15000.0, 0.0],
            "AMT_DOWN_PAYMENT": [500.0, 0.0, 1000.0, 0.0],
            "DAYS_DECISION": [-30, -400, -10, -200],
        }
    )


def test_aggregate_bureau_computes_per_applicant_rollups():
    agg = aggregate_bureau(_bureau_df())

    applicant_1 = agg[agg["SK_ID_CURR"] == 1].iloc[0]
    assert applicant_1["bureau_count"] == 3
    assert applicant_1["bureau_active_count"] == 2
    assert applicant_1["bureau_credit_day_overdue_max"] == 5
    assert applicant_1["bureau_amt_credit_sum_debt_sum"] == 3000.0
    assert applicant_1["bureau_credit_type_nunique"] == 2


def test_aggregate_previous_application_computes_per_applicant_rollups():
    agg = aggregate_previous_application(_previous_application_df())

    applicant_1 = agg[agg["SK_ID_CURR"] == 1].iloc[0]
    assert applicant_1["prev_app_count"] == 3
    assert applicant_1["prev_app_approved_count"] == 2
    assert applicant_1["prev_app_refused_count"] == 1
    assert applicant_1["prev_app_amt_annuity_mean"] == 1250.0  # mean of 1000, 1500 -- NaN excluded


def test_merge_relational_features_fills_zero_for_applicants_absent_from_either_table():
    application_df = pd.DataFrame({"SK_ID_CURR": [1, 2, 3], "AMT_INCOME_TOTAL": [50000.0, 60000.0, 70000.0]})
    bureau_agg = aggregate_bureau(_bureau_df())
    previous_agg = aggregate_previous_application(_previous_application_df())

    merged = merge_relational_features(application_df, bureau_agg, previous_agg)

    # Applicant 3 has no bureau or previous-application rows at all.
    applicant_3 = merged[merged["SK_ID_CURR"] == 3].iloc[0]
    assert applicant_3["bureau_count"] == 0
    assert applicant_3["prev_app_count"] == 0
    # A mean/sum aggregate stays NaN -- not silently zeroed -- for the
    # existing preprocessing pipeline's median imputer to handle.
    assert pd.isna(applicant_3["bureau_days_credit_mean"])
    assert len(merged) == len(application_df)


def test_relational_feature_columns_are_all_present_after_merge():
    application_df = pd.DataFrame({"SK_ID_CURR": [1, 2], "AMT_INCOME_TOTAL": [50000.0, 60000.0]})
    merged = merge_relational_features(
        application_df, aggregate_bureau(_bureau_df()), aggregate_previous_application(_previous_application_df())
    )

    for column in relational_feature_columns():
        assert column in merged.columns
