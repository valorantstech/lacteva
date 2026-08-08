"""The money path under real concurrency (ARCH-FINAL-001).

ARCH-001 rated one defect CRITICAL — two concurrent payments each claiming the
full outstanding balance of one settlement — and fixed it by locking the
settlement `FOR UPDATE` before its balance is read.

**The fix was correct. Its proof was not.** The two tests covering it in
`test_production_readiness.py` are `inspect.getsource()` string matches: they
assert that the characters `with_for_update=True` appear in the method. That
cannot distinguish a lock that works from a lock that is silently a no-op —
and on SQLite `FOR UPDATE` **is** a no-op, so no test in the main suite could
have proven it either. A guarantee about PostgreSQL concurrency, verified by
grepping Python source, is exactly the shape STD-0007 §6 exists to forbid.

This module executes the races instead, against a real engine:

1. `test_the_lock_refuses_a_concurrent_double_payment` runs the race the fix
   exists to prevent.
2. `test_the_race_reproduces_without_the_lock` removes the lock and asserts the
   race DOES occur. Without it, test 1 could pass for any reason at all — a
   proof that cannot fail proves nothing.
3. `test_opposite_order_allocations_do_not_deadlock` covers the defect this
   review found *because* the lock exists: locking in client-supplied order
   deadlocks two payments over the same pair of settlements.

Each payment runs in its own session and its own transaction, which is what
makes them genuinely concurrent rather than sequential calls that look it.
"""

import asyncio
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests import postgres_support

POSTGRES_URL = postgres_support.POSTGRES_URL
pytestmark = postgres_support.requires_postgres

#: Held open between reading a settlement's balance and writing the allocation.
#: This widens the read-modify-write window so the outcome is decided by the
#: locking, not by scheduling luck. It changes timing only — never the logic.
WINDOW_SECONDS = 0.4

PAYABLE = Decimal("1000.00")


@pytest_asyncio.fixture
async def factory(monkeypatch):
    """Sessions over the real database, with `is_postgres()` answering true."""
    from platform_core.core.config import get_settings

    monkeypatch.setattr(get_settings(), "database_url", POSTGRES_URL)
    engine = create_async_engine(POSTGRES_URL, pool_size=6, max_overflow=4)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed(factory, tenant_id: uuid.UUID, amounts: list[Decimal]):
    """One supplier and one finalized settlement per amount."""
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.settlement.models import Settlement
    from platform_core.modules.supplier.models import Supplier, SupplierProfile

    supplier_id = uuid.uuid4()
    settlement_ids = []
    async with factory() as session:
        await bind_platform_context(session, reason="concurrency test seeding")
        session.add(
            Supplier(
                id=supplier_id,
                tenant_id=tenant_id,
                code=f"S-{uuid.uuid4().hex[:6].upper()}",
                status="active",
            )
        )
        session.add(
            SupplierProfile(tenant_id=tenant_id, supplier_id=supplier_id, full_name="Test Farmer")
        )
        for index, amount in enumerate(amounts):
            settlement_id = uuid.uuid4()
            settlement_ids.append(settlement_id)
            session.add(
                Settlement(
                    id=settlement_id,
                    tenant_id=tenant_id,
                    supplier_id=supplier_id,
                    center_id=uuid.uuid4(),
                    settlement_number=f"STL-{uuid.uuid4().hex[:6].upper()}",
                    period_from=date(2026, 6 + index, 1),
                    period_to=date(2026, 6 + index, 28),
                    currency="KES",
                    gross_amount=amount,
                    adjustments_amount=Decimal("0.00"),
                    net_amount=amount,
                    status="finalized",
                    finalized_at=datetime.now(UTC),
                )
            )
        await session.commit()
    return supplier_id, settlement_ids


async def _pay(factory, tenant_id, supplier_id, settlement_ids, label):
    """One full-balance payment, in its own transaction."""
    from platform_core.core.rls import bind_tenant
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.infrastructure.events import InMemoryEventBus
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.payment.service import (
        CreatePaymentCommand,
        PaymentAllocationInput,
        PaymentService,
    )

    set_current_tenant(tenant_id)
    async with factory() as session:
        await bind_tenant(session, tenant_id)
        service = PaymentService(session, InMemoryEventBus(), AuditService(session))
        try:
            payment = await service.create(
                CreatePaymentCommand(
                    supplier_id=supplier_id,
                    currency="KES",
                    method="MOBILE_MONEY",
                    allocations=[PaymentAllocationInput(settlement_id=s) for s in settlement_ids],
                ),
                actor_id=uuid.uuid4(),
            )
            await session.commit()
            return (label, "created", Decimal(payment.amount), "")
        except Exception as exc:
            await session.rollback()
            return (label, type(exc).__name__, Decimal("0.00"), str(exc)[:200])


async def _allocated(factory, settlement_id) -> Decimal:
    from platform_core.core.rls import bind_platform_context
    from platform_core.modules.payment.models import PaymentLine

    async with factory() as session:
        await bind_platform_context(session, reason="concurrency test verification")
        total = await session.scalar(
            select(func.coalesce(func.sum(PaymentLine.amount), 0)).where(
                PaymentLine.settlement_id == settlement_id
            )
        )
    return Decimal(total)


@pytest.fixture
def wide_window(monkeypatch):
    """Hold the read-modify-write window open, so locking decides the outcome."""
    from platform_core.modules.payment.service import PaymentService

    original = PaymentService._resolve_allocation

    async def slow_resolve(self, settlement, requested):
        amount = await original(self, settlement, requested)
        await asyncio.sleep(WINDOW_SECONDS)
        return amount

    monkeypatch.setattr(PaymentService, "_resolve_allocation", slow_resolve)


async def test_the_lock_refuses_a_concurrent_double_payment(factory, wide_window):
    """The defect ARCH-001 found, executed rather than grepped.

    Two payments, one settlement, same instant, each omitting the amount —
    which means "the rest of it". Exactly one may succeed. If both do, the
    dairy has paid the same farmer twice for the same milk and nothing in the
    platform will notice: partial payment is legitimate, so no unique
    constraint can collide.
    """
    tenant_id = uuid.uuid4()
    supplier_id, (settlement_id,) = await _seed(factory, tenant_id, [PAYABLE])

    results = await asyncio.gather(
        _pay(factory, tenant_id, supplier_id, [settlement_id], "A"),
        _pay(factory, tenant_id, supplier_id, [settlement_id], "B"),
    )

    created = [r for r in results if r[1] == "created"]
    assert len(created) == 1, f"expected exactly one payment to succeed, got {results}"
    total = await _allocated(factory, settlement_id)
    assert total == PAYABLE, (
        f"{total} allocated against a {PAYABLE} payable — the settlement was paid twice"
    )


async def test_the_race_reproduces_without_the_lock(factory, wide_window, monkeypatch):
    """The control. Without this, the test above proves nothing.

    Restores the pre-ARCH-001 read path — identical except that the settlement
    is not locked — and asserts the double payment DOES happen. A proof must
    show the guard is capable of refusing; this is what establishes that the
    guard, and not the scheduler, is what refuses.
    """
    from platform_core.modules.payment.service import PaymentService
    from platform_core.modules.settlement.models import Settlement

    async def unlocked(self, settlement_id_, tenant_id_, supplier_id_, currency):
        settlement = await self._session.get(Settlement, settlement_id_)
        assert settlement is not None and settlement.tenant_id == tenant_id_
        return settlement

    monkeypatch.setattr(PaymentService, "_payable_settlement", unlocked)

    tenant_id = uuid.uuid4()
    supplier_id, (settlement_id,) = await _seed(factory, tenant_id, [PAYABLE])

    await asyncio.gather(
        _pay(factory, tenant_id, supplier_id, [settlement_id], "A"),
        _pay(factory, tenant_id, supplier_id, [settlement_id], "B"),
    )

    total = await _allocated(factory, settlement_id)
    assert total > PAYABLE, (
        "the unlocked race did NOT over-allocate, so this suite cannot tell a "
        "working lock from a missing one — widen WINDOW_SECONDS"
    )


async def test_opposite_order_allocations_do_not_deadlock(factory, monkeypatch):
    """The defect the lock itself introduced (ARCH-FINAL-001).

    A supplier with two unpaid settlements is ordinary. Two payments that
    allocate both, in opposite order, took the same two row locks in opposite
    order — PostgreSQL detects the cycle and aborts one transaction with
    SQLSTATE 40P01, which the operator sees as a 500 while trying to pay a
    farmer.

    `create` now sorts allocations by settlement id, so every transaction in
    the platform acquires these locks in the same sequence and no cycle can
    form. This test fails with a DeadlockDetectedError if that ordering is
    ever removed.
    """
    from platform_core.modules.payment.service import PaymentService

    original = PaymentService._payable_settlement

    async def slow_payable(self, *args, **kwargs):
        settlement = await original(self, *args, **kwargs)
        # Hold the first lock while the other payment takes the second.
        await asyncio.sleep(WINDOW_SECONDS)
        return settlement

    monkeypatch.setattr(PaymentService, "_payable_settlement", slow_payable)

    tenant_id = uuid.uuid4()
    half = Decimal("500.00")
    supplier_id, settlement_ids = await _seed(factory, tenant_id, [half, half])

    results = await asyncio.gather(
        _pay(factory, tenant_id, supplier_id, settlement_ids, "A"),
        _pay(factory, tenant_id, supplier_id, list(reversed(settlement_ids)), "B"),
    )

    for label, outcome, _amount, detail in results:
        assert "deadlock" not in detail.lower(), f"payment {label} deadlocked: {outcome} {detail}"

    # One payment takes both settlements; the other finds nothing outstanding.
    # Either way the money is allocated exactly once.
    for settlement_id in settlement_ids:
        assert await _allocated(factory, settlement_id) <= half
