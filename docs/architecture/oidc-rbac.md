# OIDC authentication & permission-based authorization

CHECKLIST.md Phase 6 ("Authentication + RBAC"). Started as one endpoint
(`POST /score`) to prove the pattern; now covers scoring, decisions,
models, fairness, and audit.

## The identity boundary

```
OIDC provider (Keycloak locally; any OIDC-compliant IdP in production)
     │  issues a signed access token
     ▼
Client (curl/tests today; the React app later)
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
| `admin` | `users:manage`, `tenant:manage` |
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
