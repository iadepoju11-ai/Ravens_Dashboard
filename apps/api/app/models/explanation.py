from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin


class Explanation(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "explanations"

    decision_id = db.Column(
        GUID(), db.ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    method = db.Column(db.String(50), nullable=False, default="shap")
    base_value = db.Column(db.Float, nullable=False)
    feature_attributions = db.Column(db.JSON, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "decision_id": self.decision_id,
            "method": self.method,
            "base_value": self.base_value,
            "feature_attributions": self.feature_attributions,
            "created_at": self.created_at.isoformat(),
        }
