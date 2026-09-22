"""The scoring workflow: validate -> resolve model -> predict -> explain ->
persist -> audit. The route (app/api/v1/decisions.py) only parses the HTTP
request and maps the typed exceptions below to status codes — this module
owns the actual business workflow (ERD Phase 3: "route coordinates the
request; service owns the workflow").

Prediction/explanation are delegated to a `ModelRuntime` (ERD Phase 4) —
this service depends only on that interface and is unaware of the
concrete model type. Unless a runtime is explicitly passed in (tests
only), it is resolved per model version via `runtime_resolver` — which
falls back to `PlaceholderRuntime` for any model version not backed by a
real trained artifact.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.decision import Decision
from app.models.explanation import Explanation
from app.models.model import ModelVersion
from app.models.tenant import Tenant
from app.observability.metrics import (
    EXPLANATION_DURATION_SECONDS,
    MODEL_INFERENCE_DURATION_SECONDS,
    SCORING_DURATION_SECONDS,
    SCORING_ERRORS_TOTAL,
    SCORING_REQUESTS_TOTAL,
)
from app.services import audit_service, outbox_service
from app.services.governance_service import evaluate_governance
from app.services.model_runtime import ModelRuntime
from app.services.review_service import maybe_open_review_case
from app.services.runtime_resolver import resolve_runtime

_MAX_FEATURES = 200
logger = logging.getLogger(__name__)


class ScoringValidationError(Exception):
    """A pre-scoring validation failure. `message` is always safe to show
    to an API caller — never a stack trace, DB detail, model path, or
    secret."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ScoringRuntimeError(Exception):
    """The model runtime itself failed. Never surfaces the underlying
    exception to the caller — a failed score must return an explicit error,
    not a fabricated result."""

    def __init__(self, message: str = "Unable to score this application"):
        super().__init__(message)
        self.message = message
        self.status_code = 500


@dataclass(frozen=True)
class ScoringResult:
    decision: Decision
    explanation: Explanation
    # False when this call returned a previously-recorded decision for the
    # same (tenant, request_id) instead of creating a new one.
    created: bool


class ScoringService:
    def __init__(self, session=None, runtime: ModelRuntime | None = None):
        self.session = session or db.session
        # Explicit override — used by tests to inject a fake runtime.
        # None means "resolve per model version" (the normal path).
        self._runtime_override = runtime

    def score(
        self,
        *,
        tenant: Tenant,
        application_reference,
        features,
        request_id: str,
        model_version_id: str | None = None,
    ) -> ScoringResult:
        request_start = time.perf_counter()

        existing = self._find_existing(tenant, request_id)
        if existing is not None:
            explanation = Explanation.query.filter_by(decision_id=existing.id).first()
            SCORING_REQUESTS_TOTAL.labels(outcome=existing.outcome).inc()
            SCORING_DURATION_SECONDS.observe(time.perf_counter() - request_start)
            logger.info(
                "scoring request replayed",
                extra={"decision_id": existing.id, "outcome": existing.outcome, "idempotent_replay": True},
            )
            return ScoringResult(decision=existing, explanation=explanation, created=False)

        self._validate_application_reference(application_reference)
        self._validate_features(features)
        model_version = self._resolve_model_version(tenant, model_version_id)
        self._validate_features_against_schema(features, model_version)

        try:
            runtime = self._runtime_override or resolve_runtime(model_version)
            runtime_label = type(runtime).__name__

            inference_start = time.perf_counter()
            prediction = runtime.predict(features)
            MODEL_INFERENCE_DURATION_SECONDS.labels(runtime=runtime_label).observe(
                time.perf_counter() - inference_start
            )

            outcome = self._decide_outcome(prediction.score)

            explanation_start = time.perf_counter()
            explanation_result = runtime.explain(features, prediction)
            EXPLANATION_DURATION_SECONDS.labels(method=explanation_result.method).observe(
                time.perf_counter() - explanation_start
            )
        except ScoringRuntimeError:
            SCORING_ERRORS_TOTAL.inc()
            logger.error("scoring runtime error", extra={"model_version_id": model_version.id})
            raise
        except Exception:
            # Deliberately discard the original exception from the API
            # response: it may carry internals (model paths, DB details)
            # that shouldn't reach the caller. It's still logged here in
            # full, server-side only, before being discarded.
            self.session.rollback()
            SCORING_ERRORS_TOTAL.inc()
            logger.error(
                "scoring runtime error (unexpected exception)",
                exc_info=True,
                extra={"model_version_id": model_version.id},
            )
            raise ScoringRuntimeError() from None

        decision = Decision(
            tenant_id=tenant.id,
            model_version_id=model_version.id,
            application_reference=application_reference,
            request_id=request_id,
            input_payload=features,
            score=prediction.score,
            outcome=outcome,
        )
        self.session.add(decision)
        try:
            self.session.flush()
        except IntegrityError:
            # Two concurrent calls with the same idempotency key can both
            # pass the _find_existing check above before either commits
            # (CHECKLIST.md Phase 7C: "duplicate-event safety") -- the
            # `uq_decision_tenant_request_id` constraint (app/models/decision.py)
            # is what actually arbitrates the race, and this is the loser
            # finding out. Nothing else has been added to the session yet
            # (explanation/governance/audit/outbox are all below this
            # line), so rolling back only discards this call's own losing
            # insert, not any other work.
            self.session.rollback()
            existing = self._find_existing(tenant, request_id)
            if existing is None:
                # The IntegrityError wasn't this race after all (e.g. a
                # different constraint) -- re-raise so it surfaces as a
                # genuine, unexpected scoring error rather than being
                # silently swallowed.
                raise
            explanation = Explanation.query.filter_by(decision_id=existing.id).first()
            SCORING_REQUESTS_TOTAL.labels(outcome=existing.outcome).inc()
            SCORING_DURATION_SECONDS.observe(time.perf_counter() - request_start)
            logger.info(
                "scoring request deduplicated after concurrent race",
                extra={"decision_id": existing.id, "outcome": existing.outcome, "idempotent_replay": True},
            )
            return ScoringResult(decision=existing, explanation=explanation, created=False)

        explanation = Explanation(
            decision_id=decision.id,
            method=explanation_result.method,
            base_value=explanation_result.base_value,
            feature_attributions={c.feature_name: c.value for c in explanation_result.contributions},
        )
        self.session.add(explanation)

        governance_result = evaluate_governance(model_version.id, decision.id)
        self.session.add(governance_result)

        review_case = maybe_open_review_case(tenant.id, decision.id, outcome, governance_result.passed)
        if review_case:
            self.session.add(review_case)

        audit_service.record_event(
            tenant_id=tenant.id,
            event_type="decision.created",
            entity_type="decision",
            entity_id=decision.id,
            payload={"score": prediction.score, "outcome": outcome, "model_version_id": model_version.id},
        )

        # Outbox rows, not a direct Kafka call: written in the same
        # transaction as the decision/explanation above, so "the event
        # was recorded" and "the decision was saved" are atomic — a
        # disabled or unreachable Kafka broker can never lose or roll
        # back business data. request_id ties all three events from this
        # call together as one correlation_id. Only enqueued on a genuine
        # new decision (this branch), never on an idempotent replay —
        # re-scoring the same request_id must not re-publish events either.
        outbox_service.enqueue_event(
            tenant_id=tenant.id,
            event_type="decision.created.v1",
            aggregate_type="decision",
            aggregate_id=decision.id,
            correlation_id=request_id,
            payload={"score": prediction.score, "outcome": outcome, "model_version_id": model_version.id},
        )
        outbox_service.enqueue_event(
            tenant_id=tenant.id,
            event_type="explanation.created.v1",
            aggregate_type="explanation",
            aggregate_id=explanation.id,
            correlation_id=request_id,
            payload={
                "decision_id": decision.id,
                "method": explanation.method,
                "base_value": explanation.base_value,
            },
        )
        # Distinct from decision.created.v1: marks the whole /score
        # workflow (scoring + explanation + governance + audit) as
        # finished, not just that the Decision row exists. Governance is
        # a synchronous check today (evaluate_governance, above), so this
        # still fires immediately after decision.created.v1 -- the two
        # will diverge in timing if governance ever becomes async.
        outbox_service.enqueue_event(
            tenant_id=tenant.id,
            event_type="decision.completed.v1",
            aggregate_type="decision",
            aggregate_id=decision.id,
            correlation_id=request_id,
            payload={"outcome": outcome},
        )

        self.session.commit()

        SCORING_REQUESTS_TOTAL.labels(outcome=outcome).inc()
        SCORING_DURATION_SECONDS.observe(time.perf_counter() - request_start)
        logger.info(
            "scoring request completed",
            extra={
                "decision_id": decision.id,
                "model_version_id": model_version.id,
                "outcome": outcome,
                "governance_passed": governance_result.passed,
                "review_case_opened": review_case is not None,
            },
        )

        return ScoringResult(decision=decision, explanation=explanation, created=True)

    def _find_existing(self, tenant: Tenant, request_id: str) -> Decision | None:
        # Dedup is by (tenant_id, request_id) only — this does not detect a
        # reused key sent with a *different* payload, which a stricter
        # idempotency implementation would reject as a conflict.
        return Decision.query.filter_by(tenant_id=tenant.id, request_id=request_id).first()

    def _validate_application_reference(self, value) -> None:
        if not value or not isinstance(value, str):
            raise ScoringValidationError("application_reference is required and must be a string")

    def _validate_features(self, features) -> None:
        if not isinstance(features, dict) or not features:
            raise ScoringValidationError("features is required and must be a non-empty object")
        if len(features) > _MAX_FEATURES:
            raise ScoringValidationError(f"features must not exceed {_MAX_FEATURES} entries")
        for name, value in features.items():
            if not isinstance(name, str) or not name:
                raise ScoringValidationError("feature names must be non-empty strings")
            # Numeric/string/bool/null only — no nested objects or arrays.
            # Per-model-version schema checks (unknown features, wrong
            # type) happen in _validate_features_against_schema, once the
            # model version is resolved.
            if not isinstance(value, (int, float, str, bool)) and value is not None:
                raise ScoringValidationError(f"feature '{name}' has an unsupported value type")

    def _validate_features_against_schema(self, features: dict, model_version: ModelVersion) -> None:
        """Rejects feature names the model version doesn't expect, and
        numeric features sent as the wrong type. Only enforced when the
        model version actually recorded a feature schema
        (`metrics["features"]`, written by `POST /models` — see
        `apps/workers/ml/pipeline.py`'s metadata output) — a version
        registered without one (every test fixture, and any version
        registered before this existed) resolves to `PlaceholderRuntime`
        and has nothing to validate against, same convention as
        `runtime_resolver.py`. Range checks are not implemented: no
        per-feature min/max is recorded anywhere yet.
        """
        schema = (model_version.metrics or {}).get("features")
        if not schema:
            return

        numeric_fields = set(schema.get("numeric", []))
        categorical_fields = set(schema.get("categorical", []))
        known_fields = numeric_fields | categorical_fields

        unknown = sorted(set(features) - known_fields)
        if unknown:
            raise ScoringValidationError(f"Unknown feature(s) for this model version: {unknown}")

        for name in numeric_fields & set(features):
            value = features[name]
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ScoringValidationError(f"feature '{name}' must be numeric for this model version")

    def _resolve_model_version(self, tenant: Tenant, model_version_id: str | None) -> ModelVersion:
        if model_version_id:
            model_version = ModelVersion.query.filter_by(id=model_version_id).first()
            if model_version is None or model_version.model.tenant_id != tenant.id:
                raise ScoringValidationError("Unknown model_version_id for this tenant", status_code=404)
            if model_version.status != "deployed":
                raise ScoringValidationError("Requested model version is not deployed", status_code=409)
            return model_version

        model_version = (
            ModelVersion.query.join(ModelVersion.model)
            .filter(ModelVersion.model.has(tenant_id=tenant.id), ModelVersion.status == "deployed")
            .order_by(ModelVersion.created_at.desc())
            .first()
        )
        if model_version is None:
            raise ScoringValidationError("No deployed model available for this tenant", status_code=409)
        return model_version

    def _decide_outcome(self, risk_score: float) -> str:
        if risk_score < 0.33:
            return "approve"
        if risk_score < 0.66:
            return "refer"
        return "decline"
