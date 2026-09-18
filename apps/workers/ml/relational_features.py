"""Aggregates two of Home Credit's relational tables — bureau.csv
(credit history at other institutions) and previous_application.csv
(this lender's own prior application history) — to one row per
SK_ID_CURR, joinable onto application_train.csv.

Sprint E scope decision: bureau + previous_application only. The other
four relational tables (bureau_balance.csv, installments_payments.csv,
POS_CASH_balance.csv, credit_card_balance.csv) are monthly-grain history
tables (one row per credit *per month*, not per credit), are individually
375-725MB, and are a genuinely separate body of aggregation work —
deferred, not silently skipped (see CHECKLIST.md).

Count-style aggregates (bureau_count, prev_app_count, ...) are filled
with 0 after the join: an applicant absent from bureau.csv or
previous_application.csv genuinely has zero prior credits/applications,
which is real and informative, not missing. Every other aggregate (means,
sums, maxes over an applicant's own rows) is left as NaN for the existing
preprocessing pipeline's median imputer to handle (preprocessing.py) —
introducing a second, different imputation rule here would be an
undocumented inconsistency with how every other numeric column in
application_train.csv is already treated.
"""

from __future__ import annotations

import pandas as pd

BUREAU_COUNT_COLUMNS = ["bureau_count", "bureau_active_count"]
PREVIOUS_APPLICATION_COUNT_COLUMNS = ["prev_app_count", "prev_app_approved_count", "prev_app_refused_count"]


def aggregate_bureau(bureau_df: pd.DataFrame) -> pd.DataFrame:
    grouped = bureau_df.groupby("SK_ID_CURR")
    active_counts = bureau_df[bureau_df["CREDIT_ACTIVE"] == "Active"].groupby("SK_ID_CURR").size()

    agg = pd.DataFrame(
        {
            "bureau_count": grouped.size(),
            "bureau_active_count": active_counts,
            "bureau_days_credit_mean": grouped["DAYS_CREDIT"].mean(),
            "bureau_credit_day_overdue_max": grouped["CREDIT_DAY_OVERDUE"].max(),
            "bureau_amt_credit_sum_mean": grouped["AMT_CREDIT_SUM"].mean(),
            "bureau_amt_credit_sum_debt_sum": grouped["AMT_CREDIT_SUM_DEBT"].sum(),
            "bureau_amt_credit_sum_overdue_sum": grouped["AMT_CREDIT_SUM_OVERDUE"].sum(),
            "bureau_credit_type_nunique": grouped["CREDIT_TYPE"].nunique(),
        }
    )
    agg["bureau_active_count"] = agg["bureau_active_count"].fillna(0)
    agg.index.name = "SK_ID_CURR"
    return agg.reset_index()


def aggregate_previous_application(previous_df: pd.DataFrame) -> pd.DataFrame:
    grouped = previous_df.groupby("SK_ID_CURR")
    approved_counts = previous_df[previous_df["NAME_CONTRACT_STATUS"] == "Approved"].groupby("SK_ID_CURR").size()
    refused_counts = previous_df[previous_df["NAME_CONTRACT_STATUS"] == "Refused"].groupby("SK_ID_CURR").size()

    agg = pd.DataFrame(
        {
            "prev_app_count": grouped.size(),
            "prev_app_approved_count": approved_counts,
            "prev_app_refused_count": refused_counts,
            "prev_app_amt_annuity_mean": grouped["AMT_ANNUITY"].mean(),
            "prev_app_amt_application_mean": grouped["AMT_APPLICATION"].mean(),
            "prev_app_amt_credit_mean": grouped["AMT_CREDIT"].mean(),
            "prev_app_amt_down_payment_mean": grouped["AMT_DOWN_PAYMENT"].mean(),
            "prev_app_days_decision_mean": grouped["DAYS_DECISION"].mean(),
        }
    )
    agg["prev_app_approved_count"] = agg["prev_app_approved_count"].fillna(0)
    agg["prev_app_refused_count"] = agg["prev_app_refused_count"].fillna(0)
    agg.index.name = "SK_ID_CURR"
    return agg.reset_index()


def merge_relational_features(
    application_df: pd.DataFrame, bureau_agg: pd.DataFrame, previous_agg: pd.DataFrame
) -> pd.DataFrame:
    merged = application_df.merge(bureau_agg, on="SK_ID_CURR", how="left")
    merged = merged.merge(previous_agg, on="SK_ID_CURR", how="left")

    count_columns = [c for c in BUREAU_COUNT_COLUMNS + PREVIOUS_APPLICATION_COUNT_COLUMNS if c in merged.columns]
    merged[count_columns] = merged[count_columns].fillna(0)
    return merged


def relational_feature_columns() -> list[str]:
    return [
        "bureau_count",
        "bureau_active_count",
        "bureau_days_credit_mean",
        "bureau_credit_day_overdue_max",
        "bureau_amt_credit_sum_mean",
        "bureau_amt_credit_sum_debt_sum",
        "bureau_amt_credit_sum_overdue_sum",
        "bureau_credit_type_nunique",
        "prev_app_count",
        "prev_app_approved_count",
        "prev_app_refused_count",
        "prev_app_amt_annuity_mean",
        "prev_app_amt_application_mean",
        "prev_app_amt_credit_mean",
        "prev_app_amt_down_payment_mean",
        "prev_app_days_decision_mean",
    ]
