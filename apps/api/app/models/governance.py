from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin

# Populated by the governance service (ERD Phase 3) — schema only for now.


class GovernanceResult(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "governance_results"

    decision_id = db.Column(GUID(), db.ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False)
    check_name = db.Column(db.String(100), nullable=False)
    passed = db.Column(db.Boolean, nullable=False)
    details = db.Column(db.JSON, nullable=True)

    __table_args__ = (db.Index("ix_governance_result_decision_id", "decision_id"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "decision_id": self.decision_id,
            "check_name": self.check_name,
            "passed": self.passed,
            "details": self.details,
            "created_at": self.created_at.isoformat(),
        }
