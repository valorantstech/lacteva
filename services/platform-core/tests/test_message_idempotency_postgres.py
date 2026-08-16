"""One financial event, one message — under real concurrency (DEMO-025).

`test_message_delivery.py` proves duplicate prevention on SQLite, where the
test stack shares a single connection and true concurrency cannot happen. That
is the gap this file closes: the guarantee is a UNIQUE CONSTRAINT
(`uq_notification_event` on event, template and channel), and a constraint is
only proven by two writers racing at it.

The failure it defends against is expensive in a way most are not: a duplicate
message is a duplicate *charge* from the gateway and a farmer told twice about
the same money. There is no compensating action — the SMS has gone.

Also proven here, because SQLite cannot: notification rows do not leak between
tenants under the database's own row-level security.
"""

import asyncio
import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres


@pytest.fixture(autouse=True)
def _settings_point_at_postgres(monkeypatch):
    """Make `is_postgres()` true, or every binding below is a no-op.

    The lesson DEMO-020 learned the hard way: without this the suite passes as
    a superuser and proves nothing about RLS at all.
    """
    from platform_core.core.config import get_settings

    monkeypatch.setattr(get_settings(), "database_url", POSTGRES_URL)
    monkeypatch.setattr(get_settings(), "rls_enabled", True)


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(POSTGRES_URL, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


class _CountingProvider:
    """Counts gateway calls. The number that becomes a bill from a vendor."""

    name = "counting"

    def __init__(self):
        self.calls = 0

    async def send(self, message):
        from platform_core.modules.notification.providers import DeliveryResult

        self.calls += 1
        await asyncio.sleep(0.01)  # widen the window the constraint must close
        return DeliveryResult(provider_message_id=f"counting:{self.calls}")


async def _dispatch(maker, tenant_id: uuid.UUID, event_id: uuid.UUID):
    """One dispatch of one event, in its own session and transaction."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.service import (
        NotificationRequest,
        NotificationService,
    )

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        result = await NotificationService(session).dispatch(
            NotificationRequest(
                event_id=event_id,
                event_name="sales.invoice-issued.v1",
                tenant_id=tenant_id,
                template_key="invoice_issued",
                channel="sms",
                recipient="+919845000101",
                variables={
                    "name": "Household",
                    "number": "INV-2026-000001",
                    "amount": "1250.00",
                    "currency": "INR",
                    "period_from": str(date(2026, 8, 1)),
                    "period_to": str(date(2026, 8, 31)),
                },
            )
        )
        await session.commit()
        return result


async def _count(maker, tenant_id: uuid.UUID, event_id: uuid.UUID) -> int:
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.models import Notification

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        return (
            await session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.event_id == event_id)
            )
        ) or 0


async def test_eight_concurrent_dispatches_send_one_message(factory):
    """The production shape: several workers, one financial event."""
    from platform_core.modules.notification.providers import register_provider

    provider = _CountingProvider()
    register_provider("sms", provider)
    tenant_id, event_id = uuid.uuid4(), uuid.uuid4()

    try:
        results = await asyncio.gather(
            *(_dispatch(factory, tenant_id, event_id) for _ in range(8)),
            return_exceptions=True,
        )
        raised = [r for r in results if isinstance(r, Exception)]
        assert not raised, f"a racing dispatch raised: {raised}"

        assert await _count(factory, tenant_id, event_id) == 1, (
            "one event produced more than one notification row"
        )
        assert provider.calls == 1, (
            f"the gateway was called {provider.calls} times for one event — "
            "every extra call is a charge and a message a farmer receives twice"
        )
    finally:
        from platform_core.core.rls import rebind_tenant

        async with factory() as session:
            await rebind_tenant(session, tenant_id)
            await session.execute(
                text("DELETE FROM notification WHERE event_id = :e"), {"e": event_id}
            )
            await session.commit()


async def test_the_same_event_on_two_channels_is_two_messages(factory):
    """Idempotency is per CHANNEL — an SMS and an email are not duplicates."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.models import Notification
    from platform_core.modules.notification.providers import register_provider
    from platform_core.modules.notification.service import (
        NotificationRequest,
        NotificationService,
    )

    register_provider("sms", _CountingProvider())
    register_provider("email", _CountingProvider())
    tenant_id, event_id = uuid.uuid4(), uuid.uuid4()

    try:
        for channel, recipient in (("sms", "+919845000101"), ("email", "h@example.com")):
            async with factory() as session:
                await rebind_tenant(session, tenant_id)
                await NotificationService(session).dispatch(
                    NotificationRequest(
                        event_id=event_id,
                        event_name="sales.invoice-issued.v1",
                        tenant_id=tenant_id,
                        template_key="invoice_issued",
                        channel=channel,
                        recipient=recipient,
                        variables={
                            "name": "Household",
                            "number": "INV-1",
                            "amount": "10.00",
                            "currency": "INR",
                            "period_from": "2026-08-01",
                            "period_to": "2026-08-31",
                        },
                    )
                )
                await session.commit()

        async with factory() as session:
            await rebind_tenant(session, tenant_id)
            channels = {
                row.channel
                for row in (
                    await session.scalars(
                        select(Notification).where(Notification.event_id == event_id)
                    )
                ).all()
            }
        assert channels == {"sms", "email"}
    finally:
        from platform_core.core.rls import rebind_tenant as _rebind

        async with factory() as session:
            await _rebind(session, tenant_id)
            await session.execute(
                text("DELETE FROM notification WHERE event_id = :e"), {"e": event_id}
            )
            await session.commit()


async def test_notifications_do_not_leak_between_tenants(factory):
    """The database's own isolation, not the application's filter."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.notification.providers import register_provider

    register_provider("sms", _CountingProvider())
    alpha, beta = uuid.uuid4(), uuid.uuid4()
    event_id = uuid.uuid4()

    try:
        await _dispatch(factory, alpha, event_id)

        assert await _count(factory, alpha, event_id) == 1, "the premise: alpha owns one"

        async with factory() as session:
            await rebind_tenant(session, beta)
            # No tenant filter in the SQL at all — the database must refuse.
            leaked = (
                await session.execute(
                    text("SELECT count(*) FROM notification WHERE event_id = :e"),
                    {"e": event_id},
                )
            ).scalar_one()
            assert leaked == 0, "another tenant read a message it does not own"

            deleted = await session.execute(
                text("DELETE FROM notification WHERE event_id = :e"), {"e": event_id}
            )
            assert deleted.rowcount == 0, "another tenant deleted a message it does not own"
            await session.commit()

        assert await _count(factory, alpha, event_id) == 1, "the row survived the other tenant"
    finally:
        async with factory() as session:
            await rebind_tenant(session, alpha)
            await session.execute(
                text("DELETE FROM notification WHERE event_id = :e"), {"e": event_id}
            )
            await session.commit()


async def test_the_notification_table_forces_row_level_security(factory):
    """ENABLE without FORCE protects nothing: the app owns this table."""
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = 'notification'"
                )
            )
        ).first()
    assert row is not None
    enabled, forced = row
    assert enabled and forced
