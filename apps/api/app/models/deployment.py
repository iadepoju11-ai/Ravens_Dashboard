from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin

# Records each deploy/rollback of a ModelVersion, distinct from
# ModelVersion.status (which reflects only the *current* state).


class ModelDeployment(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "model_deployments"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    model_version_id = db.Column(GUID(), db.ForeignKey("model_versions.id"), nullable=False)
    deployed_by = db.Column(GUID(), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    previous_deployment_id = db.Column(
        GUID(), db.ForeignKey("model_deployments.id", ondelete="SET NULL"), nullable=True
    )
    status = db.Column(db.String(20), nullable=False, default="active")
    rolled_back_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.CheckConstraint("status IN ('active', 'rolled_back')", name="ck_model_deployment_status"),
        db.Index("ix_model_deployment_tenant_created_at", "tenant_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "model_version_id": self.model_version_id,
            "status": self.status,
            "deployed_at": self.created_at.isoformat(),
            "rolled_back_at": self.rolled_back_at.isoformat() if self.rolled_back_at else None,
        }
