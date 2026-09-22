"""Integration tests for the observability HTTP surface (CHECKLIST.md
Phase 7B): GET /metrics (raw Prometheus format), GET /api/v1/monitoring/
observability (the frontend's JSON view of the same data), request-id
propagation, and the global safe-error-response handler. Uses the real
Flask test client, not the metrics/summary functions directly (see
tests/unit/test_observability.py for those).
"""

from unittest.mock import patch

from app.extensions import db
from app.models.model import Model, ModelVersion
from app.models.tenant import Tenant


def _create_tenant_and_deployed_model(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.flush()
    model = Model(tenant_id=tenant.id, name="obs-model")
    db.session.add(model)
    db.session.flush()
    db.session.add(ModelVersion(model_id=model.id, version="1.0.0", status="deployed", artifact_uri="file://x"))
    db.session.commit()
    return tenant


class TestMetricsEndpoint:
    def test_metrics_is_reachable_without_authentication(self, client, app):
        response = client.get("/metrics")

        assert response.status_code == 200
        assert response.content_type.startswith("text/plain")

    def test_metrics_exposes_the_expected_metric_families(self, client, app):
        response = client.get("/metrics")

        body = response.get_data(as_text=True)
        for expected in [
            "http_requests_total",
            "http_request_duration_seconds",
            "scoring_requests_total",
            "scoring_duration_seconds",
            "model_inference_duration_seconds",
            "explanation_duration_seconds",
            "db_query_duration_seconds",
            "outbox_events_published_total",
            "governance_results_total",
            "review_cases_opened_total",
        ]:
            assert expected in body, f"{expected} missing from /metrics output"


class TestObservabilityJsonEndpoint:
    def test_requires_authentication(self, client, app):
        response = client.get("/api/v1/monitoring/observability")
        assert response.status_code == 401

    def test_requires_monitoring_read_permission(self, client, app, auth_headers):
        tenant = _create_tenant_and_deployed_model("obs-perm-bank")
        # credit_analyst holds neither monitoring:read.
        response = client.get(
            "/api/v1/monitoring/observability", headers=auth_headers(tenant.id, roles=("credit_analyst",))
        )
        assert response.status_code == 403

    def test_returns_the_expected_top_level_shape(self, client, app, auth_headers):
        tenant = _create_tenant_and_deployed_model("obs-shape-bank")

        response = client.get(
            "/api/v1/monitoring/observability", headers=auth_headers(tenant.id, roles=("admin",))
        )

        assert response.status_code == 200
        observability = response.get_json()["observability"]
        for key in ["http", "scoring", "model_inference", "explanation", "database", "outbox", "governance", "review_cases"]:
            assert key in observability


class TestScoringInstrumentation:
    def test_scoring_a_real_application_increments_the_real_metrics(self, client, app, auth_headers):
        """The actual end-to-end proof: a real /score call through the
        real HTTP layer moves real counters, not just that the metric
        objects exist."""
        tenant = _create_tenant_and_deployed_model("obs-scoring-bank")
        headers = auth_headers(tenant.id, roles=("admin",))

        before = client.get("/api/v1/monitoring/observability", headers=headers).get_json()["observability"]

        score_response = client.post(
            "/api/v1/score",
            json={"application_reference": "OBS-APP-1", "features": {"income": 0.1}},
            headers=headers,
        )
        assert score_response.status_code == 201

        after = client.get("/api/v1/monitoring/observability", headers=headers).get_json()["observability"]

        before_total = sum(before["scoring"]["requests_by_outcome"].values())
        after_total = sum(after["scoring"]["requests_by_outcome"].values())
        assert after_total == before_total + 1
        assert after["scoring"]["duration"]["count"] == before["scoring"]["duration"]["count"] + 1
        assert after["model_inference"]["duration"]["count"] == before["model_inference"]["duration"]["count"] + 1
        assert after["governance"]["results_by_outcome"] != {} or before["governance"]["results_by_outcome"] != {}


class TestRequestIdPropagation:
    def test_a_supplied_request_id_is_echoed_back(self, client, app):
        response = client.get("/api/v1/health", headers={"X-Request-ID": "caller-supplied-id"})

        assert response.headers["X-Request-ID"] == "caller-supplied-id"

    def test_a_request_id_is_generated_when_none_is_supplied(self, client, app):
        response = client.get("/api/v1/health")

        assert response.headers.get("X-Request-ID")


class TestSafeErrorResponses:
    def test_an_unhandled_exception_returns_a_generic_safe_body_not_the_real_message(self, client, app, auth_headers):
        tenant = _create_tenant_and_deployed_model("obs-error-bank")
        headers = auth_headers(tenant.id, roles=("admin",))

        with patch(
            "app.api.v1.tenants.resolve_tenant_by_id",
            side_effect=RuntimeError("db path: /secret/internal/connection-string"),
        ):
            response = client.get("/api/v1/tenants", headers=headers)

        assert response.status_code == 500
        body = response.get_json()
        assert body["error"] == "An unexpected error occurred"
        assert "secret" not in response.get_data(as_text=True)
        assert "connection-string" not in response.get_data(as_text=True)
        assert body["meta"]["request_id"]

    def test_a_404_for_an_unmatched_route_is_a_normal_json_response_not_the_generic_500(self, client, app):
        response = client.get("/api/v1/this-route-does-not-exist")

        assert response.status_code == 404
        body = response.get_json()
        assert body["error"] != "An unexpected error occurred"
