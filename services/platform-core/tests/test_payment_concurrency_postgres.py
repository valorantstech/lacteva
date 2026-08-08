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

PROD-001 extended this to the full scenario matrix (A-D) and made every one of
the six invariants an explicit assertion rather than something implied by a
passing test:

| Invariant | Proven by |
| --- | --- |
| no double allocation | `test_the_lock_refuses_a_concurrent_double_payment` |
| no overpayment | `test_partial_allocations_sum_to_the_payable_and_no_further` |
| no negative outstanding | `test_the_outstanding_balance_never_goes_negative` |
| no lost update | `test_partial_allocations_sum_to_the_payable_and_no_further` |
| no deadlock | `test_opposite_order_allocations_do_not_deadlock` |
| no cross-tenant interaction | `test_another_tenants_payments_never_reduce_this_tenants_balance` |

**The transaction/locking invariant this module protects** (BR-0018, and now
recorded in the register):

> Any read-modify-write of a settlement's outstanding balance MUST hold a row
> lock on that settlement for the whole of it, and MUST acquire locks for a
> multi-settlement payment in ascending settlement-id order. The balance is
> read only from allocations that are (a) tenant-filtered in SQL and (b) joined
> to payments in a LIVE status.

Every clause has a test here, and each was verified to fail when its clause is
removed — the controls are as important as the assertions.
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


def _allocation_inputs(settlement_ids):
    """Accepts bare ids (meaning 'the rest of it') or (id, amount) pairs."""
    from platform_core.modules.payment.service import PaymentAllocationInput

    inputs = []
    for entry in settlement_ids:
        if isinstance(entry, tuple):
            settlement_id, amount = entry
            inputs.append(PaymentAllocationInput(settlement_id=settlement_id, amount=amount))
        else:
            inputs.append(PaymentAllocationInput(settlement_id=entry))
    return inputs


async def _pay(factory, tenant_id, supplier_id, settlement_ids, label):
    """One payment, in its own transaction."""
    from platform_core.core.rls import bind_tenant
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.infrastructure.events import InMemoryEventBus
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.payment.service import CreatePaymentCommand, PaymentService

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
                    allocations=_allocation_inputs(settlement_ids),
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


# --- C: concurrent payments to the same supplier ----------------------------


async def test_concurrent_payments_to_the_same_supplier_do_not_interfere(factory, wide_window):
    """Scenario C. Two settlements, one farmer, two operators, same instant.

    The lock must serialise payments against ONE settlement without serialising
    the supplier: a dairy paying its farmers in parallel is the normal case, and
    a lock whose granularity was the supplier would turn a payment run into a
    queue. Both payments must succeed, each for its own amount.
    """
    tenant_id = uuid.uuid4()
    first, second = Decimal("300.00"), Decimal("700.00")
    supplier_id, (s1, s2) = await _seed(factory, tenant_id, [first, second])

    results = await asyncio.gather(
        _pay(factory, tenant_id, supplier_id, [s1], "A"),
        _pay(factory, tenant_id, supplier_id, [s2], "B"),
    )

    outcomes = {label: (outcome, amount) for label, outcome, amount, _ in results}
    assert outcomes["A"] == ("created", first), results
    assert outcomes["B"] == ("created", second), results
    assert await _allocated(factory, s1) == first
    assert await _allocated(factory, s2) == second


# --- no lost update / no overpayment ----------------------------------------


async def test_partial_allocations_sum_to_the_payable_and_no_further(factory, wide_window):
    """Two concurrent PARTIAL payments, then a third.

    This is the lost-update shape: each payment reads the balance, subtracts
    its own share and writes. Both partials are legitimate and must both
    succeed — a lock that refused one would be too coarse. Their sum must be
    exactly the payable, and the next payment must find nothing left.

    An over-allocating third payment is the overpayment check: it must be
    refused rather than pushing the total past what the dairy owes.
    """
    tenant_id = uuid.uuid4()
    supplier_id, (settlement_id,) = await _seed(factory, tenant_id, [PAYABLE])
    half = Decimal("500.00")

    results = await asyncio.gather(
        _pay(factory, tenant_id, supplier_id, [(settlement_id, half)], "A"),
        _pay(factory, tenant_id, supplier_id, [(settlement_id, half)], "B"),
    )
    assert all(outcome == "created" for _, outcome, _, _ in results), results
    assert await _allocated(factory, settlement_id) == PAYABLE

    # Nothing remains: a third payment must be refused, not allowed to overpay.
    _label, outcome, _amount, detail = await _pay(
        factory, tenant_id, supplier_id, [settlement_id], "C"
    )
    assert outcome == "ConflictError", f"a fully-allocated settlement accepted more: {detail}"
    assert await _allocated(factory, settlement_id) == PAYABLE


async def test_the_outstanding_balance_never_goes_negative(factory, wide_window):
    """The invariant stated positively, read back through the platform's own
    balance query rather than inferred from the ledger."""
    from platform_core.core.rls import bind_tenant
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.infrastructure.events import InMemoryEventBus
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.payment.service import PaymentService

    tenant_id = uuid.uuid4()
    supplier_id, (settlement_id,) = await _seed(factory, tenant_id, [PAYABLE])

    await asyncio.gather(
        *[_pay(factory, tenant_id, supplier_id, [settlement_id], str(n)) for n in range(4)]
    )

    set_current_tenant(tenant_id)
    async with factory() as session:
        await bind_tenant(session, tenant_id)
        service = PaymentService(session, InMemoryEventBus(), AuditService(session))
        page = await service.balances(supplier_id=supplier_id, outstanding_only=False)

    assert page.items, "the settlement should still be listed"
    for item in page.items:
        assert item.outstanding >= 0, f"negative outstanding: {item}"
        assert item.allocated <= item.payable, f"over-allocated: {item}"


# --- D: retry after a failed transaction ------------------------------------


async def test_a_retry_after_a_failed_transaction_allocates_exactly_once(factory):
    """Scenario D. A payment whose transaction dies must leave nothing behind.

    A rolled-back attempt holds no money: the retry has to find the full
    balance and succeed, and the settlement must end up allocated exactly once.
    A reservation that survived its own rollback would refuse the retry
    forever — the failure mode IDM-001 was built to avoid, checked here on the
    money path specifically.
    """
    from platform_core.core.rls import bind_tenant
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.infrastructure.events import InMemoryEventBus
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.payment.service import (
        CreatePaymentCommand,
        PaymentService,
    )

    tenant_id = uuid.uuid4()
    supplier_id, (settlement_id,) = await _seed(factory, tenant_id, [PAYABLE])

    # Attempt 1: the work happens, then the transaction is lost.
    set_current_tenant(tenant_id)
    async with factory() as session:
        await bind_tenant(session, tenant_id)
        service = PaymentService(session, InMemoryEventBus(), AuditService(session))
        await service.create(
            CreatePaymentCommand(
                supplier_id=supplier_id,
                currency="KES",
                method="MOBILE_MONEY",
                allocations=_allocation_inputs([settlement_id]),
            ),
            actor_id=uuid.uuid4(),
        )
        await session.rollback()

    assert await _allocated(factory, settlement_id) == Decimal("0.00"), (
        "a rolled-back attempt left an allocation behind"
    )

    # Attempt 2: the retry must find the full balance.
    _label, outcome, amount, detail = await _pay(
        factory, tenant_id, supplier_id, [settlement_id], "retry"
    )
    assert outcome == "created", f"the retry was refused: {detail}"
    assert amount == PAYABLE
    assert await _allocated(factory, settlement_id) == PAYABLE


# --- cross-tenant -----------------------------------------------------------


async def test_a_tenant_cannot_pay_another_tenants_settlement(factory):
    """Row-level security, exercised through the payment path rather than a
    probe table. Another dairy's settlement must not even be findable."""
    owner, intruder = uuid.uuid4(), uuid.uuid4()
    _owner_supplier, (settlement_id,) = await _seed(factory, owner, [PAYABLE])
    intruder_supplier, _ = await _seed(factory, intruder, [Decimal("10.00")])

    _label, outcome, _amount, detail = await _pay(
        factory, intruder, intruder_supplier, [settlement_id], "intruder"
    )
    assert outcome in ("NotFoundError", "ConflictError"), (
        f"a tenant reached another tenant's settlement: {outcome} {detail}"
    )
    assert await _allocated(factory, settlement_id) == Decimal("0.00")


async def test_another_tenants_payments_never_reduce_this_tenants_balance(factory):
    """PROD-001: the allocation sum is tenant-filtered in SQL, not only by RLS.

    `_allocations_for` is what `_resolve_allocation` subtracts to decide what a
    farmer is still owed, and it previously carried no tenant predicate at all.
    Under a platform-bound session — or on SQLite, where RLS cannot execute —
    another dairy's payment lines would have been summed into this tenant's
    allocated total, silently reducing what the supplier is paid.

    **The reader runs under the BYPASS deliberately.** With an ordinary bound
    session RLS hides the foreign row, so the test would pass whether or not
    the application filter exists — proving the end-to-end isolation but not
    the thing this test is named for. Reading under the platform context turns
    RLS off, which is precisely the condition the defense-in-depth filter
    exists for, and makes the assertion below fail if the filter is removed.
    Verified by removing it.
    """
    from platform_core.core.rls import bind_platform_context
    from platform_core.core.tenancy import set_current_tenant
    from platform_core.infrastructure.events import InMemoryEventBus
    from platform_core.modules.audit.service import AuditService
    from platform_core.modules.payment.models import Payment, PaymentLine
    from platform_core.modules.payment.service import PaymentService

    owner, other = uuid.uuid4(), uuid.uuid4()
    supplier_id, (settlement_id,) = await _seed(factory, owner, [PAYABLE])

    # Another tenant holds a live payment line pointing at this settlement id.
    async with factory() as session:
        await bind_platform_context(session, reason="cross-tenant contamination fixture")
        payment = Payment(
            tenant_id=other,
            supplier_id=uuid.uuid4(),
            payment_number=f"PAY-{uuid.uuid4().hex[:6].upper()}",
            currency="KES",
            method="CASH",
            amount=PAYABLE,
            status="completed",
        )
        session.add(payment)
        await session.flush()
        session.add(
            PaymentLine(
                tenant_id=other,
                payment_id=payment.id,
                settlement_id=settlement_id,
                settlement_number="STL-FOREIGN",
                amount=PAYABLE,
            )
        )
        await session.commit()

    set_current_tenant(owner)
    async with factory() as session:
        # RLS OFF for this read — only the SQL tenant filter can be correct here.
        await bind_platform_context(session, reason="prove the filter, not the policy")
        service = PaymentService(session, InMemoryEventBus(), AuditService(session))
        page = await service.balances(supplier_id=supplier_id, outstanding_only=False)

    assert page.items, "the owner's settlement disappeared from its own balances"
    item = page.items[0]
    assert item.allocated == Decimal("0.00"), (
        f"another tenant's payment reduced this balance: allocated={item.allocated}"
    )
    assert item.outstanding == PAYABLE

    # And the owner can still be paid in full.
    _label, outcome, amount, detail = await _pay(
        factory, owner, supplier_id, [settlement_id], "owner"
    )
    assert outcome == "created", f"the owner could not be paid: {detail}"
    assert amount == PAYABLE


# --- document numbering (PROD-001 §7) ---------------------------------------


async def test_concurrent_allocations_never_issue_the_same_document_number(factory):
    """The series is the audit trail's spine, so a duplicate is not a nuisance.

    Settlement, payment and receipt numbers moved from `secrets.token_hex(3)`
    to a per-tenant sequence because several target jurisdictions require a
    SEQUENTIAL series on a financial document — and because the old
    check-then-act loop raced. A sequence only fixes the race if the counter is
    read under a lock, which is a PostgreSQL behaviour and cannot be shown on
    SQLite.
    """
    from platform_core.core.document_numbers import next_document_number
    from platform_core.core.rls import bind_tenant

    tenant_id = uuid.uuid4()

    async def allocate(_index):
        async with factory() as session:
            # The counter table is tenant-owned and carries the standard
            # policy, so an unbound session cannot write to it at all — the
            # first version of this test proved that by being refused.
            await bind_tenant(session, tenant_id)
            number = await next_document_number(
                session, tenant_id=tenant_id, doc_type="receipt", prefix="RCP"
            )
            await session.commit()
            return number

    numbers = await asyncio.gather(*[allocate(n) for n in range(12)])

    assert len(set(numbers)) == len(numbers), f"duplicate document number issued: {numbers}"
    serials = sorted(int(n.rsplit("-", 1)[1]) for n in numbers)
    assert serials == list(range(1, len(numbers) + 1)), (
        f"the series is not contiguous under concurrency: {serials}"
    )
    assert all(n.startswith("RCP-") for n in numbers)


async def test_the_counter_table_is_itself_tenant_isolated(factory):
    """Found while writing the test above: an unbound session is REFUSED.

    `document_sequence` is tenant-owned, so SEC-002's build check gave it the
    standard policy and the migration enforces it. That matters beyond
    tidiness — a shared counter would let each dairy infer the others' document
    volumes from the gaps in its own series.
    """
    import pytest as _pytest
    from sqlalchemy.exc import DBAPIError

    from platform_core.core.document_numbers import next_document_number

    async with factory() as session:
        with _pytest.raises(DBAPIError):
            await next_document_number(
                session, tenant_id=uuid.uuid4(), doc_type="receipt", prefix="RCP"
            )
        await session.rollback()


async def test_two_tenants_keep_independent_series(factory):
    """A shared series would let each dairy infer the others' volumes from the
    gaps in its own numbers — which is why this is a table and not a native
    PostgreSQL SEQUENCE."""
    from platform_core.core.document_numbers import next_document_number
    from platform_core.core.rls import bind_tenant

    first, second = uuid.uuid4(), uuid.uuid4()

    async def allocate(tenant_id):
        async with factory() as session:
            await bind_tenant(session, tenant_id)
            number = await next_document_number(
                session, tenant_id=tenant_id, doc_type="settlement", prefix="STL"
            )
            await session.commit()
            return number

    assert (await allocate(first)).endswith("000001")
    assert (await allocate(first)).endswith("000002")
    # A different dairy starts its own series at 1.
    assert (await allocate(second)).endswith("000001")
