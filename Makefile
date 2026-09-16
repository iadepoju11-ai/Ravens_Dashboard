.PHONY: up down api-install api-run api-test api-test-migrations api-db-upgrade web-install web-run web-test lint

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

lint:
	cd apps/api && ruff check app
	cd apps/web && npm run lint
