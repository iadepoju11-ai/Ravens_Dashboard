"""CLI commands: `flask audit verify-all-tenants`.

Not a scheduler — this project has none yet (CLAUDE.md lists Celery/RQ as
the intended tech, but nothing is wired up; picking one is a real
architecture decision, not something to bolt on unilaterally alongside
audit hardening). This command is what a scheduler would call: any
external one (cron, a Kubernetes CronJob, GitHub Actions on a schedule)
can run it periodically. It exits non-zero on any failure so a scheduler
can alert on the run itself, in addition to the MonitoringAlert rows it
writes.
"""

from __future__ import annotations

import click
from flask import Flask

from app.extensions import db
from app.models.monitoring import MonitoringAlert
from app.models.tenant import Tenant
from app.services.audit_service import verify_chain


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
