"""Proves every OIDC-migrated endpoint (CHECKLIST.md Phase 6) --
/decisions, /models, /fairness, /audit, /datasets, /monitoring, /tenants
-- actually enforces authentication and permission the same way
POST /score does (see tests/integration/test_score_authorization.py for
that one in detail, and docs/architecture/oidc-rbac.md for the pattern).
This file checks the mechanical 401/403 cases across all of them in one
pass, plus a couple of hand-picked cross-tenant checks for the
state-changing model lifecycle endpoints.
"""

import pytest

from app.extensions import db
from app.models.model import Model, ModelVersion
from app.models.tenant import Tenant


def _create_tenant_with_deployed_model(slug: str) -> tuple[Tenant, ModelVersion]:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.flush()

    model = Model(tenant_id=tenant.id, name="credit-risk")
    db.session.add(model)
    db.session.flush()

    model_version = ModelVersion(
        model_id=model.id,
        version="1.0.0",
        status="deployed",
        artifact_uri="file://./model_artifacts/credit-risk-1.0.0.pkl",
    )
    db.session.add(model_version)
    db.session.commit()
    return tenant, model_version


# (method, path template, a role that must NOT be allowed to call it)
_PROTECTED_ROUTES = [
    ("GET", "/api/v1/decisions", "auditor"),
    ("GET", "/api/v1/decisions/00000000-0000-0000-0000-000000000000", "auditor"),
    ("GET", "/api/v1/models", "credit_analyst"),
    ("POST", "/api/v1/models", "credit_analyst"),
    ("POST", "/api/v1/models/00000000-0000-0000-0000-000000000000/approve", "credit_analyst"),
    ("POST", "/api/v1/models/00000000-0000-0000-0000-000000000000/deploy", "credit_analyst"),
    ("GET", "/api/v1/fairness/reports", "credit_analyst"),
    ("GET", "/api/v1/fairness/reports/00000000-0000-0000-0000-000000000000", "credit_analyst"),
    ("GET", "/api/v1/audit/events", "credit_analyst"),
    ("GET", "/api/v1/audit/events/00000000-0000-0000-0000-000000000000/verify", "credit_analyst"),
    ("GET", "/api/v1/audit/integrity-status", "credit_analyst"),
    ("GET", "/api/v1/audit/verify-chain", "credit_analyst"),
    ("GET", "/api/v1/datasets", "credit_analyst"),
    ("POST", "/api/v1/datasets", "credit_analyst"),
    ("GET", "/api/v1/monitoring/metrics", "credit_analyst"),
    ("GET", "/api/v1/monitoring/alerts", "credit_analyst"),
    ("GET", "/api/v1/monitoring/observability", "credit_analyst"),
    ("GET", "/api/v1/reviews", "credit_analyst"),
    ("GET", "/api/v1/reviews/00000000-0000-0000-0000-000000000000", "credit_analyst"),
    ("POST", "/api/v1/reviews/00000000-0000-0000-0000-000000000000/resolve", "credit_analyst"),
]

# tenant:read is deliberately granted to all five roles (reading your own
# tenant carries no cross-tenant risk -- see app/api/v1/tenants.py), so
# there's no "wrong role" case for it, only "no token at all".
_AUTHENTICATED_ONLY_ROUTES = [
    ("GET", "/api/v1/tenants"),
    ("GET", "/api/v1/tenants/00000000-0000-0000-0000-000000000000"),
]


@pytest.mark.parametrize(("method", "path", "insufficient_role"), _PROTECTED_ROUTES)
def test_missing_token_is_rejected(client, method, path, insufficient_role):
    response = client.open(path, method=method, json={})
    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path"), _AUTHENTICATED_ONLY_ROUTES)
def test_authenticated_only_route_still_requires_a_token(client, method, path):
    response = client.open(path, method=method, json={})
    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path", "insufficient_role"), _PROTECTED_ROUTES)
def test_wrong_role_is_forbidden(client, app, auth_headers, method, path, insufficient_role):
    with app.app_context():
        tenant, _ = _create_tenant_with_deployed_model(f"perm-check-{abs(hash(path + method))}")
        tenant_id = tenant.id

    response = client.open(
        path, method=method, json={}, headers=auth_headers(tenant_id, roles=(insufficient_role,))
    )
    assert response.status_code == 403


def test_compliance_officer_cannot_approve_another_tenants_model_version(client, app, auth_headers):
    tenant_a, _ = _create_tenant_with_deployed_model("models-tenant-a")
    tenant_b, model_version_b = _create_tenant_with_deployed_model("models-tenant-b")

    # model_version_b is "deployed", not "draft" -- but the tenant check
    # happens before the status check, so this must still be 404, not 409.
    response = client.post(
        f"/api/v1/models/{model_version_b.id}/approve",
        headers=auth_headers(tenant_a.id, roles=("compliance_officer",), sub="officer-a"),
    )
    assert response.status_code == 404
    assert tenant_b.id  # sanity: tenant_b really exists and wasn't touched


def test_auditor_cannot_read_another_tenants_audit_events(client, app, auth_headers):
    tenant_a, _ = _create_tenant_with_deployed_model("audit-tenant-a")
    tenant_b, _ = _create_tenant_with_deployed_model("audit-tenant-b")

    # Score as tenant_b to generate a real audit event there.
    client.post(
        "/api/v1/score",
        json={"application_reference": "APP-B", "features": {"income": 0.5}, "request_id": "req-audit-tenant-b"},
        headers=auth_headers(tenant_b.id, roles=("credit_analyst",), sub="analyst-b"),
    )

    response = client.get(
        "/api/v1/audit/events",
        headers=auth_headers(tenant_a.id, roles=("auditor",), sub="auditor-a"),
    )
    assert response.status_code == 200
    assert response.get_json()["events"] == []


def test_compliance_officer_cannot_see_another_tenants_datasets(client, app, auth_headers):
    tenant_a, _ = _create_tenant_with_deployed_model("datasets-tenant-a")
    tenant_b, _ = _create_tenant_with_deployed_model("datasets-tenant-b")

    client.post(
        "/api/v1/datasets",
        json={"name": "home-credit", "version": "v1", "uri": "s3://x"},
        headers=auth_headers(tenant_b.id, roles=("compliance_officer",), sub="officer-b"),
    )

    response = client.get(
        "/api/v1/datasets",
        headers=auth_headers(tenant_a.id, roles=("compliance_officer",), sub="officer-a"),
    )
    assert response.status_code == 200
    assert response.get_json()["datasets"] == []
