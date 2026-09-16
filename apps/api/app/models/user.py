from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (db.UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }
