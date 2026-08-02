"""Event Relay: outbox atomicity, dispatch, retry, DLQ, replay, idempotency."""

import contextlib
import uuid
from datetime import timedelta

from platform_core.core.config import get_settings
from platform_core.core.db import get_session_factory, utcnow
from platform_core.infrastructure.events import EventEnvelope, InMemoryEventBus
from platform_core.modules.event_relay.models import DeadLetter, EventDelivery, OutboxEvent
from platform_core.modules.event_relay.service import (
    MAX_ATTEMPTS,
    OutboxEventBus,
    RelayService,
    backoff_delay,
)
from tests.conftest import register_and_login


@contextlib.contextmanager
def background_mode():
    settings = get_settings()
    settings.outbox_mode = "background"
    try:
        yield
    finally:
        settings.outbox_mode = "inline"


class FailingTransport(InMemoryEventBus):
    """Fails the first `failures` publishes, then succeeds."""

    def __init__(self, failures: int):
        super().__init__()
        self.failures = failures
        self.calls = 0

    async def publish(self, event: EventEnvelope) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("transport unavailable")
        await super().publish(event)


def _envelope(name="test.event-happened.v1", **kw) -> EventEnvelope:
    return EventEnvelope.new(name, {"n": kw.pop("n", 1)}, **kw)


async def _store(session, transport, envelope) -> OutboxEvent:
    with background_mode():
        await OutboxEventBus(session, transport).publish(envelope)
    return await session.get(OutboxEvent, envelope.id)


# --- outbox atomicity --------------------------------------------------------


async def test_rollback_discards_event(app):
    transport = InMemoryEventBus()
    async with get_session_factory()() as session:
        env = _envelope()
        await _store(session, transport, env)
        await session.rollback()
    async with get_session_factory()() as session:
        assert await session.get(OutboxEvent, env.id) is None
    assert transport.published == []  # never reached the transport either


async def test_commit_persists_pending_event(app):
    transport = InMemoryEventBus()
    async with get_session_factory()() as session:
        env = _envelope()
        row = await _store(session, transport, env)
        assert row.status == "pending" and row.attempts == 0
        await session.commit()
    assert transport.published == []  # background mode: delivery is the relay's job


async def test_inline_mode_delivers_immediately(app):
    transport = InMemoryEventBus()
    async with get_session_factory()() as session:
        env = _envelope()
        await OutboxEventBus(session, transport).publish(env)  # inline (test default)
        row = await session.get(OutboxEvent, env.id)
        assert row.status == "delivered"
        await session.commit()
    assert [e.id for e in transport.published] == [env.id]


# --- dispatch, ordering, idempotency ----------------------------------------


async def test_dispatch_delivers_in_commit_order(app):
    transport = InMemoryEventBus()
    async with get_session_factory()() as session:
        envs = [_envelope(n=i) for i in range(5)]
        for env in envs:
            await _store(session, transport, env)
        relay = RelayService(session, transport)
        delivered = await relay.dispatch_pending()
        await session.commit()
    assert delivered == 5
    assert [e.data["n"] for e in transport.published] == [0, 1, 2, 3, 4]


async def test_event_id_is_stable_idempotency_key(app):
    """The wire event id equals the outbox id — consumers dedupe on it."""
    transport = InMemoryEventBus()
    async with get_session_factory()() as session:
        env = _envelope()
        row = await _store(session, transport, env)
        relay = RelayService(session, transport)
        await relay.dispatch_pending()
        await session.commit()
    assert transport.published[0].id == row.id == env.id


async def test_delivered_event_not_dispatched_twice(app):
    transport = InMemoryEventBus()
    async with get_session_factory()() as session:
        env = _envelope()
        row = await _store(session, transport, env)
        relay = RelayService(session, transport)
        assert await relay.dispatch_pending() == 1
        assert await relay.dispatch_pending() == 0  # nothing due
        assert await relay.dispatch_one(row, now=utcnow()) is False  # CAS refuses
        await session.commit()
    assert len(transport.published) == 1


async def test_delivery_record_written_with_latency(app):
    transport = InMemoryEventBus()
    async with get_session_factory()() as session:
        env = _envelope()
        await _store(session, transport, env)
        await RelayService(session, transport).dispatch_pending()
        from sqlalchemy import select

        rows = (
            await session.scalars(select(EventDelivery).where(EventDelivery.event_id == env.id))
        ).all()
        assert len(rows) == 1
        assert rows[0].status == "success"
        assert rows[0].attempt == 1
        assert rows[0].latency_ms is not None


# --- retry engine ------------------------------------------------------------


async def test_failure_schedules_backoff_retry(app):
    transport = FailingTransport(failures=1)
    async with get_session_factory()() as session:
        env = _envelope()
        row = await _store(session, transport, env)
        relay = RelayService(session, transport)
        now = utcnow()
        assert await relay.dispatch_pending(now=now) == 0
        await session.refresh(row)
        assert row.status == "pending" and row.attempts == 1
        assert row.last_error and "unavailable" in row.last_error
        # Not due yet -> untouched; due later -> delivered.
        assert await relay.dispatch_pending(now=now) == 0
        later = now + timedelta(seconds=backoff_delay(1) + 0.1)
        assert await relay.dispatch_pending(now=later) == 1
        await session.refresh(row)
        assert row.status == "delivered" and row.attempts == 2
        await session.commit()
    assert len(transport.published) == 1


def test_backoff_is_exponential_and_capped():
    assert backoff_delay(1) == 2.0
    assert backoff_delay(2) == 4.0
    assert backoff_delay(3) == 8.0
    assert backoff_delay(100) == 300.0  # capped


async def test_failed_attempts_produce_delivery_records(app):
    transport = FailingTransport(failures=2)
    async with get_session_factory()() as session:
        env = _envelope()
        await _store(session, transport, env)
        relay = RelayService(session, transport)
        now = utcnow()
        for i in range(3):
            await relay.dispatch_pending(now=now + timedelta(seconds=400 * i))
        from sqlalchemy import select

        rows = (
            await session.scalars(
                select(EventDelivery)
                .where(EventDelivery.event_id == env.id)
                .order_by(EventDelivery.attempt)
            )
        ).all()
        assert [r.status for r in rows] == ["failed", "failed", "success"]


# --- dead letters & replay ---------------------------------------------------


async def _make_dead(session, transport) -> OutboxEvent:
    env = _envelope()
    row = await _store(session, transport, env)
    relay = RelayService(session, transport)
    now = utcnow()
    for i in range(MAX_ATTEMPTS):
        await relay.dispatch_pending(now=now + timedelta(seconds=400 * i))
    await session.refresh(row)
    return row


async def test_dead_letter_after_max_attempts(app):
    transport = FailingTransport(failures=999)
    async with get_session_factory()() as session:
        row = await _make_dead(session, transport)
        assert row.status == "dead" and row.attempts == MAX_ATTEMPTS
        from sqlalchemy import select

        dl = await session.scalar(select(DeadLetter).where(DeadLetter.event_id == row.id))
        assert dl is not None and "unavailable" in dl.reason
        # Dead events are never retried by the dispatcher.
        relay = RelayService(session, transport)
        assert await relay.dispatch_pending(now=utcnow() + timedelta(hours=1)) == 0
    assert transport.published == []


async def test_replay_dead_letter_delivers_when_transport_recovers(app):
    transport = FailingTransport(failures=MAX_ATTEMPTS)  # recovers afterwards
    async with get_session_factory()() as session:
        row = await _make_dead(session, transport)
        from sqlalchemy import select

        dl = await session.scalar(select(DeadLetter).where(DeadLetter.event_id == row.id))
        relay = RelayService(session, transport)
        replayed = await relay.replay_dead_letter(dl.id)
        assert replayed.status == "pending" and replayed.attempts == 0
        assert dl.replay_count == 1 and dl.replayed_at is not None
        assert await relay.dispatch_pending() == 1
        await session.refresh(row)
        assert row.status == "delivered"
        await session.commit()
    assert len(transport.published) == 1


async def test_retry_event_rules(app):
    transport = InMemoryEventBus()
    async with get_session_factory()() as session:
        env = _envelope()
        row = await _store(session, transport, env)
        relay = RelayService(session, transport)
        await relay.dispatch_pending()
        # Delivered events refuse plain retry but allow explicit replay.
        import pytest

        from platform_core.core.errors import ConflictError, NotFoundError

        with pytest.raises(ConflictError):
            await relay.retry_event(row.id)
        replayed = await relay.replay_delivered(row.id)
        assert replayed.status == "pending"
        assert await relay.dispatch_pending() == 1
        with pytest.raises(NotFoundError):
            await relay.retry_event(uuid.uuid4())
    assert len(transport.published) == 2  # original + replay, same event id
    assert transport.published[0].id == transport.published[1].id


async def test_stale_delivering_rows_are_reclaimed(app):
    """Crash recovery: a row stuck in 'delivering' is picked up again."""
    transport = InMemoryEventBus()
    async with get_session_factory()() as session:
        env = _envelope()
        row = await _store(session, transport, env)
        row.status = "delivering"
        row.claimed_at = utcnow() - timedelta(seconds=120)
        await session.flush()
        relay = RelayService(session, transport)
        assert await relay.dispatch_pending() == 1
        await session.refresh(row)
        assert row.status == "delivered"


# --- metadata ----------------------------------------------------------------


async def test_envelope_metadata_roundtrip(app):
    transport = InMemoryEventBus()
    agg_id, cause = uuid.uuid4(), uuid.uuid4()
    async with get_session_factory()() as session:
        env = EventEnvelope.new(
            "test.thing-happened.v1",
            {"k": "v"},
            aggregate_type="thing",
            aggregate_id=agg_id,
            causation_id=cause,
            version=3,
        )
        await _store(session, transport, env)
        await RelayService(session, transport).dispatch_pending()
    out = transport.published[0]
    assert out.aggregate_type == "thing" and out.aggregate_id == agg_id
    assert out.causation_id == cause and out.version == 3
    assert out.data == {"k": "v"}


async def test_stats_reflect_reality(app):
    transport = FailingTransport(failures=999)
    async with get_session_factory()() as session:
        ok_transport = InMemoryEventBus()
        await _store(session, ok_transport, _envelope())
        await RelayService(session, ok_transport).dispatch_pending()
        await _make_dead(session, transport)
        await _store(session, ok_transport, _envelope())  # stays pending
        stats = await RelayService(session, ok_transport).stats()
        assert stats.delivered == 1
        assert stats.dead == 1
        assert stats.pending == 1
        assert stats.average_latency_ms is not None


# --- API (internal, platform staff only) -------------------------------------


async def test_relay_api_denied_for_tenant_admin(client):
    from tests.test_org_structure import _tenant_admin

    _, headers = await _tenant_admin(client)
    assert (await client.get("/v1/_relay/status", headers=headers)).status_code == 403


async def test_relay_api_flow_for_platform_admin(client):
    _, headers = await register_and_login(client, "ops@example.com", admin=True)
    # Registration + login emitted events through the inline outbox already.
    status = (await client.get("/v1/_relay/status", headers=headers)).json()
    assert status["delivered"] >= 1 and status["dead"] == 0

    events = (await client.get("/v1/_relay/events?status=delivered", headers=headers)).json()
    assert len(events) >= 1
    assert all(e["status"] == "delivered" for e in events)
    event_id = events[0]["id"]

    # Replay a delivered event, dispatch it, and see it delivered again.
    r = await client.post(f"/v1/_relay/events/{event_id}/replay", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    r = await client.post("/v1/_relay/dispatch", headers=headers)
    assert r.status_code == 200 and r.json()["delivered"] == 1
    assert (await client.get("/v1/_relay/dead-letters", headers=headers)).json() == []


async def test_api_events_carry_correlation_id(client, bus):
    _, _headers = await register_and_login(client, admin=True)
    org_events = [e for e in bus.published if e.type == "identity.user-registered.v1"]
    assert org_events and org_events[0].correlation_id  # request id propagated


async def test_failed_request_leaves_no_orphan_events(client, bus):
    """A rolled-back business tx must not leak its events (the outbox's whole point)."""
    from tests.test_org_structure import _tenant_admin

    _, headers = await _tenant_admin(client)
    before = len(bus.published)
    async with get_session_factory()() as session:
        from sqlalchemy import func, select

        rows_before = await session.scalar(select(func.count()).select_from(OutboxEvent))
    await client.post("/v1/workspaces", json={"name": "First", "slug": "dup-slug"}, headers=headers)
    r = await client.post(
        "/v1/workspaces", json={"name": "Second", "slug": "dup-slug"}, headers=headers
    )
    assert r.status_code == 409  # conflict -> rollback
    async with get_session_factory()() as session:
        from sqlalchemy import func, select

        rows_after = await session.scalar(select(func.count()).select_from(OutboxEvent))
    # Exactly one workspace-created event exists (the successful one).
    assert rows_after == rows_before + 1
    created = [e for e in bus.published[before:] if e.type == "organization.workspace-created.v1"]
    assert len(created) == 1
