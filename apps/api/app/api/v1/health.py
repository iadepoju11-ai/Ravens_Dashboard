from flask import Blueprint, jsonify

from app.extensions import db

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    return jsonify(status="ok")


@bp.get("/health/ready")
def readiness():
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    status = "ready" if db_ok else "not_ready"
    return jsonify(status=status, dependencies={"database": db_ok}), (200 if db_ok else 503)
