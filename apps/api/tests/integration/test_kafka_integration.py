"""Proves app/services/outbox_service.py actually works against a real
Kafka broker, not just a fake `KafkaProducerLike` (see
tests/unit/test_outbox_service.py for that) or the DB-only assertions in
test_outbox_integration.py (which never enables Kafka at all).

CHECKLIST.md Phase 7E: "Kafka integration tests" -- until this file,
nothing in the automated suite ever called `publish_pending_events()`
with a real `KafkaProducer` pointed at a real broker end-to-end, or read
a published message back off the topic to confirm the wire envelope
round-trips correctly.

Requires a reachable Kafka broker (KAFKA_TEST_BOOTSTRAP_SERVERS, falling
back to KAFKA_BOOTSTRAP_SERVERS) and kafka-python-ng -- skipped
otherwise, e.g. a local venv with no broker running (same
skip-if-unavailable convention as tests/test_migrations.py's Postgres
check).
"""

from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("kafka", reason="requires kafka-python-ng to talk to a real broker")

import kafka  # noqa: E402

from app.extensions import db  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.services import outbox_service  # noqa: E402

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_TEST_BOOTSTRAP_SERVERS") or os.environ.get(
    "KAFKA_BOOTSTRAP_SERVERS"
)

if not KAFKA_BOOTSTRAP_SERVERS:
    pytest.skip(
        "Kafka integration test requires a reachable broker "
        "(set KAFKA_TEST_BOOTSTRAP_SERVERS or KAFKA_BOOTSTRAP_SERVERS)",
        allow_module_level=True,
    )


def _broker_reachable() -> bool:
    try:
        client = kafka.KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS, request_timeout_ms=5000)
        client.close()
        return True
    except Exception:
        return False


if not _broker_reachable():
    pytest.skip(f"Kafka broker at {KAFKA_BOOTSTRAP_SERVERS} is not reachable", allow_module_level=True)


@pytest.fixture(autouse=True)
def _enable_real_kafka(app):
    app.config["KAFKA_ENABLED"] = True
    app.config["KAFKA_BOOTSTRAP_SERVERS"] = KAFKA_BOOTSTRAP_SERVERS


def _create_tenant() -> Tenant:
    tenant = Tenant(name="kafka-integration-bank", slug="kafka-integration-bank")
    db.session.add(tenant)
    db.session.commit()
    return tenant


def test_publish_pending_events_publishes_to_a_real_broker_and_the_message_round_trips(app):
    tenant = _create_tenant()

    with app.app_context():
        event = outbox_service.enqueue_event(
            tenant_id=tenant.id,
            event_type="test.kafka_integration.v1",
            aggregate_type="test",
            aggregate_id=tenant.id,
            correlation_id="kafka-integration-test",
            payload={"proof": "real-broker-round-trip"},
        )
        db.session.commit()
        event_id = event.id

        consumer = kafka.KafkaConsumer(
            "test.kafka_integration.v1",
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            auto_offset_reset="earliest",
            consumer_timeout_ms=15000,
            value_deserializer=lambda v: v,
        )

        try:
            # Real KafkaProducer this time (app/services/outbox_service.py's
            # own _default_producer()), not an injected fake -- this is the
            # actual code path `flask events publish-outbox` runs in
            # staging/production.
            outcomes = outbox_service.publish_pending_events()
        finally:
            pass

        assert len(outcomes) == 1
        assert outcomes[0].event_id == event_id
        assert outcomes[0].status == "published"

        from app.models.outbox import OutboxEvent

        refreshed = OutboxEvent.query.filter_by(id=event_id).first()
        assert refreshed.status == "published"
        assert refreshed.published_at is not None

        # Read the message back off the real topic -- proves the envelope
        # (build_envelope) actually serializes and deserializes correctly
        # over the wire, not just that the DB row was updated.
        import json

        deadline = time.monotonic() + 15
        received = None
        for message in consumer:
            body = json.loads(message.value.decode("utf-8"))
            if body.get("event_id") == event_id:
                received = body
                break
            if time.monotonic() > deadline:
                break
        consumer.close()

        assert received is not None, "published message was never read back from the real topic"
        assert received["event_type"] == "test.kafka_integration.v1"
        assert received["tenant_id"] == tenant.id
        assert received["payload"] == {"proof": "real-broker-round-trip"}
