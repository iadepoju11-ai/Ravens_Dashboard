"""Tenant resolution for incoming requests.

The commercial platform will resolve tenant identity from authenticated
JWT claims issued by the enterprise identity provider (see ERD Section 1.2
and the "tenant-aware RBAC" replacement for basic authentication). Until
that identity/auth layer is built, tenant identity is taken from an
explicit header so the request pipeline (validation, scoring, governance,
audit) can be built and tested end-to-end.
"""

from __future__ import annotations

from flask import request

from app.extensions import db
from app.models.tenant import Tenant


class TenantResolutionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def resolve_tenant() -> Tenant:
    tenant_id = request.headers.get("X-Tenant-Id")
    if not tenant_id:
        raise TenantResolutionError("X-Tenant-Id header is required")

    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None or not tenant.is_active:
        raise TenantResolutionError("Unknown or inactive tenant", status_code=404)

    return tenant
