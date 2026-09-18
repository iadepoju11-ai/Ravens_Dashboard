from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=True)
    # The OIDC provider (Keycloak locally; an enterprise IdP in production)
    # owns authentication -- this app never stores a password or reproduces
    # the IdP's own auth. `oidc_subject` (the token's `sub` claim) is the
    # only identity linkage: it's how a verified token maps to a tenant and
    # a set of application-level records (see app/security/). Nullable
    # because a User row is created just-in-time on first successful login
    # (app/security/provisioning.py), not provisioned up front.
    oidc_subject = db.Column(db.String(255), nullable=True, unique=True)
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
