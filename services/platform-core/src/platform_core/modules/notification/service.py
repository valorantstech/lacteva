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

import structlog
from pydantic import BaseModel
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
from platform_core.core.tenancy import require_current_tenant
from platform_core.modules.event_relay.consumers import MAX_CONSUMER_ATTEMPTS
from platform_core.modules.event_relay.service import backoff_delay
from platform_core.modules.notification.models import Notification, NotificationRecipient
from platform_core.modules.notification.providers import (
    OutboundMessage,
    PermanentSendError,
    ProviderSendError,
    get_provider,
)
from platform_core.modules.notification.templates import (
    TemplateNotFoundError,
    TemplateRenderError,
    catalog,
    get_template,
    render,
)

log = structlog.get_logger("notification")


class NotificationRequest(BaseModel):
    """What the consumer asks for — never a message, always a template."""

    event_id: uuid.UUID
    event_name: str
    tenant_id: uuid.UUID | None = None
    template_key: str
    channel: str
    recipient_ref: uuid.UUID | None = None  # supplier/user id, resolved via the directory
    recipient: str | None = None  # explicit address when the event carries it
    language: str | None = None
    variables: dict = {}


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
    status: str
    provider: str | None
    provider_reference: str | None
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
            language=(request.language or "en"),
            recipient_ref=request.recipient_ref,
            recipient=request.recipient,
            payload=_jsonable(request.variables),
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
        self._session.add(notification)
        try:
            async with self._session.begin_nested():
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
            message = render(template, variables)
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
        notification.rendered_text = message.body
        notification.provider = provider.name
        notification.provider_reference = result.provider_message_id
        notification.status = "sent"
        notification.sent_at = now
        notification.next_attempt_at = None
        notification.error = None
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

    async def _resolve_recipient(self, notification: Notification) -> str | None:
        entry = await self._directory_entry(notification)
        if entry is None:
            return None
        if not notification.language or notification.language == "en":
            notification.language = entry.language or "en"
        return entry.phone if notification.channel == "sms" else entry.email

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
