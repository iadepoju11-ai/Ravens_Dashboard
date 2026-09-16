from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin


class FairnessEvaluation(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "fairness_evaluations"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    model_version_id = db.Column(GUID(), db.ForeignKey("model_versions.id"), nullable=False)
    protected_attribute = db.Column(db.String(100), nullable=False)
    metric_name = db.Column(db.String(100), nullable=False)
    metric_value = db.Column(db.Float, nullable=False)
    threshold = db.Column(db.Float, nullable=False)
    passed = db.Column(db.Boolean, nullable=False)

    __table_args__ = (db.Index("ix_fairness_evaluation_tenant_created_at", "tenant_id", "created_at"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "model_version_id": self.model_version_id,
            "protected_attribute": self.protected_attribute,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "passed": self.passed,
            "created_at": self.created_at.isoformat(),
        }
