# CreditGuard XAI

Commercial credit decision governance platform: reproducible ML scoring, explainability (SHAP), fairness monitoring, and tamper-evident audit evidence, built for multi-tenant lenders.

Status: proposed commercial engineering specification — not production-ready until the acceptance tests in `docs/` are completed.

## Repository layout

- `apps/api` — Flask application (API, domain services, workers)
- `apps/web` — React + TypeScript dashboard
- `apps/workers/ml` — training, evaluation, explanation, and fairness pipeline
- `packages/api-contracts`, `packages/model-contracts` — versioned shared contracts
- `infra` — Docker, Terraform, monitoring config
- `docs` — architecture, API, security, model cards, runbooks

See `docs/architecture/ERD.md` for the full engineering requirements document.

## Getting started

```
cp .env.example .env
docker-compose up --build
```

## Repository rules

1. Raw personal data must never be committed to Git.
2. Model binaries belong in an artefact store, not the source repository.
3. Secrets belong in environment configuration or a secret manager.
4. All database changes require migrations.
5. API contracts are version-controlled (`packages/api-contracts`).
6. Every new feature needs tests.
7. The commercial branch must not silently change the academic model's behaviour.
