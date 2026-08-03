"""Notification placeholder consumer (SPRINT-008B).

Proves the notification seam end-to-end: consumes completed collection
transactions and emits an INTERNAL notification through the platform
notifier port (the logging adapter today). No SMS, no email, no push —
real channels arrive with the Notifications work order, which will only
have to swap the notifier adapter, not touch this flow.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.infrastructure.events import EventEnvelope
from platform_core.infrastructure.notifications import Notification, get_notifier
from platform_core.modules.event_relay.consumers import EventConsumer, register_consumer

log = structlog.get_logger("consumers.notification")


class NotificationPlaceholderConsumer(EventConsumer):
    name = "notification-placeholder"
    event_types = ("collection.transaction-completed.v1",)

    async def handle(self, envelope: EventEnvelope, session: AsyncSession) -> None:
        data = envelope.data
        rejected = bool(data.get("rejected"))
        await get_notifier().send(
            Notification(
                channel="in-app",
                recipient=str(data.get("supplier_id") or "unknown-supplier"),
                template_key=(
                    "notification.collection_rejected"
                    if rejected
                    else "notification.collection_completed"
                ),
                payload={
                    "transaction_id": data.get("transaction_id"),
                    "net_weight": data.get("net_weight"),
                    "gross_amount": data.get("gross_amount"),
                    "currency": data.get("currency"),
                },
            )
        )
        log.info(
            "internal_notification",
            transaction_id=data.get("transaction_id"),
            supplier_id=data.get("supplier_id"),
            rejected=rejected,
        )


register_consumer(NotificationPlaceholderConsumer())
