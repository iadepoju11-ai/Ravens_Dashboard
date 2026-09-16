from app.extensions import db
from app.models.base import GUID, TimestampMixin, UUIDPKMixin


class Dataset(UUIDPKMixin, TimestampMixin, db.Model):
    """A logical, named dataset. Concrete immutable snapshots live in
    DatasetVersion so lineage (which version trained which model version)
    is explicit."""

    __tablename__ = "datasets"

    tenant_id = db.Column(GUID(), db.ForeignKey("tenants.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)

    __table_args__ = (db.UniqueConstraint("tenant_id", "name", name="uq_dataset_tenant_name"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
        }


class DatasetVersion(UUIDPKMixin, TimestampMixin, db.Model):
    __tablename__ = "dataset_versions"

    dataset_id = db.Column(GUID(), db.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    dataset = db.relationship("Dataset", backref="versions")
    version = db.Column(db.String(50), nullable=False)
    uri = db.Column(db.String(500), nullable=False)
    row_count = db.Column(db.Integer, nullable=True)
    schema = db.Column(db.JSON, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("dataset_id", "version", name="uq_dataset_version_dataset_version"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "uri": self.uri,
            "row_count": self.row_count,
            "created_at": self.created_at.isoformat(),
        }
