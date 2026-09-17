.PHONY: up down api-install api-run api-test api-test-migrations api-db-upgrade web-install web-run web-test ml-build ml-test ml-train ml-german-credit lint

up:
	docker compose up --build

down:
	docker compose down

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
