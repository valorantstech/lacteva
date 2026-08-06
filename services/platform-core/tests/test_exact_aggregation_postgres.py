"""Exact aggregation — the half only a real engine can prove (DB-002).

Two of this work order's premises are PostgreSQL behaviours that SQLite
cannot exhibit, which is precisely why they went unnoticed:

1. `SUM(double precision)` is order-dependent; `SUM(x::numeric)` is not.
   SQLite has one floating type and no plan-order guarantees to contradict.
2. `numeric(16,3)` ROUNDS ON STORE. SQLite ignores the scale entirely, so the
   projection's incremental-versus-batched divergence is simply invisible
   there — the model-based tests in `test_exact_aggregation.py` stand in for
   it, and this module proves the premise they model.

Skips without PostgreSQL; the CI proof job provides one, and a skip there is
a configuration failure rather than an expected outcome.
"""

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

# OPS-001: one guard for every PostgreSQL-only suite. A skip is allowed on a
# laptop and impossible in the verification pipeline (see postgres_support).
POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres


@pytest_asyncio.fixture
async def pg():
    engine = create_async_engine(POSTGRES_URL)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_float_summation_is_order_dependent_on_this_engine(pg):
    """The defect, demonstrated in the database rather than argued about.

    The same three values, summed left-to-right and right-to-left, disagree.
    A planner is free to choose either — and to change its mind when the
    statistics change or a parallel worker appears.
    """
    async with pg() as s:
        forwards = await s.scalar(text("SELECT (0.1::float8 + 0.2::float8) + 0.3::float8"))
        backwards = await s.scalar(text("SELECT 0.1::float8 + (0.2::float8 + 0.3::float8)"))
    assert forwards != backwards, "float8 addition was expected to be non-associative"


async def test_the_numeric_cast_removes_the_order_dependence(pg):
    """The fix, demonstrated the same way."""
    async with pg() as s:
        forwards = await s.scalar(
            text("SELECT (0.1::float8::numeric + 0.2::float8::numeric) + 0.3::float8::numeric")
        )
        backwards = await s.scalar(
            text("SELECT 0.1::float8::numeric + (0.2::float8::numeric + 0.3::float8::numeric)")
        )
    assert forwards == backwards


async def test_float_to_numeric_keeps_the_value_the_platform_displays(pg):
    """`float8::numeric` renders the shortest decimal that round-trips — the
    same rule `Decimal(str(x))` follows in the money path (BR-0005). Without
    this, casting would introduce a different value than the one shown."""
    async with pg() as s:
        for literal in ("4.2", "0.1", "125.5555", "0.0005"):
            value = await s.scalar(text(f"SELECT {literal}::float8::numeric"))
            assert str(value) == literal, f"{literal} cast to {value}"


async def test_summing_many_awkward_weights_is_exact(pg):
    """Ten thousand values of 0.001 that a float accumulator drifts on."""
    async with pg() as s:
        as_numeric = await s.scalar(
            text(
                "SELECT sum(v::numeric) FROM "
                "(SELECT 0.001::float8 AS v FROM generate_series(1, 10000)) t"
            )
        )
    assert str(as_numeric) == "10.000"


async def test_a_scaled_numeric_column_rounds_on_store(pg):
    """The premise behind the projection's explicit quantize.

    PostgreSQL rounds to the column's scale when the value is written, so a
    running total held unrounded in the identity map is NOT what the column
    contains — and where the flush falls decides the answer. SQLite does not
    do this, which is why the divergence never surfaced in the main suite.
    """
    async with pg() as s:
        await s.execute(text("CREATE TEMP TABLE db002_scale (v numeric(16,3))"))
        await s.execute(text("INSERT INTO db002_scale VALUES (0.0005), (25.00049), (1.9995)"))
        stored = [str(v) for v in (await s.execute(text("SELECT v FROM db002_scale"))).scalars()]
    assert stored == ["0.001", "25.000", "2.000"], stored


async def test_the_reporting_aggregate_compiles_and_runs_here(pg):
    """The real expression, executed. Proves the cast is valid SQL on this
    engine and returns numeric — not that it returns any particular total."""
    from platform_core.core.model_registry import import_all_models

    import_all_models()
    from decimal import Decimal

    from sqlalchemy import func, select

    from platform_core.modules.milk_collection.models import MilkCollectionTransaction as Tx
    from platform_core.modules.reporting.service import _exact

    async with pg() as s:
        total = await s.scalar(select(func.coalesce(func.sum(_exact(Tx.net_weight)), 0)))
    assert isinstance(total, Decimal | int)
