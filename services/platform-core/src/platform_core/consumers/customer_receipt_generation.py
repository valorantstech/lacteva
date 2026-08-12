"""Customer receipt generation consumer (DEMO-009).

The mirror of `receipt_generation` for the SALES side, and it follows the same
rule: a receipt is produced from the durable log, never requested by a business
module. When a customer payment is recorded, this consumer reads the event and
mints the proof — which is why a receipt can always be reproduced, and why no
billing code knows receipts exist.

Everything the receipt shows travels in `sales.customer-payment-recorded.v1`,
so the handler never calls back into billing or customer.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.tenancy import get_current_tenant, set_current_tenant
from platform_core.infrastructure.events import EventEnvelope, get_event_bus
from platform_core.modules.audit.service import AuditService
from platform_core.modules.billing.service import BillingService
from platform_core.modules.event_relay.consumers import EventConsumer, register_consumer
from platform_core.modules.event_relay.service import OutboxEventBus

CUSTOMER_PAYMENT_RECORDED = "sales.customer-payment-recorded.v1"


class CustomerReceiptGenerationConsumer(EventConsumer):
    name = "customer-receipt-generation"
    event_types = (CUSTOMER_PAYMENT_RECORDED,)

    async def handle(self, envelope: EventEnvelope, session: AsyncSession) -> None:
        if envelope.tenant_id is None or not envelope.data.get("payment_id"):
            return

        previous = get_current_tenant()
        set_current_tenant(envelope.tenant_id)
        try:
            service = BillingService(
                session, OutboxEventBus(session, get_event_bus()), AuditService(session)
            )
            await service.generate_receipt(
                tenant_id=envelope.tenant_id,
                payment_id=uuid.UUID(envelope.data["payment_id"]),
                data=envelope.data,
                source_event_id=envelope.id,
            )
        finally:
            set_current_tenant(previous)


register_consumer(CustomerReceiptGenerationConsumer())
