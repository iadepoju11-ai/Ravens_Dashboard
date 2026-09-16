import hashlib
import json

from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin


class AuditEvent(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "audit_events"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    event_type = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(100), nullable=False)
    entity_id = db.Column(GUID(), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    prev_hash = db.Column(db.String(64), nullable=True)
    hash = db.Column(db.String(64), nullable=False)

    __table_args__ = (db.Index("ix_audit_event_tenant_created_at", "tenant_id", "created_at"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "hash": self.hash,
            "prev_hash": self.prev_hash,
            "created_at": self.created_at.isoformat(),
        }


class AuditIntegrityCheck(UUIDPKMixin, TimestampMixin, db.Model):
    """A record of a hash-chain verification run. Populated on-demand today
    (the audit.verify endpoint) and, from ERD Phase 5 onward, by a periodic
    integrity-verification job."""

    __tablename__ = "audit_integrity_checks"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    checked_from_event_id = db.Column(
        GUID(), db.ForeignKey("audit_events.id", ondelete="SET NULL"), nullable=True
    )
    checked_to_event_id = db.Column(
        GUID(), db.ForeignKey("audit_events.id", ondelete="SET NULL"), nullable=True
    )
    valid = db.Column(db.Boolean, nullable=False)
    details = db.Column(db.JSON, nullable=True)

    __table_args__ = (db.Index("ix_audit_integrity_check_tenant_created_at", "tenant_id", "created_at"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "checked_from_event_id": self.checked_from_event_id,
            "checked_to_event_id": self.checked_to_event_id,
            "valid": self.valid,
            "created_at": self.created_at.isoformat(),
        }


def compute_hash(prev_hash: str | None, event_type: str, entity_type: str, entity_id: str, payload: dict) -> str:
    digest_input = json.dumps(
        {
            "prev_hash": prev_hash,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
        },
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()
