from flask import Blueprint, jsonify

from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant_by_id
from app.security.authentication import authenticate
from app.security.permissions import require_permission

bp = Blueprint("tenants", __name__)


@bp.get("/tenants")
def list_tenants():
    """No role in this application is a cross-tenant platform administrator
    -- this always returns only the caller's own tenant, never every
    tenant on the platform (see CHECKLIST.md Phase 5, "tenant isolation
    enforced on every query"). `tenant:read` is granted to all five
    CreditGuard roles for exactly that reason: reading your own tenant's
    name/status carries no cross-tenant risk, so it isn't gated further.
    """
    identity = authenticate()
    require_permission(identity, "tenant:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    return jsonify(tenants=[tenant.to_dict()])


@bp.get("/tenants/<tenant_id>")
def get_tenant(tenant_id: str):
    identity = authenticate()
    require_permission(identity, "tenant:read")

    try:
        tenant = resolve_tenant_by_id(identity.tenant_id)
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    if tenant_id != tenant.id:
        return jsonify(error="not_found"), 404

    return jsonify(tenant=tenant.to_dict())
