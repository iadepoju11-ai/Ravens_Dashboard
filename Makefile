.PHONY: up down api-install api-run api-test api-test-migrations api-db-upgrade web-install web-run web-test ml-build ml-test ml-train ml-german-credit lint staging-up staging-down staging-seed staging-logs staging-ps staging-smoke-test staging-redeploy staging-load-test staging-resilience-test

up:
	docker compose up --build

down:
	docker compose down

# --- Staging (CHECKLIST.md Phase 7A) ---
# Separate compose file/project (docker-compose.staging.yml, project name
# creditguard-staging) so it can run alongside the dev stack above without
# port/volume collisions. Secrets come from .env.staging (gitignored --
# copy .env.staging.example and fill in real values first, see
# docs/runbooks/deployment.md for the full procedure including rollback).

staging-up:
	docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build

# Idempotent -- safe to run after every staging-up, not just the first.
staging-seed:
	docker compose -f docker-compose.staging.yml --env-file .env.staging exec api flask seed staging

staging-down:
	docker compose -f docker-compose.staging.yml --env-file .env.staging down

staging-logs:
	docker compose -f docker-compose.staging.yml --env-file .env.staging logs -f

staging-ps:
	docker compose -f docker-compose.staging.yml --env-file .env.staging ps

# Requires `pip install -r tests/smoke/requirements.txt` once, and a
# staging stack that's already up (staging-up) and seeded (staging-seed).
staging-smoke-test:
	cd tests/smoke && python -m pytest . -v

# The whole redeploy sequence in one command -- see
# docs/runbooks/deployment.md for what to do if this fails partway
# through (rollback procedure).
staging-redeploy: staging-up staging-seed staging-smoke-test

# CHECKLIST.md Phase 7C. Requires `pip install -r tests/load/requirements.txt`
# once, and a staging stack already up + seeded. Prints a measured
# latency/throughput report -- see docs/performance/staging-baseline.md
# for what a real run of this produced and how to read it. Override
# concurrency/volume: `make staging-load-test ARGS="--concurrency 25 --total-requests 250"`.
staging-load-test:
	cd tests/load && python load_test_score.py $(ARGS)

# CHECKLIST.md Phase 7C. Requires `pip install -r tests/resilience/requirements.txt`
# once, and a staging stack already up + seeded. Only the non-destructive
# duplicate-request-safety test runs by default; the tests that stop/
# restart real staging containers (Postgres, Kafka, the api container)
# require the explicit RUN_RESILIENCE_TESTS=1 opt-in -- see
# tests/resilience/conftest.py and docs/runbooks/deployment.md.
staging-resilience-test:
	cd tests/resilience && RUN_RESILIENCE_TESTS=1 python -m pytest . -v

api-install:
	cd apps/api && pip install -r requirements.txt

api-run:
	cd apps/api && python -m app.main

api-test:
	cd apps/api && python -m pytest tests/unit tests/integration

# Requires a reachable Postgres (see docker-compose.yml's postgres service,
# host port 5433) — exercises the real Alembic migration path.
api-test-migrations:
	cd apps/api && python -m pytest tests/test_migrations.py -v

api-db-upgrade:
	cd apps/api && flask db upgrade

web-install:
	cd apps/web && npm install

web-run:
	cd apps/web && npm run dev

web-test:
	cd apps/web && npm test

ml-build:
	docker build -t creditguard-ml-workers ./apps/workers

# Override HOME_CREDIT_DATA_DIR to point at wherever the Home Credit CSVs
# actually live, e.g.:
#   make ml-train HOME_CREDIT_DATA_DIR=/c/path/to/home_credit
HOME_CREDIT_DATA_DIR ?= $(CURDIR)/data/home_credit

ml-test: ml-build
	docker run --rm creditguard-ml-workers python -m pytest tests/ -v

ml-train: ml-build
	docker run --rm \
		-v "$(HOME_CREDIT_DATA_DIR):/workers/data/home_credit:ro" \
		-v "$(CURDIR)/model_artifacts:/workers/model_artifacts" \
		creditguard-ml-workers

# Override GERMAN_CREDIT_DATA_DIR similarly to HOME_CREDIT_DATA_DIR above.
GERMAN_CREDIT_DATA_DIR ?= $(CURDIR)/data/german_credit

ml-german-credit: ml-build
	docker run --rm \
		-v "$(GERMAN_CREDIT_DATA_DIR):/workers/data/german_credit:ro" \
		-v "$(CURDIR)/model_artifacts:/workers/model_artifacts" \
		creditguard-ml-workers python -m ml.german_credit_pipeline

lint:
	cd apps/api && ruff check app
	cd apps/workers && ruff check ml tests
	cd apps/web && npm run lint
