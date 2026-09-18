"""Tenant resolution for incoming requests.

Tenant identity comes from an authenticated Identity's tenant_id
(app/security/ -- verified via the OIDC access token), never a
client-supplied header. See docs/architecture/oidc-rbac.md.
"""

from __future__ import annotations

from app.extensions import db
from app.models.tenant import Tenant


class TenantResolutionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def resolve_tenant_by_id(tenant_id: str) -> Tenant:
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None or not tenant.is_active:
        raise TenantResolutionError("Unknown or inactive tenant", status_code=404)

    return tenant
