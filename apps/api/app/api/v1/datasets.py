from flask import Blueprint, jsonify, request

from app.extensions import db
from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant
from app.models.dataset import Dataset, DatasetVersion

bp = Blueprint("datasets", __name__)


@bp.get("/datasets")
def list_datasets():
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    datasets = Dataset.query.filter_by(tenant_id=tenant.id).order_by(Dataset.created_at.desc()).all()
    return jsonify(
        datasets=[
            {**d.to_dict(), "versions": [v.to_dict() for v in d.versions]}
            for d in datasets
        ]
    )


@bp.post("/datasets")
def register_dataset():
    """Registers a dataset version, creating the parent logical Dataset
    (identified by tenant + name) on first use."""
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    body = request.get_json(silent=True) or {}
    name = body.get("name")
    version = body.get("version")
    uri = body.get("uri")

    if not all([name, version, uri]):
        return jsonify(error="name, version, and uri are required"), 400

    dataset = Dataset.query.filter_by(tenant_id=tenant.id, name=name).first()
    if dataset is None:
        dataset = Dataset(tenant_id=tenant.id, name=name)
        db.session.add(dataset)
        db.session.flush()
    elif DatasetVersion.query.filter_by(dataset_id=dataset.id, version=version).first() is not None:
        return jsonify(error="This dataset version is already registered"), 409

    dataset_version = DatasetVersion(
        dataset_id=dataset.id,
        version=version,
        uri=uri,
        row_count=body.get("row_count"),
        schema=body.get("schema"),
    )
    db.session.add(dataset_version)
    db.session.commit()

    return jsonify(dataset=dataset.to_dict(), version=dataset_version.to_dict()), 201
