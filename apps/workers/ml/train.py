"""Trains a baseline LogisticRegression and an XGBoost comparison model on
Home Credit application_train.csv. Each artifact bundles its own fitted
preprocessing pipeline (see preprocessing.py) so there is a single
self-contained object that goes straight from a raw feature dict to a
prediction — no separate preprocessing state to keep in sync at serving
time. Training happens here, offline — never inside a live request
handler (see CLAUDE.md's non-negotiable rules).
"""

from __future__ import annotations

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from ml.config import RANDOM_SEED, TARGET_COLUMN
from ml.preprocessing import build_preprocessor


def train_logistic_regression(train_df, numeric_columns, categorical_columns) -> Pipeline:
    pipeline = Pipeline(
        steps=[
            ("preprocess", build_preprocessor(numeric_columns, categorical_columns)),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=RANDOM_SEED)),
        ]
    )
    X = train_df[numeric_columns + categorical_columns]
    y = train_df[TARGET_COLUMN]
    pipeline.fit(X, y)
    return pipeline


def train_xgboost(train_df, numeric_columns, categorical_columns) -> Pipeline:
    class_counts = train_df[TARGET_COLUMN].value_counts().sort_index()
    scale_pos_weight = class_counts[0] / class_counts[1]

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
                    scale_pos_weight=scale_pos_weight,
                    eval_metric="auc",
                    random_state=RANDOM_SEED,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    X = train_df[numeric_columns + categorical_columns]
    y = train_df[TARGET_COLUMN]
    pipeline.fit(X, y)
    return pipeline


def save_pipeline(pipeline: Pipeline, path) -> None:
    joblib.dump(pipeline, path)
