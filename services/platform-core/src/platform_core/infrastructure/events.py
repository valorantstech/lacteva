"""Event infrastructure: platform envelope + event bus port and adapters.

Envelope fields follow the platform event rules (docs/09-events): id, type,
source, time, tenant context, trace context, payload. Event *types* follow
`<domain>.<past-tense-fact>.v<major>` (STD-0002).

TODO(M1): transactional outbox — publish must happen atomically with the DB
commit (write to an outbox table in the same transaction; a relay publishes
to RabbitMQ). Until then, publish-after-commit can drop events on crash.
TODO(M1): consumer framework (queue binding, retry, dead-letter, idempotency
keys) — only publishing is implemented in the foundation.
"""

import uuid
from typing import Any, Protocol

import structlog
from pydantic import BaseModel, Field

from platform_core.core.config import get_settings
from platform_core.core.db import utcnow
from platform_core.core.tenancy import get_current_tenant

log = structlog.get_logger("events")


class EventEnvelope(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    type: str
    source: str
    time: str
    tenant_id: uuid.UUID | None = None
    actor_id: uuid.UUID | None = None
    trace_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def new(
        cls,
        event_type: str,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID | None = None,
    ) -> "EventEnvelope":
        ctx = structlog.contextvars.get_contextvars()
        return cls(
            type=event_type,
            source=get_settings().service_name,
            time=utcnow().isoformat(),
            tenant_id=get_current_tenant(),
            actor_id=actor_id,
            trace_id=ctx.get("request_id"),
            data=data,
        )


class EventBus(Protocol):
    async def publish(self, event: EventEnvelope) -> None: ...


class InMemoryEventBus:
    """Test/dev bus: records events for assertions."""

    def __init__(self) -> None:
        self.published: list[EventEnvelope] = []

    async def publish(self, event: EventEnvelope) -> None:
        self.published.append(event)
        log.debug("event_published", type=event.type, id=str(event.id))


class NullEventBus:
    async def publish(self, event: EventEnvelope) -> None:  # pragma: no cover
        log.warning("event_dropped_null_bus", type=event.type)


class RabbitMQEventBus:
    """Publishes to the `lacteva.events` topic exchange, routing key = event type."""

    EXCHANGE = "lacteva.events"

    def __init__(self, url: str) -> None:
        self._url = url
        self._connection = None
        self._channel = None
        self._exchange = None

    async def _ensure(self):
        if self._exchange is None:
            import aio_pika

            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel()
            self._exchange = await self._channel.declare_exchange(
                self.EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
            )
        return self._exchange

    async def publish(self, event: EventEnvelope) -> None:
        import aio_pika

        exchange = await self._ensure()
        await exchange.publish(
            aio_pika.Message(
                body=event.model_dump_json().encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=str(event.id),
            ),
            routing_key=event.type,
        )
        log.info("event_published", type=event.type, id=str(event.id))

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        settings = get_settings()
        if settings.event_bus == "rabbitmq":
            _bus = RabbitMQEventBus(settings.rabbitmq_url)
        elif settings.event_bus == "memory":
            _bus = InMemoryEventBus()
        else:
            _bus = NullEventBus()
    return _bus


def reset_event_bus() -> None:
    global _bus
    _bus = None
