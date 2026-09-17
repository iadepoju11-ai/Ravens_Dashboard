from flask import Blueprint, jsonify

from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant

bp = Blueprint("tenants", __name__)


@bp.get("/tenants")
def list_tenants():
    """Until a platform-administrator role exists (ERD Phase 6 RBAC),
    this can only return the caller's own tenant — listing every tenant
    on the platform to any caller would be a cross-tenant data leak (see
    CHECKLIST.md Phase 5, "tenant isolation enforced on every query").
    """
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    return jsonify(tenants=[tenant.to_dict()])


@bp.get("/tenants/<tenant_id>")
def get_tenant(tenant_id: str):
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    if tenant_id != tenant.id:
        return jsonify(error="not_found"), 404

    return jsonify(tenant=tenant.to_dict())
