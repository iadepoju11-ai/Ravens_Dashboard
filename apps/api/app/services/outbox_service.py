"""Publishes pending outbox rows to Kafka (CHECKLIST.md "Kafka & events").

Nothing in the request-handling path (ScoringService, etc.) talks to
Kafka directly — see `enqueue_event`, which only ever writes a row to the
same DB transaction as the business change it describes. This module is
the only thing that actually talks to Kafka, and only when explicitly
invoked (`flask events publish-outbox`, app/cli.py) — no scheduler is
wired up to call it automatically yet, same reasoning as the periodic
audit-verification command already in app/cli.py: picking Celery/RQ/cron
is a real architecture decision, not something to fold in here.

Handles:
- **Kafka disabled** (`KAFKA_ENABLED=False`): returns immediately,
  doesn't even construct a producer. Outbox rows stay "pending" — nothing
  is lost; they publish whenever Kafka is enabled and this command next runs.
- **Kafka unavailable** (broker unreachable): every pending event in this
  run is recorded as a failed attempt (attempts incremented, last_error
  set), never crashes or loses the row.
- **Retry**: a row stays "pending" after a failed attempt (up to
  `MAX_ATTEMPTS`, after which it moves to "failed" and raises a
  `MonitoringAlert`) — the next `publish-outbox` run retries it
  automatically, with no separate retry/backoff logic needed here.
- **Duplicate delivery**: a row's own id is used as the message's
  `event_id` every time it's (re)published, so re-publishing after a
  crash between "Kafka ack" and "commit status=published" produces an
  identical message, not a new one — a consumer deduplicating by
  `event_id` is unaffected by the replay.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from flask import current_app

from app.extensions import db
from app.models.base import utcnow
from app.models.monitoring import MonitoringAlert
from app.models.outbox import OutboxEvent
from app.observability.metrics import OUTBOX_EVENTS_PUBLISHED_TOTAL

MAX_ATTEMPTS = 10
SCHEMA_VERSION = 1
logger = logging.getLogger(__name__)


class _FutureLike(Protocol):
    def get(self, timeout: float | None = None) -> object: ...


class KafkaProducerLike(Protocol):
    """The subset of kafka.KafkaProducer's interface this module needs —
    a test can inject any object satisfying this instead of a real one.

    `key` is passed as a raw string, not pre-encoded: the real KafkaProducer
    (see `_default_producer`) is configured with a `key_serializer` that
    encodes it, so encoding it again here would double-encode and fail."""

    def send(self, topic: str, key: str | None, value: dict) -> _FutureLike: ...


def enqueue_event(
    *,
    tenant_id: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict,
    correlation_id: str,
) -> OutboxEvent:
    """Adds an outbox row to the current DB session — does not commit.
    Call this alongside the business write it describes and commit both
    together, so they succeed or fail as a single transaction."""
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        payload=payload,
        status="pending",
    )
    db.session.add(event)
    return event


def build_envelope(event: OutboxEvent) -> dict:
    return {
        "event_id": event.id,
        "event_type": event.event_type,
        "schema_version": SCHEMA_VERSION,
        "tenant_id": event.tenant_id,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": event.aggregate_id,
        "correlation_id": event.correlation_id,
        "occurred_at": event.created_at.isoformat(),
        "payload": event.payload,
    }


@dataclass(frozen=True)
class PublishOutcome:
    event_id: str
    event_type: str
    status: str  # "published" | "retry" | "failed"


def _default_producer() -> KafkaProducerLike:
    from kafka import KafkaProducer  # imported lazily — only needed here

    return KafkaProducer(
        bootstrap_servers=current_app.config["KAFKA_BOOTSTRAP_SERVERS"],
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
    )


def publish_pending_events(producer: KafkaProducerLike | None = None) -> list[PublishOutcome]:
    if not current_app.config["KAFKA_ENABLED"]:
        return []

    owns_producer = producer is None
    try:
        active_producer = producer or _default_producer()
    except Exception:
        # Broker unreachable at construction time -- every pending event
        # fails this round, same handling as a per-event send failure.
        active_producer = None

    outcomes: list[PublishOutcome] = []
    try:
        pending = OutboxEvent.query.filter_by(status="pending").order_by(OutboxEvent.created_at.asc()).all()

        for event in pending:
            if active_producer is None:
                outcomes.append(_record_failure(event, "Kafka broker unavailable"))
                continue

            try:
                future = active_producer.send(
                    event.event_type,
                    key=str(event.aggregate_id),
                    value=build_envelope(event),
                )
                future.get(timeout=10)
            except Exception as exc:
                outcomes.append(_record_failure(event, str(exc)))
            else:
                event.status = "published"
                event.published_at = utcnow()
                db.session.commit()
                OUTBOX_EVENTS_PUBLISHED_TOTAL.labels(status="published").inc()
                outcomes.append(PublishOutcome(event_id=event.id, event_type=event.event_type, status="published"))
    finally:
        if owns_producer and active_producer is not None and hasattr(active_producer, "close"):
            active_producer.close()

    return outcomes


def _record_failure(event: OutboxEvent, error: str) -> PublishOutcome:
    event.attempts += 1
    event.last_error = error[:2000]

    if event.attempts >= MAX_ATTEMPTS:
        event.status = "failed"
        db.session.add(
            MonitoringAlert(
                tenant_id=event.tenant_id,
                alert_type="outbox_publish_failure",
                severity="high",
                message=(
                    f"Event {event.id} ({event.event_type}) failed to publish after "
                    f"{event.attempts} attempts: {error[:500]}"
                ),
            )
        )
        db.session.commit()
        OUTBOX_EVENTS_PUBLISHED_TOTAL.labels(status="failed").inc()
        logger.error(
            "outbox event permanently failed",
            extra={"event_id": event.id, "event_type": event.event_type, "attempts": event.attempts},
        )
        return PublishOutcome(event_id=event.id, event_type=event.event_type, status="failed")

    db.session.commit()
    OUTBOX_EVENTS_PUBLISHED_TOTAL.labels(status="retry").inc()
    return PublishOutcome(event_id=event.id, event_type=event.event_type, status="retry")
