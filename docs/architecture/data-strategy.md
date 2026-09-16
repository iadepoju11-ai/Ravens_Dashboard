# Data strategy

Referenced by `CHECKLIST.md` Phase 4 (real model runtime / reference model
milestone). Defines what data the commercial model is developed on, what it
is validated on before a pilot, and what "big enough" means for this product
— deliberately not a row-count target (see `CLAUDE.md`: accuracy on a public
benchmark does not make the product production-ready).

---

## Phase A — Development dataset

Public data used to build and iterate on the modelling pipeline before any
lender data is available.

- **Primary**: Home Credit — richer feature surface than German Credit (the
  academic prototype's dataset; see `docs/architecture/repository-inventory.md`
  §1.6), but Home Credit is not automatically larger-or-more-representative
  for every lending product it might be applied to. Its population, target
  definition, feature availability, and historical context must be documented
  before use, not assumed from its size.
- **Benchmark**: German Credit — kept as a comparison point against the
  academic baseline.
- **Optional**: LendingClub — only if licensing and technical provenance
  (collection context, field definitions, known biases) are confirmed
  suitable; not used by default.

## Phase B — Commercial validation dataset

A partner lender's anonymised historical dataset is what actually establishes
whether the model is useful for that lender's population — Phase A data
cannot substitute for this. Required contents, where lawfully collected and
usable:

- Loan applications and application dates.
- Applicant financial information the lender is permitted to use.
- Credit outcomes, repayment performance, default/delinquency outcomes.
- Protected-group information for fairness evaluation.
- Existing decision outcomes and model scores, if the lender has them (useful
  as a comparison baseline, not as a label source).

---

## Data requirements (acceptance criteria)

| Requirement | Acceptance criterion |
| --- | --- |
| Data provenance | Every dataset has a documented source, licence, collection context, and version. |
| Dataset versioning | Every model links to the exact dataset version used for training. |
| Target definition | The repayment/default target is explicitly defined with an observation window. |
| Leakage prevention | Features not available at decision time are excluded. |
| Time-aware evaluation | Validation uses later-period data rather than only random splits, where applicable. |
| Missing data | Missingness is analysed and handled through a documented pipeline. |
| Duplicate records | Duplicate and related records are detected before splitting. |
| Bias review | Data quality and potential discriminatory patterns are documented. |
| Privacy | Personal data access and processing are controlled and documented. |
| Reproducibility | Training can be repeated from the same code, configuration, and dataset version. |

These map onto `CHECKLIST.md` Phase 4's "Larger documented dataset" and
"Fixed, reproducible preprocessing pipeline; leakage / post-decision feature
checks" items, and onto Phase 5's tenant/data-governance items.

---

## Sizing

No arbitrary row-count target (e.g. "10 million rows") — that makes the
product look commercial without making it valid. Instead:

- **Development**: Home Credit plus other legally usable public datasets.
- **Internal model validation**: a documented holdout and out-of-time test.
- **Pilot**: a lender-specific dataset with enough positive and negative
  outcome observations for statistically meaningful validation — sized to the
  partner's actual data availability, not a fixed target.
- **Production**: a controlled retraining process, not continuous
  uncontrolled learning.

Commercial acceptance is based on data quality, predictive performance,
calibration, stability, fairness, and business usefulness — not row count
alone.
