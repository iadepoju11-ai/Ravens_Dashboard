from flask import Blueprint, jsonify

from app.extensions import db
from app.models.tenant import Tenant

bp = Blueprint("tenants", __name__)


@bp.get("/tenants")
def list_tenants():
    tenants = Tenant.query.order_by(Tenant.name).all()
    return jsonify(tenants=[t.to_dict() for t in tenants])


@bp.get("/tenants/<tenant_id>")
def get_tenant(tenant_id: str):
    tenant = db.session.get(Tenant, tenant_id)
    if tenant is None:
        return jsonify(error="not_found"), 404
    return jsonify(tenant=tenant.to_dict())
