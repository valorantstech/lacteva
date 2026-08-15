"""Financial document numbering (PROD-001).

## The decision

Settlement, payment and receipt numbers were `secrets.token_hex(3)` — 24 bits
of randomness — allocated by a check-then-act loop that generated a candidate,
`SELECT`ed to see whether it was free, and retried up to five times.

QR-0007 rated that Medium. Reviewing it against what these documents actually
ARE, it is not acceptable, for two independent reasons:

1. **Legal.** Settlements, payments and especially receipts are financial
   documents. Kenya's eTIMS, India's GST invoicing rules and the EU VAT
   directive all require invoice/receipt numbers to run in a **sequential
   series**. A random hex string cannot satisfy that in any of them, and
   renumbering historical documents after a pilot has issued them is far worse
   than choosing correctly now.
2. **Correctness.** The check-then-act loop has a race — two transactions can
   generate the same candidate, both find it free, and one fails on the unique
   constraint with a 500 — and its collision probability grows with the square
   of the document count, so it degrades exactly as a customer succeeds.

So: a **per-tenant, per-type, per-year monotonic sequence**, allocated under a
row lock.

    STL-2026-000001    settlements
    PAY-2026-000001    payments
    RCP-2026-000001    receipts

## What "gapless" honestly means here

The sequence is **monotonic and unique**, and gapless in the ordinary case. It
is not gapless under rollback: a transaction that allocates number 42 and then
fails leaves 42 unused, because releasing it would require holding the lock
until commit across every other allocator, which serialises the whole platform
behind one counter.

That trade is deliberate and it is the standard one. Where a jurisdiction
requires strict gaplessness, the accepted practice is a reconciliation register
that records issued-and-voided numbers rather than preventing gaps — noted as
future work in DBD-0001 rather than built speculatively.

## Why a table rather than a PostgreSQL SEQUENCE

A native sequence is per-database, not per-tenant, so every dairy would share
one series and each could infer the others' volumes from the gaps. It also
cannot reset per year. Sequences are also explicitly non-transactional, which
buys nothing here since we accept rollback gaps anyway.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Integer, String, UniqueConstraint, Uuid, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin

#: Zero-padding for the serial part. Six digits carries a million documents of
#: one type per tenant per year; the format degrades gracefully past that
#: (the number simply grows) rather than wrapping or failing.
WIDTH = 6


class DocumentSequence(Base, IdMixin):
    """One counter per (tenant, document type, period)."""

    __tablename__ = "document_sequence"
    __table_args__ = (
        UniqueConstraint("tenant_id", "doc_type", "period", name="uq_document_sequence"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    #: `settlement` | `payment` | `receipt` — the series, not the table.
    doc_type: Mapped[str] = mapped_column(String(30))
    #: The reset window. `2026` today; a market requiring a fiscal year that
    #: does not start in January changes this string and nothing else.
    period: Mapped[str] = mapped_column(String(10))
    next_value: Mapped[int] = mapped_column(Integer, default=1)


def period_for(on: date) -> str:
    """The series window a document dated `on` belongs to.

    `on` is a BUSINESS date and is now required. It defaulted to
    `utcnow().date()` until DEMO-020, which is UTC's year: a receipt handed
    over at 04:00 on 1 January in Bengaluru was stamped with the year that
    ended ninety minutes earlier, so an Indian dairy's first receipts of every
    January carried the previous year's series — on a sequential financial
    document several target jurisdictions require to be exactly that.

    Kenya and Qatar are three hours ahead of UTC and were wrong for the same
    three hours. Nothing failed, because the counter is per `(tenant, type,
    period)` and simply kept counting in the old year.
    """
    return str(on.year)


async def next_document_number(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    doc_type: str,
    prefix: str,
    period: str | None = None,
) -> str:
    """Allocate the next number in this tenant's series.

    The counter row is locked `FOR UPDATE` before it is read, for exactly the
    reason `PaymentService._payable_settlement` locks a settlement: this is a
    read-modify-write, and without the lock two concurrent allocations both
    read the same value and both return it. That failure is worse here than a
    duplicate payment would be, because the unique constraint turns it into a
    500 on the document the user was creating.
    """
    if period is None:
        # The TENANT's year, resolved here so that all seven document series
        # get it from one place rather than each remembering to ask. The
        # lookup is a cached locale read, not a round trip per document.
        from platform_core.core.business_time import business_today
        from platform_core.core.org_context import tenant_timezone

        period = period_for(business_today(await tenant_timezone(session, tenant_id)))
    statement = (
        select(DocumentSequence)
        .where(
            DocumentSequence.tenant_id == tenant_id,
            DocumentSequence.doc_type == doc_type,
            DocumentSequence.period == period,
        )
        .with_for_update()
    )
    sequence = await session.scalar(statement)

    if sequence is None:
        # First document of the year. Two concurrent transactions can both
        # reach here, so the insert goes in a SAVEPOINT: the loser's constraint
        # violation rolls back only this nested block, leaving the caller's
        # business transaction — which may already hold a settlement lock —
        # entirely intact. A bare rollback here would silently discard it.
        try:
            async with session.begin_nested():
                sequence = DocumentSequence(
                    tenant_id=tenant_id, doc_type=doc_type, period=period, next_value=1
                )
                session.add(sequence)
                await session.flush()
        except IntegrityError:
            sequence = await session.scalar(statement)
            if sequence is None:  # pragma: no cover - the row must exist by now
                raise

    value = sequence.next_value
    sequence.next_value = value + 1
    await session.flush()
    return f"{prefix}-{period}-{value:0{WIDTH}d}"
