"""One organization, one trial — under real concurrency (DEMO-026).

`test_subscription.py` proves the rules on SQLite, where the test stack shares
a single connection and true concurrency cannot happen. This is the half that
cannot be proven there: the duplicate prevention is a UNIQUE CONSTRAINT, and a
constraint is only proven by writers racing at it.

The failure it defends against is commercially specific: two trial rows for one
dairy means two trial windows, and the later one silently extends free access.
A dairy that signs up twice by double-clicking must not get sixty days.

Also proven here, because SQLite cannot: a subscription row does not leak
between tenants under the database's own row-level security. Commercial
standing is exactly the kind of thing a competitor must never read.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

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


async def _make_org(maker, tenant_id: uuid.UUID, *, tz: str, created_at: datetime) -> None:
    """An organization row written directly — this module is about the race."""
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="subscription concurrency test seed")
        await session.execute(
            text(
                "INSERT INTO organization "
                "(id, name, slug, country_code, org_type, status, currency_code, timezone, "
                " supported_languages, default_locale, created_at) "
                "VALUES (:id, :n, :s, 'IN', 'processor', 'active', 'INR', :tz, "
                "        '[\"en\"]', 'en', :c)"
            ),
            {
                "id": tenant_id,
                "n": f"Race {tenant_id}",
                "s": f"race-{tenant_id}",
                "tz": tz,
                "c": created_at,
            },
        )
        await session.commit()


async def _ensure_trial(maker, tenant_id: uuid.UUID):
    """One `ensure_trial`, in its own session and transaction."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.subscription.service import SubscriptionService

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        row = await SubscriptionService(session, tenant_id).ensure_trial()
        await session.commit()
        return (row.trial_started_on, row.trial_ends_on)


async def _count(maker, tenant_id: uuid.UUID) -> int:
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.subscription.models import Subscription

    async with maker() as session:
        await rebind_tenant(session, tenant_id)
        return (
            await session.scalar(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.tenant_id == tenant_id)
            )
        ) or 0


async def _cleanup(maker, tenant_id: uuid.UUID) -> None:
    from platform_core.core.rls import bind_platform_context

    async with maker() as session:
        await bind_platform_context(session, reason="subscription concurrency test cleanup")
        await session.execute(
            text("DELETE FROM subscription WHERE tenant_id = :t"), {"t": tenant_id}
        )
        await session.execute(text("DELETE FROM organization WHERE id = :t"), {"t": tenant_id})
        await session.commit()


async def test_eight_concurrent_signups_produce_one_trial(factory):
    """The double-click, the retry and the racing worker, all at once."""
    tenant_id = uuid.uuid4()
    created = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)
    await _make_org(factory, tenant_id, tz="Asia/Kolkata", created_at=created)

    try:
        results = await asyncio.gather(
            *(_ensure_trial(factory, tenant_id) for _ in range(8)),
            return_exceptions=True,
        )
        raised = [r for r in results if isinstance(r, Exception)]
        assert not raised, f"a racing signup raised: {raised}"

        assert await _count(factory, tenant_id) == 1, (
            "one organization ended with more than one trial — free access doubles"
        )
        # Every caller saw the SAME window. A race that returned different
        # dates to different callers would be a trial nobody could reason about.
        windows = set(results)
        assert len(windows) == 1, f"racing callers disagreed about the trial window: {windows}"

        start, ends = results[0]
        assert (ends - start).days == 30
        # 20:00 UTC on the 14th is already the 15th in Bengaluru.
        assert start.isoformat() == "2026-08-15", "the trial starts on the DAIRY's day"
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_second_call_much_later_does_not_extend_the_trial(factory):
    """Re-reading a month later must return the original window."""
    tenant_id = uuid.uuid4()
    created = datetime(2026, 1, 1, 6, 0, tzinfo=UTC)
    await _make_org(factory, tenant_id, tz="Africa/Nairobi", created_at=created)

    try:
        first = await _ensure_trial(factory, tenant_id)
        await asyncio.sleep(0.05)
        later = await _ensure_trial(factory, tenant_id)
        assert first == later, "the trial moved when somebody looked at it again"
        assert await _count(factory, tenant_id) == 1
        # And it is anchored to the organization's creation, not to now.
        assert first[0].isoformat() == "2026-01-01"
        assert first[1] == first[0] + timedelta(days=30)
    finally:
        await _cleanup(factory, tenant_id)


async def test_a_subscription_does_not_leak_between_tenants(factory):
    """Commercial standing is exactly what a competitor must not read."""
    from platform_core.core.rls import rebind_tenant

    alpha, beta = uuid.uuid4(), uuid.uuid4()
    created = datetime(2026, 8, 1, 6, 0, tzinfo=UTC)
    await _make_org(factory, alpha, tz="Asia/Kolkata", created_at=created)
    await _make_org(factory, beta, tz="Africa/Nairobi", created_at=created)

    try:
        await _ensure_trial(factory, alpha)
        assert await _count(factory, alpha) == 1, "the premise: alpha has a trial"

        async with factory() as session:
            await rebind_tenant(session, beta)
            # No tenant filter in the SQL at all — the database must refuse.
            leaked = (
                await session.execute(
                    text("SELECT count(*) FROM subscription WHERE tenant_id = :t"), {"t": alpha}
                )
            ).scalar_one()
            assert leaked == 0, "another tenant read a subscription it does not own"

            deleted = await session.execute(
                text("DELETE FROM subscription WHERE tenant_id = :t"), {"t": alpha}
            )
            assert deleted.rowcount == 0, "another tenant deleted a subscription it does not own"
            await session.commit()

        assert await _count(factory, alpha) == 1, "alpha's subscription survived"
    finally:
        await _cleanup(factory, alpha)
        await _cleanup(factory, beta)


async def test_the_subscription_table_forces_row_level_security(factory):
    """ENABLE without FORCE protects nothing: the app owns this table."""
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = 'subscription'"
                )
            )
        ).first()
    assert row is not None, "the subscription table does not exist in the migrated database"
    enabled, forced = row
    assert enabled and forced


async def test_the_unique_constraint_exists_and_is_the_guarantee(factory):
    """Named explicitly: it is what stops a second trial, not Python."""
    async with factory() as session:
        names = {
            r[0]
            for r in (
                await session.execute(
                    text(
                        "SELECT conname FROM pg_constraint c "
                        "JOIN pg_class t ON t.oid = c.conrelid "
                        "WHERE t.relname = 'subscription' AND c.contype = 'u'"
                    )
                )
            ).all()
        }
    assert "uq_subscription_tenant" in names
