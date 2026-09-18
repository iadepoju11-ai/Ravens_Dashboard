import os

from flask import Flask, jsonify

from app.config import CONFIG_BY_NAME
from app.extensions import cors, db, jwt, migrate


def create_app(config_name: str | None = None, database_uri: str | None = None) -> Flask:
    config_name = config_name or os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(CONFIG_BY_NAME[config_name])

    # Flask-SQLAlchemy 3.x builds the engine inside db.init_app() and never
    # re-reads app.config afterwards -- setting SQLALCHEMY_DATABASE_URI post
    # hoc (e.g. in a test fixture) silently binds nothing and the app keeps
    # talking to whatever the config class defaulted to. Callers that need a
    # different database than the named config's default (real-Postgres
    # migration/permission tests, in particular) must go through this
    # parameter instead.
    if database_uri is not None:
        app.config["SQLALCHEMY_DATABASE_URI"] = database_uri

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app)

    from app import models  # noqa: F401  (registers ORM models with SQLAlchemy metadata)
    from app.api.v1 import register_blueprints
    from app.cli import register_cli
    from app.security.jwt_verifier import TokenValidationError
    from app.security.permissions import AuthorizationError

    register_blueprints(app)
    register_cli(app)

    # Every OIDC-migrated route (app/security/) raises one of these two --
    # never a route-specific message -- so handling them once here instead
    # of in a try/except repeated in every route avoids that duplication
    # scaling with the number of protected endpoints. Routes not yet
    # migrated (still on the X-Tenant-Id header) never raise either.
    @app.errorhandler(TokenValidationError)
    def _handle_token_validation_error(exc: TokenValidationError):
        return jsonify(error=exc.message), exc.status_code

    @app.errorhandler(AuthorizationError)
    def _handle_authorization_error(exc: AuthorizationError):
        return jsonify(error=exc.message), exc.status_code

    return app
