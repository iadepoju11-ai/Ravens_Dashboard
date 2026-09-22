"""Computes a lightweight governance check for a freshly-scored decision:
whether the model version has any FairnessEvaluation on record that
failed its threshold. Gives GovernanceResult (ERD Phase 3) its first real
writer -- previously nothing anywhere constructed one.

Deliberately a single, synchronous check tied to real fairness data
(Sprint D), not a general governance-rule engine -- matches CLAUDE.md's
"well-structured modular monolith" stance rather than standing up an
async governance pipeline for one check.

`passed=True` when there are zero recorded evaluations, same as "no
known failure" everywhere else in this codebase treats missing
monitoring data (see fairness.py's own empty-state copy) -- it is not
"verified fair", and `details` always records how many evaluations were
actually considered so a caller can tell the two cases apart.
"""

from __future__ import annotations

import logging

from app.models.fairness import FairnessEvaluation
from app.models.governance import GovernanceResult
from app.observability.metrics import GOVERNANCE_RESULTS_TOTAL

CHECK_NAME_FAIRNESS_STATUS = "model_fairness_status"
logger = logging.getLogger(__name__)


def evaluate_governance(model_version_id: str, decision_id: str) -> GovernanceResult:
    evaluations = FairnessEvaluation.query.filter_by(model_version_id=model_version_id).all()
    failing = [e for e in evaluations if not e.passed]
    passed = not failing

    GOVERNANCE_RESULTS_TOTAL.labels(passed=str(passed).lower()).inc()
    if not passed:
        logger.warning(
            "governance check failed",
            extra={
                "decision_id": decision_id,
                "model_version_id": model_version_id,
                "check_name": CHECK_NAME_FAIRNESS_STATUS,
                "failing_metric_count": len(failing),
            },
        )

    return GovernanceResult(
        decision_id=decision_id,
        check_name=CHECK_NAME_FAIRNESS_STATUS,
        passed=passed,
        details={
            "evaluations_considered": len(evaluations),
            "failing_metrics": [
                {
                    "metric_name": e.metric_name,
                    "protected_attribute": e.protected_attribute,
                    "metric_value": e.metric_value,
                    "threshold": e.threshold,
                }
                for e in failing
            ],
        },
    )
