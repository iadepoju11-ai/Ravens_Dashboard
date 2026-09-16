from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin

# ERD Section "Phase 6 — React frontend & identity".
ROLE_SLUGS = ("compliance_officer", "risk_analyst", "auditor", "platform_administrator")


class Role(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "roles"

    slug = db.Column(db.String(100), nullable=False, unique=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(500), nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "slug": self.slug, "name": self.name, "description": self.description}


class UserRole(TimestampMixin, db.Model):
    __tablename__ = "user_roles"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    user_id = db.Column(GUID(), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id = db.Column(GUID(), db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
