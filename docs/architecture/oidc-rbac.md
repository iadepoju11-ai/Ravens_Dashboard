# OIDC authentication & permission-based authorization

CHECKLIST.md Phase 6 ("Authentication + RBAC"). Started as one endpoint
(`POST /score`) to prove the pattern; now covers scoring, decisions,
models, fairness, and audit, plus a real login flow in the React app
(Overview page only so far).

## The identity boundary

```
OIDC provider (Keycloak locally; any OIDC-compliant IdP in production)
     │  issues a signed access token
     ▼
React app (apps/web) -- Authorization Code + PKCE
     │  Authorization: Bearer <token>
     ▼
Flask API — app/security/
     ├── jwt_verifier.py   verifies signature (via the issuer's JWKS),
     │                     issuer, audience, expiry
     ├── provisioning.py   maps the token's `sub` to a User row
     │                     (just-in-time on first login)
     └── permissions.py    role claims -> permissions
     ▼
Identity(user_id, tenant_id, oidc_subject, email, roles)
```

The provider (Keycloak/enterprise IdP) owns **authentication**: proving who
the caller is. This application owns **tenancy and authorization**: which
tenant that person belongs to and what they're allowed to do. Concretely:
a token's `tenant_id` claim only matters the *first* time a given `sub` is
seen — `app/security/provisioning.py` creates the `User` row from it, but
every later request uses that stored `User.tenant_id`, not the token
claim. The token can't move a user between tenants after the fact; only
this application's own data can. CLAUDE.md is explicit that a client
(or, here, a stale/altered claim) is never trusted for tenant identity.

## Roles and permissions

Roles are carried as claims on the token (Keycloak's `realm_access.roles`)
— there's no separate role-assignment table in this application's own
database. `app/security/permissions.py` maps each role to the
permissions it grants; routes check permissions (`require_permission`),
never role names directly, so a bank asking for a different permission
model later is a change to one dict, not a grep across every route.

| Role | Permissions |
| --- | --- |
| `admin` | `users:manage`, `tenant:manage`, `decisions:read`, `audit:read`, `fairness:read` |
| `credit_analyst` | `decisions:create`, `decisions:read` |
| `compliance_officer` | `decisions:read`, `models:read`, `models:create`, `models:approve`, `models:deploy`, `fairness:read`, `fairness:review` |
| `auditor` | `audit:read`, `audit:export`, `audit:verify` |
| `data_protection_officer` | `datasets:read`, `audit:read` |

`compliance_officer` owns the whole model lifecycle (`models:create` and
`models:deploy`, not just `models:approve`) because no dedicated data-
scientist/model-ops role exists among the five CreditGuard roles —
revisit if that changes. `audit:read` vs `audit:verify` is a real split,
not a naming accident: `/audit/events` and `/audit/integrity-status` only
*read* recorded state (`audit:read`, also granted to
`data_protection_officer`), while `/audit/events/<id>/verify` and
`/audit/verify-chain` actually *run* a fresh integrity check and persist
its result (`audit:verify`, `auditor` only).

`admin`'s three read permissions were added while building the real
Overview page (below): it needs `decisions:read` + `audit:read` +
`fairness:read` together, and no other single role holds all three (each
is deliberately scoped to its own workflow). An administrator overseeing
a tenant reasonably needs to see the same dashboard, without gaining any
of the *write* permissions those roles carry — `admin` still cannot
create a decision, approve a model, or verify the audit chain.

The pre-existing `roles`/`user_roles` tables (`app/models/role.py`) predate
this design and stay schema-only for now — they were never wired to
anything, and roles-as-claims (above) is the actual source of truth.
Revisit if this application ever needs to *assign* roles itself rather
than reading them from the IdP.

## What's actually wired up

Every route below follows the same three-line shape:

```python
identity = authenticate()
require_permission(identity, "decisions:create")
tenant = resolve_tenant_by_id(identity.tenant_id)  # not the X-Tenant-Id header
```

`authenticate()` extracts the bearer token, verifies it, resolves/
provisions the `User`, builds the `Identity`, and stashes it
(`set_current_identity`) for the rest of the request. `TokenValidationError`
(401) and `AuthorizationError` (403) are handled by a global Flask error
handler (`app/__init__.py`) — a route that calls `authenticate()`/
`require_permission()` never needs its own try/except for either; only
`TenantResolutionError` (still per-route, matching the pre-existing
header-based pattern) needs one.

| Endpoint | Permission |
| --- | --- |
| `POST /score` | `decisions:create` |
| `GET /decisions`, `GET /decisions/<id>` | `decisions:read` |
| `GET /models` | `models:read` |
| `POST /models` | `models:create` |
| `POST /models/<id>/approve` | `models:approve` |
| `POST /models/<id>/deploy` | `models:deploy` |
| `GET /fairness/reports`, `GET /fairness/reports/<id>` | `fairness:read` |
| `GET /audit/events`, `GET /audit/integrity-status` | `audit:read` |
| `GET /audit/events/<id>/verify`, `GET /audit/verify-chain` | `audit:verify` |

Approving and deploying a model version now also record who did it —
`ModelVersion.approved_by`/`ModelDeployment.deployed_by` are set from
`identity.user_id`, which was impossible before this workstream (there
was no authenticated user to attribute either action to).

`/datasets`, `/monitoring/*`, and `/tenants` are unchanged and still trust
the `X-Tenant-Id` header (`app/infrastructure/security/tenant_context.py`)
— not named in this phase's scope; migrate them the same way if/when
they need it.

## Frontend (apps/web)

Real login only, Overview page only — the other stub pages
(`NotYetBuiltPage`) are unchanged. Authorization Code + PKCE against the
`creditguard-web` Keycloak client (public, no secret, browser-appropriate
— never the password/direct grant used for manual API testing), via
`react-oidc-context`:

- `src/services/authConfig.ts` — the one place `react-oidc-context` is
  configured; nothing else imports it directly.
- `src/services/useIdentity.ts` — the one seam the rest of the app reads
  identity through (`isAuthenticated`, `accessToken`, `tenantId`, `email`,
  `login`/`logout`), same shape as the backend's `get_current_identity()`.
  `tenantId` here is informational only (populates the `X-Tenant-Id`
  header the few not-yet-migrated endpoints still need) — it is never
  what makes the backend trust a tenant; the backend derives that itself
  from the verified access token, same as always.
- `src/app/AuthGate.tsx` — gates the whole app behind a real session
  (loading / sign-in screen / error), so `OverviewPage` and everything
  else under it can assume `isAuthenticated` is true and never has its
  own "please log in" branch.
- `apiClient.ts`'s `apiFetch` now sends both `Authorization: Bearer` (for
  migrated endpoints) and `X-Tenant-Id` (for the ones that still need it)
  on every call — harmless for either side to receive the one it ignores.

Verified as an actual Authorization Code + PKCE round trip, not just unit
tests against a mocked identity: no browser automation is available in
this environment, so the verification script drove the real HTTP flow
instead (build a PKCE challenge, hit Keycloak's real `/auth` endpoint,
submit the real login form, capture the redirect's authorization code,
exchange it at the real `/token` endpoint, then call the real API with
the resulting access token) — this is the exact protocol sequence
`oidc-client-ts` performs internally, just scripted instead of clicked.
It came back clean: correct `iss`/`aud`/`tenant_id`/roles on the issued
token, and a real 200 from `GET /decisions`. A human still needs to
click through the actual browser UX at least once — that part is not
substitutable.

## Testing approach

Unit and integration tests (`tests/unit/test_jwt_verifier.py`,
`tests/unit/test_permissions.py`,
`tests/integration/test_score_authorization.py`,
`tests/integration/test_endpoint_authorization.py`) use a locally
generated RSA keypair standing in for Keycloak's signing key, with the
JWKS lookup monkeypatched out (`tests/conftest.py`'s `_fake_jwk_client`
fixture, autouse) — fast, no live Keycloak needed, and still exercises
the real signature/issuer/audience/expiry validation logic in
`app/security/jwt_verifier.py`, not a mock of it.
`test_endpoint_authorization.py` parametrizes the mechanical 401
(no token) and 403 (wrong role) checks across every migrated endpoint in
one pass, plus a couple of hand-picked cross-tenant checks for the
state-changing model lifecycle actions; `test_score_authorization.py` and
`test_audit_security.py` cover the rest of `POST /score` and the audit
chain in more depth.

The one thing that can't be faked is Keycloak's own behavior — see
"Two Keycloak gotchas" in `docs/local-development.md` for the real
end-to-end verification performed against the dockerized container, and
the two configuration traps it caught (a claim silently missing, not
erroring) that no amount of testing against a fake JWKS could have found.
