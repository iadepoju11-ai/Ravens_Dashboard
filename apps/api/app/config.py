import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://creditguard:creditguard@localhost:5433/creditguard"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-me")

    KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093")
    KAFKA_AUDIT_TOPIC = os.environ.get("KAFKA_AUDIT_TOPIC", "creditguard.audit.events")
    KAFKA_MONITORING_TOPIC = os.environ.get("KAFKA_MONITORING_TOPIC", "creditguard.monitoring.events")

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
