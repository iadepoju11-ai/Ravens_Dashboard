"""Paths and constants for the Sprint E relational-features comparison
run: application_train.csv + bureau.csv + previous_application.csv,
compared against the application-only reference model (pipeline.py,
credit-risk-v1). A comparison artifact, not a replacement — see
relational_pipeline.py's module docstring for why it is kept separate.
"""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("HOME_CREDIT_DATA_DIR", "/workers/data/home_credit"))
APPLICATION_TRAIN_PATH = DATA_DIR / "application_train.csv"
BUREAU_PATH = DATA_DIR / "bureau.csv"
PREVIOUS_APPLICATION_PATH = DATA_DIR / "previous_application.csv"

ARTIFACT_DIR = Path(os.environ.get("MODEL_ARTIFACT_DIR", "/workers/model_artifacts"))
MODEL_PATH = ARTIFACT_DIR / "credit-risk-v1-relational.joblib"
METADATA_PATH = ARTIFACT_DIR / "credit-risk-v1-relational-metadata.json"
REPORT_PATH = ARTIFACT_DIR / "credit-risk-v1-relational-comparison-report.json"
LEAKAGE_REPORT_PATH = ARTIFACT_DIR / "credit-risk-v1-relational-leakage-report.json"

RANDOM_SEED = 42

ID_COLUMN = "SK_ID_CURR"
TARGET_COLUMN = "TARGET"
PROTECTED_ATTRIBUTE_COLUMN = "CODE_GENDER"

TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
HOLDOUT_FRACTION = 0.15
