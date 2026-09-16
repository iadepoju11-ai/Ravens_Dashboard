# Repository inventory

Two separate, unrelated git repositories inform this project. This document
is the baseline snapshot referenced by `CHECKLIST.md` Phase 0.

- **Academic prototype** — `C:\Users\iadep\Documents\XAI Dashboard\XAI_Middleware`
  (remote: `github.com/iadepoju11-ai/XAI-Dashboard.git`). Kept as-is, untouched,
  at its own path. Not merged into this repo. Referenced here only so the
  commercial rebuild understands what behavior/contract it is superseding.
- **Commercial rebuild** — this repository (`Commercial XAI Middleware Dashboard`).
  Fresh git history, no shared code with the academic prototype.

Decision (2026-09-16): the two stay separate repos. The commercial product
trains on a much larger dataset (Home Credit, replacing the academic
prototype's ~1,000-row German Credit set) and folds in the dissertation's
documented future-work items (see below), rather than branching the academic
repo.

---

## 1. Academic prototype — current behavior (reference baseline)

### 1.1 Backend routes (`backend/app.py`, `auth.py`, `compliance.py`)

Session-cookie auth (`@auth.require_auth`), no per-role backend authorization
(role gating is UI-only in the React app).

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/login` | Session login, sets `user_id`/`role`/`username`/`display_name` |
| POST | `/api/auth/logout` | Clear session |
| GET | `/api/auth/me` | Current session user |
| POST | `/api/score` | Build feature vector → `predict_proba` → decision (accept if p≥0.5) → SHAP → fairness → audit log → Kafka publish |
| GET | `/api/audit` | Paginated audit search (`page`, `page_size`, `decision`, `date_from`, `date_to`, `customer_id`) |
| GET | `/api/audit/export` | Full export, JSON or CSV |
| GET | `/api/audit/<application_id>` | Single audit record |
| GET | `/api/audit/stats` | Totals, accept/deny counts, probability histogram, explanation coverage |
| GET | `/api/fairness` | Current Fairlearn metrics over a rolling window |
| GET | `/api/fairness/history` | Past fairness-check records |
| GET | `/api/health` | Model/version, feature count, Kafka/Postgres/SHAP status, latency percentiles, `hash_chain: not_implemented` |
| GET/POST | `/api/customers`, `/api/customers/<id>` | Legacy Postgres customer registry (separate from audit DB); 503 if unreachable |
| POST | `/api/counterfactual` | Stub — always returns `not_implemented` (DiCE-ML deferred) |

### 1.2 ML / explainability

- **Dataset**: German Credit (~1,000 rows). Home Credit and LendingClub CSVs exist
  under `data/` but are unused by the current training code.
- **Model**: grid-searched XGBoost vs. HistGradientBoostingClassifier (5-fold CV,
  ROC-AUC); saved model is XGBoost, `cv_auc=0.807`, `holdout_auc=0.7675`,
  57 features. AUC floor gate = 0.80.
- **Features**: numeric fields (`duration, credit_amount, installment_commitment,
  residence_since, age, existing_credits, num_dependents`) plus one-hot blocks
  for 12 categorical fields, then `StandardScaler`. Protected attributes
  (`sex`, `personal_status`) are excluded from the model but tracked for
  fairness. Several feature values reaching the model are hardcoded constants
  in `_build_feature_vector` rather than collected from the API — only 6
  request fields actually vary per call.
- **Explainability**: `shap.TreeExplainer`, local per-instance only (no global
  explainer path in production code). Returns all 57 feature attributions,
  plus a `top_factors` split (top 5 positive / top 5 negative by magnitude).
- **Fairness**: Fairlearn `demographic_parity_difference` / `equalized_odds_difference`
  computed over a rolling window (`FAIRNESS_WINDOW_SIZE=500`, needs ≥10
  decisions with both `sex` groups present); alerts when
  `demographic_parity_ratio < DEMOGRAPHIC_PARITY_THRESHOLD` (default 0.80).
  Uses the model's own decision as pseudo-ground-truth (no real outcome label).
- **Counterfactuals**: not implemented — explicit stub pending DiCE-ML.

### 1.3 Database / audit

SQLAlchemy 2.0, defaults to `sqlite:///audit.db` (Postgres supported via the
same `DATABASE_URL`). Append-only is enforced only at the ORM level
(`before_update`/`before_delete` listeners raise `RuntimeError`) — no DB
constraint, no hash chain (`/api/health` reports this explicitly).

- `audit_records` — id (uuid), application_id, timestamp, input_features (JSON),
  decision, probability, shap_values (JSON), fairness_flags (JSON, nullable),
  model_version, customer_id (nullable).
- `fairness_checks` — id, timestamp, demographic_parity_ratio,
  demographic_parity_difference, equalized_odds_difference, alert, n_decisions.
- `users` — id, username, password_hash, role. Roles: `compliance_officer`,
  `auditor`, `dpo`, `system_administrator`.

### 1.4 Kafka

- Topic `credit-decisions` (single topic, gated by `KAFKA_ENABLED`, default off).
- Producer payload is narrower than the audit record: `{application_id,
  decision, probability, model_version}` — no SHAP values, no input features.
- Consumer is a standalone demo script only, not part of the running app.

### 1.5 Frontend

React 18 + Vite, `react-router-dom`, `axios`. Routes: `/` (Overview), `/score`
(Dashboard — scoring form + SHAP display, largest file), `/customers` (legacy
registry CRUD), `/fairness` (FairnessMonitor), `/audit` (AuditPanel),
`/health` (SystemHealth), plus `Login`/`AuthContext`. Every page footer
carries a "not certified or production-ready, synthetic data only" disclaimer.

### 1.6 Documented future work / known gaps (source: dissertation `eval/EVALUATION.md` §9, `docs/API.md`)

These are carried forward into this project's roadmap rather than discovered
independently:

1. **Net/monthly income field** — most-requested usability feedback (3 of 11
   trial participants); flagged in the dissertation as the primary
   post-dissertation enhancement candidate.
2. **Transaction-history integration** and **external credit-bureau linkage** —
   the academic model scores on application-form fields alone, with no live
   connection to transaction data or bureau data. Named as an explicit scope
   boundary to close in the commercial product.
3. **Counterfactual explanations (DiCE-ML)** — deferred as a "Phase 3 stretch
   goal" in the academic prototype; still not implemented anywhere.
4. **Hash-chained, tamper-evident audit** — explicitly `not_implemented` in the
   academic prototype. This commercial rebuild already has this
   (`app/services/audit_service.py`, SHA-256 chain) — ahead of baseline.
5. **Per-role backend authorization** — the academic prototype only gates
   roles in the UI; backend endpoints are open to any authenticated session.
   The commercial RBAC (Phase 6) must enforce roles server-side.
6. **Concurrency/scaling** — GIL-bound single dev-process latency degrades
   under load (p50 930ms at 5 concurrent users in the dissertation's load
   test); horizontal scaling via Gunicorn/replicas was explicitly out of
   prototype scope. Relevant to this project's Phase 7 load testing.

---

## 2. Commercial rebuild — current state (this repo)

### 2.1 Routes (`apps/api/app/api/v1/`)

| Method | Path | Status |
| --- | --- | --- |
| GET | `/api/v1/health`, `/api/v1/health/ready` | Implemented |
| POST | `/api/v1/score` | Implemented (placeholder scoring/explanation services) |
| GET | `/api/v1/decisions/<id>` | Implemented |
| GET | `/api/v1/tenants`, `/api/v1/tenants/<id>` | Implemented |
| GET | `/api/v1/models`, POST `/api/v1/models/<id>/deploy` | Implemented |
| GET/POST | `/api/v1/datasets` | Implemented |
| GET | `/api/v1/fairness/reports`, `/api/v1/fairness/reports/<id>` | Implemented (no fairness worker yet, so always empty until Phase 4/5) |
| GET | `/api/v1/audit/events`, `/api/v1/audit/events/<id>/verify` | Implemented, hash-chained |
| GET | `/api/v1/monitoring/metrics`, `/api/v1/monitoring/alerts` | Metrics real; alerts stub (empty) |
| POST | `/api/v1/auth/login`, `/api/v1/auth/refresh` | Placeholder (501) — OIDC/RBAC deferred |

### 2.2 DB tables (`apps/api/app/models/`, post-Phase-1)

17 tables, live via Alembic migrations (`apps/api/migrations/`), applied and
verified against real Postgres: `tenants`, `users`, `roles`, `user_roles`,
`datasets`, `dataset_versions`, `models`, `model_versions`, `decisions`,
`explanations`, `governance_results`, `audit_events`,
`audit_integrity_checks`, `fairness_evaluations`, `monitoring_alerts`,
`review_cases`, `model_deployments`. UUID primary/foreign keys use a custom
`GUID` type — native Postgres `uuid` in production, `CHAR(36)` on SQLite for
tests. See `docs/database-migrations.md`.

### 2.3 React frontend

Not started. `apps/web/` is an empty scaffold (Phase 6).

### 2.4 Kafka / ML worker code

Not started. `apps/workers/` is an empty scaffold (Phase 3/4).

### 2.5 Secrets check

`.gitignore` covers `.env`, `.env.*` (except `.env.example`), `data/raw/*`,
`data/processed/*`, `model_artifacts/*`. No secrets present in tracked files
as of this writing — `.env.example` contains only placeholder values.
