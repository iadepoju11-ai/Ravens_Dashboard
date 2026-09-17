"""Trains a baseline LogisticRegression and tree-based comparison models.
Each artifact bundles its own fitted preprocessing pipeline
(see preprocessing.py) so there is a single self-contained object that
goes straight from a raw feature dict to a prediction — no separate
preprocessing state to keep in sync at serving time. Training happens
here, offline — never inside a live request handler (see CLAUDE.md's
non-negotiable rules).

Dataset-agnostic (target_column/random_seed are parameters, not hardcoded)
so the same functions serve both the Home Credit pipeline (pipeline.py)
and the German Credit benchmark comparison (german_credit_pipeline.py).
"""

from __future__ import annotations

import joblib
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from ml.preprocessing import build_preprocessor


def _scale_pos_weight(train_df, target_column: str) -> float:
    class_counts = train_df[target_column].value_counts().sort_index()
    return class_counts[0] / class_counts[1]


def train_logistic_regression(
    train_df, numeric_columns, categorical_columns, target_column: str, random_seed: int
) -> Pipeline:
    pipeline = Pipeline(
        steps=[
            ("preprocess", build_preprocessor(numeric_columns, categorical_columns)),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=random_seed)),
        ]
    )
    X = train_df[numeric_columns + categorical_columns]
    y = train_df[target_column]
    pipeline.fit(X, y)
    return pipeline


def train_xgboost(
    train_df, numeric_columns, categorical_columns, target_column: str, random_seed: int
) -> Pipeline:
    pipeline = Pipeline(
        steps=[
            ("preprocess", build_preprocessor(numeric_columns, categorical_columns)),
            (
                "model",
                XGBClassifier(
                    n_estimators=300,
                    max_depth=4,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    scale_pos_weight=_scale_pos_weight(train_df, target_column),
                    eval_metric="auc",
                    random_state=random_seed,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    X = train_df[numeric_columns + categorical_columns]
    y = train_df[target_column]
    pipeline.fit(X, y)
    return pipeline


def train_lightgbm(
    train_df, numeric_columns, categorical_columns, target_column: str, random_seed: int
) -> Pipeline:
    """A second, independently-implemented tree-boosting library —
    exercises SklearnPipelineRuntime (apps/api) against something other
    than XGBoost, proving the adapter's genericity (it only ever calls
    predict_proba(), which both libraries' sklearn-API classifiers
    implement) rather than asserting that without evidence.
    """
    pipeline = Pipeline(
        steps=[
            ("preprocess", build_preprocessor(numeric_columns, categorical_columns)),
            (
                "model",
                LGBMClassifier(
                    n_estimators=300,
                    max_depth=4,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    scale_pos_weight=_scale_pos_weight(train_df, target_column),
                    random_state=random_seed,
                    n_jobs=-1,
                    verbose=-1,
                ),
            ),
        ]
    )
    X = train_df[numeric_columns + categorical_columns]
    y = train_df[target_column]
    pipeline.fit(X, y)
    return pipeline


def save_pipeline(pipeline: Pipeline, path) -> None:
    joblib.dump(pipeline, path)
