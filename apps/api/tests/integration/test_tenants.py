"""Confirms the /tenants endpoints don't leak other tenants' records
(CHECKLIST.md Phase 5, "tenant isolation enforced on every query") — until
a platform-administrator role exists, a caller can only ever see its own
tenant.
"""

from app.extensions import db
from app.models.tenant import Tenant


def _create_tenant(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.commit()
    return tenant


def test_list_tenants_requires_a_tenant_header(client):
    response = client.get("/api/v1/tenants")
    assert response.status_code == 400


def test_list_tenants_returns_only_the_caller_own_tenant(client, app):
    own_tenant = _create_tenant("own-bank")
    _other_tenant = _create_tenant("other-bank")

    response = client.get("/api/v1/tenants", headers={"X-Tenant-Id": own_tenant.id})

    assert response.status_code == 200
    tenants = response.get_json()["tenants"]
    assert [t["id"] for t in tenants] == [own_tenant.id]


def test_get_tenant_cannot_fetch_another_tenants_record(client, app):
    own_tenant = _create_tenant("get-own-bank")
    other_tenant = _create_tenant("get-other-bank")

    own_response = client.get(f"/api/v1/tenants/{own_tenant.id}", headers={"X-Tenant-Id": own_tenant.id})
    assert own_response.status_code == 200

    other_response = client.get(f"/api/v1/tenants/{other_tenant.id}", headers={"X-Tenant-Id": own_tenant.id})
    assert other_response.status_code == 404
