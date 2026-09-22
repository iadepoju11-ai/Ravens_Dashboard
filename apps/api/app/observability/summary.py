"""Turns the raw Prometheus metric registry (metrics.py) into a curated
JSON summary for GET /api/v1/monitoring/observability — counts,
breakdowns, and per-histogram count/sum/average/p50/p95.

Percentiles are computed from each histogram's cumulative bucket counts
by linear interpolation within the bucket containing the target rank —
the same approximation Prometheus's own `histogram_quantile()` PromQL
function uses (not a fundamentally different, more-precise calculation
that GET /metrics's raw exposition format couldn't also support). If the
target rank falls in the `+Inf` overflow bucket, this returns the
previous (highest finite) bucket boundary rather than interpolating into
infinity — the same conservative fallback Prometheus itself documents
for that case.
"""

from __future__ import annotations

from prometheus_client.samples import Sample

from app.observability.metrics import REGISTRY


def _family(metric_name: str):
    # prometheus_client strips a trailing "_total" from a Counter's family
    # name (a Counter registered as "foo_total" collects as family name
    # "foo", with samples named "foo_total") -- every Counter metric name
    # in metrics.py ends in _total by Prometheus convention, so matching
    # only the exact name would silently find nothing for any of them.
    # Histogram names (e.g. "..._duration_seconds") don't end in _total
    # and match directly.
    candidates = {metric_name}
    if metric_name.endswith("_total"):
        candidates.add(metric_name[: -len("_total")])
    for family in REGISTRY.collect():
        if family.name in candidates:
            return family
    return None


def _matches(sample: Sample, label_filter: dict[str, str] | None) -> bool:
    if not label_filter:
        return True
    return all(sample.labels.get(key) == value for key, value in label_filter.items())


def counter_total(metric_name: str, label_filter: dict[str, str] | None = None) -> int:
    family = _family(metric_name)
    if family is None:
        return 0
    return int(
        sum(
            sample.value
            for sample in family.samples
            if sample.name.endswith("_total") and _matches(sample, label_filter)
        )
    )


def counter_breakdown(metric_name: str, label_key: str) -> dict[str, int]:
    family = _family(metric_name)
    if family is None:
        return {}
    breakdown: dict[str, int] = {}
    for sample in family.samples:
        if not sample.name.endswith("_total"):
            continue
        key = sample.labels.get(label_key, "unknown")
        breakdown[key] = breakdown.get(key, 0) + int(sample.value)
    return breakdown


def histogram_summary(metric_name: str) -> dict:
    family = _family(metric_name)
    if family is None:
        return {"count": 0, "sum_seconds": 0.0, "avg_ms": None, "p50_ms": None, "p95_ms": None}

    count = 0.0
    total_seconds = 0.0
    buckets: list[tuple[float, float]] = []
    for sample in family.samples:
        if sample.name.endswith("_count"):
            count += sample.value
        elif sample.name.endswith("_sum"):
            total_seconds += sample.value
        elif sample.name.endswith("_bucket"):
            le = sample.labels.get("le")
            if le is not None:
                buckets.append((float(le), sample.value))
    buckets.sort(key=lambda pair: pair[0])

    def quantile_ms(q: float) -> float | None:
        if count == 0:
            return None
        target = q * count
        prev_le, prev_cumulative = 0.0, 0.0
        for le, cumulative in buckets:
            if cumulative >= target:
                if le == float("inf"):
                    return round(prev_le * 1000, 2) if prev_le else None
                if cumulative == prev_cumulative:
                    return round(le * 1000, 2)
                fraction = (target - prev_cumulative) / (cumulative - prev_cumulative)
                return round((prev_le + fraction * (le - prev_le)) * 1000, 2)
            prev_le, prev_cumulative = le, cumulative
        return None

    return {
        "count": int(count),
        "sum_seconds": round(total_seconds, 4),
        "avg_ms": round((total_seconds / count) * 1000, 2) if count else None,
        "p50_ms": quantile_ms(0.50),
        "p95_ms": quantile_ms(0.95),
    }


def build_observability_summary() -> dict:
    http_total = counter_total("http_requests_total")
    http_by_status = counter_breakdown("http_requests_total", "status")
    http_errors = sum(count for status, count in http_by_status.items() if status.startswith(("4", "5")))

    return {
        "http": {
            "total_requests": http_total,
            "requests_by_status": http_by_status,
            "error_rate": round(http_errors / http_total, 4) if http_total else None,
            "unhandled_exceptions": counter_total("http_errors_total"),
            "latency": histogram_summary("http_request_duration_seconds"),
        },
        "scoring": {
            "requests_by_outcome": counter_breakdown("scoring_requests_total", "outcome"),
            "runtime_errors": counter_total("scoring_errors_total"),
            "duration": histogram_summary("scoring_duration_seconds"),
        },
        "model_inference": {"duration": histogram_summary("model_inference_duration_seconds")},
        "explanation": {"duration": histogram_summary("explanation_duration_seconds")},
        "database": {
            "errors": counter_total("db_errors_total"),
            "query_duration": histogram_summary("db_query_duration_seconds"),
        },
        "outbox": {"events_by_status": counter_breakdown("outbox_events_published_total", "status")},
        "governance": {"results_by_outcome": counter_breakdown("governance_results_total", "passed")},
        "review_cases": {"opened_by_reason": counter_breakdown("review_cases_opened_total", "reason")},
    }
