"""Paths and constants for the German Credit benchmark comparison run.

Scope (see docs/architecture/data-strategy.md Phase A): kept as a
comparison point against the academic prototype's own dataset/baseline
(docs/architecture/repository-inventory.md §1.2) — not a candidate
production model. ~1,000 rows, no absolute date field either (same
time-aware-evaluation limitation as Home Credit).
"""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("GERMAN_CREDIT_DATA_DIR", "/workers/data/german_credit"))
DATA_PATH = DATA_DIR / "german_credit_clean.csv"

ARTIFACT_DIR = Path(os.environ.get("MODEL_ARTIFACT_DIR", "/workers/model_artifacts"))
REPORT_PATH = ARTIFACT_DIR / "german-credit-benchmark-report.json"

RANDOM_SEED = 42

TARGET_COLUMN = "target"
# Raw target is 1 = good credit, 0 = bad credit (the academic prototype's
# own encoding, data/prepare_german_credit.py: `target = (class == "good")`)
# — the OPPOSITE polarity from Home Credit's TARGET, where 1 = default.
# Recoded at load time so both reports mean the same thing by "1":
# elevated credit risk. Getting this backwards would silently invert
# every metric without erroring.
RAW_TARGET_GOOD_CREDIT_VALUE = 1

# Both columns carry gender-adjacent information — personal_status
# combines marital status with sex in the original UCI coding — and are
# excluded from model features entirely, mirroring Home Credit's
# CODE_GENDER exclusion.
PROTECTED_ATTRIBUTE_COLUMNS = ("sex", "personal_status")
# Used only for the subgroup-performance breakdown (evaluate.py takes a
# single column) — "sex" is the closer analogue to Home Credit's
# CODE_GENDER of the two.
SUBGROUP_COLUMN = "sex"

TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
HOLDOUT_FRACTION = 0.15
