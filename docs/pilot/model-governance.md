# Model governance

Part of the pilot package (`docs/pilot/README.md`). How a model goes
from a trained artifact to a live decision, and what governs it along
the way — verified against the real service code
(`apps/api/app/services/`) and the real reference model's own
documented evaluation (`docs/model_cards/credit-risk-v1.md`).

## The model lifecycle

```
register (draft)
   → approve (approved)
      → deploy (deployed)
```

Three separate, deliberate steps, each requiring a specific permission
(`roles-and-permissions.md`) — registering a version never makes it
live, and approving it never deploys it. Deploying a new version
automatically archives whatever was previously deployed for that model
and records the deployment as its own auditable event. A client scoring
an application can never select an unapproved or undeployed model
version — either the tenant's current deployed version is used
automatically, or an explicit request for a non-deployed version is
rejected outright.

## The reference model, honestly described

This repository includes a real, trained, validated model
(`credit-risk-v1`, XGBoost, trained on Kaggle's Home Credit Default Risk
dataset's main application table): holdout ROC-AUC **0.7573**, SHAP
explanation fidelity verified to a reconstruction error of **2.03e-6**
(explanations are provably faithful to what the model actually computed,
not just plausible-looking numbers), a real Fairlearn fairness
evaluation (demographic parity difference 0.0987, equalized odds
difference 0.0874, both within a 0.10 threshold on the `CODE_GENDER`
protected attribute), and documented data-quality/leakage checks (zero
applicant-id overlap across train/validation/holdout splits, nothing
flagged by target-correlation or suspicious-column-name scans).

**This model is proven to work end-to-end through the real API — it is
not currently registered or deployed in any running environment.** Every
staging/demo deployment this project has run so far scores against a
documented placeholder runtime (an averaged score, never presented as a
real prediction). Standing up a real pilot means explicitly registering,
approving, and deploying this artifact (or a promoted successor — see
below) through the normal three-step lifecycle above; it is not automatic
and not implied by the platform being deployed.

A relational-features comparison (adding credit-bureau history and this
lender's own prior-application history — two of Home Credit's six
available relational tables) measured a modest, real improvement: holdout
ROC-AUC **0.7573 → 0.7640**, PR-AUC **0.2408 → 0.2555**. This comparison
result is **not** registered as a model version and does not replace the
reference model — promoting it is a deliberate future step (re-running
the reference model's own data-quality/leakage checks against the
expanded feature set, a new model card, and the normal
register → approve → deploy flow), not something that happens by
training a better number. See `known-limitations.md` for what remains
unused (the four monthly-grain relational tables) and why.

## Explainability

SHAP `TreeExplainer` for tree-based models (what the reference model
is) — every explanation is linked to the exact model version that
produced it, with feature attributions turned into ranked, human-readable
reason codes. **There is no explainer for non-tree model types today**
(no LIME, no model-agnostic fallback) — the runtime that loads a model
artifact fails fast with a clear, specific error for an unsupported model
type rather than crashing opaquely or silently guessing, proven by a test
that deliberately loads this project's own logistic-regression baseline
artifact and confirms it's rejected. If a non-tree model is ever a real
deployment candidate, it needs its own explainer built first — not
assumed to "just work" through the existing SHAP path.

**Explanations are never generative.** Nothing in this system uses a
language model to invent or phrase a reason for a decision — an
explanation is exclusively derived from the real model's own computed
feature contributions, transformed into reason codes by fixed,
deterministic logic. This is a hard design boundary, not a current
implementation detail that might change casually.

## Fairness

Computed **offline**, by the ML training pipeline (which has no database
access), and persisted via an authenticated endpoint — never computed
live during a scoring request. A metric that fails its configured
threshold automatically raises a monitoring alert (severity `high`). A
metric reported as "not applicable" (too few members in a group to
compute reliably) is recorded as skipped, never silently folded into a
misleading pass/fail.

**What this is and isn't**: a statistical check against one configured
metric and one configured threshold on one specific dataset run. It is
explicitly **not** a legal or ethical fairness verdict, and no fixed
threshold here is presented as a universal legal standard — thresholds
are configurable and must be justified by whoever operates a real
deployment, not inherited from this repository's own illustrative
defaults. Statistical monitoring, legal compliance review, model-risk
review, and business policy are treated as four different
responsibilities, never conflated into one "fair: yes/no" label.

## Governance checks and human review

Every scored decision is automatically evaluated by a governance check;
a `refer` outcome or a failing governance check automatically opens a
review case, visible to `compliance_officer`/`admin` roles, with a real
workflow (`open` → `in_review` → `closed`, claim-then-resolve, no
re-opening a closed case) rather than a free-form status field. This
happens inside the same `/score` request that produced the decision —
governance information travels with the decision, not bolted on as a
separate later process.

## Datasets

Registered independently of models (`POST /datasets`), versioned the
same way models are, and can be linked to a model version at
registration time (which training dataset version produced this model)
— provenance is recorded, not assumed from a filename.
