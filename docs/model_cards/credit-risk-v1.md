# Model card: credit-risk v1.0.0-dev

Status: **development reference model** — trained and validated as
`CHECKLIST.md` Phase 4's "first reference model milestone", and (2026-09-17)
wired into the live API end to end: `apps/api/app/services/runtimes/sklearn_pipeline_runtime.py`
loads this exact artifact, and `tests/integration/test_model_registration.py::test_score_against_the_real_deployed_model_uses_shap_tree_explanations`
registers it via `POST /api/v1/models`, links it to a registered
`DatasetVersion`, approves it via `POST /api/v1/models/<id>/approve`,
deploys it via `POST /api/v1/models/<id>/deploy`, and confirms `/score`
returns real `shap-tree` explanations. See "What's not done yet" for what
that end-to-end path still doesn't cover.

Trained: 2026-09-16. Reproducible via `apps/workers/ml/pipeline.py`
(`docker build -t creditguard-ml-workers ./apps/workers && docker run --rm
-v <path-to-home_credit-csvs>:/workers/data/home_credit:ro -v
./model_artifacts:/workers/model_artifacts creditguard-ml-workers`),
`random_seed=42`. See `docs/model_cards/german-credit-benchmark.md` for
the comparison run `data-strategy.md` calls for (German Credit, not a
candidate model in its own right).

---

## Dataset

- **Source**: Kaggle "Home Credit Default Risk" competition, `application_train.csv` only (307,511 rows, 122 columns) — see `docs/architecture/data-strategy.md` Phase A.
- **Scope limitation**: this milestone deliberately uses only the main application table, not the full relational feature set (`bureau.csv`, `bureau_balance.csv`, `previous_application.csv`, `installments_payments.csv`, `POS_CASH_balance.csv`, `credit_card_balance.csv`). Those are a documented follow-up, not part of this artifact.
- **Target**: `TARGET` (1 = defaulted, 0 = repaid). Positive rate 8.07% — meaningfully imbalanced.
- **Split**: 70% train / 15% validation / 15% holdout, **stratified random** (by `TARGET`), `random_seed=42`.
- **Not time-aware**: `application_train.csv` has no absolute calendar date field (`DAYS_*` columns are relative offsets, not sortable across applicants), so a genuine out-of-time split isn't possible from this table alone. This is a documented limitation, not silently presented as time-aware evaluation — revisit once `previous_application.csv`'s `DAYS_DECISION` or Phase B partner data (which will have real dates) is incorporated.

## Features

- 105 numeric + 15 categorical = 120 input features. Full list in `model_artifacts/credit-risk-v1-metadata.json` (gitignored, regenerate via the pipeline).
- **Excluded from model input entirely**: `SK_ID_CURR` (id), `TARGET` (label), `CODE_GENDER` (protected attribute — tracked separately for subgroup evaluation below, never a model input; mirrors the academic prototype's approach, `docs/architecture/repository-inventory.md` §1.2).
- **Leakage review**: `application_train.csv` is Kaggle's pre-decision application snapshot by design — no columns represent information only available after a credit decision. No additional leakage-prone columns were identified or removed at this stage.
- **Missing data**: numeric columns median-imputed, categorical columns most-frequent-imputed (`apps/workers/ml/preprocessing.py`) — a simple, documented strategy, not a missingness deep-dive. Several columns (`OWN_CAR_AGE`, the building `_AVG`/`_MODE`/`_MEDI` columns, `EXT_SOURCE_1`) have substantial missingness in the raw data; imputation quality for these is a candidate for follow-up.

## Models compared

| | Baseline: Logistic Regression | Comparison: XGBoost |
| --- | --- | --- |
| Class imbalance handling | `class_weight="balanced"` | `scale_pos_weight` = negative/positive ratio |
| Preprocessing | Median/mode impute → scale (numeric) → one-hot (categorical), bundled into the same serialized pipeline as the model | Same |

## Validation results

| Metric | Logistic Regression (val) | XGBoost (val) | XGBoost (holdout) |
| --- | --- | --- | --- |
| ROC-AUC | 0.7459 | 0.7553 | 0.7573 |
| PR-AUC | 0.2283 | 0.2451 | 0.2408 |
| Brier score | 0.2042 | 0.1956 | 0.1947 |
| Precision @ 0.5 | 0.160 | 0.166 | 0.168 |
| Recall @ 0.5 | 0.675 | 0.676 | 0.679 |

XGBoost outperforms the logistic regression baseline on every metric, and validation/holdout numbers for XGBoost are close (0.7553 vs 0.7573 ROC-AUC) — no sign of overfitting to the validation split. **0.5 is an illustrative decision threshold**, not a calibrated business policy threshold; confusion matrices and the expected-cost figure in `model_artifacts/credit-risk-v1-validation-report.json` use it only to make precision/recall concrete, not as a recommendation.

**Expected cost** uses an explicit, illustrative, *not validated* cost assumption (false negative = 10× false positive cost) — a placeholder for a real business cost model, not itself a business input.

## Subgroup performance (CODE_GENDER)

| Group | n (holdout) | Positive rate | ROC-AUC |
| --- | --- | --- | --- |
| F | 30,429 | 6.96% | 0.7535 |
| M | 15,698 | 10.23% | 0.7525 |

ROC-AUC is close across groups (no large discriminative-power gap), but the **positive (default) rate differs meaningfully** between groups in this public dataset (6.96% vs 10.23%). This is reported as a fact about the data and this model's predictions on it — **not** a fairness verdict; per `CLAUDE.md`, statistical monitoring, legal compliance, and business policy review are different things, and this single AUC/rate comparison on a public benchmark is not equivalent to Fairlearn-based fairness monitoring (`fairness_evaluations`, ERD Phase 5) against a real deployed model and real outcomes.

## SHAP explanation fidelity

`apps/workers/ml/explain.py` verifies that, for a 500-applicant holdout sample, `base_value + sum(shap_values)` reconstructs the XGBoost model's own raw margin output:

- Max reconstruction error: **2.03e-6** (tolerance 1e-3) — **passed**.

This confirms the SHAP explanations are faithful to what the model actually computed, not just plausible-looking numbers.

## What's not done yet

- **No drift or out-of-time stability metrics** — both require a baseline this milestone doesn't have yet (see "Validation results" and the JSON report's explicit `"not_applicable_*"` values, not a silently-omitted metric).
- **Full relational feature engineering** (bureau history, previous applications, payment behavior) is out of scope for this milestone (see "Dataset" above).
- **Fairness evaluation** beyond the single subgroup AUC/rate comparison above (Fairlearn demographic parity / equalized odds, `fairness_evaluations` table) is ERD Phase 5 work.
- **No LIME (or any) explainer for non-tree models.** `SklearnPipelineRuntime` only supports tree-based models via `shap.TreeExplainer` and fails fast with a clear error otherwise (`UnsupportedModelTypeError`) — proven by a test that loads this project's *own* logistic regression baseline artifact and confirms it's rejected rather than crashing opaquely or silently misbehaving. If the baseline is ever a genuine deployment candidate, it needs its own explainer.
- **This model is only registered inside a test's transaction**, not for real in any actual tenant's data — the end-to-end test above proves the wiring works, it doesn't mean this model is live anywhere. Real registration happens once a tenant needs it deployed.

## Artifacts

Local only, gitignored (`model_artifacts/*`) — not committed, not yet in an artefact store:

- `credit-risk-v1.joblib` — the XGBoost pipeline (preprocessing + model bundled together).
- `credit-risk-v1-baseline-logreg.joblib` — the logistic regression baseline.
- `credit-risk-v1-metadata.json` — full feature list, dataset version, training timestamp.
- `credit-risk-v1-validation-report.json` — full metrics (this document quotes the headline numbers).
