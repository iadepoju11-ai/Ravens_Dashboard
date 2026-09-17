import os

from flask import Flask

from app.config import CONFIG_BY_NAME
from app.extensions import cors, db, jwt, migrate


def create_app(config_name: str | None = None) -> Flask:
    config_name = config_name or os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(CONFIG_BY_NAME[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app)

    from app import models  # noqa: F401  (registers ORM models with SQLAlchemy metadata)
    from app.api.v1 import register_blueprints
    from app.cli import register_cli

    register_blueprints(app)
    register_cli(app)

    return app
