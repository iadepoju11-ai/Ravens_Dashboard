from flask import Flask

from app.api.v1 import audit, auth, datasets, decisions, fairness, health, models, monitoring, tenants

API_V1_PREFIX = "/api/v1"


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(health.bp, url_prefix=API_V1_PREFIX)
    app.register_blueprint(auth.bp, url_prefix=API_V1_PREFIX)
    app.register_blueprint(tenants.bp, url_prefix=API_V1_PREFIX)
    app.register_blueprint(decisions.bp, url_prefix=API_V1_PREFIX)
    app.register_blueprint(models.bp, url_prefix=API_V1_PREFIX)
    app.register_blueprint(datasets.bp, url_prefix=API_V1_PREFIX)
    app.register_blueprint(fairness.bp, url_prefix=API_V1_PREFIX)
    app.register_blueprint(audit.bp, url_prefix=API_V1_PREFIX)
    app.register_blueprint(monitoring.bp, url_prefix=API_V1_PREFIX)
