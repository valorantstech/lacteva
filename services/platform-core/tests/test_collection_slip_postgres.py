"""The collection slip number on real PostgreSQL (P0-BIZ-003).

`test_collection_slip.py` proves the document on SQLite. This is the half
SQLite cannot prove:

* the UNIQUE constraint the migration created is real on the engine that
  matters, by name;
* two concurrent readers lazily minting a number for the same pre-slip
  transaction end up with ONE number and NO gap in the series — the loser's
  rollback must undo its own sequence increment, then survive losing its
  transaction-scoped RLS binding (the same SET LOCAL semantics that made
  IDM-001 a 500) and re-read the winner's number.

The race runs through the PUBLIC `slip()` path, so what is proven is the
behaviour a request would get, not a private helper in isolation.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres


@pytest.fixture(autouse=True)
def _settings_point_at_postgres(monkeypatch):
    """Make `is_postgres()` true, or every binding below is a no-op."""
    from platform_core.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", POSTGRES_URL)
    monkeypatch.setattr(settings, "rls_enabled", True)


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(POSTGRES_URL, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean(factory):
    yield
    from platform_core.core.rls import bind_platform_context

    async with factory() as session:
        await bind_platform_context(session, reason="slip proof cleanup")
        await session.execute(
            text("DELETE FROM milk_collection_transaction WHERE container_identifier = 'PG-SLIP'")
        )
        await session.execute(
            text("DELETE FROM document_sequence WHERE doc_type = 'collection_slip'")
        )
        await session.commit()


def _bare_service(session):
    """The service with only what `slip()` touches. The collaborators a slip
    read never uses are deliberately absent — if the read path ever starts
    publishing events or re-pricing, this construction fails loudly, which is
    the correct alarm."""
    from platform_core.modules.milk_collection.service import MilkCollectionService

    return MilkCollectionService(session, None, None, None, None, None)


async def _seed_completed_pre_slip_tx(factory, tenant_id: uuid.UUID) -> uuid.UUID:
    from platform_core.core.db import utcnow
    from platform_core.core.rls import rebind_tenant
    from platform_core.modules.milk_collection.models import MilkCollectionTransaction

    async with factory() as session:
        await rebind_tenant(session, tenant_id)
        tx = MilkCollectionTransaction(
            tenant_id=tenant_id,
            session_id=uuid.uuid4(),
            center_id=uuid.uuid4(),
            operator_id=uuid.uuid4(),
            state="COMPLETED",
            milk_type="cow",
            container_identifier="PG-SLIP",
            completed_at=utcnow(),
        )
        session.add(tx)
        await session.commit()
        return tx.id


async def test_the_unique_constraint_is_real_on_postgres(factory):
    """The migration's constraint, read back from the catalog by name."""
    async with factory() as session:
        row = await session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conname = 'uq_milk_tx_slip' "
                "AND conrelid = 'milk_collection_transaction'::regclass"
            )
        )
    assert row.scalar() == "uq_milk_tx_slip"


async def test_concurrent_lazy_mints_agree_on_one_number_and_leave_no_gap(factory):
    """Two readers ask for the same pre-slip transaction's slip at once.

    The winner assigns …-000001. The loser's CAS finds the row taken, rolls
    back (undoing its own increment), rebinds RLS, and reads the winner's
    number — so both callers hold the SAME slip, exactly one number was
    consumed, and the next allocation in the series is …-000002.
    """
    from platform_core.core.rls import rebind_tenant
    from platform_core.core.tenancy import set_current_tenant

    tenant = uuid.uuid4()
    tx_id = await _seed_completed_pre_slip_tx(factory, tenant)
    set_current_tenant(tenant)

    async def read_slip() -> str:
        async with factory() as session:
            await rebind_tenant(session, tenant)
            view = await _bare_service(session).slip(tx_id)
            await session.commit()
            return view.slip_number

    first, second = await asyncio.gather(read_slip(), read_slip())
    assert first == second, "one transaction, one slip — regardless of who asked first"
    assert first.endswith("-000001"), first

    async with factory() as session:
        await rebind_tenant(session, tenant)
        count = await session.scalar(
            text("SELECT count(*) FROM milk_collection_transaction WHERE slip_number = :n"),
            {"n": first},
        )
        assert count == 1
        from platform_core.core.document_numbers import next_document_number

        probe = await next_document_number(
            session, tenant_id=tenant, doc_type="collection_slip", prefix="SLP"
        )
        await session.rollback()  # the probe is a measurement, not an allocation
    assert probe.endswith("-000002"), (
        f"the loser's rollback must return its number to the series — got {probe}"
    )


async def test_a_slip_number_is_invisible_to_another_tenant(factory):
    """The column rides the table's row policy: another tenant sees nothing."""
    from platform_core.core.rls import rebind_tenant
    from platform_core.core.tenancy import set_current_tenant

    tenant, stranger = uuid.uuid4(), uuid.uuid4()
    tx_id = await _seed_completed_pre_slip_tx(factory, tenant)
    set_current_tenant(tenant)

    async with factory() as session:
        await rebind_tenant(session, tenant)
        view = await _bare_service(session).slip(tx_id)
        await session.commit()

    async with factory() as session:
        await rebind_tenant(session, stranger)
        count = await session.scalar(
            text("SELECT count(*) FROM milk_collection_transaction WHERE slip_number = :n"),
            {"n": view.slip_number},
        )
    assert count == 0
