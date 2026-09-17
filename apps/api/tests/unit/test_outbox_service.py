"""Unit tests for the transactional outbox publisher (CHECKLIST.md "Kafka
& events"). Uses a fake producer injected via the KafkaProducerLike
protocol -- no real Kafka broker involved, so these stay fast and run in
the SQLite-only local venv too.
"""

from app.extensions import db
from app.models.monitoring import MonitoringAlert
from app.models.outbox import OutboxEvent
from app.models.tenant import Tenant
from app.services import outbox_service


class _FakeFuture:
    def __init__(self, result=None, error: Exception | None = None):
        self._result = result
        self._error = error

    def get(self, timeout=None):
        if self._error:
            raise self._error
        return self._result


class _FakeProducer:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.sent: list[tuple[str, bytes, dict]] = []

    def send(self, topic, key, value):
        self.sent.append((topic, key, value))
        if self.should_fail:
            return _FakeFuture(error=RuntimeError("simulated broker failure"))
        return _FakeFuture(result="ok")


def _create_tenant(slug: str) -> Tenant:
    tenant = Tenant(name=slug, slug=slug)
    db.session.add(tenant)
    db.session.commit()
    return tenant


def _enqueue(tenant_id: str) -> OutboxEvent:
    event = outbox_service.enqueue_event(
        tenant_id=tenant_id,
        event_type="decision.created.v1",
        aggregate_type="decision",
        aggregate_id="00000000-0000-0000-0000-000000000001",
        correlation_id="req-1",
        payload={"score": 0.5, "outcome": "refer"},
    )
    db.session.commit()
    return event


def test_enqueue_event_does_not_touch_kafka(app):
    tenant = _create_tenant("outbox-enqueue-bank")
    event = _enqueue(tenant.id)

    assert event.status == "pending"
    assert event.attempts == 0


def test_publish_is_a_noop_when_kafka_disabled(app):
    tenant = _create_tenant("outbox-disabled-bank")
    event = _enqueue(tenant.id)
    app.config["KAFKA_ENABLED"] = False

    outcomes = outbox_service.publish_pending_events()

    assert outcomes == []
    db.session.refresh(event)
    assert event.status == "pending"


def test_publish_succeeds_via_injected_producer_and_builds_the_full_envelope(app):
    tenant = _create_tenant("outbox-success-bank")
    event = _enqueue(tenant.id)
    app.config["KAFKA_ENABLED"] = True
    fake_producer = _FakeProducer()

    outcomes = outbox_service.publish_pending_events(producer=fake_producer)

    assert len(outcomes) == 1
    assert outcomes[0].status == "published"
    db.session.refresh(event)
    assert event.status == "published"
    assert event.published_at is not None

    topic, key, envelope = fake_producer.sent[0]
    assert topic == "decision.created.v1"
    assert key == event.aggregate_id
    assert envelope == {
        "event_id": event.id,
        "event_type": "decision.created.v1",
        "schema_version": 1,
        "tenant_id": tenant.id,
        "aggregate_type": "decision",
        "aggregate_id": "00000000-0000-0000-0000-000000000001",
        "correlation_id": "req-1",
        "occurred_at": event.created_at.isoformat(),
        "payload": {"score": 0.5, "outcome": "refer"},
    }


def test_publish_failure_retries_without_losing_the_row(app):
    tenant = _create_tenant("outbox-retry-bank")
    event = _enqueue(tenant.id)
    app.config["KAFKA_ENABLED"] = True

    outcomes = outbox_service.publish_pending_events(producer=_FakeProducer(should_fail=True))

    assert outcomes[0].status == "retry"
    db.session.refresh(event)
    assert event.status == "pending"
    assert event.attempts == 1
    assert "simulated broker failure" in event.last_error


def test_publish_marks_failed_and_raises_an_alert_after_max_attempts(app):
    tenant = _create_tenant("outbox-max-attempts-bank")
    event = _enqueue(tenant.id)
    event.attempts = outbox_service.MAX_ATTEMPTS - 1
    db.session.commit()
    app.config["KAFKA_ENABLED"] = True

    outcomes = outbox_service.publish_pending_events(producer=_FakeProducer(should_fail=True))

    assert outcomes[0].status == "failed"
    db.session.refresh(event)
    assert event.status == "failed"
    assert event.attempts == outbox_service.MAX_ATTEMPTS

    alerts = MonitoringAlert.query.filter_by(tenant_id=tenant.id, alert_type="outbox_publish_failure").all()
    assert len(alerts) == 1
    assert alerts[0].severity == "high"


def test_kafka_unavailable_at_producer_construction_retries_pending_events(app, monkeypatch):
    tenant = _create_tenant("outbox-unavailable-bank")
    event = _enqueue(tenant.id)
    app.config["KAFKA_ENABLED"] = True

    def _raise_no_brokers():
        raise ConnectionError("no brokers available")

    monkeypatch.setattr(outbox_service, "_default_producer", _raise_no_brokers)

    outcomes = outbox_service.publish_pending_events()

    assert outcomes[0].status == "retry"
    db.session.refresh(event)
    assert event.status == "pending"
    assert "unavailable" in event.last_error.lower()


def test_republishing_reuses_the_same_event_id_for_duplicate_delivery_safety(app):
    # If a crash happens between "Kafka ack" and "commit status=published",
    # the next run re-publishes the same row. A consumer deduplicating by
    # event_id must see the identical id both times -- prove the envelope
    # doesn't mint a new id on a second publish attempt.
    tenant = _create_tenant("outbox-dedup-bank")
    event = _enqueue(tenant.id)

    first_envelope = outbox_service.build_envelope(event)
    second_envelope = outbox_service.build_envelope(event)

    assert first_envelope["event_id"] == second_envelope["event_id"] == event.id
