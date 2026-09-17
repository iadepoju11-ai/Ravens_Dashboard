"""Tests the `flask audit verify-all-tenants` command that a periodic
scheduler is meant to call (CHECKLIST.md Phase 5) — no scheduler exists
yet, but the command itself is real and tested.
"""

from app.extensions import db
from app.models.monitoring import MonitoringAlert
from app.models.tenant import Tenant
from app.services import audit_service


def _create_tenant(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.commit()
    return tenant


def test_verify_all_tenants_succeeds_when_all_chains_are_valid(app):
    tenant = _create_tenant("cli-happy-bank")
    audit_service.record_event(
        tenant_id=tenant.id,
        event_type="decision.created",
        entity_type="decision",
        entity_id="00000000-0000-0000-0000-000000000001",
        payload={},
    )
    db.session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(args=["audit", "verify-all-tenants"])

    assert result.exit_code == 0
    assert MonitoringAlert.query.count() == 0


def test_verify_all_tenants_alerts_and_exits_nonzero_on_a_broken_chain(app):
    tenant = _create_tenant("cli-broken-bank")
    event = audit_service.record_event(
        tenant_id=tenant.id,
        event_type="decision.created",
        entity_type="decision",
        entity_id="00000000-0000-0000-0000-000000000001",
        payload={},
    )
    db.session.commit()
    event.payload = {"tampered": True}
    db.session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(args=["audit", "verify-all-tenants"])

    assert result.exit_code != 0
    alerts = MonitoringAlert.query.filter_by(tenant_id=tenant.id).all()
    assert len(alerts) == 1
    assert alerts[0].alert_type == "audit_chain_integrity_failure"
    assert alerts[0].severity == "critical"
