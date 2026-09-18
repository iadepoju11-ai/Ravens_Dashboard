# OIDC authentication & permission-based authorization

CHECKLIST.md Phase 6 ("Authentication + RBAC"). This is the first slice of
that work — one endpoint (`POST /score`) migrated end to end, proving the
pattern before it's rolled out everywhere else.

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
| `compliance_officer` | `decisions:read`, `models:read`, `models:approve`, `fairness:read`, `fairness:review` |
| `auditor` | `audit:read`, `audit:export`, `audit:verify` |
| `data_protection_officer` | `datasets:read`, `audit:read` |

The pre-existing `roles`/`user_roles` tables (`app/models/role.py`) predate
this design and stay schema-only for now — they were never wired to
anything, and roles-as-claims (above) is the actual source of truth.
Revisit if this application ever needs to *assign* roles itself rather
than reading them from the IdP.

## What's actually wired up

Only `POST /score` (`app/api/v1/decisions.py`) uses this. It:

1. Calls `authenticate()` — extracts the bearer token, verifies it,
   resolves/provisions the `User`, builds the `Identity`.
2. Calls `require_permission(identity, "decisions:create")`.
3. Resolves the tenant from `identity.tenant_id`
   (`resolve_tenant_by_id`), not the `X-Tenant-Id` header the rest of
   the API still uses.

Every other endpoint (`/decisions`, `/models`, `/fairness`, `/audit`, …)
is unchanged and still trusts the `X-Tenant-Id` header
(`app/infrastructure/security/tenant_context.py`) — deliberately: this was
built as one vertical slice to prove the pattern against real
infrastructure before repeating it five more times. Migrating the rest is
the next unit of work, along with cross-tenant/401/403 integration tests
for each of them (see CHECKLIST.md).

## Testing approach

Unit and integration tests (`tests/unit/test_jwt_verifier.py`,
`tests/unit/test_permissions.py`,
`tests/integration/test_score_authorization.py`) use a locally generated
RSA keypair standing in for Keycloak's signing key, with the JWKS lookup
monkeypatched out (`tests/conftest.py`'s `_fake_jwk_client` fixture,
autouse) — fast, no live Keycloak needed, and still exercises the real
signature/issuer/audience/expiry validation logic in
`app/security/jwt_verifier.py`, not a mock of it.

The one thing that can't be faked is Keycloak's own behavior — see
"Two Keycloak gotchas" in `docs/local-development.md` for the real
end-to-end verification performed against the dockerized container, and
the two configuration traps it caught (a claim silently missing, not
erroring) that no amount of testing against a fake JWKS could have found.
