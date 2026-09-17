from flask import Blueprint, jsonify, request

from app.extensions import db
from app.infrastructure.security.tenant_context import TenantResolutionError, resolve_tenant
from app.models.dataset import DatasetVersion
from app.models.deployment import ModelDeployment
from app.models.model import Model, ModelVersion

bp = Blueprint("models", __name__)


@bp.get("/models")
def list_models():
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    models = Model.query.filter_by(tenant_id=tenant.id).order_by(Model.created_at.desc()).all()
    return jsonify(
        models=[
            {**m.to_dict(), "versions": [v.to_dict() for v in m.versions]}
            for m in models
        ]
    )


@bp.post("/models")
def register_model_version():
    """Registers a model version, creating the parent logical Model
    (identified by tenant + name) on first use. New versions always start
    as "draft" — approval and deployment are separate, deliberate steps
    (see deploy_model below); nothing here can put a version live."""
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    body = request.get_json(silent=True) or {}
    name = body.get("name")
    version = body.get("version")
    artifact_uri = body.get("artifact_uri")
    metrics = body.get("metrics")
    training_dataset_version_id = body.get("training_dataset_version_id")

    if not all([name, version, artifact_uri]):
        return jsonify(error="name, version, and artifact_uri are required"), 400
    if metrics is not None and not isinstance(metrics, dict):
        return jsonify(error="metrics must be an object if provided"), 400

    if training_dataset_version_id:
        dataset_version = DatasetVersion.query.filter_by(id=training_dataset_version_id).first()
        if dataset_version is None or dataset_version.dataset.tenant_id != tenant.id:
            return jsonify(error="Unknown training_dataset_version_id for this tenant"), 404

    model = Model.query.filter_by(tenant_id=tenant.id, name=name).first()
    if model is None:
        model = Model(tenant_id=tenant.id, name=name)
        db.session.add(model)
        db.session.flush()
    elif ModelVersion.query.filter_by(model_id=model.id, version=version).first() is not None:
        return jsonify(error="This model version is already registered"), 409

    model_version = ModelVersion(
        model_id=model.id,
        version=version,
        status="draft",
        artifact_uri=artifact_uri,
        metrics=metrics,
        training_dataset_version_id=training_dataset_version_id or None,
    )
    db.session.add(model_version)
    db.session.commit()

    return jsonify(model=model.to_dict(), model_version=model_version.to_dict()), 201


@bp.post("/models/<model_id>/approve")
def approve_model_version(model_id: str):
    """Approve a draft model version. `model_id` names a ModelVersion id.

    No reviewer identity is recorded yet — ModelVersion.approved_by is a
    foreign key to users.id, and there is no authenticated user to
    attribute this to until the OIDC/RBAC workstream (auth.py) lands.
    """
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    model_version = ModelVersion.query.filter_by(id=model_id).first()
    if model_version is None or model_version.model.tenant_id != tenant.id:
        return jsonify(error="not_found"), 404

    if model_version.status != "draft":
        return jsonify(error="Only draft model versions can be approved"), 409

    model_version.status = "approved"
    model_version.approved_at = db.func.now()
    db.session.commit()

    return jsonify(model_version=model_version.to_dict())


@bp.post("/models/<model_id>/deploy")
def deploy_model(model_id: str):
    """Deploy a model *version*. `model_id` names a ModelVersion id — kept
    as the URL segment name to match the ERD's fixed route shape."""
    try:
        tenant = resolve_tenant()
    except TenantResolutionError as exc:
        return jsonify(error=exc.message), exc.status_code

    model_version = ModelVersion.query.filter_by(id=model_id).first()
    if model_version is None or model_version.model.tenant_id != tenant.id:
        return jsonify(error="not_found"), 404

    if model_version.status != "approved":
        return jsonify(error="Only approved model versions can be deployed"), 409

    # Source of truth for "what's currently deployed" is ModelVersion.status;
    # ModelDeployment is the history log linked via previous_deployment_id
    # when a matching "active" row exists (it may not, e.g. after a status
    # set outside this endpoint).
    previous_version = ModelVersion.query.filter_by(
        model_id=model_version.model_id, status="deployed"
    ).first()
    previous_deployment = None
    if previous_version is not None:
        previous_deployment = ModelDeployment.query.filter_by(
            model_version_id=previous_version.id, status="active"
        ).first()
        if previous_deployment is not None:
            previous_deployment.status = "rolled_back"
            previous_deployment.rolled_back_at = db.func.now()
        previous_version.status = "archived"

    model_version.status = "deployed"
    deployment = ModelDeployment(
        tenant_id=tenant.id,
        model_version_id=model_version.id,
        previous_deployment_id=previous_deployment.id if previous_deployment else None,
        status="active",
    )
    db.session.add(deployment)
    db.session.commit()

    return jsonify(model_version=model_version.to_dict(), deployment=deployment.to_dict())
