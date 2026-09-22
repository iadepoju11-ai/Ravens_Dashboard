import os
import time

from flask import Flask, Response, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import CONFIG_BY_NAME
from app.extensions import cors, db, limiter, migrate
from app.observability import context as observability_context
from app.observability.logging_config import configure_logging
from app.observability.metrics import (
    HTTP_ERRORS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    REGISTRY as METRICS_REGISTRY,
)


def create_app(config_name: str | None = None, database_uri: str | None = None) -> Flask:
    config_name = config_name or os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(CONFIG_BY_NAME[config_name])
    configure_logging(app)

    # CHECKLIST.md Phase 7D: fail loudly at startup rather than silently
    # running with a secret nobody actually set. "change-me" is the
    # documented placeholder in .env.example/.env.staging.example, never a
    # real value -- if it's still set under FLASK_ENV=production, someone
    # skipped the setup step in docs/runbooks/deployment.md, and this
    # should stop the process instead of signing sessions/tokens with a
    # secret an attacker could just read from this repository.
    if config_name == "production" and app.config["SECRET_KEY"] == "change-me":
        raise RuntimeError(
            "SECRET_KEY is still the default placeholder value under a production config -- "
            "set a real, generated secret (see .env.staging.example) before starting this app."
        )

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
    # Only echoes CORS headers back for an Origin in this explicit list
    # (CHECKLIST.md Phase 7D) -- flask_cors.CORS() with no `origins` given
    # defaults to allowing every origin, wrong for a platform serving real
    # tenant credit-decision data to a browser.
    cors.init_app(app, origins=app.config["CORS_ALLOWED_ORIGINS"])
    limiter.init_app(app)

    from app import models  # noqa: F401  (registers ORM models with SQLAlchemy metadata)
    from app.api.v1 import register_blueprints
    from app.cli import register_cli
    from werkzeug.exceptions import HTTPException

    from app.observability.db import instrument_engine
    from app.security.jwt_verifier import TokenValidationError
    from app.security.permissions import AuthorizationError

    with app.app_context():
        instrument_engine(db.engine)

    register_blueprints(app)
    register_cli(app)

    # Not under /api/v1 and deliberately unauthenticated (Prometheus
    # scraping convention -- the scraper is never a logged-in tenant
    # user). A real deployment restricts who can reach this at the
    # network/ingress level, the same way it would for any other scrape
    # endpoint; see docs/runbooks/deployment.md's "Known limitations".
    # GET /api/v1/monitoring/observability (app/api/v1/monitoring.py) is
    # the authenticated, tenant-permission-gated JSON view of this same
    # data, for the frontend.
    @app.get("/metrics")
    @limiter.exempt  # scraped frequently and legitimately by design -- not abuse.
    def _metrics():
        return Response(generate_latest(METRICS_REGISTRY), mimetype=CONTENT_TYPE_LATEST)

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

    # HTTPException (404 unmatched route, 405 wrong method, ...) is a
    # normal, expected outcome -- registered explicitly so it doesn't fall
    # through to the broad Exception handler below (HTTPException *is* an
    # Exception subclass; without this, Flask's handler-resolution MRO
    # walk would match the broader handler first and turn every 404 into
    # a generic 500 "unexpected error" response). Not counted as an
    # unhandled exception -- http_errors_total tracks genuine bugs only.
    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException):
        return jsonify(error=exc.description or exc.name), exc.code

    # Genuinely unhandled exceptions -- anything not already caught by a
    # more specific handler above or inside a service (ScoringRuntimeError,
    # etc.). Logged in full (message, type, traceback) for an operator;
    # the API response never repeats any of that back to the caller, same
    # discipline ScoringRuntimeError already applies to the scoring path,
    # now applied globally so a *new* unhandled exception anywhere can't
    # leak a stack trace/DB detail/secret just because nothing caught it
    # yet.
    @app.errorhandler(Exception)
    def _handle_unexpected_exception(exc: Exception):
        HTTP_ERRORS_TOTAL.labels(exception_type=type(exc).__name__).inc()
        app.logger.error(
            "unhandled exception",
            exc_info=exc,
            extra={"exception_type": type(exc).__name__},
        )
        return jsonify(error="An unexpected error occurred", meta={"request_id": observability_context.get_request_id()}), 500

    @app.before_request
    def _observability_before_request():
        observability_context.reset_context()
        incoming_request_id = request.headers.get(observability_context.REQUEST_ID_HEADER)
        observability_context.set_request_id(incoming_request_id or observability_context.new_request_id())
        request.environ["_observability_start"] = time.perf_counter()

    @app.after_request
    def _observability_after_request(response):
        start = request.environ.get("_observability_start")
        duration = time.perf_counter() - start if start is not None else 0.0
        route = request.url_rule.rule if request.url_rule else "unmatched"

        HTTP_REQUESTS_TOTAL.labels(method=request.method, route=route, status=str(response.status_code)).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, route=route).observe(duration)

        response.headers[observability_context.REQUEST_ID_HEADER] = observability_context.get_request_id()

        # Security headers (CHECKLIST.md Phase 7D) -- applied to every
        # response, not just HTML ones: this API never renders HTML itself,
        # so a strict, blanket CSP is safe rather than something to tune per
        # route. HSTS is included even though this stack has no TLS today
        # (docs/runbooks/deployment.md's "Known limitations") -- browsers
        # ignore it on a plain-HTTP response per spec, so it's inert until a
        # real deployment terminates TLS in front of this app, not
        # misleading in the meantime.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        app.logger.info(
            "request completed",
            extra={
                "http_method": request.method,
                "http_route": route,
                "http_status": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        return response

    return app
