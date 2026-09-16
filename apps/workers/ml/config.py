"""Paths and constants for the Home Credit reference model pipeline.

Scope (see docs/architecture/data-strategy.md Phase A and CHECKLIST.md
Phase 4): application_train.csv only for this first milestone — not the
full relational feature set (bureau, previous applications, payment
history), which is deferred to a later iteration.
"""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("HOME_CREDIT_DATA_DIR", "/workers/data/home_credit"))
APPLICATION_TRAIN_PATH = DATA_DIR / "application_train.csv"
APPLICATION_TEST_PATH = DATA_DIR / "application_test.csv"

ARTIFACT_DIR = Path(os.environ.get("MODEL_ARTIFACT_DIR", "/workers/model_artifacts"))
REPORT_PATH = ARTIFACT_DIR / "credit-risk-v1-validation-report.json"
MODEL_PATH = ARTIFACT_DIR / "credit-risk-v1.joblib"
BASELINE_MODEL_PATH = ARTIFACT_DIR / "credit-risk-v1-baseline-logreg.joblib"
METADATA_PATH = ARTIFACT_DIR / "credit-risk-v1-metadata.json"

RANDOM_SEED = 42

ID_COLUMN = "SK_ID_CURR"
TARGET_COLUMN = "TARGET"
# Excluded from model features entirely (not just "handled carefully") —
# tracked separately for subgroup evaluation only. Mirrors the academic
# prototype's approach (repository-inventory.md §1.2) of keeping protected
# attributes out of the model's own inputs.
PROTECTED_ATTRIBUTE_COLUMN = "CODE_GENDER"

# No absolute calendar date exists in application_train.csv (DAYS_* fields
# are relative offsets, not a sortable application date), so a genuine
# out-of-time split isn't possible from this table alone — a stratified
# random split is used instead, and this is documented as a limitation
# rather than silently presented as time-aware evaluation.
TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
HOLDOUT_FRACTION = 0.15
