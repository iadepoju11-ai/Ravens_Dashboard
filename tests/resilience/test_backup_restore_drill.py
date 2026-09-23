"""The real disaster-recovery drill (CHECKLIST.md Phase 7F): backup,
destroy the database, restore, and prove the *application* recovers --
not just that `pg_restore` exits 0.

score (before) -> backup -> score (after) -> DROP DATABASE -> restore
-> flask db upgrade -> API healthy -> authenticate -> the "before"
decision is back -> the "after" decision is gone (proves this is a
real point-in-time restore, not a no-op) -> the audit chain still
verifies post-restore.

The most destructive test in this repo -- it drops the entire staging
database. Requires RUN_RESILIENCE_TESTS=1, same opt-in as every other
destructive test in this directory (see conftest.py). Always restores
staging to a known-good seeded state in a `finally` block, pass or
fail: the backup taken during the test itself, re-seeded.
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests

from conftest import REPO_ROOT, REQUEST_TIMEOUT, auth_headers, compose, is_api_ready, wait_until

pytestmark = pytest.mark.destructive

BACKUP_SCRIPT = REPO_ROOT / "scripts" / "staging-backup.sh"
RESTORE_SCRIPT = REPO_ROOT / "scripts" / "staging-restore.sh"


def _bash() -> str:
    """Windows commonly has more than one `bash` on PATH (Git Bash, WSL's
    System32 shim, ...); subprocess's PATH search doesn't necessarily
    resolve the same one an interactive Git Bash shell would (`which
    bash`) -- WSL's bash.exe rejects a native Windows path like this
    script passes, with a confusing "No such file or directory". Prefer
    Git Bash explicitly when it's present; fall back to whatever `bash`
    resolves to otherwise (e.g. a non-Windows CI runner, where this
    ambiguity doesn't exist)."""
    for candidate in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.path.exists(candidate):
            return candidate
    return "bash"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=kwargs.pop("timeout", 60), **kwargs)


def _latest_backup() -> Path:
    backups = sorted((REPO_ROOT / "backups" / "staging").glob("creditguard-staging-*.dump"))
    assert backups, "no backup file was produced"
    return backups[-1]


def _score(api_base_url, token, application_reference, model_version_id):
    response = requests.post(
        f"{api_base_url}/score",
        json={
            "application_reference": application_reference,
            "features": {"income": 0.2},
            "model_version_id": model_version_id,
            "request_id": str(uuid.uuid4()),
        },
        headers=auth_headers(token),
        timeout=REQUEST_TIMEOUT,
    )
    assert response.status_code == 201, response.text
    return response.json()["decision"]["id"]


def test_backup_restore_drill_recovers_real_application_data(api_base_url, admin_token, deployed_model_version_id):
    drill_start = time.monotonic()
    wait_until(lambda: is_api_ready(api_base_url), timeout=30, description="API to be ready before the drill starts")

    before_reference = f"dr-drill-before-{uuid.uuid4().hex[:8]}"
    before_decision_id = _score(api_base_url, admin_token, before_reference, deployed_model_version_id)

    backup_result = _run([_bash(), str(BACKUP_SCRIPT)], timeout=60)
    assert backup_result.returncode == 0, backup_result.stdout + backup_result.stderr
    backup_file = _latest_backup()
    backup_taken_at = time.monotonic()

    # Written *after* the backup -- must NOT survive the restore. This is
    # what proves the drill is a genuine point-in-time restore, not a
    # trivial "the data's all still there because nothing destroyed it".
    after_reference = f"dr-drill-after-{uuid.uuid4().hex[:8]}"
    after_decision_id = _score(api_base_url, admin_token, after_reference, deployed_model_version_id)

    try:
        restore_result = _run([_bash(), str(RESTORE_SCRIPT), str(backup_file)], timeout=120)
        assert restore_result.returncode == 0, restore_result.stdout + restore_result.stderr

        # The restored dump is already at head (taken from a live,
        # migrated database) -- this proves running it again post-restore
        # is a safe no-op, the same guarantee a restore of an *older*
        # backup against a since-migrated app would need.
        migrate_result = compose("exec", "-T", "api", "flask", "db", "upgrade", check=False, timeout=60)
        assert migrate_result.returncode == 0, migrate_result.stdout + migrate_result.stderr

        wait_until(lambda: is_api_ready(api_base_url), timeout=60, description="API to become ready again after restore")
        recovery_complete_at = time.monotonic()

        before_response = requests.get(
            f"{api_base_url}/decisions/{before_decision_id}", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        )
        assert before_response.status_code == 200
        assert before_response.json()["decision"]["application_reference"] == before_reference

        after_response = requests.get(
            f"{api_base_url}/decisions/{after_decision_id}", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        )
        assert after_response.status_code == 404, (
            "the post-backup decision survived the restore -- this backup was not a real point-in-time snapshot"
        )

        verify_response = requests.get(
            f"{api_base_url}/audit/verify-chain", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        )
        assert verify_response.status_code == 200
        assert verify_response.json()["valid"] is True, verify_response.json()

        # A real, evidence-based RTO for this deployment shape (single
        # host, docker compose, no HA) -- not an invented enterprise
        # number. See docs/runbooks/disaster-recovery.md.
        print(f"\n[dr-drill] backup took {backup_taken_at - drill_start:.1f}s")
        print(f"[dr-drill] restore + migrate + recovery took {recovery_complete_at - backup_taken_at:.1f}s")
        print(f"[dr-drill] total drill time {recovery_complete_at - drill_start:.1f}s")
    finally:
        # Leave staging seeded and usable regardless of pass/fail --
        # re-seed is idempotent (app/cli.py's seed staging), safe even if
        # the restored backup already had the fixed-id tenants in it.
        compose("exec", "-T", "api", "flask", "seed", "staging", check=False, timeout=30)
