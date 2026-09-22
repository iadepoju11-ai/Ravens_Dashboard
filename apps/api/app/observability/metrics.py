"""Prometheus-format application metrics (CHECKLIST.md Phase 7B).

Registered against `prometheus_client`'s default global `REGISTRY` --
correct for how this app actually runs today (gunicorn with no `--workers`
flag, i.e. one sync worker per container, see apps/api/Dockerfile): a
single process means in-process counters are accurate for the whole
container without needing `prometheus_client`'s multiprocess mode (which
needs a shared directory and different wiring). If this is ever scaled to
multiple workers per container, revisit — the numbers `GET /metrics`
reports would silently become per-worker instead of per-container.

Every metric instrumented here is read two ways:
- `GET /metrics` (app/api/v1/observability.py) — the raw Prometheus
  exposition format, for a real Prometheus/Grafana/any-compatible-vendor
  to scrape.
- `GET /api/v1/monitoring/observability` (same file) — a curated JSON
  summary (counts, error rates, average durations) of the same
  underlying data, for the frontend Monitoring page. Real percentiles
  (p50/p95) are computed from each histogram's bucket counts via linear
  interpolation within the containing bucket -- the same approximation
  Prometheus's own `histogram_quantile()` uses, not a fundamentally
  different calculation.
"""

from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import CollectorRegistry, Counter, Histogram

REGISTRY = CollectorRegistry(auto_describe=True)

DEFAULT_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)

# --- HTTP (app/__init__.py's before/after_request hooks) ---
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests handled, by method/route/status.",
    ["method", "route", "status"],
    registry=REGISTRY,
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds, by method/route.",
    ["method", "route"],
    buckets=DEFAULT_LATENCY_BUCKETS,
    registry=REGISTRY,
)
HTTP_ERRORS_TOTAL = Counter(
    "http_errors_total",
    "Unhandled exceptions caught by the global error handler, by exception type.",
    ["exception_type"],
    registry=REGISTRY,
)

# --- Scoring flow (app/services/scoring_service.py) ---
SCORING_REQUESTS_TOTAL = Counter(
    "scoring_requests_total",
    "Completed /score calls, by outcome (approve/refer/decline) — excludes validation/runtime failures.",
    ["outcome"],
    registry=REGISTRY,
)
SCORING_DURATION_SECONDS = Histogram(
    "scoring_duration_seconds",
    "End-to-end ScoringService.score() duration, successful calls only.",
    buckets=DEFAULT_LATENCY_BUCKETS,
    registry=REGISTRY,
)
SCORING_ERRORS_TOTAL = Counter(
    "scoring_errors_total",
    "Scoring attempts that raised ScoringRuntimeError (the model runtime itself failed).",
    registry=REGISTRY,
)

# --- Model inference / explanation (app/services/runtime_resolver.py + runtimes/) ---
MODEL_INFERENCE_DURATION_SECONDS = Histogram(
    "model_inference_duration_seconds",
    "ModelRuntime.predict() duration, by runtime type.",
    ["runtime"],
    buckets=DEFAULT_LATENCY_BUCKETS,
    registry=REGISTRY,
)
EXPLANATION_DURATION_SECONDS = Histogram(
    "explanation_duration_seconds",
    "ModelRuntime.explain() duration, by explanation method (placeholder/shap-tree/...).",
    ["method"],
    buckets=DEFAULT_LATENCY_BUCKETS,
    registry=REGISTRY,
)

# --- PostgreSQL (app/observability/db.py, SQLAlchemy engine events) ---
DB_QUERY_DURATION_SECONDS = Histogram(
    "db_query_duration_seconds",
    "SQL statement execution duration.",
    buckets=DEFAULT_LATENCY_BUCKETS,
    registry=REGISTRY,
)
DB_ERRORS_TOTAL = Counter(
    "db_errors_total",
    "SQL statement executions that raised an error (SQLAlchemy handle_error event).",
    registry=REGISTRY,
)

# --- Kafka / outbox (app/services/outbox_service.py) ---
OUTBOX_EVENTS_PUBLISHED_TOTAL = Counter(
    "outbox_events_published_total",
    "Outbox publish attempts, by outcome (published/retry/failed).",
    ["status"],
    registry=REGISTRY,
)

# --- Governance / review workflow (app/services/governance_service.py, review_service.py) ---
GOVERNANCE_RESULTS_TOTAL = Counter(
    "governance_results_total",
    "GovernanceResult rows written, by whether the check passed.",
    ["passed"],
    registry=REGISTRY,
)
REVIEW_CASES_OPENED_TOTAL = Counter(
    "review_cases_opened_total",
    "ReviewCase rows opened, by trigger reason.",
    ["reason"],
    registry=REGISTRY,
)


@contextmanager
def observe_duration(histogram: Histogram, **label_values: str):
    """`with observe_duration(HISTOGRAM, label="value"): ...` — records
    wall-clock duration even if the block raises, so a slow failure is
    still visible in the latency distribution, not silently excluded."""
    start = time.perf_counter()
    try:
        yield
    finally:
        target = histogram.labels(**label_values) if label_values else histogram
        target.observe(time.perf_counter() - start)
