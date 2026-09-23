# Security overview

Part of the pilot package (`docs/pilot/README.md`). A pilot-audience
summary of the real, verified security posture — the full engineering
detail (including every real finding and fix, not just a clean summary)
is `docs/architecture/security-hardening.md`,
`docs/architecture/oidc-rbac.md`, and
`docs/architecture/audit-threat-model.md`.

## Positioning — read this first

CreditGuard XAI is positioned as *"an AI credit decision governance and
explainability platform."* It is **not** marketed as, and does not
claim to be, "EU AI Act compliant" or "GDPR compliant" merely because it
has SHAP explanations, fairness metrics, and an audit log. The EU AI Act
treats creditworthiness evaluation of natural persons as high-risk
(Annex III); this platform is designed with that in mind (risk-management
documentation, data governance, logging/traceability, human oversight,
audit evidence) but compliance is a legal determination for the deploying
organization to make with its own counsel, not a claim this software
makes for itself.

## Authentication and tenant isolation

- **Authentication is delegated entirely to an external OIDC provider.**
  This application never sees or stores a password; it verifies a
  signed access token's signature (against the issuer's published keys),
  issuer, audience, and expiry on every request. The signing-algorithm
  allowlist is fixed in code, not inferred from the token itself —
  verified by regression tests against both the classic unsigned-token
  ("`alg: none`") forgery and the RS256-to-HS256 key-confusion attack.
- **Tenant identity is never trusted from a client.** A token's tenant
  claim only matters the first time a given user is seen (to create
  their record); every later request uses the tenant already on file,
  never re-read from the token — a stale or altered claim cannot move a
  user between tenants after the fact.
- **Cross-tenant access was systematically verified, not assumed.** A
  dedicated test suite proves a caller with the *correct* permission
  still cannot reach another tenant's decisions, models, fairness
  reports, reviews, audit records, or exports — every such attempt
  returns a plain "not found," indistinguishable from the record simply
  not existing, never a response that confirms the id is real but
  off-limits. Result of that audit: no cross-tenant leak was found: every
  endpoint already scoped correctly before the audit; the work closed a
  *test-coverage* gap, not a live vulnerability.

## Network-facing hardening

- **CORS** is restricted to an explicit allow-list of origins (the
  real frontend's own origin) — never a wildcard.
- **Security response headers** are applied to every response
  (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Content-Security-Policy: default-src 'none'`, `Strict-Transport-Security`
  — the last one inert until TLS terminates in front of this stack, not
  misleading in the meantime).
- **Rate limiting** exists app-wide, with a stricter limit on the
  scoring endpoint specifically (see `operational-runbook.md`) — verified
  against the real deployment, not just configured and assumed.
- **Request body size is capped** (1 MB default) — a clean rejection,
  not an unbounded read into memory.
- **A default/placeholder secret cannot silently run in production** —
  the application refuses to start under a production configuration if
  its signing secret is still the documented placeholder value.

## Audit evidence — what "tamper-evident" means here, precisely

Every governed action (a decision, an export, a review resolution) is
recorded as a hash-chained event — each event's hash covers the previous
event's hash, so any change to a historical record, or a deleted/inserted
record, changes the chain from that point forward in a way that's
detectable by walking and re-verifying it. This is enforced two ways:
**cryptographically** (the hash chain itself) and **procedurally**
(the database role the running application connects as can `INSERT`
into audit tables but never `UPDATE` or `DELETE` them — enforced by
PostgreSQL itself, not just application code, and verified by tests that
attempt exactly those forbidden operations directly against the
database and confirm they're rejected).

**The precise, honest claim**: this is *tamper-evident*, not
cryptographically *immutable* against every possible attacker. A party
with database-owner-level access (not the restricted runtime role) could
still alter both the records and the hash chain consistently, in a way
this design alone cannot detect — a hash chain anchored only inside the
same database it's protecting has that structural limit. External
anchoring (publishing a periodic chain-root commitment somewhere outside
this system's own control) would close that gap and does not exist yet
— see `known-limitations.md`. "Immutable" is never used to describe this
system's audit trail; "tamper-evident" and "append-only" are the accurate
terms, used deliberately.

## Dependency, container, and secret hygiene

Every release-quality-gated build (CI/CD, CHECKLIST.md Phase 7E) runs
dependency vulnerability scanning (Python and JavaScript, production
dependencies only for the JS build — dev/build tooling that never ships
is tracked separately, not silenced), container image scanning (fails
on any fixed critical vulnerability in either built image), and secret
scanning across the full git history. Real vulnerabilities were found
and fixed this way during development (dependency version bumps, and
critical OS-package CVEs in both base images) — not a theoretical
capability, a demonstrated one.

## What this section does not cover

MFA, SSO federation specifics, and formal penetration testing are not
part of this application's own scope — MFA/SSO is a property of whatever
OIDC identity provider a pilot deployment chooses, not something this
codebase implements independently (see `known-limitations.md`). No
third-party security assessment or penetration test has been performed
against this system; everything in this document is this project's own
internal verification, stated as such.
