from app.extensions import db
from app.models.base import TimestampMixin, UUIDPKMixin


class Tenant(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "tenants"

    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(100), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }
