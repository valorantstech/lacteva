"""Notification infrastructure: channel-agnostic port + adapters.

Foundation ships the port and a structured-log adapter. Real channels are
adapters to be added per market (TODO markers below) — the port stays stable.
"""

import uuid
from typing import Any, Protocol

import structlog
from pydantic import BaseModel, Field

from platform_core.core.i18n import translate

log = structlog.get_logger("notifications")


class Notification(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    channel: str  # "email" | "sms" | "push" | "in-app"
    recipient: str  # address/number/device token per channel
    template_key: str  # i18n catalog key prefix, e.g. "notification.welcome"
    locale: str = "en"
    payload: dict[str, Any] = Field(default_factory=dict)


class Notifier(Protocol):
    async def send(self, notification: Notification) -> None: ...


class LoggingNotifier:
    """Dev/test adapter: renders and logs instead of sending."""

    async def send(self, notification: Notification) -> None:
        subject = translate(f"{notification.template_key}.subject", notification.locale)
        log.info(
            "notification_sent",
            channel=notification.channel,
            recipient=notification.recipient,
            template=notification.template_key,
            locale=notification.locale,
            subject=subject,
        )


# TODO(M2): EmailNotifier (SES via aws-sdk), SmsNotifier (market-specific
# gateways — SMS is the primary channel for smallholder markets), PushNotifier
# (FCM for the Flutter app). Channel routing + per-user channel preferences
# belong to a notification-preferences module, not the port.

_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    global _notifier
    if _notifier is None:
        _notifier = LoggingNotifier()
    return _notifier
