"""Tests the `flask audit verify-all-tenants` command that a periodic
scheduler is meant to call (CHECKLIST.md Phase 5) — no scheduler exists
yet, but the command itself is real and tested. Also tests `flask seed
staging` (CHECKLIST.md Phase 7A).
"""

from app.cli import STAGING_TENANT_A_ID, STAGING_TENANT_B_ID
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


def test_seed_staging_creates_both_fixed_id_tenants(app):
    runner = app.test_cli_runner()

    result = runner.invoke(args=["seed", "staging"])

    assert result.exit_code == 0
    tenant_a = Tenant.query.filter_by(id=STAGING_TENANT_A_ID).first()
    tenant_b = Tenant.query.filter_by(id=STAGING_TENANT_B_ID).first()
    assert tenant_a is not None
    assert tenant_b is not None
    assert tenant_a.id != tenant_b.id
    assert "created:" in result.output


def test_seed_staging_is_idempotent(app):
    runner = app.test_cli_runner()
    runner.invoke(args=["seed", "staging"])

    result = runner.invoke(args=["seed", "staging"])

    assert result.exit_code == 0
    assert Tenant.query.filter_by(id=STAGING_TENANT_A_ID).count() == 1
    assert Tenant.query.filter_by(id=STAGING_TENANT_B_ID).count() == 1
    assert "already seeded" in result.output
