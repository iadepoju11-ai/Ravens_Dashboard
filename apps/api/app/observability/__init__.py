"""Vendor-neutral observability: structured JSON logging (logging_config.py),
Prometheus-format metrics (metrics.py), and request/correlation-id
propagation (context.py). CHECKLIST.md Phase 7B.

"Vendor-neutral" here means: standard library `logging` reconfigured to
emit JSON lines (any log shipper — Loki, CloudWatch, ELK, a vendor
agent — can ingest that without this app knowing which one), and the
Prometheus text exposition format for metrics (an open, widely-adopted
standard scraped by Prometheus itself, Grafana Agent, Datadog, and most
other observability vendors) — nothing in this package imports a
vendor-specific SDK.
"""
