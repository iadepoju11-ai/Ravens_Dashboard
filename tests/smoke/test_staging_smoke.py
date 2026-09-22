"""Black-box smoke tests against a REAL running deployment -- real HTTP
requests to the deployed api (and, transitively, Postgres/Keycloak/Kafka
behind it), never Flask's in-process test client. This is what proves the
*deployed* system works, not just that the code passes its own unit/
integration suite against an in-memory app.

Prerequisites (see docs/runbooks/deployment.md):
  1. docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
  2. docker compose -f docker-compose.staging.yml --env-file .env.staging exec api flask seed staging
  3. pip install -r tests/smoke/requirements.txt
  4. pytest tests/smoke/ -v

Sequential by design: module-scoped fixtures build state up (register a
model -> approve -> deploy -> score against it -> everything else reads
that same decision). This suite's own requirements.txt deliberately
excludes any test-randomization plugin, so pytest's default file-order
execution is safe to rely on -- each class below runs in the order it's
defined, top to bottom.

Every application_reference/model name includes `run_id` (a fresh UUID
per test session) so repeated runs against a long-lived staging
environment never collide with a previous run's data.
"""

from __future__ import annotations

import uuid

import pytest
import requests

from conftest import REQUEST_TIMEOUT, auth_headers


@pytest.fixture(scope="session")
def run_id() -> str:
    return uuid.uuid4().hex[:10]


@pytest.fixture(scope="session")
def deployed_model_version_id(api_base_url, admin_token, run_id) -> str:
    """Registers, approves, and deploys a model version with no
    artifact_uri/metrics that resolve to a real trained artifact -- it
    resolves to PlaceholderRuntime (app/services/placeholder_runtime.py),
    the same fallback every test fixture in the unit/integration suite
    relies on. This is deliberate: the smoke suite must pass on a fresh
    clone with no Kaggle dataset and no `make ml-train` run, not just on
    a machine that happens to have the real credit-risk-v1 artifact
    mounted into model_artifacts/.
    """
    headers = auth_headers(admin_token)

    register = requests.post(
        f"{api_base_url}/models",
        json={
            "name": f"smoke-model-{run_id}",
            "version": "1.0.0",
            "artifact_uri": "file://smoke-placeholder.pkl",
        },
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    assert register.status_code == 201, register.text
    model_version_id = register.json()["model_version"]["id"]

    approve = requests.post(f"{api_base_url}/models/{model_version_id}/approve", headers=headers, timeout=REQUEST_TIMEOUT)
    assert approve.status_code == 200, approve.text
    assert approve.json()["model_version"]["status"] == "approved"

    deploy = requests.post(f"{api_base_url}/models/{model_version_id}/deploy", headers=headers, timeout=REQUEST_TIMEOUT)
    assert deploy.status_code == 200, deploy.text
    assert deploy.json()["model_version"]["status"] == "deployed"

    return model_version_id


def _score(api_base_url, token, application_reference, features):
    response = requests.post(
        f"{api_base_url}/score",
        json={"application_reference": application_reference, "features": features},
        headers=auth_headers(token),
        timeout=REQUEST_TIMEOUT,
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestAuthentication:
    def test_a_request_with_no_token_is_rejected(self, api_base_url):
        response = requests.get(f"{api_base_url}/decisions", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 401

    def test_a_request_with_a_garbage_token_is_rejected(self, api_base_url):
        response = requests.get(
            f"{api_base_url}/decisions", headers=auth_headers("not-a-real-token"), timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 401

    def test_a_real_keycloak_token_is_accepted(self, api_base_url, admin_token):
        # tenant:read is granted to all five roles -- the cheapest real
        # endpoint to prove the whole verify path (signature, issuer,
        # audience, expiry against the real staging Keycloak JWKS) works.
        response = requests.get(f"{api_base_url}/tenants", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        assert response.json()["tenants"][0]["slug"] == "staging-smoke-bank"


class TestModelOperations:
    def test_register_approve_deploy_a_model_version(self, deployed_model_version_id):
        # The fixture itself asserts each step; this test just names the
        # workflow explicitly so a failure here reads as "model
        # operations broke", not an opaque fixture-setup error.
        assert deployed_model_version_id

    def test_deployed_model_is_listed(self, api_base_url, admin_token, deployed_model_version_id):
        response = requests.get(f"{api_base_url}/models", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        version_ids = {
            version["id"] for model in response.json()["models"] for version in model["versions"]
        }
        assert deployed_model_version_id in version_ids


class TestScoringAndDecisionRetrieval:
    def test_score_an_application_and_retrieve_the_decision(
        self, api_base_url, admin_token, run_id, deployed_model_version_id
    ):
        # PlaceholderRuntime averages numeric feature values -- 0.1 lands
        # well inside the "approve" band (< 0.33), a deterministic,
        # non-flaky way to pick an outcome without a real trained model.
        result = _score(api_base_url, admin_token, f"SMOKE-{run_id}-APPROVE", {"income": 0.1})
        decision_id = result["decision"]["id"]
        assert result["decision"]["outcome"] == "approve"
        assert result["explanation"]["method"] == "placeholder"

        get_response = requests.get(
            f"{api_base_url}/decisions/{decision_id}", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        )
        assert get_response.status_code == 200
        assert get_response.json()["decision"]["id"] == decision_id
        assert get_response.json()["explanation"]["reason_codes"]

    def test_a_refer_outcome_opens_a_review_case(self, api_base_url, admin_token, run_id, deployed_model_version_id):
        # No numeric features -> PlaceholderRuntime.predict() falls back to
        # score=0.5, squarely in the refer band (0.33 <= x < 0.66) --
        # deterministically exercises review_service.maybe_open_review_case.
        result = _score(api_base_url, admin_token, f"SMOKE-{run_id}-REFER", {"segment": "test"})
        assert result["decision"]["outcome"] == "refer"


class TestReviewCases:
    @pytest.fixture(scope="class", autouse=True)
    def refer_decision(self, api_base_url, admin_token, run_id, deployed_model_version_id):
        return _score(api_base_url, admin_token, f"SMOKE-{run_id}-REVIEW", {"segment": "review-case-source"})

    def test_the_refer_decision_has_an_open_review_case(self, api_base_url, admin_token, refer_decision):
        decision_id = refer_decision["decision"]["id"]
        response = requests.get(
            f"{api_base_url}/reviews?status=open", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 200
        matching = [r for r in response.json()["reviews"] if r["decision_id"] == decision_id]
        assert len(matching) == 1
        assert matching[0]["reason"]

    def test_claim_then_close_the_review_case(self, api_base_url, admin_token, refer_decision):
        decision_id = refer_decision["decision"]["id"]
        reviews = requests.get(
            f"{api_base_url}/reviews?status=open", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        ).json()["reviews"]
        review_id = next(r["id"] for r in reviews if r["decision_id"] == decision_id)

        claim = requests.post(
            f"{api_base_url}/reviews/{review_id}/resolve",
            json={"status": "in_review"},
            headers=auth_headers(admin_token),
            timeout=REQUEST_TIMEOUT,
        )
        assert claim.status_code == 200
        assert claim.json()["review"]["status"] == "in_review"
        assert claim.json()["review"]["assigned_to"]

        close = requests.post(
            f"{api_base_url}/reviews/{review_id}/resolve",
            json={"status": "closed"},
            headers=auth_headers(admin_token),
            timeout=REQUEST_TIMEOUT,
        )
        assert close.status_code == 200
        assert close.json()["review"]["status"] == "closed"
        assert close.json()["review"]["resolved_at"]


class TestFairness:
    def test_record_and_read_back_a_fairness_evaluation(self, api_base_url, admin_token, deployed_model_version_id):
        response = requests.post(
            f"{api_base_url}/fairness/evaluate",
            json={
                "model_version_id": deployed_model_version_id,
                "metrics": [
                    {
                        "protected_attribute": "smoke_test_attribute",
                        "metric_name": "demographic_parity_difference",
                        "metric_value": 0.02,
                        "threshold": 0.10,
                        "passed": True,
                    }
                ],
            },
            headers=auth_headers(admin_token),
            timeout=REQUEST_TIMEOUT,
        )
        assert response.status_code == 201, response.text
        assert len(response.json()["reports"]) == 1

        reports = requests.get(
            f"{api_base_url}/fairness/reports", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        )
        assert reports.status_code == 200
        assert any(r["model_version_id"] == deployed_model_version_id for r in reports.json()["reports"])


class TestAuditAndExport:
    def test_scoring_activity_produced_real_audit_events(self, api_base_url, admin_token):
        response = requests.get(f"{api_base_url}/audit/events", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        assert any(e["event_type"] == "decision.created" for e in response.json()["events"])

    def test_the_audit_chain_is_intact(self, api_base_url, admin_token):
        response = requests.get(
            f"{api_base_url}/audit/verify-chain", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 200
        assert response.json()["valid"] is True

    def test_export_the_audit_log(self, api_base_url, admin_token):
        response = requests.get(f"{api_base_url}/audit/export", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["event_count"] == len(body["events"])
        assert body["meta"]["exported_by"]


class TestMonitoring:
    def test_metrics_reflect_the_decisions_scored_above(self, api_base_url, admin_token):
        response = requests.get(
            f"{api_base_url}/monitoring/metrics", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 200
        assert response.json()["metrics"]["decision_count"] >= 1

    def test_alerts_endpoint_is_reachable(self, api_base_url, admin_token):
        response = requests.get(
            f"{api_base_url}/monitoring/alerts", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 200
        assert isinstance(response.json()["alerts"], list)


class TestTenantIsolation:
    def test_the_other_tenant_cannot_see_this_tenants_decisions(
        self, api_base_url, admin_token, other_tenant_token, run_id, deployed_model_version_id
    ):
        own = _score(api_base_url, admin_token, f"SMOKE-{run_id}-ISOLATION", {"income": 0.2})
        decision_id = own["decision"]["id"]

        cross_tenant_get = requests.get(
            f"{api_base_url}/decisions/{decision_id}",
            headers=auth_headers(other_tenant_token),
            timeout=REQUEST_TIMEOUT,
        )
        assert cross_tenant_get.status_code == 404

        cross_tenant_list = requests.get(
            f"{api_base_url}/decisions", headers=auth_headers(other_tenant_token), timeout=REQUEST_TIMEOUT
        )
        assert cross_tenant_list.status_code == 200
        assert decision_id not in {d["id"] for d in cross_tenant_list.json()["decisions"]}

    def test_the_other_tenant_cannot_see_this_tenants_model(
        self, api_base_url, other_tenant_token, deployed_model_version_id
    ):
        response = requests.get(f"{api_base_url}/models", headers=auth_headers(other_tenant_token), timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        version_ids = {version["id"] for model in response.json()["models"] for version in model["versions"]}
        assert deployed_model_version_id not in version_ids

    def test_each_tenant_sees_only_its_own_tenant_record(self, api_base_url, admin_token, other_tenant_token):
        mine = requests.get(f"{api_base_url}/tenants", headers=auth_headers(admin_token), timeout=REQUEST_TIMEOUT)
        theirs = requests.get(f"{api_base_url}/tenants", headers=auth_headers(other_tenant_token), timeout=REQUEST_TIMEOUT)
        assert mine.json()["tenants"][0]["slug"] == "staging-smoke-bank"
        assert theirs.json()["tenants"][0]["slug"] == "staging-smoke-bank-b"
