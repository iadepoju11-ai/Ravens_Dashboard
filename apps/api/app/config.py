import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://creditguard:creditguard@localhost:5433/creditguard"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-me")

    # OIDC (app/security/): standard issuer/JWKS/audience validation, not
    # provider-specific code -- Keycloak locally, swappable for an
    # enterprise IdP later without touching app/security/jwt_verifier.py.
    # OIDC_ISSUER must match the `iss` claim on tokens the API actually
    # receives, which for Docker-network traffic is the *internal*
    # hostname (see docs/local-development.md) -- not the host-side port
    # a human would use to reach the Keycloak admin console.
    OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "http://keycloak:8080/realms/creditguard")
    OIDC_JWKS_URL = os.environ.get(
        "OIDC_JWKS_URL", "http://keycloak:8080/realms/creditguard/protocol/openid-connect/certs"
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


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")


class ProductionConfig(Config):
    DEBUG = False


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
