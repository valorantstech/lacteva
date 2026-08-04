"""Channel provider abstraction (NOT-001).

A provider is the thing that actually hands a rendered message to a channel.
The platform ships ADAPTERS ONLY — a logging adapter (which delegates to the
existing `Notifier` port, preserving that abstraction) and a placeholder
adapter that accepts and records without side effects. Real gateways (market
SMS providers, transactional email) are deployment concerns that implement
this same protocol; no provider-specific code lives in the platform.

Selection is configuration (`LACTEVA_NOTIFICATION_SMS_PROVIDER`,
`LACTEVA_NOTIFICATION_EMAIL_PROVIDER`), and providers can be swapped at
runtime through `register_provider` — the seam deployments and tests use.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

import structlog

from platform_core.core.config import get_settings
from platform_core.infrastructure.notifications import Notification, get_notifier

log = structlog.get_logger("notification.provider")


class ProviderSendError(Exception):
    """Delivery failed. Retryable — the notification keeps its history."""


@dataclass(frozen=True)
class OutboundMessage:
    channel: str
    recipient: str
    title: str
    body: str
    language: str
    template_key: str
    notification_id: uuid.UUID


class ChannelProvider(Protocol):
    name: str

    async def send(self, message: OutboundMessage) -> str:
        """Deliver, returning a provider reference for the audit trail."""
        ...


class LoggingProvider:
    """Delegates to the platform `Notifier` port (preserved abstraction) and
    logs the rendered message. The dev/test default."""

    def __init__(self, channel: str):
        self.name = f"logging-{channel}"
        self._channel = channel

    async def send(self, message: OutboundMessage) -> str:
        await get_notifier().send(
            Notification(
                id=message.notification_id,
                channel=self._channel,
                recipient=message.recipient,
                template_key=message.template_key,
                locale=message.language,
                payload={"title": message.title, "body": message.body},
            )
        )
        log.info(
            "notification_dispatched",
            channel=self._channel,
            template=message.template_key,
            recipient=message.recipient,
            language=message.language,
        )
        return f"{self.name}:{message.notification_id}"


class PlaceholderProvider:
    """Accepts and records without any side effect — the stand-in until a
    market gateway is configured. Deliveries are marked sent so the pipeline
    is exercised end to end; nothing leaves the platform."""

    def __init__(self, channel: str):
        self.name = f"placeholder-{channel}"
        self._channel = channel

    async def send(self, message: OutboundMessage) -> str:
        log.debug(
            "notification_placeholder",
            channel=self._channel,
            template=message.template_key,
            recipient=message.recipient,
        )
        return f"{self.name}:{uuid.uuid4()}"


_PROVIDERS: dict[str, ChannelProvider] = {}


def register_provider(channel: str, provider: ChannelProvider) -> None:
    """Install a provider for a channel (deployment wiring; tests use it to
    inject failing or recording adapters)."""
    _PROVIDERS[channel] = provider


def reset_providers() -> None:
    _PROVIDERS.clear()


def get_provider(channel: str) -> ChannelProvider:
    if channel not in _PROVIDERS:
        settings = get_settings()
        configured = {
            "sms": settings.notification_sms_provider,
            "email": settings.notification_email_provider,
        }.get(channel, "logging")
        _PROVIDERS[channel] = (
            PlaceholderProvider(channel)
            if configured == "placeholder"
            else LoggingProvider(channel)
        )
    return _PROVIDERS[channel]
