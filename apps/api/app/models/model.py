from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin

MODEL_VERSION_STATUSES = ("draft", "approved", "deployed", "archived")


class Model(UUIDPKMixin, TimestampMixin, db.Model):
    """A logical, named model family. Concrete trained artefacts, their
    approval/deployment status, and their metrics live in ModelVersion."""

    __tablename__ = "models"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)

    __table_args__ = (db.UniqueConstraint("tenant_id", "name", name="uq_model_tenant_name"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
        }


class ModelVersion(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "model_versions"

    model_id = db.Column(GUID(), db.ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    model = db.relationship("Model", backref="versions")
    version = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="draft")
    artifact_uri = db.Column(db.String(500), nullable=False)
    training_dataset_version_id = db.Column(
        GUID(), db.ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True
    )
    metrics = db.Column(db.JSON, nullable=True)
    approved_by = db.Column(GUID(), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("model_id", "version", name="uq_model_version_model_version"),
        db.CheckConstraint(
            "status IN ('draft', 'approved', 'deployed', 'archived')", name="ck_model_version_status"
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "model_id": self.model_id,
            "version": self.version,
            "status": self.status,
            "artifact_uri": self.artifact_uri,
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat(),
        }
