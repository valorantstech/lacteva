"""Receipt generation consumer (RCP-001).

Receipts are produced from the durable log, never requested by a business
module: when a payment completes, this consumer reads the event and mints the
artifact. That is why a receipt can always be reproduced — the fact that
justifies it is permanent — and why no payment code knows receipts exist.

Everything the receipt shows travels in `payment.completed.v1` (PAY-001
enriched it for exactly this reason), so the handler never calls back into
the payment, settlement, or supplier modules.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.tenancy import get_current_tenant, set_current_tenant
from platform_core.infrastructure.events import EventEnvelope, get_event_bus
from platform_core.modules.audit.service import AuditService
from platform_core.modules.event_relay.consumers import EventConsumer, register_consumer
from platform_core.modules.event_relay.service import OutboxEventBus
from platform_core.modules.receipt.service import ReceiptService

PAYMENT_COMPLETED = "payment.completed.v1"


class ReceiptGenerationConsumer(EventConsumer):
    name = "receipt-generation"
    event_types = (PAYMENT_COMPLETED,)

    async def handle(self, envelope: EventEnvelope, session: AsyncSession) -> None:
        if envelope.tenant_id is None or not envelope.data.get("payment_id"):
            return

        # The receipt publishes its own events, and the envelope factory reads
        # the tenant from context — so the consumer establishes that context
        # for the work it does, exactly as a request would.
        previous = get_current_tenant()
        set_current_tenant(envelope.tenant_id)
        try:
            # The receipt's own events go through the outbox in the SAME
            # transaction as the receipt row: either both land or neither does.
            service = ReceiptService(
                session, OutboxEventBus(session, get_event_bus()), AuditService(session)
            )
            await service.generate(
                tenant_id=envelope.tenant_id,
                payment_id=uuid.UUID(envelope.data["payment_id"]),
                data=envelope.data,
                source_event_id=envelope.id,
                correlation_id=_parse_uuid(envelope.correlation_id),
                actor_id=envelope.actor_id,
            )
        finally:
            set_current_tenant(previous)


def _parse_uuid(value) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


register_consumer(ReceiptGenerationConsumer())
