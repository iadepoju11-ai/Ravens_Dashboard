# CreditGuard XAI — pilot overview

CHECKLIST.md Phase 8B. This is the entry point to the pilot deployment
package — everything a prospective pilot partner needs to understand
what this product does today, what it requires to run, and what it does
not yet do. Every claim in this package is checked against the real,
verified implementation (CHECKLIST.md's entire Phase 7 record — staging
deployment, observability, resilience, security, CI/CD, disaster
recovery) and against `docs/pilot/known-limitations.md`'s factual gap
register, not aspirational.

## 1. What is CreditGuard XAI?

A multi-tenant credit-decision **governance** platform. It sits between
a lender's existing systems and their credit model, and returns a credit
decision **together with** its explanation, model version, governance
checks, and tamper-evident audit evidence. The core design principle:
*governance information travels with the credit decision* — an
explanation, a governance check, and an audit record are produced in the
same request that produces the decision, not bolted on afterward.

## 2. What problem does it solve?

Lenders using ML for credit decisions face two related problems: proving
*why* a decision was made (to the applicant, to a regulator, to internal
model risk review), and proving the decision-making process itself is
governed (approved models only, tamper-evident records, fairness
monitoring, human review for edge cases). CreditGuard XAI is
infrastructure for both — it does not replace a lender's underwriting
policy or core banking system, it wraps a model with the governance layer
around it.

## 3. What does the current version actually do?

The full vertical slice works end to end, real infrastructure, not a
mock:

- **Score** an application against an approved, deployed model version
  (`POST /score`), idempotently (safe to retry).
- **Explain** the decision — SHAP (tree models) when a real trained
  model is deployed, a documented placeholder otherwise (see §10 and
  `known-limitations.md` — **no real model is deployed in this repo's
  own environments today**, only registered/validated in a test; see
  §10 before assuming a live pilot gets real SHAP explanations
  automatically).
- **Govern** — an automatic governance check and, for a `refer` outcome
  or a failing check, an automatic human-review case.
- **Audit** — every decision is a tamper-evident, hash-chained event,
  independently verifiable and exportable.
- **Isolate tenants** — every query is scoped to the caller's own
  tenant, verified by a dedicated cross-tenant test suite
  (`docs/architecture/security-hardening.md`).
- **Authenticate** via OIDC (any compliant identity provider), **not**
  its own login system.
- **Deploy, observe, survive faults, and recover** — a documented,
  drilled staging deployment with structured logging, Prometheus
  metrics, fault-injection tests (Postgres/Kafka/API-container failure),
  a security-hardening pass, CI/CD gates, and a real, timed
  backup/restore + rollback drill. See §§13–15 and
  `docs/pilot/operational-runbook.md`.

## 4. What infrastructure does it require?

One Docker host running `docker-compose.staging.yml`: PostgreSQL, an
OIDC provider (Keycloak locally; swappable), Kafka (producer-only — see
§10), the API (Flask/gunicorn), and the frontend (React, served by
nginx). No Kubernetes, no managed cloud services, no multi-region setup
— see `docs/pilot/deployment-guide.md` for the exact topology and
`known-limitations.md` for what a real production target would still
need on top of this.

## 5. How is authentication performed?

OIDC — Authorization Code + PKCE from the browser, bearer tokens to the
API. The identity provider (any OIDC-compliant IdP) owns *authentication*
(proving who someone is); this application owns *tenancy and
authorization* (which tenant they belong to, what they're allowed to
do) — a token's tenant claim only matters the first time a user is seen,
never re-trusted from the token afterward. Full detail:
`docs/pilot/security-overview.md` and `docs/architecture/oidc-rbac.md`.

## 6. What roles exist?

Five: `admin`, `credit_analyst`, `compliance_officer`, `auditor`,
`data_protection_officer` — each with a fixed, least-privilege
permission set (a credit analyst can score and read decisions; an
auditor can read/verify/export the audit chain but never score or touch
models). Full matrix: `docs/pilot/roles-and-permissions.md`.

## 7. How is a model registered?

`POST /models` — creates a versioned `ModelVersion` record in `draft`
status, pointing at a trained artifact. Registering a version never
makes it live. See `docs/pilot/model-governance.md`.

## 8. How is a model approved?

`POST /models/{id}/approve` — a separate, deliberate step from
registration; only a `compliance_officer` or `admin` can approve, and
only a `draft` version can be approved.

## 9. How is a model deployed?

`POST /models/{id}/deploy` — only an `approved` version can be deployed;
deploying automatically archives whatever was previously deployed for
that model. A client can never select an unapproved or undeployed model
version to score against — `/score` resolves the tenant's current
deployed version itself, or rejects an explicitly-requested one that
isn't deployed.

## 10. How is a credit decision scored, and how are explanations
generated?

`POST /score` resolves the deployed model version, runs inference,
generates an explanation, and persists both in one request. **Important
distinction, stated plainly**: this repository has a real, trained,
validated XGBoost model (`docs/model_cards/credit-risk-v1.md` — holdout
ROC-AUC 0.7573, real SHAP explanations with reconstruction error
2.03e-6) that has been proven to work end-to-end through the full
API — but it is **not currently registered/deployed in any running
environment** (dev or staging), only exercised inside one integration
test's own transaction. Every staging/resilience/smoke test run this
project has ever done scores against `PlaceholderRuntime` (an averaged
score, a documented stand-in, never presented as a real model). A real
pilot deployment must explicitly register, approve, and deploy a real
trained model version — this doesn't happen automatically. See
`docs/pilot/model-governance.md` for the exact procedure and
`known-limitations.md` for what "real model deployed" does and doesn't
currently include (drift monitoring, non-tree explainers, etc.).

## 11. How are fairness results recorded?

`POST /fairness/evaluate` — persists metrics computed *offline* by the
ML pipeline (this application never computes fairness metrics itself;
the ML worker has no database access). A failing metric automatically
raises a monitoring alert. Statistical fairness monitoring, legal
compliance, and business policy are treated as three different things,
never conflated — see `docs/pilot/security-overview.md`'s compliance
positioning section.

## 12. How is the audit chain verified?

`GET /audit/verify-chain` walks the tenant's entire hash-chained event
sequence and detects tamper, deletion, reordering, and forks.
"Tamper-evident" is the accurate claim — the chain plus a Postgres
permission separation (the application's runtime role can only `INSERT`
into audit tables, never `UPDATE`/`DELETE`) makes unauthorized
modification *detectable and resisted at the ordinary-privilege level*,
not cryptographically un-alterable by someone with owner-level database
access. See `docs/architecture/audit-threat-model.md` for the exact
threat model this is and isn't designed against.

## 13. How are backups performed, and how is recovery performed?

Scripted (`scripts/staging-backup.sh`/`staging-restore.sh`), with a real,
timed, automated drill (backup → destroy the database → restore →
verify) proving actual application recovery, not just that `pg_restore`
exits `0`. Full detail, including honestly-scoped RPO/RTO targets and an
application-rollback drill: `docs/runbooks/disaster-recovery.md` and the
operational summary in `docs/pilot/operational-runbook.md`.

## 14. What isn't supported yet?

See `docs/pilot/known-limitations.md` — a factual, evidence-based gap
register, not a vague "more work is needed" statement. Highlights: no
scheduled backups (manual/scripted only), no TLS in this stack's own
topology (expected to terminate at a reverse proxy/load balancer in
front of it), no Kafka consumers (the outbox/producer side is real and
tested; nothing consumes the topics yet — a deliberate boundary, not an
oversight), no MFA/SSO beyond what the chosen IdP itself provides, no
drift monitoring (no deployed model has generated decision history yet
to measure drift against), and four of Home Credit's six relational
tables remain unused in the reference model (a modest, measured
improvement from two of them is documented, not yet promoted to
production).

## Document index

| Document | Covers |
| --- | --- |
| `deployment-guide.md` | Topology, prerequisites, first deploy, redeploy |
| `configuration-reference.md` | Every environment variable, what it does, dev vs. staging defaults |
| `roles-and-permissions.md` | The 5 roles, full permission matrix |
| `operational-runbook.md` | Day-to-day operation: scoring, monitoring, backup, incident response |
| `security-overview.md` | Authentication, tenant isolation, hardening, compliance positioning |
| `model-governance.md` | Model/dataset lifecycle, explainability, fairness, review workflow |
| `known-limitations.md` | The production-readiness gap register (CHECKLIST.md Phase 8C) |
| `../../openapi/creditguard-openapi.yaml` | The full API contract, machine-readable (CHECKLIST.md Phase 8A) |

Every document here links back to the authoritative engineering
documentation (`docs/runbooks/`, `docs/architecture/`,
`docs/model_cards/`) it's derived from, rather than duplicating exact
commands that could drift out of sync — this package is a curated,
pilot-audience entry point, not a replacement for the underlying
engineering record.
