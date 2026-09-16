from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin

# A human-review workflow for a decision (e.g. a "refer" outcome, or a
# fairness/governance flag). Populated from ERD Phase 6 onward — schema only
# for now.


class ReviewCase(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "review_cases"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    decision_id = db.Column(GUID(), db.ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False)
    assigned_to = db.Column(GUID(), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="open")
    reason = db.Column(db.String(500), nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.CheckConstraint("status IN ('open', 'in_review', 'closed')", name="ck_review_case_status"),
        db.Index("ix_review_case_tenant_created_at", "tenant_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "decision_id": self.decision_id,
            "assigned_to": self.assigned_to,
            "status": self.status,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
