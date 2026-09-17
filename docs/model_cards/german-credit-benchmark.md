# German Credit benchmark comparison

Not a model card — this is a **benchmark comparison point**, not a
candidate production model. Results are not registered as a
`Model`/`ModelVersion`. See `docs/architecture/data-strategy.md` Phase A
("German Credit — kept as a comparison point against the academic
baseline") and `docs/architecture/repository-inventory.md` §1.2 for the
academic prototype's own result (XGBoost, `cv_auc=0.807`,
`holdout_auc=0.7675`, German Credit, 57 features after one-hot encoding).

Reproducible via `apps/workers/ml/german_credit_pipeline.py`
(`docker run --rm -v <path-to-german_credit-csvs>:/workers/data/german_credit:ro
-v ./model_artifacts:/workers/model_artifacts creditguard-ml-workers python -m
ml.german_credit_pipeline`), `random_seed=42`.

## Dataset

- **Source**: UCI German Credit (via `data/german_credit/german_credit_clean.csv`,
  the academic prototype's own cleaned copy), 1,000 rows, 21 feature columns.
- **Target polarity fix**: the raw `target` column is `1 = good credit`,
  `0 = bad credit` (`data/prepare_german_credit.py`: `target = (class ==
  "good")`) — the **opposite** polarity from Home Credit's `TARGET`
  (`1 = default`). Recoded at load time (`german_credit_pipeline.py`) so
  `1` consistently means elevated credit risk in both reports. Getting
  this backwards would have silently inverted every metric without
  erroring — called out explicitly here and in `german_credit_config.py`
  because it's exactly the kind of mistake that doesn't announce itself.
- **Excluded from model features**: `sex` and `personal_status` (the
  latter combines marital status with sex in the original UCI coding) —
  same protected-attribute-exclusion policy as Home Credit's `CODE_GENDER`.
- **Split**: 70/15/15 stratified random (700/150/150 rows) — same caveat
  as Home Credit: no absolute date field, so not a time-aware split.
- **Small-sample caveat**: 150-row validation/holdout sets mean these
  metrics carry real sampling noise (a handful of applicants flipping
  outcome measurably moves ROC-AUC) — read them as a rough comparison
  point, not a precise estimate.

## Why this run exists

Two purposes: (1) the comparison point `data-strategy.md` calls for, and
(2) evidence — not just an assertion — that `apps/api`'s
`SklearnPipelineRuntime` adapter genuinely works with more than one
boosting library. It only ever calls `predict_proba()`, so nothing
XGBoost-specific should matter; this run trains LightGBM side by side to
check that.

## Results (holdout)

| Model | ROC-AUC | PR-AUC | Brier | Precision @ 0.5 | Recall @ 0.5 |
| --- | --- | --- | --- | --- | --- |
| Logistic regression | 0.8212 | 0.6679 | 0.1668 | 0.618 | 0.756 |
| XGBoost | 0.8199 | 0.6836 | 0.1511 | 0.682 | 0.667 |
| LightGBM | 0.7901 | 0.6672 | 0.1657 | 0.625 | 0.556 |

Unlike Home Credit (where XGBoost clearly beat the logistic regression
baseline), **the three models are close on this dataset, with logistic
regression matching or slightly beating both tree-based models on
ROC-AUC.** This is a plausible, honestly-reported result, not a bug: at
n=1,000 with mostly simple, near-linear relationships, a well-regularized
linear model can match tree ensembles, and the validation/holdout numbers
for each model move by several points between the two splits (e.g.
XGBoost validation 0.7742 vs. holdout 0.8199) — exactly the sampling noise
the small-sample caveat above warns about. This is *not* directly
comparable to the academic prototype's own `holdout_auc=0.7675` figure:
different train/holdout split, different preprocessing, different
feature set (that prototype used 57 one-hot-encoded features from all 21
raw columns without recoding the target the same way this pipeline does).

Subgroup performance by `sex` (holdout, XGBoost): group `0`, n=54, ROC-AUC
0.839; group `1`, n=96, ROC-AUC 0.810 — close, but at these sample sizes
(54 and 96) not a statistically meaningful fairness comparison either way,
reported for completeness rather than as a finding.

## What this does and doesn't establish

- **Does**: give a second, independent data point alongside Home Credit,
  and prove `SklearnPipelineRuntime` works against a LightGBM-trained
  pipeline without any code change (`apps/api/tests/unit/test_sklearn_pipeline_runtime.py`
  tests only the Home Credit XGBoost artifact directly, but
  `apps/workers/tests/test_pipeline.py::test_train_and_evaluate_lightgbm`
  confirms the same `evaluate()`/pipeline-shape contract holds for it).
- **Doesn't**: replace or outperform the Home Credit model as a candidate
  for anything — German Credit's tiny size and different population make
  it unsuitable as a production dataset (see `data-strategy.md`); this
  is a sanity-check comparison, full stop.
