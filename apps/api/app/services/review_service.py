"""Opens a ReviewCase (ERD Phase 6, previously schema-only) when a
decision needs a human's attention: a "refer" outcome -- the score band
this system already treats as "not confident enough to auto-decide"
(see ScoringService._decide_outcome) -- or a failing GovernanceResult
(governance_service.py). Both are real, existing signals; this is what
finally routes them to an actual review queue instead of a "refer"
outcome just sitting in the decisions list with no follow-up.

A genuine runtime failure (ScoringRuntimeError) is NOT routed here: no
Decision is ever persisted for a failed scoring attempt (the session is
rolled back before a Decision row exists -- see scoring_service.py), and
ReviewCase.decision_id is a required foreign key. There is nothing to
attach a review case to, so that path stays a plain error response,
unchanged -- CHECKLIST.md's "error *or* human-review" phrasing turned
out to mean "a completed-but-borderline decision", not "a crashed one",
once ReviewCase's actual schema was checked.
"""

from __future__ import annotations

import logging

from app.models.review import ReviewCase
from app.observability.metrics import REVIEW_CASES_OPENED_TOTAL

REASON_REFER_OUTCOME = "Score fell in the refer band"
REASON_GOVERNANCE_FAILURE = "Model version has a failing fairness evaluation"

logger = logging.getLogger(__name__)


def maybe_open_review_case(
    tenant_id: str, decision_id: str, outcome: str, governance_passed: bool
) -> ReviewCase | None:
    reasons = []
    metric_labels = []
    if outcome == "refer":
        reasons.append(REASON_REFER_OUTCOME)
        metric_labels.append("refer_outcome")
    if not governance_passed:
        reasons.append(REASON_GOVERNANCE_FAILURE)
        metric_labels.append("governance_failure")

    if not reasons:
        return None

    # One increment per distinct reason, not one per review case -- a case
    # opened for both reasons at once should show up in both counters,
    # not force a combined "refer_outcome+governance_failure" label value
    # that would grow unboundedly with every new reason combination.
    for label in metric_labels:
        REVIEW_CASES_OPENED_TOTAL.labels(reason=label).inc()

    logger.info(
        "review case opened",
        extra={"tenant_id": tenant_id, "decision_id": decision_id, "reasons": metric_labels},
    )

    return ReviewCase(
        tenant_id=tenant_id,
        decision_id=decision_id,
        status="open",
        reason="; ".join(reasons),
    )
