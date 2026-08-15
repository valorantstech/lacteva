"""The business-date rule, inside real SQL (DEMO-019).

`local_date_sql` compiles to different SQL on each engine, and only one of
them runs in production. PostgreSQL gets `AT TIME ZONE`, which reads the IANA
database the server ships with; SQLite gets a fixed offset, because SQLite has
no timezone database at all.

That split is the reason this file exists. A trend chart bucketed correctly on
SQLite and wrongly on PostgreSQL would pass the whole suite and be wrong in
front of a dairy — the exact shape STD-0007 §6 forbids, and the same reason
`test_rls_postgres.py` exists for a guarantee SQLite cannot express either.

So this asserts the PostgreSQL expression on a real engine, including a zone
that observes DST — which the SQLite path cannot do and production may one day
need.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, literal, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from platform_core.core.business_time import local_date_sql
from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

UTC = ZoneInfo("UTC")

# No table, and deliberately none (DEMO-020).
#
# This suite used to CREATE a probe table, which needs CREATE on schema
# `public`. That is fine for an owner and impossible for the unprivileged role
# the nine-step proof runs its tests as — so when the suite was finally added
# to `postgres-proof.sh`, every test in it errored with "permission denied for
# schema public". The expression under test takes a timestamptz EXPRESSION,
# not a stored column, so a bound literal exercises exactly the same SQL with
# no schema rights at all.


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine(POSTGRES_URL)
    yield engine
    await engine.dispose()


async def _local_date(engine, instant: datetime, timezone: str) -> date:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        column = literal(instant, DateTime(timezone=True))
        return await session.scalar(select(local_date_sql(column, timezone, "postgresql")))


@pytest.mark.parametrize(
    "timezone,expected",
    [
        ("Asia/Kolkata", date(2026, 8, 15)),
        ("Africa/Nairobi", date(2026, 8, 14)),
        ("Asia/Qatar", date(2026, 8, 14)),
    ],
)
async def test_postgres_buckets_by_the_dairys_day(engine, timezone, expected):
    """20:00 UTC: 01:30 in Bengaluru, 23:00 in Nairobi and Doha."""
    instant = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)
    assert await _local_date(engine, instant, timezone) == expected


async def test_postgres_and_utc_disagree_and_postgres_is_right(engine):
    """The defect in one assertion: truncating UTC gives the 14th, and the
    dairy is on the 15th."""
    instant = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)
    assert instant.date() == date(2026, 8, 14)
    assert await _local_date(engine, instant, "Asia/Kolkata") == date(2026, 8, 15)


async def test_local_midnight_is_the_first_moment_of_the_day(engine):
    """18:30 UTC is exactly midnight in Bengaluru: the first instant of the
    15th, not the last of the 14th."""
    assert await _local_date(
        engine, datetime(2026, 8, 14, 18, 30, tzinfo=UTC), "Asia/Kolkata"
    ) == date(2026, 8, 15)
    assert await _local_date(
        engine, datetime(2026, 8, 14, 18, 29, 59, tzinfo=UTC), "Asia/Kolkata"
    ) == date(2026, 8, 14)


async def test_postgres_handles_a_zone_that_observes_dst(engine):
    """The half of the rule SQLite cannot express.

    Europe/London is in the country registry and has no tenant today. In
    August it is UTC+1, in January UTC+0 — so the SAME wall-clock instant
    buckets differently across the year, and a fixed offset would be an hour
    wrong for half of it.
    """
    # 23:30 UTC on 14 August is 00:30 on the 15th in London (BST, UTC+1).
    assert await _local_date(
        engine, datetime(2026, 8, 14, 23, 30, tzinfo=UTC), "Europe/London"
    ) == date(2026, 8, 15)
    # 23:30 UTC on 14 January is still the 14th in London (GMT, UTC+0).
    assert await _local_date(
        engine, datetime(2026, 1, 14, 23, 30, tzinfo=UTC), "Europe/London"
    ) == date(2026, 1, 14)
