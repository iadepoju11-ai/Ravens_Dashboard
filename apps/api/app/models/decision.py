from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin

DECISION_OUTCOMES = ("approve", "refer", "decline")


class Decision(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "decisions"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    model_version_id = db.Column(GUID(), db.ForeignKey("model_versions.id"), nullable=False)
    application_reference = db.Column(db.String(255), nullable=False)
    # Client-supplied (or server-generated fallback) idempotency key. The
    # uniqueness constraint is schema-only for now — actual dedup lookup
    # before scoring lands in ERD Phase 3 ("idempotency key enforced").
    request_id = db.Column(db.String(255), nullable=False)
    input_payload = db.Column(db.JSON, nullable=False)
    score = db.Column(db.Float, nullable=False)
    outcome = db.Column(db.String(20), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "request_id", name="uq_decision_tenant_request_id"),
        db.CheckConstraint("outcome IN ('approve', 'refer', 'decline')", name="ck_decision_outcome"),
        db.Index("ix_decision_tenant_created_at", "tenant_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "model_version_id": self.model_version_id,
            "application_reference": self.application_reference,
            "request_id": self.request_id,
            "score": self.score,
            "outcome": self.outcome,
            "created_at": self.created_at.isoformat(),
        }
