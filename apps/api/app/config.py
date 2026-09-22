import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://creditguard:creditguard@localhost:5433/creditguard"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # CHECKLIST.md Phase 7D: caps the size of any request body Flask will
    # read into memory (`request.get_json()` et al.) before this app ever
    # sees it -- 1 MB comfortably covers the largest legitimate payload
    # (a /score call's feature dict, capped at 200 entries by
    # ScoringService._validate_features) with headroom, while still
    # bounding the worst case for an oversized/malicious body. Flask
    # itself returns a clean 413 once this is exceeded -- nothing here has
    # to detect it.
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 1_000_000))

    # CHECKLIST.md Phase 7D: the React SPA's own origin(s) -- comma-separated,
    # since dev/staging use different ports (docs/runbooks/deployment.md's
    # topology table) and a real deployment may add its own. flask-cors
    # only ever echoes back a request's Origin header when it's in this
    # list -- there is no "*" default here the way flask_cors.CORS()
    # itself defaults to when given no explicit origins.
    CORS_ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]

    # OIDC (app/security/): standard issuer/JWKS/audience validation, not
    # provider-specific code -- Keycloak locally, swappable for an
    # enterprise IdP later without touching app/security/jwt_verifier.py.
    # OIDC_ISSUER must match the `iss` claim on tokens the API actually
    # receives -- Keycloak is pinned to present itself as
    # localhost:8081 (KC_HOSTNAME, docker-compose.yml) regardless of which
    # network path issued the token, since both a browser (the React app)
    # and this API container need to agree on one issuer string. Only the
    # JWKS *fetch* address (OIDC_JWKS_URL) needs to be reachable from
    # wherever this process actually runs -- see docs/local-development.md.
    OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "http://localhost:8081/realms/creditguard")
    OIDC_JWKS_URL = os.environ.get(
        "OIDC_JWKS_URL", "http://localhost:8081/realms/creditguard/protocol/openid-connect/certs"
    )
    OIDC_AUDIENCE = os.environ.get("OIDC_AUDIENCE", "creditguard-api")

    # Off by default (matches the academic prototype's own KAFKA_ENABLED
    # flag) -- the outbox table still records every event regardless, so
    # nothing is lost while Kafka is disabled; enabling it later just lets
    # the publisher start draining the backlog. See app/services/outbox_service.py.
    KAFKA_ENABLED = os.environ.get("KAFKA_ENABLED", "false").lower() == "true"
    KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093")

    MODEL_REGISTRY_URI = os.environ.get("MODEL_REGISTRY_URI", "file://./model_artifacts")
    DATASET_STORE_URI = os.environ.get("DATASET_STORE_URI", "file://./data/processed")

    # Rate limiting (CHECKLIST.md Phase 7D, app/extensions.py's `limiter`).
    # Keyed by remote address, not tenant/identity -- a simplification
    # documented here rather than silently assumed: a real per-tenant
    # limit would need the bearer token parsed before Flask-Limiter's
    # key_func runs, which is a bigger change than this pass's scope.
    # Per-IP still meaningfully bounds a single abusive or malfunctioning
    # caller. `RATELIMIT_DEFAULT` applies to every route unless overridden
    # (POST /score, app/api/v1/decisions.py) or exempted (health checks,
    # /metrics -- both hit legitimately and frequently by
    # healthchecks/scrapers, see app/api/v1/health.py and app/__init__.py).
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "300 per minute")
    RATELIMIT_HEADERS_ENABLED = True


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    # The unit/integration suite fires hundreds of requests from a single
    # process, all sharing one "remote address" under Flask's test client --
    # real rate limiting would make the *test suite itself* flaky, not just
    # a misbehaving caller. Rate limiting's own behaviour is instead tested
    # directly, on a dedicated app instance that re-enables it with a tiny
    # override limit (tests/unit/test_rate_limiting.py).
    RATELIMIT_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
