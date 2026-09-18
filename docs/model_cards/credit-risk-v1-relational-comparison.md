# Relational features comparison (Sprint E)

Not a model card for a new production model — this is a **comparison
run** answering one question: does adding two of Home Credit's
relational tables (credit bureau history, this lender's own prior
application history) improve on the `application_train.csv`-only
reference model (`credit-risk-v1`, see `credit-risk-v1.md`)? Results are
**not registered** as a `Model`/`ModelVersion` and do **not** replace
`credit-risk-v1.joblib` — promoting this feature set to production is a
separate, deliberate step (re-run `credit-risk-v1`'s own data-quality/
leakage checks against the expanded feature set, update its model card,
go through the normal register → approve → deploy flow).

Reproducible via `apps/workers/ml/relational_pipeline.py`:

```
docker run --rm \
  -v <path-to-home_credit-csvs>:/workers/data/home_credit:ro \
  -v ./model_artifacts:/workers/model_artifacts \
  creditguard-ml-workers python -m ml.relational_pipeline
```

`random_seed=42`, same 70/15/15 stratified split logic as `pipeline.py`.

## Scope decision

Home Credit ships **six** relational tables beyond `application_train.csv`.
This comparison uses two:

| Table | Used? | Why |
| --- | --- | --- |
| `bureau.csv` (170MB) | ✅ | Credit history at other institutions — the single highest-value relational table in most public Home Credit analyses. |
| `previous_application.csv` (405MB) | ✅ | This lender's own prior application history. |
| `bureau_balance.csv` (376MB) | ❌ deferred | Monthly grain (one row per bureau credit *per month*, not per credit) — a second, separate aggregation problem. |
| `installments_payments.csv` (723MB) | ❌ deferred | Monthly grain, largest file. |
| `POS_CASH_balance.csv` (393MB) | ❌ deferred | Monthly grain. |
| `credit_card_balance.csv` (425MB) | ❌ deferred | Monthly grain. |

The four deferred tables are all instalment/balance-history tables — one
row per credit *per month*, not one row per credit — and are a genuinely
separate body of aggregation work, not a natural extension of the
`groupby(SK_ID_CURR)` approach used here. Deferred deliberately (see
`CHECKLIST.md`), not silently skipped.

## Feature engineering (`apps/workers/ml/relational_features.py`)

Both tables are aggregated to **one row per `SK_ID_CURR`**, then
left-joined onto `application_train.csv`:

- **`bureau.csv`** → count of prior credits, count currently active,
  mean days-since-credit-opened, max days-overdue, mean/sum of credit
  amounts, sum of overdue amounts, number of distinct credit types (8
  features).
- **`previous_application.csv`** → count of prior applications to this
  lender, count approved, count refused, mean annuity/application
  amount/credit amount/down payment, mean days-since-decision (8
  features).

Count-style features (`bureau_count`, `prev_app_approved_count`, ...) are
filled with `0` for an applicant with no rows in a table — a real,
informative value (no prior credit history), not a missing one. Every
other aggregate is left as `NaN` for the existing preprocessing
pipeline's median imputer (`preprocessing.py`) to handle, consistent with
how every other numeric column in `application_train.csv` is already
treated. 16 relational features in total, tested against synthetic data
in `apps/workers/tests/test_relational_features.py` (4 tests).

The join happens **before** the train/val/holdout split (both tables are
per-applicant, and the split is still on distinct `SK_ID_CURR`), so
`pipeline.py`'s own leakage checks (`leakage.py::run_leakage_checks`) were
re-run against the merged frame — **0 applicant-id overlap across
splits**, same clean result as `credit-risk-v1`.

## Results

Both models below are XGBoost, trained in the **same run**, same split,
same seed — so the comparison is apples-to-apples between the two
feature sets, not confounded by using a different random split for each
(as would happen comparing against a separately-run `credit-risk-v1`).

| Feature set | Split | n | ROC-AUC | PR-AUC | Brier |
| --- | --- | --- | --- | --- | --- |
| `application_train.csv` only | Validation | 46,127 | 0.7553 | 0.2451 | 0.1956 |
| `application_train.csv` only | Holdout | 46,127 | **0.7573** | 0.2408 | 0.1947 |
| + bureau + previous_application | Validation | 46,127 | 0.7629 | 0.2531 | 0.1921 |
| + bureau + previous_application | Holdout | 46,127 | **0.7640** | 0.2555 | 0.1913 |

Adding the 16 bureau/previous-application features improves holdout
ROC-AUC by **+0.0068** (0.7573 → 0.7640) and holdout PR-AUC by **+0.0147**
(0.2408 → 0.2555) — a real, modest improvement, not a dramatic one. Both
subgroup-performance breakdowns (`CODE_GENDER`) show the same pattern as
`credit-risk-v1`: similar ROC-AUC across `F`/`M`, a real difference in
positive rate. (The relational-features run's validation split happens to
include 2 `XNA` rows, correctly reported as "sample too small to report
reliably" rather than silently folded into a group.)

Full numbers: `model_artifacts/credit-risk-v1-relational-comparison-report.json`
(gitignored, regenerated on every run).

## What this does and doesn't establish

- **Does**: give an honest, same-run answer to "is bureau/previous-application
  history worth adding" — yes, by a modest amount, on this dataset and
  this feature engineering. Confirms the join/aggregation logic is
  leak-free against the real 307,511-row dataset (not just synthetic
  test data).
- **Doesn't**: represent the ceiling of what the full six-table relational
  feature set could achieve — the four deferred monthly-grain tables
  (especially `installments_payments.csv`, which captures actual
  repayment behavior) are a plausible source of further improvement, not
  yet measured. Doesn't replace `credit-risk-v1` as the deployed model;
  see the promotion-is-a-separate-step note above.
