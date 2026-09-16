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

from dataclasses import dataclass

from app.extensions import db
from app.models.decision import Decision
from app.models.explanation import Explanation
from app.models.model import ModelVersion
from app.models.tenant import Tenant
from app.services import audit_service
from app.services.model_runtime import ModelRuntime
from app.services.runtime_resolver import resolve_runtime

_MAX_FEATURES = 200


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
        existing = self._find_existing(tenant, request_id)
        if existing is not None:
            explanation = Explanation.query.filter_by(decision_id=existing.id).first()
            return ScoringResult(decision=existing, explanation=explanation, created=False)

        self._validate_application_reference(application_reference)
        self._validate_features(features)
        model_version = self._resolve_model_version(tenant, model_version_id)

        try:
            runtime = self._runtime_override or resolve_runtime(model_version)
            prediction = runtime.predict(features)
            outcome = self._decide_outcome(prediction.score)
            explanation_result = runtime.explain(features, prediction)
        except ScoringRuntimeError:
            raise
        except Exception:
            # Deliberately discard the original exception: it may carry
            # internals (model paths, DB details) that shouldn't reach the
            # API caller. A failed score must return an explicit error, not
            # a misleading success.
            self.session.rollback()
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
        self.session.flush()

        explanation = Explanation(
            decision_id=decision.id,
            method=explanation_result.method,
            base_value=explanation_result.base_value,
            feature_attributions={c.feature_name: c.value for c in explanation_result.contributions},
        )
        self.session.add(explanation)

        audit_service.record_event(
            tenant_id=tenant.id,
            event_type="decision.created",
            entity_type="decision",
            entity_id=decision.id,
            payload={"score": prediction.score, "outcome": outcome, "model_version_id": model_version.id},
        )

        self.session.commit()
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
            # A fixed per-model-version feature schema (required features,
            # types, ranges, unexpected-feature rejection) is ERD Phase 4
            # work, once the real ModelRuntime defines what each model
            # version actually expects.
            if not isinstance(value, (int, float, str, bool)) and value is not None:
                raise ScoringValidationError(f"feature '{name}' has an unsupported value type")

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
