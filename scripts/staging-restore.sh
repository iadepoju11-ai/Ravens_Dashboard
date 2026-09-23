#!/usr/bin/env bash
set -euo pipefail

# Restores a staging PostgreSQL backup (CHECKLIST.md Phase 7F).
# Drops and recreates the database first -- this is the genuine
# "the database was lost/corrupted" disaster-recovery path (see
# docs/backup-restore.md's dev-level equivalent), not a merge into
# whatever's currently there. --no-owner avoids failures if the
# restoring role's name doesn't exactly match what was dumped.
#
# Stops the `api` container before dropping the database and restarts
# it after restoring -- a real finding from actually running this drill,
# not a hypothetical: `DROP DATABASE` fails outright
# ("database ... is being accessed by other users") while the api
# container's own SQLAlchemy connection pool holds live connections to
# it. A real production restore would need the application offline for
# exactly this reason anyway (it can't safely serve requests against a
# half-restored database) -- this script makes that explicit and
# automatic rather than a manual prerequisite someone has to remember.
#
# Does NOT run `flask db upgrade` afterward -- callers must do that
# explicitly once the restore completes, in case the app version being
# restored-to expects migrations newer than what the backup contains
# (docs/runbooks/disaster-recovery.md's restore drill does this step
# explicitly and verifies it's a safe no-op when the backup is already
# at head).
#
# Usage: scripts/staging-restore.sh <backup-file>

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <backup-file>" >&2
  exit 1
fi

BACKUP_FILE="$1"
if [ ! -f "$BACKUP_FILE" ]; then
  echo "backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose -f "$REPO_ROOT/docker-compose.staging.yml" --env-file "$REPO_ROOT/.env.staging")

echo "[restore] $(date -u +%Y-%m-%dT%H:%M:%SZ) stopping api (it holds live connections DROP DATABASE can't run alongside)"
"${COMPOSE[@]}" stop api

echo "[restore] $(date -u +%Y-%m-%dT%H:%M:%SZ) dropping and recreating the staging database"
"${COMPOSE[@]}" exec -T postgres psql -U creditguard -d postgres -c "DROP DATABASE creditguard;"
"${COMPOSE[@]}" exec -T postgres psql -U creditguard -d postgres -c "CREATE DATABASE creditguard OWNER creditguard;"

echo "[restore] $(date -u +%Y-%m-%dT%H:%M:%SZ) restoring from $BACKUP_FILE"
"${COMPOSE[@]}" exec -T postgres pg_restore -U creditguard -d creditguard --no-owner < "$BACKUP_FILE"

echo "[restore] $(date -u +%Y-%m-%dT%H:%M:%SZ) restarting api"
"${COMPOSE[@]}" start api

echo "[restore] $(date -u +%Y-%m-%dT%H:%M:%SZ) done -- run 'flask db upgrade' next if the restored backup might predate the current schema"
