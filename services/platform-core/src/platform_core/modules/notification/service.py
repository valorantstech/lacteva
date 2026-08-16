"""Notification dispatcher and history (NOT-001).

The dispatcher is the ONLY thing in the platform that sends messages.
Business modules never call it — notifications originate exclusively from
durable domain events, consumed by the notification consumer (BR-0016).

Retry reuses the consumer framework's semantics and constants
(`backoff_delay`, `MAX_CONSUMER_ATTEMPTS`): failed → wait → retry → …→ dead.
It is applied to the NOTIFICATION rather than to the event, because event
processing succeeded — it is the delivery that failed, and raising would
roll back the very history this module exists to keep.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Literal

import structlog
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import as_utc, utcnow
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.core.metrics import (
    NOTIFICATION_PROVIDER_ERRORS,
    NOTIFICATION_PROVIDER_SECONDS,
    NOTIFICATION_RETRIES,
    NOTIFICATIONS_DEAD,
    NOTIFICATIONS_FAILED,
    NOTIFICATIONS_SENT,
)
from platform_core.core.org_context import tenant_locale
from platform_core.core.tenancy import require_current_tenant
from platform_core.modules.event_relay.consumers import MAX_CONSUMER_ATTEMPTS
from platform_core.modules.event_relay.service import backoff_delay
from platform_core.modules.notification.models import (
    Notification,
    NotificationDevice,
    NotificationRecipient,
)
from platform_core.modules.notification.providers import (
    OutboundMessage,
    PermanentSendError,
    ProviderSendError,
    get_provider,
    vendor_template_for,
)
from platform_core.modules.notification.templates import (
    TemplateNotFoundError,
    TemplateRenderError,
    catalog,
    get_template,
    render,
)

log = structlog.get_logger("notification")


def _token_suffix(token: str) -> str:
    """The last few characters, which identify a device in a support call and
    reach no handset."""
    return f"…{token[-6:]}" if len(token) > 6 else "…"


def _device_view(device: NotificationDevice) -> "PushDeviceView":
    return PushDeviceView(
        id=device.id,
        platform=device.platform,
        label=device.label,
        language=device.language,
        token_suffix=_token_suffix(device.token),
        last_seen_at=as_utc(device.last_seen_at),
    )


#: What a secret variable looks like everywhere except the outbound message
#: (SEC-003 / F-04). Deliberately not empty and not a plausible token: an
#: operator reading a stored body should be able to tell that something was
#: removed rather than that the message was malformed.
REDACTED = "[redacted]"


class NotificationRequest(BaseModel):
    """What the consumer asks for — never a message, always a template."""

    event_id: uuid.UUID
    event_name: str
    tenant_id: uuid.UUID | None = None
    template_key: str
    channel: str
    #: DEMO-028. What business record this message is ABOUT — a settlement, an
    #: invoice. Separate from `event_id`, which says what produced it.
    source_type: str | None = None
    source_id: uuid.UUID | None = None
    recipient_ref: uuid.UUID | None = None  # supplier/user id, resolved via the directory
    recipient: str | None = None  # explicit address when the event carries it
    language: str | None = None
    variables: dict = {}
    #: SEC-003 / F-04: variables whose VALUES are secrets. Rendered into the
    #: outbound message, stored in `secret_payload` only until delivery, never
    #: returned by any API, never logged. See `Notification.secret_payload`.
    secret_variables: dict = {}


class RegisterPushDeviceCommand(BaseModel):
    """What a phone tells the platform after signing in (DEMO-012 §10).

    Validated HERE rather than in the service, so a malformed registration is
    a 422 from the framework instead of a 500 from a `ValueError` this
    application has no handler for.
    """

    token: str = Field(min_length=1, max_length=400)
    #: Constrained because the outbound payload differs per platform: a value
    #: the gateway does not know is a message that silently goes nowhere.
    platform: Literal["android", "ios", "web"] = "android"
    label: str = Field(default="", max_length=80)
    language: str = Field(default="en", max_length=8)

    @field_validator("token")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        token = value.strip()
        if not token:
            raise ValueError("token is required")
        return token


class PushDeviceView(BaseModel):
    """A device, WITHOUT its token.

    Named `Push…` and not `Device…` deliberately: `operational_readiness`
    already exports `DeviceView` and `RegisterDeviceCommand` for weighing
    scales and analyzers. Two identically-named DTOs in one API produce ONE
    OpenAPI component — a generated client would get one of them wrong — and
    in `routes.py` the second import silently shadowed the first.

    The token is never returned — not to the operator who can read the
    notification history, and not to the phone that supplied it. Anyone
    holding it can push to that handset, and an endpoint that hands it back
    turns a read grant into that capability. The suffix is enough for a
    support call and useless to a sender.
    """

    id: uuid.UUID
    platform: str
    label: str
    language: str
    token_suffix: str
    last_seen_at: datetime


class NotificationView(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    event_name: str
    template_key: str
    channel: str
    language: str
    recipient: str | None
    recipient_ref: uuid.UUID | None
    title: str | None
    rendered_text: str | None
    #: What LACTEVA did: pending | sent | failed | dead. `sent` means the
    #: provider accepted the request.
    status: str
    provider: str | None
    provider_reference: str | None
    #: DEMO-028. What the PROVIDER said: accepted | sent | delivered | unknown.
    #: `None` before the first successful attempt. Every adapter in this
    #: platform reports `accepted` today — nothing receives a delivery receipt,
    #: so nothing may claim one.
    provider_status: str | None = None
    #: DEMO-028. The business record this message is about.
    source_type: str | None = None
    source_id: uuid.UUID | None = None
    attempt_count: int
    next_attempt_at: datetime | None
    error: str | None
    payload: dict
    created_at: datetime
    sent_at: datetime | None
    failed_at: datetime | None

    model_config = {"from_attributes": True}


class NotificationPage(BaseModel):
    items: list[NotificationView]
    total: int
    limit: int
    offset: int


class NotificationStats(BaseModel):
    total: int
    by_status: dict[str, int]
    by_channel: dict[str, int]
    retryable: int


class ChannelPosture(BaseModel):
    """What an operator may know about one channel's gateway (DEMO-031).

    **Never a credential, and never a URL.** A URL is not a secret but it
    identifies the vendor and the account path, and an operator troubleshooting
    "did it go?" does not need it. What they need is whether the channel is
    configured, whether the platform is permitted to use it, and whether it can
    report deliveries — three yes/no answers that leak nothing.
    """

    channel: str
    #: The adapter's own name, e.g. `sandbox-sms`, `http-sms`, `disabled`.
    provider: str
    #: Configured means the adapter has what it needs to be built at all.
    configured: bool
    #: Whether this adapter would actually attempt a network call in the
    #: current messaging mode.
    can_send: bool
    #: Whether it can receive delivery receipts (DEMO-029).
    reports_delivery: bool


class MessagingPosture(BaseModel):
    """The one screen answer to "is this deployment able to send?"."""

    #: `test` | `sandbox` | `production`.
    mode: str
    #: True only in `production`. A deployment showing false has never sent a
    #: real message, whatever else is configured.
    sends_real_messages: bool
    channels: list[ChannelPosture]


class TemplateView(BaseModel):
    key: str
    channel: str
    language: str
    title: str
    body: str
    variables: list[str]


class RenderedPreview(BaseModel):
    key: str
    channel: str
    language: str
    title: str
    body: str
    variables_used: dict


#: Config key a tenant sets to choose how its people are reached, per purpose.
#: `notification.channel.settlement_finalized = "whatsapp"`.
CHANNEL_CONFIG_PREFIX = "notification.channel."

#: Channels a tenant may choose between for an outbound business message.
#: `push` is deliberately absent: it reaches an app the recipient may not have
#: installed, so it is a mapping the platform makes, never a preference a
#: tenant expresses for a farmer with a feature phone.
SELECTABLE_CHANNELS = ("sms", "whatsapp", "email")


async def resolve_channel(
    session: AsyncSession,
    template_key: str,
    default: str,
    tenant_id: uuid.UUID | None = None,
) -> str:
    """Which channel this tenant wants for this kind of message (DEMO-025).

    **This is the multi-country seam, and it contains no country.** An Indian
    dairy that wants WhatsApp settlement slips and a Kenyan one that wants SMS
    differ by a configuration row, not by a branch — so adding Qatar, or a
    market nobody has met yet, is a row too.

    Falls back to the event mapping's own default whenever the tenant has said
    nothing, which is what makes this safe to introduce: every existing
    deployment keeps the channel it already had.

    An unrecognised value falls back rather than raising. A typo in a config
    row must not stop a farmer being told about their money; it should send on
    the default and be visible in the notification history.
    """
    from platform_core.core.tenancy import get_current_tenant, set_current_tenant
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.configuration.service import ConfigurationService

    # `ConfigurationService.resolve` scopes itself from the tenant CONTEXTVAR,
    # and the dispatch consumer does not set one — it carries the tenant on the
    # event and passes it explicitly, as every other lookup here does. So the
    # variable is set for the duration of this read and restored afterwards.
    # Without this the lookup silently found nothing and every tenant kept the
    # default channel, which is a configuration feature that does not work.
    previous = get_current_tenant()
    if tenant_id is not None:
        set_current_tenant(tenant_id)
    try:
        # A real audit service rather than None: `resolve` does not write today,
        # and a read that starts auditing tomorrow must not fail here.
        chosen = await ConfigurationService(session, AuditService(session)).resolve(
            f"{CHANNEL_CONFIG_PREFIX}{template_key}"
        )
    except Exception:
        return default
    finally:
        if tenant_id is not None:
            set_current_tenant(previous)
    if isinstance(chosen, str) and chosen in SELECTABLE_CHANNELS:
        return chosen
    log.warning(
        "notification_channel_config_ignored",
        template=template_key,
        configured=str(chosen)[:40],
    )
    return default


def provider_name(channel: str) -> str:
    """The provider's name for a metric label. Falls back rather than raising:
    a metrics lookup must never be the thing that breaks a delivery."""
    try:
        return get_provider(channel).name
    except Exception:
        return "unknown"


class NotificationService:
    def __init__(self, session: AsyncSession):
        self._session = session

    # --- dispatch -----------------------------------------------------------

    async def dispatch(self, request: NotificationRequest) -> Notification | None:
        """Create (idempotently) and attempt one notification.

        Returns None when the event already produced this notification — a
        consumer replay or duplicate delivery must never re-send.
        """
        existing = await self._session.scalar(
            select(Notification).where(
                Notification.event_id == request.event_id,
                Notification.template_key == request.template_key,
                Notification.channel == request.channel,
            )
        )
        if existing is not None:
            return None
        notification = Notification(
            tenant_id=request.tenant_id,
            event_id=request.event_id,
            event_name=request.event_name,
            template_key=request.template_key,
            channel=request.channel,
            # DEMO-013 §14: the ORGANIZATION's default, not the literal "en".
            # An event carries no language of its own; whose language it is
            # written in is a fact about the dairy receiving it, and later
            # about the person — `_resolve_recipient` narrows it to the
            # recipient's own choice when the directory or the device knows one.
            language=(
                request.language
                or (await tenant_locale(self._session, request.tenant_id)).default_language
            ),
            source_type=request.source_type,
            source_id=request.source_id,
            recipient_ref=request.recipient_ref,
            recipient=request.recipient,
            payload=_jsonable(request.variables),
            secret_payload=_jsonable(request.secret_variables) or None,
        )
        # DEPLOY-001: the uniqueness must decide the race, not the SELECT
        # above. `(event, template, channel)` is BR-0017's idempotency key, and
        # a check-then-act leaves a gap between the check and the insert — two
        # writers both see nothing, both insert, and one dies on
        # `uq_notification_event`, failing a consumer execution and spending a
        # retry for a message that was correctly NOT sent twice.
        #
        # The savepoint keeps the loser's violation from poisoning the whole
        # consumer transaction; losing the race means the notification already
        # exists, which is exactly the `None` this method returns for a replay.
        #
        # DEMO-025: the `add` belongs INSIDE the savepoint. It used to sit
        # outside, and entering `begin_nested()` can autoflush the pending
        # insert first — so the violation happened OUTSIDE the savepoint,
        # poisoned the outer transaction, and the caller's `commit()` raised
        # `PendingRollbackError`. The `except` below caught nothing because
        # nothing had been contained.
        #
        # It survived because SQLite's test stack shares one connection and
        # never actually races. Eight concurrent dispatches on real PostgreSQL
        # showed seven losers taking down their own transactions.
        try:
            async with self._session.begin_nested():
                self._session.add(notification)
                await self._session.flush()
        except IntegrityError:
            return None
        await self._attempt(notification)
        return notification

    async def retry(self, notification_id: uuid.UUID) -> Notification:
        """Operator-triggered retry of a failed or dead notification."""
        notification = await self._session.get(Notification, notification_id)
        if notification is None:
            raise NotFoundError("notification not found")
        if notification.status == "sent":
            raise ConflictError("notification was already delivered")
        await self._attempt(notification, forced=True)
        return notification

    async def retry_pending(self, *, limit: int = 100, now: datetime | None = None) -> dict:
        """Sweep due failed notifications. Driven by the background loop."""
        now = now or utcnow()
        rows = await self._session.scalars(
            select(Notification)
            .where(
                Notification.status == "failed",
                or_(
                    Notification.next_attempt_at.is_(None),
                    Notification.next_attempt_at <= now,
                ),
            )
            .order_by(Notification.next_attempt_at)
            .limit(limit)
        )
        sent = failed = 0
        for notification in rows.all():
            await self._attempt(notification, now=now)
            if notification.status == "sent":
                sent += 1
            else:
                failed += 1
        return {"retried": sent + failed, "sent": sent, "failed": failed}

    async def _attempt(
        self, notification: Notification, *, forced: bool = False, now: datetime | None = None
    ) -> None:
        now = now or utcnow()
        notification.attempt_count += 1
        if notification.attempt_count > 1:
            NOTIFICATION_RETRIES.labels(notification.channel).inc()
        try:
            recipient = notification.recipient or await self._resolve_recipient(notification)
            if not recipient:
                raise ProviderSendError("no recipient address on file")
            notification.recipient = recipient
            template = get_template(
                notification.template_key, notification.channel, notification.language
            )
            variables = dict(notification.payload)
            if "name" in template.variables and "name" not in variables:
                variables["name"] = await self._recipient_name(notification)
            # SEC-003 / F-04: two renders of the same template. The provider
            # gets the real secret; everything that is stored, shown or logged
            # gets the redacted one. Rendering twice rather than substituting
            # afterwards means the marker cannot be defeated by a token that
            # happens to contain template syntax.
            secrets_in_play = dict(notification.secret_payload or {})
            message = render(template, {**variables, **secrets_in_play})
            storable = (
                render(template, {**variables, **{k: REDACTED for k in secrets_in_play}})
                if secrets_in_play
                else message
            )
            provider = get_provider(notification.channel)
            # Provider latency is the number that tells an operator whether a
            # delivery backlog is the gateway's fault or ours.
            with NOTIFICATION_PROVIDER_SECONDS.labels(notification.channel, provider.name).time():
                result = await provider.send(
                    OutboundMessage(
                        channel=notification.channel,
                        recipient=recipient,
                        title=message.title,
                        body=message.body,
                        language=message.language,
                        template_key=notification.template_key,
                        notification_id=notification.id,
                        # DEMO-031: the same values, in the template's declared
                        # order, for adapters whose vendor takes positional
                        # template parameters rather than text. Derived from
                        # what the template already declares — the domain gains
                        # no new concept and no vendor appears anywhere here.
                        parameters=tuple(
                            str({**variables, **secrets_in_play}.get(name, ""))
                            for name in template.variables
                        ),
                        vendor_template=vendor_template_for(
                            notification.template_key, notification.channel
                        ),
                    )
                )
        except PermanentSendError as exc:
            # MSG-001: a retry cannot change this outcome. An invalid number,
            # a rejected sender id, a bad credential. Before MSG-001 every
            # failure was retried to exhaustion, so one mistyped number spent
            # five gateway calls and five backoff windows to reach the same
            # answer it had the first time.
            NOTIFICATION_PROVIDER_ERRORS.labels(
                notification.channel, provider_name(notification.channel), "permanent"
            ).inc()
            self._record_failure(
                notification, str(exc)[:500], now=now, forced=forced, permanent=True
            )
            # DEMO-012 §10: a push that failed permanently usually failed
            # because the token is dead — the app was uninstalled, or the
            # token rotated. Keeping it means every future notification for
            # that user spends a gateway call to learn the same thing.
            await self._forget_dead_token(notification)
            return
        except (TemplateRenderError, TemplateNotFoundError) as exc:
            # A missing template or an unrenderable one is a DEPLOYMENT fault,
            # not a delivery fault. Retrying it five times changes nothing and
            # buries the real signal — that the platform shipped a template
            # key it cannot render — under a retry backlog.
            self._record_failure(
                notification, str(exc)[:500], now=now, forced=forced, permanent=True
            )
            return
        except ProviderSendError as exc:
            NOTIFICATION_PROVIDER_ERRORS.labels(
                notification.channel,
                provider_name(notification.channel),
                "timeout" if "timeout" in str(exc).lower() else "transient",
            ).inc()
            self._record_failure(notification, str(exc)[:500], now=now, forced=forced)
            return
        except Exception as exc:  # a provider must never break the consumer
            # Unknown means retryable. Giving up on an unfamiliar error would
            # silently drop a farmer's message for a fault we have not
            # diagnosed yet.
            log.exception("notification_provider_unexpected", error=type(exc).__name__)
            self._record_failure(notification, str(exc)[:500], now=now, forced=forced)
            return
        notification.language = message.language
        notification.title = message.title
        notification.rendered_text = storable.body
        notification.provider = provider.name
        notification.provider_reference = result.provider_message_id
        # DEMO-028. The provider's own word, kept separate from ours.
        #
        # `status = "sent"` is what LACTEVA did: it handed the message over and
        # the gateway took it. `provider_status` is what the GATEWAY said, and
        # for every adapter in this platform today that is `accepted` — none
        # receives a delivery receipt. Recording both is what lets the portal
        # stop calling an accepted request a delivery.
        notification.provider_status = result.status
        notification.status = "sent"
        notification.sent_at = now
        notification.next_attempt_at = None
        notification.error = None
        # Delivered: the secret has served its purpose and must not outlive it
        # in the row, in a query, or in tonight's backup.
        notification.secret_payload = None
        NOTIFICATIONS_SENT.labels(notification.channel, notification.template_key).inc()

    def _record_failure(
        self,
        notification: Notification,
        error: str,
        *,
        now: datetime,
        forced: bool,
        permanent: bool = False,
    ) -> None:
        """Record the failure and decide whether it is worth trying again.

        MSG-001 added `permanent`. The retry budget exists for faults that
        pass — a gateway restart, a throttle, a network blip. Spending it on
        a number that does not exist wastes money on every attempt and puts
        the messages behind it in the queue further back for nothing.

        A permanent failure still goes to `dead`, not to a silent drop: it is
        visible in the notification history, retryable by an operator who has
        fixed the underlying problem, and counted.
        """
        notification.error = error
        notification.failed_at = now
        notification.provider = notification.provider or None
        exhausted = permanent or (
            notification.attempt_count >= MAX_CONSUMER_ATTEMPTS and not forced
        )
        if exhausted:
            notification.status = "dead"
            notification.next_attempt_at = None
            # SEC-003 / F-04: dead is terminal for delivery, so it is terminal
            # for the secret too. An operator retry of a dead invitation will
            # correctly find no token and fail to render — which is the honest
            # outcome: issue a new invitation rather than resurrect a secret
            # that has been sitting in the database since it stopped working.
            notification.secret_payload = None
            NOTIFICATIONS_DEAD.labels(notification.channel, notification.template_key).inc()
            log.error(
                "notification_dead",
                notification_id=str(notification.id),
                template=notification.template_key,
                # Why it stopped: a permanent rejection needs someone to fix
                # the data, an exhausted budget needs someone to check the
                # gateway. Different reactions, so different log fields.
                reason="permanent" if permanent else "attempts_exhausted",
                attempts=notification.attempt_count,
                error=error,
            )
        else:
            notification.status = "failed"
            notification.next_attempt_at = now + _timedelta_seconds(
                backoff_delay(notification.attempt_count)
            )
            NOTIFICATIONS_FAILED.labels(notification.channel, notification.template_key).inc()
            log.warning(
                "notification_failed",
                notification_id=str(notification.id),
                attempt=notification.attempt_count,
                error=error,
            )

    # --- devices (DEMO-012 §10) ----------------------------------------------

    async def register_device(
        self,
        user_id: uuid.UUID,
        command: RegisterPushDeviceCommand,
        *,
        customer_id: uuid.UUID | None = None,
    ) -> PushDeviceView:
        """Record (or refresh) the handset a user can be pushed to.

        Idempotent by token, because the app calls this on every start: the
        gateway hands out the same token until it rotates, and a fresh row
        per launch would push the same message to a phone five times.

        A token already held by ANOTHER user moves to this one. That is not a
        conflict to reject — it is a handset that was signed into a different
        account, and the previous owner must stop receiving its notifications
        at once. Rejecting would leave the old binding in place, which is the
        outcome that leaks.
        """
        token = command.token
        tenant_id = require_current_tenant()

        device = await self._session.scalar(
            select(NotificationDevice).where(NotificationDevice.token == token)
        )
        if device is None:
            device = NotificationDevice(tenant_id=tenant_id, user_id=user_id, token=token)
            self._session.add(device)
        else:
            device.tenant_id = tenant_id
            device.user_id = user_id
        device.customer_id = customer_id
        device.platform = command.platform
        device.label = (command.label or "")[:80]
        device.language = (command.language or "en")[:8]
        device.last_seen_at = utcnow()
        await self._session.flush()
        log.info(
            "push_device_registered",
            user_id=str(user_id),
            platform=device.platform,
            token_suffix=_token_suffix(token),
        )
        return _device_view(device)

    async def list_devices(self, user_id: uuid.UUID) -> list[PushDeviceView]:
        tenant_id = require_current_tenant()
        rows = await self._session.scalars(
            select(NotificationDevice)
            .where(
                NotificationDevice.tenant_id == tenant_id,
                NotificationDevice.user_id == user_id,
            )
            .order_by(NotificationDevice.last_seen_at.desc())
        )
        return [_device_view(d) for d in rows]

    async def revoke_device(self, user_id: uuid.UUID, device_id: uuid.UUID) -> None:
        """Sign-out, or a token the gateway says is dead.

        Deleted rather than deactivated. A revoked token is not evidence of
        anything and keeping it is keeping a way to reach a handset that no
        longer belongs to this account.
        """
        tenant_id = require_current_tenant()
        device = await self._session.get(NotificationDevice, device_id)
        if device is None or device.tenant_id != tenant_id or device.user_id != user_id:
            # Another user's device is a 404, never a 403 — the house rule.
            raise NotFoundError("device not found")
        await self._session.delete(device)
        await self._session.flush()

    async def _forget_dead_token(self, notification: Notification) -> None:
        """The gateway said the token is gone. Stop holding it.

        Called on a PERMANENT push failure. Without this, an uninstalled app
        leaves a token that fails forever, and every future notification for
        that user spends a gateway call to learn the same thing again.
        """
        if notification.channel != "push" or not notification.recipient:
            return
        device = await self._session.scalar(
            select(NotificationDevice).where(NotificationDevice.token == notification.recipient)
        )
        if device is not None:
            await self._session.delete(device)
            log.info("push_device_forgotten", token_suffix=_token_suffix(notification.recipient))

    # --- recipients ----------------------------------------------------------

    async def _directory_entry(self, notification: Notification) -> NotificationRecipient | None:
        """The recipient's phone/email, from the rebuildable directory.

        MT-001: scoped by tenant as well as by subject, and that is not
        redundant. This runs inside the DISPATCH CONSUMER, which holds a
        platform-bound session — RLS is deliberately bypassed there, so the
        predicate below is the only thing standing between a notification and
        another tenant's directory entry.

        `subject_id` is a UUID and will not collide by accident. The point is
        that it does not have to: the consequence of a match here is sending
        one dairy's payment details to another dairy's phone number, which is
        the worst outcome the notification path has. A one-clause filter is
        not worth omitting to save it.
        """
        if notification.recipient_ref is None:
            return None
        return await self._session.scalar(
            select(NotificationRecipient).where(
                NotificationRecipient.tenant_id == notification.tenant_id,
                NotificationRecipient.subject_id == notification.recipient_ref,
            )
        )

    #: Which contact detail a channel needs. WhatsApp travels to a phone
    #: number, so it reads the phone — without this it would have fallen
    #: through to the email address and failed on every send (DEMO-025).
    _CHANNEL_CONTACT: ClassVar[dict[str, str]] = {
        "sms": "phone",
        "whatsapp": "phone",
        "email": "email",
    }

    async def _resolve_recipient(self, notification: Notification) -> str | None:
        """Where this message goes when the request did not say.

        The caller's own `recipient` is preferred by `_attempt` before this is
        reached — which is how a household is billed at all, since the
        directory is built from supplier events and customers emit none
        (DEMO-025). This is the fallback, and it is also where the recipient's
        own LANGUAGE is picked up: a slip in the wrong language is barely
        better than no slip.
        """
        if notification.channel == "push":
            return await self._resolve_device_token(notification)
        entry = await self._directory_entry(notification)
        if entry is None:
            return None
        if not notification.language or notification.language == "en":
            notification.language = entry.language or notification.language or "en"
        # WhatsApp travels to a phone number. Without this it fell through to
        # the email address and would have failed on every send (DEMO-025).
        return getattr(entry, self._CHANNEL_CONTACT.get(notification.channel, "email"))

    async def _resolve_device_token(self, notification: Notification) -> str | None:
        """The most recently seen handset for this user.

        Tenant-scoped as well as user-scoped for the same reason
        `_directory_entry` is: this runs in the dispatch consumer, which holds
        a platform-bound session with RLS deliberately bypassed, so the
        predicate below is the only thing between a notification and another
        tenant's device.

        The reference is matched against the user OR the customer, because the
        two kinds of event that reach a household name different subjects: a
        bill-issued event knows a customer id and has never heard of a user
        account. Both are UUIDs from the same tenant and neither collides with
        the other by accident.

        One device, not all of them: a person carrying two handsets gets the
        one they last used, and the alternative — a notification row per
        device — would break the `(event, template, channel)` idempotency key
        that stops a replay re-sending.
        """
        if notification.recipient_ref is None:
            return None
        device = await self._session.scalar(
            select(NotificationDevice)
            .where(
                NotificationDevice.tenant_id == notification.tenant_id,
                or_(
                    NotificationDevice.user_id == notification.recipient_ref,
                    NotificationDevice.customer_id == notification.recipient_ref,
                ),
            )
            .order_by(NotificationDevice.last_seen_at.desc())
            .limit(1)
        )
        if device is None:
            return None
        if not notification.language or notification.language == "en":
            notification.language = device.language or notification.language or "en"
        return device.token

    async def _recipient_name(self, notification: Notification) -> str:
        entry = await self._directory_entry(notification)
        return (entry.display_name if entry else "") or "supplier"

    # --- history queries ------------------------------------------------------

    async def get(self, notification_id: uuid.UUID) -> Notification:
        tenant_id = require_current_tenant()
        notification = await self._session.get(Notification, notification_id)
        if notification is None or notification.tenant_id not in (tenant_id, None):
            raise NotFoundError("notification not found")
        return notification

    async def search(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        channel: str | None = None,
        template_key: str | None = None,
        event_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> NotificationPage:
        tenant_id = require_current_tenant()
        limit = max(1, min(limit, 100))
        stmt = select(Notification).where(
            or_(Notification.tenant_id == tenant_id, Notification.tenant_id.is_(None))
        )
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Notification.recipient).like(like),
                    func.lower(Notification.rendered_text).like(like),
                    func.lower(Notification.title).like(like),
                )
            )
        if status:
            stmt = stmt.where(Notification.status == status)
        if channel:
            stmt = stmt.where(Notification.channel == channel)
        if template_key:
            stmt = stmt.where(Notification.template_key == template_key)
        if event_id:
            stmt = stmt.where(Notification.event_id == event_id)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.scalars(
            stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        )
        return NotificationPage(
            items=[NotificationView.model_validate(row) for row in rows.all()],
            total=total or 0,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def posture() -> MessagingPosture:
        """Provider configuration as an operator may see it (DEMO-031).

        A static method and a settings read: this is a property of the
        DEPLOYMENT, not of a tenant, and every tenant sees the same answer
        because every tenant shares the gateway. What is per-tenant is the
        CHANNEL CHOICE, which lives in the configuration store and is already
        isolated by RLS.
        """
        from platform_core.core.config import get_settings
        from platform_core.modules.notification.providers import (
            DisabledProvider,
            supports_receipts,
        )

        settings = get_settings()
        mode = settings.messaging_mode
        channels: list[ChannelPosture] = []
        for channel in ("sms", "whatsapp", "email", "push"):
            try:
                provider = get_provider(channel)
                name = getattr(provider, "name", "unknown")
                configured = not isinstance(provider, DisabledProvider)
                reports = supports_receipts(provider)
            except Exception:
                # A channel whose adapter cannot even be built is NOT
                # configured. Saying so is the honest answer; raising here
                # would take the whole screen down for one misconfiguration.
                name, configured, reports = "unavailable", False, False
            channels.append(
                ChannelPosture(
                    channel=channel,
                    provider=name,
                    configured=configured,
                    can_send=configured and mode in ("sandbox", "production"),
                    reports_delivery=reports,
                )
            )
        return MessagingPosture(
            mode=mode,
            sends_real_messages=mode == "production",
            channels=channels,
        )

    async def stats(self) -> NotificationStats:
        tenant_id = require_current_tenant()
        scope = or_(Notification.tenant_id == tenant_id, Notification.tenant_id.is_(None))
        by_status = dict(
            (
                await self._session.execute(
                    select(Notification.status, func.count())
                    .where(scope)
                    .group_by(Notification.status)
                )
            ).all()
        )
        by_channel = dict(
            (
                await self._session.execute(
                    select(Notification.channel, func.count())
                    .where(scope)
                    .group_by(Notification.channel)
                )
            ).all()
        )
        return NotificationStats(
            total=sum(by_status.values()),
            by_status=by_status,
            by_channel=by_channel,
            retryable=by_status.get("failed", 0),
        )

    # --- template catalog ------------------------------------------------------

    @staticmethod
    def templates() -> list[TemplateView]:
        return [
            TemplateView(
                key=template.key,
                channel=template.channel,
                language=template.language,
                title=template.title,
                body=template.body,
                variables=list(template.variables),
            )
            for template in catalog()
        ]

    @staticmethod
    def preview(key: str, channel: str, language: str | None, variables: dict) -> RenderedPreview:
        """Render a template with supplied (or placeholder) variables."""
        try:
            template = get_template(key, channel, language)
        except TemplateNotFoundError as exc:
            raise NotFoundError(str(exc)) from exc
        values = {name: f"<{name}>" for name in template.variables}
        values.update({k: v for k, v in variables.items() if v is not None})
        message = render(template, values)
        return RenderedPreview(
            key=template.key,
            channel=template.channel,
            language=template.language,
            title=message.title,
            body=message.body,
            variables_used=values,
        )


def _timedelta_seconds(seconds: float):
    from datetime import timedelta

    return timedelta(seconds=seconds)


def _jsonable(variables: dict) -> dict:
    """Template variables live in a JSON column — keep them transport-safe."""
    return {
        key: (str(value) if isinstance(value, Decimal | uuid.UUID | datetime) else value)
        for key, value in variables.items()
    }


def as_utc_safe(value: datetime | None) -> datetime | None:
    return as_utc(value) if value is not None else None
