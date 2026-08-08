"""The price is stored exactly (DEPLOY-001).

`pricing_matrix_row.unit_price` was `double precision`. BR-0005 made all
*arithmetic* exact, but exact arithmetic on an inexact input is still inexact —
the price was already approximate before the first multiplication, and it is
the number every calculation, settlement, payment and receipt descends from.

This is a PostgreSQL-only suite because it is a statement about STORAGE.
SQLite has no distinct numeric type with a declared scale: it would accept
every assertion below while storing a float, which is exactly the illusion the
migration exists to remove.
"""

import uuid
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

#: Prices a real rate card contains: whole shillings, ordinary money, the full
#: four-decimal precision the column now carries, and both bounds.
PRICES = ["44.7291", "56.85", "3.3", "0.1", "52", "44.0001", "9999.9999", "0.0001"]


@pytest_asyncio.fixture
async def factory(monkeypatch):
    from platform_core.core.config import get_settings

    monkeypatch.setattr(get_settings(), "database_url", POSTGRES_URL)
    engine = create_async_engine(POSTGRES_URL)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_the_column_is_numeric_with_four_decimals(factory):
    """Read from the catalogue, not from the model — the model is what the
    migration was supposed to make true, not evidence that it did."""
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT data_type, numeric_precision, numeric_scale "
                    "FROM information_schema.columns "
                    "WHERE table_name='pricing_matrix_row' AND column_name='unit_price'"
                )
            )
        ).first()
    assert row is not None, "pricing_matrix_row.unit_price is missing"
    data_type, precision, scale = row
    assert data_type == "numeric", f"unit_price is {data_type}, not numeric"
    assert (precision, scale) == (12, 4), f"unit_price is numeric({precision},{scale})"


async def test_it_matches_the_transaction_column_it_is_copied_into(factory):
    """`milk_collection_transaction.unit_price` receives this value. Two money
    columns that hold the same number must agree on how they hold it."""
    async with factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT table_name, numeric_precision, numeric_scale "
                    "FROM information_schema.columns WHERE column_name='unit_price' "
                    "AND table_name IN ('pricing_matrix_row','milk_collection_transaction') "
                    "ORDER BY table_name"
                )
            )
        ).all()
    shapes = {name: (p, s) for name, p, s in rows}
    assert len(shapes) == 2, shapes
    assert len(set(shapes.values())) == 1, f"the two unit_price columns disagree: {shapes}"


async def test_a_price_survives_a_write_and_read_unchanged(factory):
    """The property the migration bought: what goes in comes back out.

    Written through the ORM and read back through raw SQL, so the assertion
    cannot be satisfied by a Python-side conversion.
    """
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.pricing.models import PricingMatrixRow

    tenant_id, matrix_id = uuid.uuid4(), uuid.uuid4()
    written: dict[str, str] = {}
    async with factory() as session:
        await bind_platform_context(session, reason="precision test seeding")
        for index, price in enumerate(PRICES):
            row_id = uuid.uuid4()
            written[str(row_id)] = price
            session.add(
                PricingMatrixRow(
                    id=row_id,
                    tenant_id=tenant_id,
                    matrix_id=matrix_id,
                    sequence=index + 1,
                    from_value=float(index),
                    to_value=float(index + 1),
                    unit_price=Decimal(price),
                    active=True,
                )
            )
        await session.commit()

    async with factory() as session:
        await bind_platform_context(session, reason="precision test verification")
        stored = dict(
            (str(row_id), value)
            for row_id, value in (
                await session.execute(
                    text(
                        "SELECT id::text, unit_price::text FROM pricing_matrix_row "
                        "WHERE tenant_id = :tenant"
                    ),
                    {"tenant": str(tenant_id)},
                )
            ).all()
        )

    assert len(stored) == len(PRICES)
    for row_id, expected in written.items():
        assert Decimal(stored[row_id]) == Decimal(expected), (
            f"price changed in storage: {expected} -> {stored[row_id]}"
        )


async def test_a_price_is_not_a_float_when_it_comes_back(factory):
    """A `Decimal` out of the driver is what keeps BR-0005 honest: if this
    returned a float, every downstream `Decimal(str(x))` would be laundering an
    approximation rather than preserving an exact value."""
    from sqlalchemy import select

    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.pricing.models import PricingMatrixRow

    tenant_id = uuid.uuid4()
    async with factory() as session:
        await bind_platform_context(session, reason="precision test seeding")
        session.add(
            PricingMatrixRow(
                tenant_id=tenant_id,
                matrix_id=uuid.uuid4(),
                sequence=1,
                from_value=3.0,
                to_value=4.0,
                unit_price=Decimal("44.7291"),
                active=True,
            )
        )
        await session.commit()

    async with factory() as session:
        await bind_platform_context(session, reason="precision test verification")
        row = await session.scalar(
            select(PricingMatrixRow).where(PricingMatrixRow.tenant_id == tenant_id)
        )
    assert isinstance(row.unit_price, Decimal), f"unit_price came back as {type(row.unit_price)}"
    assert row.unit_price == Decimal("44.7291")


async def test_the_check_constraint_still_refuses_a_non_positive_price(factory):
    """`ck_matrix_row_price` predates the type change and must survive it —
    a NUMERIC column with no constraint would accept 0.0000, which the float
    column never did."""
    from sqlalchemy.exc import IntegrityError

    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.pricing.models import PricingMatrixRow

    async with factory() as session:
        await bind_platform_context(session, reason="precision test constraint")
        session.add(
            PricingMatrixRow(
                tenant_id=uuid.uuid4(),
                matrix_id=uuid.uuid4(),
                sequence=1,
                from_value=3.0,
                to_value=4.0,
                unit_price=Decimal("0"),
                active=True,
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            return
    raise AssertionError("a zero unit_price was accepted")
