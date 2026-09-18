"""Turns a decision's already-persisted, already-verified SHAP feature
attributions into a ranked, human-readable list of reasons.

CLAUDE.md is explicit: "Do not use a generative model to invent reasons
for a credit decision. NLG (if added) only transforms verified model
contributions and approved policy facts into text." This is exactly
that and nothing more -- a pure, deterministic transformation of
Explanation.feature_attributions (sorting + light string formatting), no
model call, no invented content. Every reason code traces directly back
to a real SHAP value the explainer actually computed.

Not persisted: reason codes are fully derivable from
Explanation.feature_attributions (the audit-relevant record already
stored), so recomputing them on read keeps that raw SHAP output as the
one source of truth rather than duplicating it -- if this ranking/
formatting logic ever improves, existing explanations benefit
automatically instead of being stuck with whatever logic ran at write
time.
"""

from __future__ import annotations

DEFAULT_TOP_N = 5

_COLUMN_TRANSFORMER_PREFIXES = ("numeric__", "categorical__")


def _humanize_feature_name(raw_name: str) -> str:
    """Best-effort readability pass, not a guaranteed business-friendly
    label: strips the preprocessing pipeline's ColumnTransformer prefix
    and turns underscores into spaces. A one-hot-encoded categorical
    feature keeps its appended category value as part of the label (e.g.
    "categorical__NAME_CONTRACT_TYPE_Cash loans" -> "NAME CONTRACT TYPE
    Cash loans") -- the encoder's own naming doesn't reliably separate
    the original column name from the category value, so this doesn't
    try to split them further.
    """
    name = raw_name
    for prefix in _COLUMN_TRANSFORMER_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    return name.replace("_", " ").strip()


def generate_reason_codes(feature_attributions: dict[str, float], top_n: int = DEFAULT_TOP_N) -> list[dict]:
    """Ranks features by |SHAP value| (largest impact first, in either
    direction) and returns the top `top_n` as reason codes.

    Positive SHAP values push the prediction toward TARGET=1 (elevated
    default risk); negative values push toward TARGET=0 (lower risk) --
    see docs/model_cards/credit-risk-v1.md for this model's target
    polarity. A feature with a positive contribution to a *declined*
    application and a feature with a positive contribution to an
    *approved* one both read as "increased_risk" here, consistently --
    the direction is about the model's risk score, not the eventual
    outcome, which callers should already have from Decision.outcome.
    """
    ranked = sorted(feature_attributions.items(), key=lambda item: abs(item[1]), reverse=True)

    reason_codes = []
    for rank, (raw_name, value) in enumerate(ranked[:top_n], start=1):
        if value > 0:
            direction = "increased_risk"
        elif value < 0:
            direction = "decreased_risk"
        else:
            direction = "no_effect"

        reason_codes.append(
            {
                "rank": rank,
                "feature": raw_name,
                "label": _humanize_feature_name(raw_name),
                "contribution": float(value),
                "direction": direction,
            }
        )

    return reason_codes
