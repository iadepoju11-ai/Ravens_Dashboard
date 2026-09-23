# CreditGuard XAI API — OpenAPI specification

CHECKLIST.md Phase 8A. `creditguard-openapi.yaml` documents the **actual
implemented** `/api/v1` contract, verified against the real route/model
source (`apps/api/app/api/v1/`, `apps/api/app/models/`) on 2026-09-23 —
not an aspirational or planned future API. Validated against OpenAPI
3.0.3 with both `openapi-spec-validator` (structural) and `@redocly/cli
lint` (semantic, 0 errors) before being committed.

Two things worth reading in the spec's own top-level `description`
before using it, because they differ from what a generic REST API
convention might lead you to expect: error bodies are always the flat
`{"error": "<string>"}` shape (never nested `error.code`/`message`/
`details`), and a `meta` key appears on only two responses in the entire
API (the generic `500` handler, and `GET /audit/export`'s success body)
— not on every response.

## Viewing it

No tooling is installed in this repo for this — any standard OpenAPI
viewer works against the file directly, e.g.:

```
npx @redocly/cli preview-docs openapi/creditguard-openapi.yaml
```

or paste its contents into <https://editor.swagger.io> (a third-party
site — don't paste anything containing real secrets or tenant data; the
spec itself contains neither).

## Keeping it accurate

This spec is hand-maintained, not generated from the Flask routes. If a
route's request/response shape, status codes, or required permission
changes, update this file in the same change — CHECKLIST.md Phase 8A's
entire point was documenting the *real* contract, and a stale spec is
worse than no spec (it actively misleads an integrator). There is no CI
check yet that fails a build when the two drift apart — a real, stated
gap, not silently assumed solved (see the production-readiness gap
register, CHECKLIST.md Phase 8C).
