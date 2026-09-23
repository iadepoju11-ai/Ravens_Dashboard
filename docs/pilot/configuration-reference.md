# Configuration reference

Part of the pilot package (`docs/pilot/README.md`). Every environment
variable this application reads, verified against the real
`.env.example` (local development) and `.env.staging.example` (staging
template) files — not a reconstructed or idealized list. **Never copy
the dev defaults into a real deployment** — `change-me`,
`creditguard`/`creditguard_app_dev_password`, and similar are
intentionally public, well-known local-dev convenience values.

## API

| Variable | Purpose | Dev default | Staging |
| --- | --- | --- | --- |
| `FLASK_ENV` | `development` or `production`. In `production`, the app refuses to start if `SECRET_KEY` is still the literal placeholder `change-me` — a fail-fast guard, not a silent insecure default. | `development` | `production` |
| `SECRET_KEY` | Flask session-signing secret. | `change-me` (placeholder — must be a real generated value) | Generated (`openssl rand -hex 16` or equivalent) |
| `LOG_LEVEL` | Structured JSON logging verbosity. | `INFO` | `INFO` |
| `MAX_CONTENT_LENGTH` | Request body size cap in bytes (a `413` beyond this). | `1000000` (1 MB) | Same |
| `CORS_ALLOWED_ORIGINS` | Comma-separated list of origins allowed to make cross-origin browser requests. Never `*` — an origin not in this list gets no CORS header at all. | The dev frontend's own origin | The staging frontend's own origin |
| `RATELIMIT_DEFAULT` | App-wide rate limit, per remote address. `POST /score` has its own stricter, hardcoded override (30/minute) regardless of this value. | `300 per minute` | Same |

## Database

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Owner/DDL connection — used only for running migrations, never what the running application connects as day-to-day. |
| `APP_DB_PASSWORD` / `APP_DATABASE_URL` | The restricted runtime role's credentials — what the API actually connects as. Full CRUD on ordinary tables; append-only (`INSERT` only, no `UPDATE`/`DELETE`) on audit tables; no DDL rights at all. `APP_DB_PASSWORD` must match what the database-role-creation migration used to create the role, or the API cannot authenticate. |
| `MIGRATION_TEST_DATABASE_URL` (dev only) | A deliberately separate Postgres instance the migration test suite downgrades-then-upgrades against, so it never wipes data in the main development database. |
| `DB_OWNER_PASSWORD` (staging only) | The owner role's password, used by the one-shot `migrate` service. |

## Kafka

| Variable | Purpose |
| --- | --- |
| `KAFKA_ENABLED` | `false` by default everywhere. The transactional outbox records every event in Postgres regardless of this flag — nothing is lost while it's disabled. There is no consumer of these topics yet (see `known-limitations.md`), so enabling it has no downstream effect beyond publishing to topics nothing reads. |
| `KAFKA_BOOTSTRAP_SERVERS` | Broker address. |

## Identity (OIDC)

| Variable | Purpose |
| --- | --- |
| `OIDC_ISSUER` | Must exactly match the `iss` claim on tokens the API actually receives — both the browser and the API need to agree on one issuer string, which can differ from the network path used to *fetch* signing keys. |
| `OIDC_JWKS_URL` | Where the API fetches the issuer's signing keys — a container-reachable address, not necessarily the same as `OIDC_ISSUER`. |
| `OIDC_AUDIENCE` | Expected token audience. |
| `KEYCLOAK_ADMIN_PASSWORD` (staging only) | Keycloak's own admin console password — unrelated to any application-level credential. |

**Swapping identity providers**: nothing in this application is
Keycloak-specific — `app/security/jwt_verifier.py` only ever does
standard OIDC verification (signature via the issuer's published JWKS,
issuer, audience, expiry) against whatever `OIDC_ISSUER`/`OIDC_JWKS_URL`
point at. Pointing these at a real enterprise IdP is a configuration
change, not a code change — provided that IdP's tokens carry the
`tenant_id` and `realm_access.roles` claims this application's identity
resolution and RBAC expect (see `roles-and-permissions.md`); mapping
those from whatever claim shape a specific enterprise IdP produces may
need a small adapter, not evaluated against any specific vendor's IdP
yet.

## Model / dataset artefact store

| Variable | Purpose |
| --- | --- |
| `MODEL_REGISTRY_URI` | Where trained model artifacts are read from. Local filesystem path by default (`file://./model_artifacts`) — a real production deployment would point this at a real artefact store, not a bind-mounted directory (see `known-limitations.md`). |
| `DATASET_STORE_URI` | Same pattern, for processed dataset files. |

## Frontend (baked in at image build time)

| Variable | Purpose |
| --- | --- |
| `VITE_API_BASE_URL` | The API's base URL the SPA calls. |
| `VITE_OIDC_AUTHORITY` / `VITE_OIDC_CLIENT_ID` / `VITE_OIDC_REDIRECT_URI` | The browser-side OIDC Authorization Code + PKCE configuration (a public client, no client secret). |

**Important**: these `VITE_*` values are compiled into the static
JavaScript bundle at Docker **build** time (Vite inlines them), not read
at container start. Changing any of them means rebuilding the `web`
image, not just restarting the container or editing an env file on a
running host.
