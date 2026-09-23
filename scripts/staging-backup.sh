#!/usr/bin/env bash
set -euo pipefail

# Backs up the staging PostgreSQL database (CHECKLIST.md Phase 7F).
# Timestamped custom-format pg_dump (same format/flags
# docs/backup-restore.md's dev-level drill already verified round-trips
# this schema correctly, including audit-chain timestamp precision),
# retained locally under backups/staging/ (gitignored -- dumps contain
# real tenant/decision data, never committed).
#
# No scheduler runs this automatically -- same "no scheduler wired up"
# reasoning as `flask audit verify-all-tenants` and
# `flask events publish-outbox` (app/cli.py): picking cron/a Kubernetes
# CronJob/GitHub Actions-on-a-schedule is a real infra decision for
# wherever this actually gets deployed, not something to bolt on here.
# This script exits non-zero on failure specifically so it's safe to
# wire into whichever scheduler is chosen later, the same convention
# those two CLI commands already follow.
#
# Usage: scripts/staging-backup.sh
# Env:   BACKUP_RETENTION_COUNT (default 7) -- how many recent backups
#        to keep; older ones are pruned after a successful backup.

RETENTION_COUNT="${BACKUP_RETENTION_COUNT:-7}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$REPO_ROOT/backups/staging"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/creditguard-staging-$TIMESTAMP.dump"
COMPOSE=(docker compose -f "$REPO_ROOT/docker-compose.staging.yml" --env-file "$REPO_ROOT/.env.staging")

mkdir -p "$BACKUP_DIR"

echo "[backup] $(date -u +%Y-%m-%dT%H:%M:%SZ) starting: $BACKUP_FILE"

# -F c (custom format): compressed, supports selective/parallel restore,
# required for pg_restore below (unlike a plain SQL dump). Written to a
# .tmp path first and renamed only on success, so a failed/interrupted
# dump never leaves a truncated file that looks like a valid backup.
if "${COMPOSE[@]}" exec -T postgres pg_dump -U creditguard -F c -d creditguard > "$BACKUP_FILE.tmp"; then
  mv "$BACKUP_FILE.tmp" "$BACKUP_FILE"
  SIZE="$(du -h "$BACKUP_FILE" | cut -f1)"
  echo "[backup] $(date -u +%Y-%m-%dT%H:%M:%SZ) success: $BACKUP_FILE ($SIZE)"
else
  rm -f "$BACKUP_FILE.tmp"
  echo "[backup] $(date -u +%Y-%m-%dT%H:%M:%SZ) FAILED" >&2
  exit 1
fi

# Retention: keep only the RETENTION_COUNT most recent backups. Host-local
# only -- there is no off-host/cloud copy (see docs/runbooks/disaster-recovery.md's
# "Known limitations"), so this bounds local disk usage, nothing more.
mapfile -t existing < <(ls -1t "$BACKUP_DIR"/creditguard-staging-*.dump 2>/dev/null || true)
if [ "${#existing[@]}" -gt "$RETENTION_COUNT" ]; then
  for old in "${existing[@]:$RETENTION_COUNT}"; do
    echo "[backup] pruning old backup: $old"
    rm -f "$old"
  done
fi
