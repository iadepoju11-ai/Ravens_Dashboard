from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin

# Populated by the monitoring worker (ERD Section 3.1) — schema only for now.


class MonitoringAlert(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "monitoring_alerts"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    alert_type = db.Column(db.String(100), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    message = db.Column(db.String(1000), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    source_entity_type = db.Column(db.String(100), nullable=True)
    source_entity_id = db.Column(GUID(), nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')", name="ck_monitoring_alert_severity"
        ),
        db.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')", name="ck_monitoring_alert_status"
        ),
        db.Index("ix_monitoring_alert_tenant_created_at", "tenant_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
