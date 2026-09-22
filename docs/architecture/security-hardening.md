# Security hardening: verification and controls

CHECKLIST.md Phase 7D. A systematic security verification pass across
authentication, OIDC token validation, RBAC, object-level authorization,
tenant isolation, input validation, rate limiting, CORS/security headers,
secret exposure, dependency/container vulnerabilities, and audit-write
protection. Everything below was verified for real — against the real
staging deployment where the check is deployment-shaped, or with a real
regression test where it's code-shaped — not assumed correct from
reading the code. See `docs/architecture/oidc-rbac.md` for the
authentication/RBAC design this builds on, and
`docs/architecture/audit-threat-model.md` for the audit chain's own
threat model (unchanged this pass, only reconfirmed).

## Authentication & OIDC token validation

Already covered by `apps/api/tests/unit/test_jwt_verifier.py` (signature,
issuer, audience, expiry). This pass added two attack-specific
regression tests against `app/security/jwt_verifier.py`:

- **`alg: none`** — an unsigned token with no signature segment.
  Rejected because PyJWT's `decode()` never treats "none" as implicitly
  valid; `jwt_verifier.py` never lists it in its `algorithms=["RS256"]`
  allowlist either.
- **RS256→HS256 algorithm confusion** — the classic attack: since an
  RSA *public* key is not secret (it's published in the issuer's JWKS),
  an attacker who knows it could forge a validly-HMAC-signed token if a
  verifier ever passed that public key to an HMAC algorithm. Built by
  hand with Python's `hmac` module rather than `jwt.encode(...,
  algorithm="HS256")`, because PyJWT's own *encoder* independently
  refuses to HMAC-sign with a PEM-formatted key — using the real encoder
  would have proven PyJWT guards itself, not that `jwt_verifier.py`'s
  `algorithms=["RS256"]` allowlist (passed to `decode()`, never inferred
  from the token's own header) is what actually rejects the forged token.

Both pass: this application's fixed `algorithms=["RS256"]` allowlist is
the correct mitigation for both, and now has a regression test proving
it, not just a design decision documented in a comment.

## RBAC

`app/security/permissions.py`'s five-role model was already extensively
tested (`apps/api/tests/unit/test_permissions.py`, 34 tests) — unchanged
this pass. Verified it still passes with every other change made.

## Object-level authorization / cross-tenant isolation

Every direct-object-access endpoint across the seven entity types this
pass was asked to verify, and where each is covered:

| Entity | Endpoint | Covered by |
| --- | --- | --- |
| Decisions | `GET /decisions` (list) | `test_decisions_list.py::test_list_decisions_does_not_leak_other_tenants` |
| Decisions | `GET /decisions/<id>` | `test_cross_tenant_isolation.py::test_decision_by_id_is_not_found_for_another_tenant` (new) |
| Models | `POST /models/<id>/approve` | `test_endpoint_authorization.py::test_compliance_officer_cannot_approve_another_tenants_model_version` |
| Models | `POST /models/<id>/deploy` | `test_cross_tenant_isolation.py::test_model_deploy_is_not_found_for_another_tenants_model_version` (new) |
| Datasets | `GET /datasets` (list; no by-id endpoint exists) | `test_endpoint_authorization.py::test_compliance_officer_cannot_see_another_tenants_datasets` |
| Fairness reports | `GET /fairness/reports/<id>` | `test_cross_tenant_isolation.py::test_fairness_report_by_id_is_not_found_for_another_tenant` (new) |
| Reviews | `GET /reviews/<id>` | `test_reviews.py::test_get_review_returns_not_found_for_another_tenants_review` |
| Reviews | `POST /reviews/<id>/resolve` | `test_cross_tenant_isolation.py::test_review_resolve_is_not_found_and_makes_no_change_for_another_tenants_case` (new) |
| Audit records | `GET /audit/events` (list) | `test_endpoint_authorization.py::test_auditor_cannot_read_another_tenants_audit_events` |
| Audit records | `GET /audit/events/<id>/verify` | `test_cross_tenant_isolation.py::test_audit_event_verify_by_id_is_not_found_and_writes_no_integrity_check_for_another_tenant` (new) |
| Exports | `GET /audit/export` | `test_cross_tenant_isolation.py::test_audit_export_only_ever_returns_the_callers_own_tenants_events` (new) |

Every case above asserts three things, not just "200 vs 404": the
response is `404 not_found` (never `403`, which would confirm the id is
real just off-limits, and never `200` with real cross-tenant data), and
where the endpoint is state-changing (model deploy, review resolve), a
follow-up query confirms the target row was genuinely untouched — a
`404` that still silently mutated something would be worse than an
honest error.

**Result: no cross-tenant leak or IDOR was found.** Every endpoint
already resolved tenant identity from the authenticated `Identity`
(`app/infrastructure/security/tenant_context.py`), never a client-
supplied value, and either filtered its query by `tenant_id` directly or
checked ownership (`model_version.model.tenant_id != tenant.id`) after a
by-id lookup, before this pass added anything. This pass's contribution
is closing the *test coverage* gap, not a code fix — six new integration
tests (`test_cross_tenant_isolation.py`) plus three routes
(`/reviews`, `/reviews/<id>`, `/reviews/<id>/resolve`) and
`/monitoring/observability` added to the existing mechanical 401/403
sweep in `test_endpoint_authorization.py`'s `_PROTECTED_ROUTES`, which
hadn't listed them.

## Duplicate-request safety (a real bug, found and fixed)

Not originally an object-level authorization issue, but found while
verifying "handle duplicate requests safely" (CLAUDE.md): two genuinely
concurrent `/score` calls with the same client-supplied idempotency key
(`request_id`) could both pass `ScoringService`'s initial "does this
decision already exist" check before either committed — the loser then
hit `uq_decision_tenant_request_id`'s database constraint and 500'd
instead of receiving the winner's decision.

**Fixed**: `apps/api/app/services/scoring_service.py` now catches the
`IntegrityError` on the losing insert, rolls back, re-looks-up the
winner's decision, and returns it as a replay (`created=False`).
Regression-tested deterministically (`test_scoring_service.py::test_a_concurrent_duplicate_request_is_deduplicated_not_crashed`
forces the exact race window without real threads) and, separately,
under genuine concurrent HTTP load against real staging Postgres
(`tests/resilience/test_duplicate_request_safety.py`, CHECKLIST.md Phase
7C — see that suite's own honest caveat about what it can and can't
prove given this deployment's single-worker gunicorn).

## API input validation

- **Request body size cap**: `MAX_CONTENT_LENGTH` (`app/config.py`,
  default 1 MB) — Flask/Werkzeug reject an oversized body with a clean
  `413` once the body is actually read, before it's fully buffered into
  memory. Proven end-to-end against a real authenticated `/score` call
  (`tests/integration/test_request_size_limit.py`) — a request rejected
  earlier in the pipeline (e.g. a missing token) never reads the body at
  all, so an oversized-body test needs a fully valid request reaching
  `request.get_json()` to mean anything, not just any route.
- **String field length validation**: `application_reference` and
  `request_id` are now capped at 255 characters in `ScoringService`
  (matching `Decision`'s own `db.String(255)` columns) and rejected with
  a structured `400`, not left to the database. On SQLite (this
  project's test database) an oversized value would otherwise be
  silently accepted — SQLite doesn't enforce `VARCHAR` length at all; on
  real Postgres it would instead surface as an unhandled `DataError` (a
  safe, but less clean, generic `500`).
- **Not done this pass**: comprehensive per-field length validation
  across every other string column in the schema (model/dataset names,
  alert messages, etc.). The body-size cap bounds the worst case
  (nothing can arrive that's dramatically larger than any legitimate
  payload); auditing and validating every individual field is a larger,
  separate effort than this pass's scope, and is an explicit, documented
  gap rather than a silent one.

## Rate limiting

`app/extensions.py`'s `limiter` (Flask-Limiter), keyed by remote address:

- App-wide default (`RATELIMIT_DEFAULT`, default `300 per minute`) on
  every route except health checks and `/metrics` (`@limiter.exempt` —
  hit frequently and legitimately by container healthchecks and
  Prometheus scrapers, see `app/api/v1/health.py` and `app/__init__.py`).
- `POST /score` has its own stricter override (`@limiter.limit("30 per
  minute")`, `app/api/v1/decisions.py`) — the single most expensive
  request in the system (model inference, explanation generation, an
  audit write, three outbox writes), and the one most worth bounding per
  caller.
- **Verified for real against staging**: 35 rapid `POST /score` calls
  from one caller returned `201` for the first ~26 and `429` for the
  rest, in the same request window — the limit is real, not just
  configured.
- **Known simplification**: keyed by remote address, not by tenant or
  authenticated identity — a real per-tenant limit would need the bearer
  token parsed and verified before Flask-Limiter's `key_func` runs,
  which is a bigger change than this pass's scope. Per-IP still
  meaningfully bounds a single abusive or malfunctioning caller.
- **Known limitation**: in-memory storage (`RATELIMIT_STORAGE_URI`,
  default `memory://`) — correct for how this app runs today (a single
  gunicorn worker per container, the same assumption already documented
  for Prometheus metrics in `app/observability/metrics.py`). A real
  multi-worker or multi-container deployment would need a shared backend
  (Redis) or these limits would silently become per-worker/per-container
  instead of a real aggregate limit.
- Disabled in the automated test suite (`TestingConfig.RATELIMIT_ENABLED
  = False`) so hundreds of requests sharing one "remote address" under
  Flask's test client don't make the *test suite itself* flaky — the
  mechanism has its own dedicated tests
  (`apps/api/tests/unit/test_rate_limiting.py`) that re-enable it on a
  purpose-built app instance.

## CORS and security headers

- **CORS**: `flask_cors.CORS()` with no `origins` argument defaults to
  allowing *every* origin — wrong for a platform serving real tenant
  credit-decision data to a browser. `app/config.py`'s
  `CORS_ALLOWED_ORIGINS` (comma-separated, defaults to the dev Vite
  origin) is now passed explicitly; flask-cors only ever echoes back
  `Access-Control-Allow-Origin` for a request whose `Origin` header
  matches this list. Verified for real against staging: the staging web
  origin (`http://localhost:8090`) gets the header echoed back;
  `http://evil.example.com` gets nothing.
- **Security headers**, applied to every response
  (`app/__init__.py`'s `after_request` hook): `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  `Content-Security-Policy: default-src 'none'` (safe as a blanket
  policy — this API never renders HTML itself), and
  `Strict-Transport-Security` (inert until a real deployment terminates
  TLS in front of this app — browsers ignore HSTS on a plain-HTTP
  response per spec, so it's not misleading in the meantime, just not
  yet load-bearing; see "No TLS anywhere" in
  `docs/runbooks/deployment.md`'s "Known limitations").

## Secret exposure

- **Fail-fast startup guard**: `create_app()` now raises `RuntimeError`
  if `FLASK_ENV=production` and `SECRET_KEY` is still the literal
  placeholder `"change-me"` — someone skipped the setup step in
  `docs/runbooks/deployment.md` rather than a secret nobody actually set.
  Verified staging's real `.env.staging` already has a real, generated
  `SECRET_KEY` (unaffected by this guard) before relying on it.
- **Removed an unused, misleading auth dependency**: `Flask-JWT-Extended`
  (`JWTManager`) was initialized (`jwt.init_app(app)`) but never actually
  used anywhere — every real token verification path is the custom
  PyJWT-based `app/security/jwt_verifier.py`. An initialized-but-inert
  second auth library sitting in the app is exactly the kind of thing
  that can mislead a future security review into assuming it does
  something; removed entirely (`app/extensions.py`, `app/__init__.py`,
  `requirements.txt`), along with the `JWT_SECRET_KEY` config value it
  was the only consumer of (also removed from `.env.example`,
  `.env.staging.example`, the real `.env.staging`, and
  `.github/workflows/test.yml`).

## Dependency and container vulnerability scanning

New `.github/workflows/security.yml` (CHECKLIST.md's own target repo
shape already listed `security.yml` alongside `test.yml`/`deploy.yml` —
this was the missing one): `pip-audit` against `apps/api/requirements.txt`,
`npm audit --omit=dev` against `apps/web` (production dependencies
only — `npm audit --omit=dev` is what's actually shipped in the built
image, not the dev/build/test toolchain), and `trivy` image scans of both
built images (fails only on `CRITICAL` vulnerabilities with a fix
available — `--ignore-unfixed`, since base-image OS packages routinely
carry unfixed HIGH/CRITICAL findings nothing here can act on; a second,
always-green step reports the full HIGH/CRITICAL list for visibility).
Runs on every push/PR to master plus a weekly schedule, so a CVE
disclosed against an already-merged, unchanged dependency is still
caught.

**Real findings from running all of this for real while writing it, not
just wiring the CI steps blind:**

- `pip-audit` found real CVEs with available fixes in `Flask` (3.0.3,
  `PYSEC-2026-2151`), `Flask-Cors` (4.0.1, three separate CVEs —
  `PYSEC-2024-71`, `PYSEC-2026-1383/1384/1385`), and `python-dotenv`
  (1.0.1, `PYSEC-2026-2270`). Bumped to `Flask==3.1.3`,
  `Flask-Cors==6.0.0`, `python-dotenv==1.2.2` — the full backend suite
  (243 tests) re-verified green against all three upgrades together.
- `pytest` (8.2.2, `PYSEC-2026-1845`, fixed in 9.0.3) is a known,
  **deliberately deferred** finding: an 8→9 major version is its own
  compatibility surface for this project's fixture-heavy suite, the
  advisory concerns pytest's own test-collection machinery running
  against untrusted code (not a risk for this repository's trusted test
  suite), and the running container's `CMD` is gunicorn, never
  `pytest`, even though the package is present in the image (no
  separate prod/dev requirements split exists). Tracked by name in
  `requirements.txt`'s own comment and excluded from the CI gate by ID
  (`pip-audit --ignore-vuln PYSEC-2026-1845`), not by silencing the
  whole job — a *new* vulnerability in anything else still fails it.
- `npm audit` (no `--omit=dev`) found 5 findings (up to **critical** —
  a Vitest UI arbitrary-file-read advisory) entirely in the
  `vite`/`vitest`/`esbuild`/`vite-node` dev/build/test toolchain — none
  of it ships in `apps/web/Dockerfile`'s built nginx image (confirmed:
  `npm audit --omit=dev` reports **0 vulnerabilities**). Fixing them
  means `vite` 5→8 and `vitest` 2→5, both major version jumps with real
  breaking-change surface for this project's test/build config —
  deliberately deferred for the same proportionate-effort reasoning as
  pytest above, and for the same reason: zero production exposure, a CI
  gate that would otherwise be red from day one over an accepted,
  documented risk. `npm audit --omit=dev` (0 vulnerabilities) is what
  actually gates the build; the full report runs alongside it for
  visibility, never failing.
- `trivy` found real, **fixed** `CRITICAL` OS-package vulnerabilities in
  both built images' base layers: `perl-base` in `creditguard-api`
  (`python:3.12-slim`, three CVEs including `CVE-2026-13221`) and
  `libcrypto3`/`libssl3` in `creditguard-web` (`nginx:1.27-alpine`,
  `CVE-2026-31789`, an OpenSSL heap-overflow). Fixed by adding an
  explicit `apt-get upgrade -y` (`apps/api/Dockerfile`) and `apk upgrade`
  (`apps/web/Dockerfile`) before installing anything else — picks up
  whatever patched packages the upstream Debian/Alpine security repos
  already have, rather than waiting for a fresh base-image tag. Rebuilt
  both images and re-scanned: **0 critical fixed vulnerabilities
  remaining** in either, confirmed via `trivy image --severity CRITICAL
  --ignore-unfixed` against the rebuilt images, not assumed from reading
  the Dockerfile diff.

## Audit-write protection

Unchanged this pass — already covered by
`apps/api/tests/integration/test_db_permissions.py` (CHECKLIST.md Phase
5): the restricted `creditguard_app` role can `INSERT` into
`audit_events`/`audit_integrity_checks` (append-only) but has no
`UPDATE`/`DELETE`/DDL rights on them at all, enforced by Postgres itself,
not just application code. Re-verified passing against real Postgres
this pass alongside every other change.

## Existing suites confirmed unaffected

Backend: 243 passed (SQLite; up from 215 before this pass — 28 new
tests: 2 JWT attack regressions, 2 scoring-service length-validation
tests, 1 scoring-service concurrency test carried over from Phase 7C,
6 cross-tenant isolation tests, 5 security-hardening tests, 4 rate-limit
tests, 4 new mechanical-sweep route parametrizations, 1 request-size
test, and the pre-existing counts these build on); ruff clean. Frontend
untouched this pass (no frontend files changed) — not re-verified beyond
what Phase 7C already confirmed. Staging: rebuilt with every change in
this document, full smoke suite (27/27) and resilience suite (4/4) both
re-verified passing against the rebuilt deployment; CORS and rate
limiting additionally confirmed with real `curl`/HTTP calls against the
running staging API, not only through the test suites.
