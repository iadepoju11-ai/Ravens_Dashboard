# Production-readiness gap register

CHECKLIST.md Phase 8C. Part of the pilot package (`docs/pilot/README.md`).
A factual register of what this system does and does not currently do,
each row checked against the real implementation and this project's own
verification record (CHECKLIST.md's Phase 7 entries) — not a vague "more
work is required" statement. "Current state" describes what's actually
built and verified today; "Pilot implication" describes what a real
pilot deployment would need to decide or add on top of it. Several of
these are **deliberate scope boundaries** stated in this project's own
engineering guidance (CLAUDE.md), not oversights — marked as such below.

## Infrastructure and operations

| Area | Current state | Pilot implication |
| --- | --- | --- |
| Backup | Scripted, drilled (`scripts/staging-backup.sh`/`staging-restore.sh`), a real timed backup→destroy→restore→verify cycle passed against live staging (12.8s total, small dataset). | No scheduler exists — backups are manually/script triggered. A production cadence must be automated before go-live. |
| RPO | Unbounded today (no scheduler runs backups automatically) — stated plainly, not glossed over. Target **≤ 1 hour** *if* a scheduler is added. | Automated backup scheduling required before this target is real. |
| RTO | Target **≤ 15 minutes** for a database-only incident; the real drill took under 15 seconds. | Not validated at production data volume — restore time at real row counts is unmeasured. |
| Off-host backup storage | None — backups live on the same host as the database they protect. | A total host loss loses both simultaneously. An off-host destination (object storage, a second host) is required for real DR coverage. |
| Backup encryption | None — plain files on local disk, exactly as sensitive as the database itself. | Encryption at rest (and in transit, if backups ever leave the host) is required for a real deployment. |
| TLS | None in this topology — Keycloak runs in dev mode, the API and web server plain HTTP. | A reverse proxy or load balancer terminating TLS in front of the whole stack is required before any real traffic. |
| Secrets management | `.env` files (staging: real generated secrets, never committed; dev: intentionally public placeholder values). | A real secrets manager (Vault, a cloud provider's equivalent) is required for a production deployment; `.env` files don't scale to real operational secret rotation. |
| High availability | Single Docker host, one container per service, no load balancer, no failover. | No HA/failover exists. A pilot's acceptable downtime tolerance should be set with this in mind, not assumed away. |
| API capacity | Single gunicorn worker per container. A real load-test baseline measured a practical ceiling of **~70 req/s** for `/score` on this topology, bottlenecked on worker queueing (not application logic — server-side scoring time stayed flat under load). | More workers (needs `prometheus_client` multiprocess mode to keep metrics accurate — not wired up) or horizontal scaling (no load balancer exists) are both real, undone levers. Size a pilot's expected request volume against the measured ceiling, don't assume it scales automatically. |
| Rate limiting | Real, verified against live staging — app-wide default plus a stricter override on `/score`. Keyed by remote IP address, in-memory storage. | Per-IP, not per-tenant/per-user — a shared corporate network could share one limit across real distinct users. In-memory storage means limits are accurate for exactly one process; a real multi-worker/multi-instance deployment needs a shared backend (e.g. Redis) or limits silently become per-instance instead of a true aggregate. |
| Image deployment | Every push to `master` that passes the full CI gate publishes SHA-tagged images to GHCR. | The staging compose file doesn't pin to a specific published tag today — it always builds from source. Pinning is a small config change, not done yet. |
| API documentation staying in sync | `openapi/creditguard-openapi.yaml` is hand-written and verified against the real routes as of 2026-09-23. | No CI check fails a build when the routes and the spec drift apart — a real, stated gap. |
| Incident process | A documented recovery *procedure* and verification checklist exist (`docs/runbooks/disaster-recovery.md`). | No formal on-call rotation, incident-declaration process, or authorization chain for who may trigger a production restore — organizational decisions this codebase doesn't and can't make. |
| Third-party security assessment | None performed. Everything in `docs/pilot/security-overview.md` is this project's own internal verification (real regression tests, real fault-injection drills), stated as such. | A real pilot handling real applicant data should commission independent review before go-live, not rely solely on internal verification. |

## Security and governance boundaries

| Area | Current state | Pilot implication |
| --- | --- | --- |
| Audit anchoring | Internal hash chain, enforced by both cryptography (the chain itself) and Postgres permission separation (the runtime role cannot `UPDATE`/`DELETE` audit tables — verified by tests that attempt exactly that and confirm rejection). Correctly described as **tamper-evident**, never **immutable**. | A party with database-owner-level access (not the application's own restricted role) could still alter records and the chain consistently. External anchoring (a periodic chain-root commitment stored outside this system's own control) would close that specific gap and does not exist. |
| MFA / SSO | Not implemented independently of the chosen identity provider — this application delegates authentication entirely to OIDC and has no MFA logic of its own. | MFA/SSO federation is a property of whichever real IdP a pilot connects, and needs to be a requirement placed on that IdP choice, not assumed as a feature of this codebase. |
| Kafka consumers | None exist. The producer/transactional-outbox side is real and tested (a genuine broker outage doesn't lose events; a real publish/consume round-trip is proven in CI) — this is a **deliberate architectural boundary**, not unfinished plumbing (CLAUDE.md: Kafka is for async workloads only, never the critical scoring path). | No asynchronous downstream workflow can consume these events yet. Adding a consumer is real, scoped, additive work only once a concrete use case exists — not a prerequisite for a synchronous-scoring pilot. |
| Dev-only dependency exceptions | Two documented, deliberately deferred findings: `pytest` (a test-only dependency, never invoked by the running container — its `CMD` is gunicorn) and the frontend's `vite`/`vitest`/`esbuild` toolchain (confirmed **zero** production exposure — none of it ships in the built nginx image; `npm audit --omit=dev` reports 0 vulnerabilities). Both are major-version bumps with real compatibility surface, explicitly named and tracked rather than silently ignored. | Neither blocks a pilot; both should eventually be upgraded as ordinary maintenance, not urgent security work. |

## Data and ML scope

| Area | Current state | Pilot implication |
| --- | --- | --- |
| Deployed model | A real, trained, validated model exists (`credit-risk-v1`, holdout ROC-AUC 0.7573) and has been proven to work end-to-end through the real API — but **is not currently registered or deployed in any running environment**. Every staging/demo run to date scores against a documented placeholder runtime. | Standing up a real pilot requires explicitly registering, approving, and deploying a real model version through the normal lifecycle (`docs/pilot/model-governance.md`) — this does not happen automatically just because the platform is deployed. |
| Training data | The public Kaggle "Home Credit Default Risk" dataset only. No pilot partner's real portfolio data has been used to train or validate anything. | A real pilot needs its own validation against that partner's actual applicant population before any performance number here can be treated as representative of pilot-specific accuracy. |
| Relational features | Two of Home Credit's six available relational tables (credit bureau history, prior applications to this lender) are used in a **comparison run only** — not registered or promoted to production. A modest, real improvement was measured (holdout ROC-AUC +0.0068, PR-AUC +0.0147). The four remaining tables (all monthly-grain payment/balance history — the largest, `installments_payments.csv`, captures actual repayment behavior) are entirely unused. | A materially stronger model likely requires the deferred monthly-grain feature engineering — a separate, scoped body of work, not started. |
| Model evaluation methodology | Stratified random train/validation/holdout split, not an out-of-time split — the source dataset has no absolute calendar date field usable for genuine time-based evaluation. Stated as a limitation in the model's own card, not silently presented as time-aware validation. | A real deployment should validate temporal stability (does the model degrade on more recent applications than it saw in training) once real, dated decision history exists — see "Drift monitoring" below. |
| Decision threshold | The illustrative `0.5` score threshold used in the reference model's own validation report is exactly that — illustrative, never calibrated against a real business cost model. The "expected cost" figure in that report uses an explicit, stated, not-validated cost assumption. | A real deployment needs its own calibrated decision threshold(s), set by the pilot partner's actual business policy — not inherited from this repository's illustrative default. |
| Drift monitoring | Not applicable yet — no deployed model has generated real decision history to measure drift against (the underlying alerting mechanism, `MonitoringAlert`, already exists and is exercised for fairness/audit/outbox alerts today). | Becomes meaningful only after a real model is deployed and accumulating decisions — not a current gap so much as a next step once "Deployed model" above is addressed. |
| Explainability coverage | SHAP `TreeExplainer` for tree-based models only — verified to fail fast with a clear error for an unsupported model type (proven by a test that deliberately tries to load a non-tree artifact), not to crash opaquely or silently misbehave. No LIME or other model-agnostic explainer exists. | Only relevant if a non-tree model ever becomes a real deployment candidate — not a gap for the current tree-based reference model. |
| Fairness thresholds | Configurable, illustrative defaults (e.g. 0.10 demographic parity/equalized-odds difference) — explicitly not presented as a universal legal standard. | A real deployment must set and justify its own thresholds against the pilot partner's actual legal/policy requirements, not inherit these defaults. |

## Explicitly out of scope (by design, not by omission)

The following are deliberately **not** part of this project's current
engineering effort, stated here so they read as considered decisions,
not gaps someone forgot about: Kubernetes, multi-region deployment,
managed PostgreSQL, managed Kafka, cloud-native secret management,
automated multi-region failover, full active-active API clusters. The
stated objective of this project's platform-engineering work
(CHECKLIST.md Phase 7) was demonstrating that the system can be
deployed, observed, secured, tested, and recovered using the
infrastructure it actually has — not building enterprise production
infrastructure speculatively ahead of an actual pilot's real
requirements. Revisit any of these only once a specific pilot's scale or
contractual requirements actually call for it.
