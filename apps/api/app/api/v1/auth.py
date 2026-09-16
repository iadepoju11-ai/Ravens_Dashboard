"""Enterprise identity integration (OIDC + tenant-aware RBAC, ERD Section
1.2) is a separate workstream from the API skeleton and is not wired up
yet. These endpoints are placeholders so the route shape is reserved.
"""

from flask import Blueprint, jsonify

bp = Blueprint("auth", __name__)


@bp.post("/auth/login")
def login():
    return jsonify(error="not_implemented"), 501


@bp.post("/auth/refresh")
def refresh():
    return jsonify(error="not_implemented"), 501
