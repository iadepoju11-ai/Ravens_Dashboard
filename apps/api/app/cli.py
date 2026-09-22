"""CLI commands: `flask audit verify-all-tenants`, `flask events publish-outbox`,
`flask seed staging`.

The first two aren't a scheduler — this project has none yet (CLAUDE.md
lists Celery/RQ as the intended tech, but nothing is wired up; picking
one is a real architecture decision, not something to bolt on
unilaterally alongside audit hardening or the outbox). Both are what a
scheduler would call: any external one (cron, a Kubernetes CronJob,
GitHub Actions on a schedule) can run them periodically. Both exit
non-zero on failure so a scheduler can alert on the run itself, in
addition to the MonitoringAlert rows they write.

`seed staging` is the one piece of state a fresh deploy can't get from
migrations alone (CHECKLIST.md Phase 7A: "deployable... without
undocumented manual configuration") — see its own docstring.
"""

from __future__ import annotations

import click
from flask import Flask

from app.extensions import db
from app.models.monitoring import MonitoringAlert
from app.models.tenant import Tenant
from app.services.audit_service import verify_chain
from app.services.outbox_service import publish_pending_events

# Fixed, non-random ids -- must match infra/keycloak/creditguard-realm.json's
# seeded `smoke-admin`/`smoke-other-tenant` users' `tenant_id` attribute
# exactly, so a token issued for either user resolves (via
# resolve_tenant_by_id) to a tenant that actually exists. Two tenants, not
# one, so the staging smoke-test suite can prove cross-tenant isolation,
# not just "auth works".
STAGING_TENANT_A_ID = "11111111-1111-4111-8111-111111111111"
STAGING_TENANT_B_ID = "22222222-2222-4222-8222-222222222222"


def register_cli(app: Flask) -> None:
    @app.cli.group("audit")
    def audit_group():
        """Audit maintenance commands."""

    @audit_group.command("verify-all-tenants")
    def verify_all_tenants():
        """Runs verify_chain for every tenant; writes a MonitoringAlert
        and exits non-zero if any tenant's chain is invalid."""
        any_invalid = False

        for tenant in Tenant.query.order_by(Tenant.name).all():
            result = verify_chain(tenant.id)
            if result.valid:
                click.echo(f"valid   tenant={tenant.id} events_checked={result.events_checked}")
                continue

            any_invalid = True
            click.echo(
                f"INVALID tenant={tenant.id} events_checked={result.events_checked} "
                f"failures={len(result.failures)}",
                err=True,
            )
            db.session.add(
                MonitoringAlert(
                    tenant_id=tenant.id,
                    alert_type="audit_chain_integrity_failure",
                    severity="critical",
                    message=(
                        f"Audit chain verification failed: {len(result.failures)} "
                        f"failure(s) across {result.events_checked} events"
                    ),
                )
            )

        db.session.commit()

        if any_invalid:
            raise SystemExit(1)

    @app.cli.group("events")
    def events_group():
        """Outbox/Kafka event commands."""

    @events_group.command("publish-outbox")
    def publish_outbox():
        """Publishes every pending outbox row to Kafka. A no-op (exit 0,
        nothing touched) if KAFKA_ENABLED is false. Exits non-zero if any
        event permanently failed (reached MAX_ATTEMPTS) this run —
        events merely retried (broker temporarily unreachable) don't
        fail the command, since the next scheduled run will retry them."""
        outcomes = publish_pending_events()

        if not outcomes:
            click.echo("no pending events (or Kafka is disabled)")
            return

        for outcome in outcomes:
            click.echo(f"{outcome.status:9s} {outcome.event_type:24s} {outcome.event_id}")

        failed = [o for o in outcomes if o.status == "failed"]
        click.echo(f"{len(outcomes)} event(s) processed, {len(failed)} permanently failed")

        if failed:
            raise SystemExit(1)

    @app.cli.group("seed")
    def seed_group():
        """Seed commands for a fresh environment."""

    @seed_group.command("staging")
    def seed_staging():
        """Creates the two fixed-id tenants the staging smoke-test suite
        (tests/smoke/) and its Keycloak users
        (infra/keycloak/creditguard-realm.json's `smoke-admin`/
        `smoke-other-tenant`) are wired to. Run once after `flask db
        upgrade` on a fresh deploy — docker-compose.staging.yml's
        `migrate` service does not call this automatically, since seeding
        is idempotent but a schema migration failing partway through
        should never be masked by a seed step that "succeeds" against a
        half-migrated database.

        Safe to re-run: does nothing for a tenant id that already exists,
        never updates or duplicates.
        """
        seeds = [
            (STAGING_TENANT_A_ID, "Staging Smoke Bank", "staging-smoke-bank"),
            (STAGING_TENANT_B_ID, "Staging Smoke Bank B", "staging-smoke-bank-b"),
        ]
        created = []
        for tenant_id, name, slug in seeds:
            if Tenant.query.filter_by(id=tenant_id).first() is not None:
                continue
            db.session.add(Tenant(id=tenant_id, name=name, slug=slug))
            created.append(slug)

        db.session.commit()
        click.echo(f"created: {', '.join(created)}" if created else "already seeded, nothing to do")
