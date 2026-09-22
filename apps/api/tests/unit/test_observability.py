"""Unit tests for app/observability/: the JSON log formatter, request/
tenant context propagation, and the Prometheus-registry summary
(count/breakdown/histogram-quantile) logic used by
GET /api/v1/monitoring/observability. Deliberately independent of Flask
request handling — tests/integration/test_observability_endpoints.py
covers the wiring into real requests.
"""

import json
import logging

from prometheus_client import CollectorRegistry, Counter, Histogram

from app.observability import context
from app.observability.logging_config import JsonFormatter
from app.observability.summary import counter_breakdown, counter_total, histogram_summary


def _make_record(message: str, level: int = logging.INFO, exc_info=None, **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger", level=level, pathname=__file__, lineno=1, msg=message, args=(), exc_info=exc_info
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class TestJsonFormatter:
    def test_formats_a_plain_message_as_valid_json_with_expected_fields(self):
        record = _make_record("hello")

        parsed = json.loads(JsonFormatter().format(record))

        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert "timestamp" in parsed

    def test_includes_extra_fields_passed_by_the_caller(self):
        record = _make_record("scoring request completed", decision_id="d1", outcome="approve")

        parsed = json.loads(JsonFormatter().format(record))

        assert parsed["decision_id"] == "d1"
        assert parsed["outcome"] == "approve"

    def test_includes_request_id_and_tenant_id_from_context_when_set(self):
        context.set_request_id("req-123")
        context.set_tenant_id("tenant-456")
        try:
            parsed = json.loads(JsonFormatter().format(_make_record("hi")))
        finally:
            context.reset_context()

        assert parsed["request_id"] == "req-123"
        assert parsed["tenant_id"] == "tenant-456"

    def test_request_id_and_tenant_id_are_null_outside_any_context(self):
        context.reset_context()

        parsed = json.loads(JsonFormatter().format(_make_record("hi")))

        assert parsed["request_id"] is None
        assert parsed["tenant_id"] is None

    def test_includes_a_formatted_traceback_for_exceptions(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = _make_record("failed", level=logging.ERROR, exc_info=sys.exc_info())

        parsed = json.loads(JsonFormatter().format(record))

        assert "exception" in parsed
        assert "ValueError: boom" in parsed["exception"]


class TestContext:
    def test_reset_context_clears_both_values(self):
        context.set_request_id("req-1")
        context.set_tenant_id("tenant-1")

        context.reset_context()

        assert context.get_request_id() is None
        assert context.get_tenant_id() is None

    def test_new_request_id_is_a_non_empty_unique_string(self):
        first = context.new_request_id()
        second = context.new_request_id()

        assert first != second
        assert len(first) > 0


class TestSummary:
    def _registry_with(self):
        registry = CollectorRegistry()
        counter = Counter("t_requests_total", "d", ["status"], registry=registry)
        histogram = Histogram("t_duration_seconds", "d", buckets=(0.1, 0.5, 1.0), registry=registry)
        return registry, counter, histogram

    def test_counter_total_sums_across_all_label_values(self, monkeypatch):
        registry, counter, _ = self._registry_with()
        counter.labels(status="200").inc(3)
        counter.labels(status="500").inc(2)
        monkeypatch.setattr("app.observability.summary.REGISTRY", registry)

        assert counter_total("t_requests_total") == 5

    def test_counter_total_with_a_label_filter(self, monkeypatch):
        registry, counter, _ = self._registry_with()
        counter.labels(status="200").inc(3)
        counter.labels(status="500").inc(2)
        monkeypatch.setattr("app.observability.summary.REGISTRY", registry)

        assert counter_total("t_requests_total", {"status": "500"}) == 2

    def test_counter_total_is_zero_for_an_unknown_metric(self, monkeypatch):
        registry, _, _ = self._registry_with()
        monkeypatch.setattr("app.observability.summary.REGISTRY", registry)

        assert counter_total("does_not_exist_total") == 0

    def test_counter_breakdown_groups_by_label(self, monkeypatch):
        registry, counter, _ = self._registry_with()
        counter.labels(status="200").inc(3)
        counter.labels(status="500").inc(1)
        monkeypatch.setattr("app.observability.summary.REGISTRY", registry)

        assert counter_breakdown("t_requests_total", "status") == {"200": 3, "500": 1}

    def test_histogram_summary_reports_count_sum_and_average(self, monkeypatch):
        registry, _, histogram = self._registry_with()
        histogram.observe(0.05)
        histogram.observe(0.05)
        monkeypatch.setattr("app.observability.summary.REGISTRY", registry)

        result = histogram_summary("t_duration_seconds")

        assert result["count"] == 2
        assert result["sum_seconds"] == 0.1
        assert result["avg_ms"] == 50.0

    def test_histogram_summary_is_empty_but_well_formed_with_no_observations(self, monkeypatch):
        registry, _, _ = self._registry_with()
        monkeypatch.setattr("app.observability.summary.REGISTRY", registry)

        result = histogram_summary("t_duration_seconds")

        assert result == {"count": 0, "sum_seconds": 0.0, "avg_ms": None, "p50_ms": None, "p95_ms": None}

    def test_histogram_summary_p50_p95_are_plausible_for_a_known_distribution(self, monkeypatch):
        registry, _, histogram = self._registry_with()
        # 100 observations, evenly spread: p50 should land near the middle
        # bucket, p95 near the top -- exact values depend on the bucket
        # interpolation, this checks the *ordering* and rough magnitude
        # rather than pinning brittle exact numbers to bucket-boundary math.
        for i in range(100):
            histogram.observe(0.001 + (i / 100) * 0.9)
        monkeypatch.setattr("app.observability.summary.REGISTRY", registry)

        result = histogram_summary("t_duration_seconds")

        assert result["p50_ms"] is not None
        assert result["p95_ms"] is not None
        assert result["p50_ms"] < result["p95_ms"]
