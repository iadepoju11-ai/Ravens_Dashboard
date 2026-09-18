"""Confirms the /tenants endpoints don't leak other tenants' records
(CHECKLIST.md Phase 5, "tenant isolation enforced on every query") — no
role in this application is a cross-tenant platform administrator, so a
caller can only ever see its own tenant, derived from its verified
identity (see docs/architecture/oidc-rbac.md), never a client-supplied id.
"""

from app.extensions import db
from app.models.tenant import Tenant


def _create_tenant(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.commit()
    return tenant


def test_list_tenants_requires_a_token(client):
    response = client.get("/api/v1/tenants")
    assert response.status_code == 401


def test_list_tenants_returns_only_the_callers_own_tenant(client, app, auth_headers):
    own_tenant = _create_tenant("own-bank")
    _other_tenant = _create_tenant("other-bank")

    response = client.get("/api/v1/tenants", headers=auth_headers(own_tenant.id))

    assert response.status_code == 200
    tenants = response.get_json()["tenants"]
    assert [t["id"] for t in tenants] == [own_tenant.id]


def test_get_tenant_cannot_fetch_another_tenants_record(client, app, auth_headers):
    own_tenant = _create_tenant("get-own-bank")
    other_tenant = _create_tenant("get-other-bank")
    headers = auth_headers(own_tenant.id)

    own_response = client.get(f"/api/v1/tenants/{own_tenant.id}", headers=headers)
    assert own_response.status_code == 200

    other_response = client.get(f"/api/v1/tenants/{other_tenant.id}", headers=headers)
    assert other_response.status_code == 404
