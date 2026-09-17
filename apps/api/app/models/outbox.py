from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin

OUTBOX_EVENT_STATUSES = ("pending", "published", "failed")


class OutboxEvent(UUIDPKMixin, TimestampMixin, db.Model):
    """A transactional outbox row (CHECKLIST.md "Kafka & events"). Written
    in the same DB transaction as the business change it describes, so
    "the event was recorded" and "the business write happened" are
    atomic — see app/services/outbox_service.py for the publish side.
    """

    __tablename__ = "outbox_events"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    event_type = db.Column(db.String(100), nullable=False)
    aggregate_type = db.Column(db.String(100), nullable=False)
    aggregate_id = db.Column(GUID(), nullable=False)
    correlation_id = db.Column(db.String(100), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.Text, nullable=True)
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.CheckConstraint("status IN ('pending', 'published', 'failed')", name="ck_outbox_event_status"),
        db.Index("ix_outbox_event_status_created_at", "status", "created_at"),
        db.Index("ix_outbox_event_tenant_created_at", "tenant_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "correlation_id": self.correlation_id,
            "status": self.status,
            "attempts": self.attempts,
            "created_at": self.created_at.isoformat(),
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }
