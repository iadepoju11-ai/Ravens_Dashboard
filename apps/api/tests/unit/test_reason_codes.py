"""Unit tests for app/services/reason_codes.py -- a pure, deterministic
transform of already-computed SHAP values, never a generative one (see
the module docstring / CLAUDE.md)."""

from app.services.reason_codes import generate_reason_codes


def test_ranks_by_absolute_magnitude_not_raw_value():
    attributions = {
        "numeric__AMT_INCOME_TOTAL": -0.6,
        "numeric__AMT_CREDIT": 0.1,
        "numeric__EXT_SOURCE_1": 0.9,
    }

    reasons = generate_reason_codes(attributions, top_n=3)

    assert [r["feature"] for r in reasons] == [
        "numeric__EXT_SOURCE_1",
        "numeric__AMT_INCOME_TOTAL",
        "numeric__AMT_CREDIT",
    ]
    assert [r["rank"] for r in reasons] == [1, 2, 3]


def test_limits_to_top_n():
    attributions = {f"feature_{i}": float(i) for i in range(10)}

    reasons = generate_reason_codes(attributions, top_n=3)

    assert len(reasons) == 3


def test_default_top_n_is_five():
    attributions = {f"feature_{i}": float(i) for i in range(10)}

    reasons = generate_reason_codes(attributions)

    assert len(reasons) == 5


def test_positive_value_means_increased_risk():
    reasons = generate_reason_codes({"numeric__AMT_CREDIT": 0.42})

    assert reasons[0]["direction"] == "increased_risk"
    assert reasons[0]["contribution"] == 0.42


def test_negative_value_means_decreased_risk():
    reasons = generate_reason_codes({"numeric__AMT_CREDIT": -0.42})

    assert reasons[0]["direction"] == "decreased_risk"


def test_zero_value_means_no_effect():
    reasons = generate_reason_codes({"numeric__AMT_CREDIT": 0.0})

    assert reasons[0]["direction"] == "no_effect"


def test_humanizes_numeric_column_transformer_prefix():
    reasons = generate_reason_codes({"numeric__AMT_INCOME_TOTAL": 0.1})

    assert reasons[0]["label"] == "AMT INCOME TOTAL"


def test_humanizes_categorical_column_transformer_prefix():
    reasons = generate_reason_codes({"categorical__NAME_CONTRACT_TYPE_Cash loans": 0.1})

    assert reasons[0]["label"] == "NAME CONTRACT TYPE Cash loans"


def test_leaves_an_unprefixed_feature_name_alone_besides_underscores():
    reasons = generate_reason_codes({"already_plain_name": 0.1})

    assert reasons[0]["label"] == "already plain name"


def test_empty_attributions_produce_no_reason_codes():
    assert generate_reason_codes({}) == []


def test_every_reason_code_traces_back_to_a_real_attribution_value():
    # The point of the "no generative model" constraint made concrete:
    # every contribution in the output must be a value that was actually
    # in the input, never invented or approximated.
    attributions = {"numeric__AMT_INCOME_TOTAL": 0.31415, "numeric__AMT_CREDIT": -0.27182}

    reasons = generate_reason_codes(attributions)

    for reason in reasons:
        assert attributions[reason["feature"]] == reason["contribution"]
