# Roles and permissions

Part of the pilot package (`docs/pilot/README.md`). Verified against the
real `ROLE_PERMISSIONS` mapping (`apps/api/app/security/permissions.py`)
— every permission string below is exactly what the code checks, not an
approximation.

## Where roles come from

Roles are carried as claims on the OIDC access token
(`realm_access.roles`) — there is no separate role-assignment table or
admin UI in this application itself. The identity provider is the
source of truth for "who has which role"; this application only maps
role → permission and enforces it on every request. A caller can hold
more than one role at once; their effective permissions are the union
of all roles they carry.

## The five roles

| Role | Intended for | Full permission set |
| --- | --- | --- |
| `credit_analyst` | Front-line staff scoring applications | `decisions:create`, `decisions:read`, `tenant:read` |
| `compliance_officer` | Model risk / governance staff | `decisions:read`, `models:read`, `models:create`, `models:approve`, `models:deploy`, `datasets:read`, `datasets:create`, `monitoring:read`, `fairness:read`, `fairness:review`, `review:read`, `review:resolve`, `tenant:read` |
| `auditor` | Internal/external audit | `audit:read`, `audit:export`, `audit:verify`, `tenant:read` |
| `data_protection_officer` | Privacy/data governance | `datasets:read`, `audit:read`, `tenant:read` |
| `admin` | Full tenant administration | Every permission above, unioned, plus `users:manage` and `tenant:manage` (which no other role has) |

Notably: **no role, including `admin`, is a cross-tenant platform
administrator.** `admin` has every permission *within its own tenant*;
`GET /tenants` always returns only the caller's own tenant record for
every role, never a real multi-tenant listing.

## Why compliance_officer owns the whole model lifecycle

There is deliberately no separate "data scientist" or "model ops" role
among the five — `compliance_officer` owns register → approve → deploy
as one continuous responsibility, plus the datasets those models cite
and model-risk monitoring. This was a deliberate scope decision for the
current five-role set, not an oversight; revisit if a pilot's actual org
chart needs a narrower split (e.g. a role that can register a model
version but not approve/deploy it).

## Endpoint → permission map

| Endpoint | Required permission |
| --- | --- |
| `POST /score` | `decisions:create` |
| `GET /decisions`, `GET /decisions/{id}` | `decisions:read` |
| `GET /models` | `models:read` |
| `POST /models` | `models:create` |
| `POST /models/{id}/approve` | `models:approve` |
| `POST /models/{id}/deploy` | `models:deploy` |
| `GET /datasets` | `datasets:read` |
| `POST /datasets` | `datasets:create` |
| `GET /fairness/reports`, `GET /fairness/reports/{id}` | `fairness:read` |
| `POST /fairness/evaluate` | `fairness:review` |
| `GET /audit/events`, `GET /audit/integrity-status` | `audit:read` |
| `GET /audit/events/{id}/verify`, `GET /audit/verify-chain` | `audit:verify` |
| `GET /audit/export` | `audit:export` |
| `GET /monitoring/metrics`, `/monitoring/alerts`, `/monitoring/observability` | `monitoring:read` |
| `GET /reviews`, `GET /reviews/{id}` | `review:read` |
| `POST /reviews/{id}/resolve` | `review:resolve` |
| `GET /tenants`, `GET /tenants/{id}` | `tenant:read` (every role holds this — reading your own tenant carries no cross-tenant risk) |

The full machine-readable contract, including exact request/response
shapes and error codes per endpoint, is `openapi/creditguard-openapi.yaml`.

## Verified, not assumed

Every permission boundary in this table has a passing automated test —
a mechanical sweep proving every endpoint rejects a caller missing the
required permission (`403`), plus a dedicated cross-tenant test suite
proving a caller with the *right* permission still cannot reach another
tenant's decisions, models, fairness reports, reviews, audit records, or
exports (`404`, indistinguishable from "doesn't exist," never a `403`
that would confirm the id is real). See
`docs/architecture/security-hardening.md` for the full verification
write-up — this was a systematic audit, not an assumption that RBAC
"just works" because the code looks right.
