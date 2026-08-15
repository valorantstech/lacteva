"""The period guard on a real engine, under the real security model (DEMO-021).

`test_closed_period_protection.py` proves the guard REFUSES, on SQLite, where
the tenant boundary is the application's own filter. This file proves the other
half, which SQLite structurally cannot: that the guard reads a period the
DATABASE agrees the tenant owns.

The failure this defends against is specific and would be invisible on SQLite.
`check_open` looks up a period by tenant and date. If row-level security were
not enforcing on `financial_period`, that lookup could find — or fail to find —
another organization's period, and a dairy's books would be shut, or left open,
by somebody else's decision.
"""

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import text
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
async def live():
    engine = create_async_engine(POSTGRES_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _bind(session, tenant_id):
    from platform_core.core.rls import rebind_tenant

    await rebind_tenant(session, tenant_id)


async def _close_period(session, tenant_id, start: date, end: date, label: str) -> None:
    await session.execute(
        text(
            "INSERT INTO financial_period "
            "(id, tenant_id, period_start, period_end, status, label, created_at, closed_at) "
            "VALUES (:id, :t, :a, :b, 'closed', :l, now(), now())"
        ),
        {"id": uuid.uuid4(), "t": tenant_id, "a": start, "b": end, "l": label},
    )


async def test_the_guard_refuses_only_the_owning_tenant(live):
    """One dairy closes August. The other must be entirely unaffected."""
    from platform_core.modules.business_calendar.service import BusinessCalendarService

    alpha, beta = uuid.uuid4(), uuid.uuid4()
    inside = date(2026, 8, 15)
    label = f"guard-probe-{alpha}"

    async with live() as s:
        await _bind(s, alpha)
        await _close_period(s, alpha, date(2026, 8, 1), date(2026, 8, 31), label)
        await s.commit()

    try:
        # The owner is refused — the premise, and the guarantee.
        async with live() as s:
            await _bind(s, alpha)
            guard = await BusinessCalendarService(s, alpha).check_open(inside)
            assert guard.allowed is False, "the owning tenant must be refused"
            assert guard.period is not None

        # The other tenant sees no period at all and is therefore allowed.
        # If RLS were not enforcing, this would find alpha's row and refuse —
        # one dairy's month-end would shut another's books.
        async with live() as s:
            await _bind(s, beta)
            guard = await BusinessCalendarService(s, beta).check_open(inside)
            assert guard.allowed is True, "another tenant's closure must not bind"
            assert guard.period is None
    finally:
        async with live() as s:
            await _bind(s, alpha)
            await s.execute(text("DELETE FROM financial_period WHERE label = :l"), {"l": label})
            await s.commit()


async def test_the_refusal_names_the_period_and_is_a_conflict(live):
    """`assert_open` raises the platform's ConflictError, not a bare error."""
    from platform_core.core.errors import ConflictError
    from platform_core.modules.business_calendar.service import assert_period_open

    tenant = uuid.uuid4()
    label = f"guard-raise-{tenant}"

    async with live() as s:
        await _bind(s, tenant)
        await _close_period(s, tenant, date(2026, 9, 1), date(2026, 9, 30), label)
        await s.commit()

    try:
        async with live() as s:
            await _bind(s, tenant)
            with pytest.raises(ConflictError) as excinfo:
                await assert_period_open(
                    s, tenant, date(2026, 9, 15), operation="issuing an invoice"
                )
            message = str(excinfo.value)
            assert "issuing an invoice" in message
            assert "2026-09-01" in message and "2026-09-30" in message

            # A date outside it passes, on the same engine and binding.
            await assert_period_open(s, tenant, date(2026, 10, 1), operation="issuing an invoice")
    finally:
        async with live() as s:
            await _bind(s, tenant)
            await s.execute(text("DELETE FROM financial_period WHERE label = :l"), {"l": label})
            await s.commit()


async def test_an_organization_calendar_day_does_not_leak_into_resolution(live):
    """Resolution must read only the bound tenant's exception."""
    from platform_core.modules.business_calendar.service import BusinessCalendarService

    alpha, beta = uuid.uuid4(), uuid.uuid4()
    day = date(2026, 8, 15)

    async with live() as s:
        await _bind(s, alpha)
        await s.execute(
            text(
                "INSERT INTO organization_calendar_day "
                "(id, tenant_id, day, working, kind, name, created_at) "
                "VALUES (:id, :t, :d, false, 'holiday', 'Alpha only', now())"
            ),
            {"id": uuid.uuid4(), "t": alpha, "d": day},
        )
        await s.commit()

    try:
        async with live() as s:
            await _bind(s, alpha)
            assert await BusinessCalendarService(s, alpha).is_working_day(day) is False

        async with live() as s:
            await _bind(s, beta)
            # Beta declared nothing, so beta works — alpha's holiday is invisible.
            assert await BusinessCalendarService(s, beta).is_working_day(day) is True
    finally:
        async with live() as s:
            await _bind(s, alpha)
            await s.execute(text("DELETE FROM organization_calendar_day WHERE name = 'Alpha only'"))
            await s.commit()
