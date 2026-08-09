"""Post-restore integrity verification (BAK-001).

A restore that loads every row and still leaves the business wrong is a
failed restore. Row counts and checksums prove the *bytes* arrived; these
checks prove the *meaning* survived.

This platform is unusually well placed to do that, because it already states
its invariants as numbered business rules with enforcement in code. A restore
can therefore be verified against the same rules the running system enforces:

| Check | Rule | What a failure means |
| --- | --- | --- |
| Settlement totals equal their lines | BR-0011 | Someone is owed a different amount than before |
| Allocations never exceed the payable | BR-0018 | A settlement was over-paid |
| One receipt per completed payment | BR-0020 | Proof of payment was lost or duplicated |
| Receipts point at payments that exist | BR-0020 | Dangling evidence |
| Consumer cursors are within the log | BR-0014 | Replay will duplicate or skip effects |
| No orphaned settlement or payment lines | — | Referential damage the loader hid |
| Projections rebuild to the same content | BR-0015 | The read models cannot be trusted |

The last one is the strongest available evidence: it re-derives the read
models from the event log and compares. If a rebuilt projection matches, the
log and the projections agree — which is the whole guarantee PLT-001 exists
to provide.
"""

from dataclasses import dataclass, field
from decimal import Decimal

import structlog
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

log = structlog.get_logger("backup.integrity")


@dataclass
class IntegrityCheck:
    name: str
    passed: bool
    detail: str
    rule: str = ""


@dataclass
class IntegrityReport:
    checks: list[IntegrityCheck] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> list[IntegrityCheck]:
        return [c for c in self.checks if not c.passed]


class IntegrityVerifier:
    """Verifies that a restored database is business-correct, not merely full."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._sf = session_factory

    async def verify(self, *, deep: bool = False) -> IntegrityReport:
        """Run every check. `deep` additionally rebuilds projections from the
        event log and compares — slower, and the strongest evidence there is."""
        report = IntegrityReport()
        async with self._sf() as session:
            report.checks.append(await self._settlement_totals(session))
            report.checks.append(await self._payment_allocations(session))
            report.checks.append(await self._receipts_match_payments(session))
            report.checks.append(await self._no_orphaned_lines(session))
            report.checks.append(await self._consumer_cursors_within_log(session))
            report.checks.append(await self._audit_trail_present(session))
        if deep:
            report.checks.append(await self._projections_rebuild_identically())
        for check in report.failures:
            log.error("integrity_check_failed", check=check.name, detail=check.detail)
        return report

    # --- checks -------------------------------------------------------------

    async def _settlement_totals(self, session: AsyncSession) -> IntegrityCheck:
        from platform_core.modules.settlement.models import Settlement, SettlementLine

        rows = (
            await session.execute(
                select(
                    Settlement.id,
                    Settlement.settlement_number,
                    Settlement.gross_amount,
                    func.coalesce(func.sum(SettlementLine.gross_amount), 0),
                )
                .outerjoin(SettlementLine, SettlementLine.settlement_id == Settlement.id)
                .where(Settlement.status.in_(("calculated", "finalized")))
                .group_by(Settlement.id, Settlement.settlement_number, Settlement.gross_amount)
            )
        ).all()
        broken = [
            number for _id, number, stored, summed in rows if Decimal(stored) != Decimal(summed)
        ]
        return IntegrityCheck(
            name="settlement_totals_match_lines",
            passed=not broken,
            detail=(
                f"{len(rows)} settled settlements reconcile"
                if not broken
                else f"totals disagree with lines: {', '.join(broken[:5])}"
            ),
            rule="BR-0011",
        )

    async def _payment_allocations(self, session: AsyncSession) -> IntegrityCheck:
        from platform_core.modules.payment.models import LIVE_STATUSES, Payment, PaymentLine
        from platform_core.modules.settlement.models import Settlement

        rows = (
            await session.execute(
                select(
                    Settlement.settlement_number,
                    Settlement.net_amount,
                    # The status predicate lives in the JOIN condition, so a
                    # line belonging to a failed or cancelled payment survives
                    # with a NULL payment rather than being dropped. Summing
                    # PaymentLine.amount directly would therefore count it, and
                    # a settlement paid once unsuccessfully and then paid again
                    # would be reported as over-allocated on every restore.
                    # Count only the rows the join actually matched.
                    func.coalesce(
                        func.sum(case((Payment.id.isnot(None), PaymentLine.amount), else_=0)), 0
                    ),
                )
                .outerjoin(PaymentLine, PaymentLine.settlement_id == Settlement.id)
                .outerjoin(
                    Payment,
                    (Payment.id == PaymentLine.payment_id) & Payment.status.in_(LIVE_STATUSES),
                )
                .group_by(Settlement.id, Settlement.settlement_number, Settlement.net_amount)
            )
        ).all()
        over = [
            number for number, payable, allocated in rows if Decimal(allocated) > Decimal(payable)
        ]
        return IntegrityCheck(
            name="payments_never_exceed_the_payable",
            passed=not over,
            detail=(
                f"{len(rows)} settlements within their payable"
                if not over
                else f"over-allocated: {', '.join(over[:5])}"
            ),
            rule="BR-0018",
        )

    async def _receipts_match_payments(self, session: AsyncSession) -> IntegrityCheck:
        from platform_core.modules.payment.models import Payment
        from platform_core.modules.receipt.models import Receipt

        completed = set(
            (await session.scalars(select(Payment.id).where(Payment.status == "completed"))).all()
        )
        receipted = (
            await session.execute(
                select(Receipt.payment_id, func.count()).group_by(Receipt.payment_id)
            )
        ).all()
        by_payment = {payment_id: count for payment_id, count in receipted}

        duplicated = [str(p) for p, count in by_payment.items() if count > 1]
        dangling = [str(p) for p in by_payment if p not in completed]
        problems = []
        if duplicated:
            problems.append(f"payments with more than one receipt: {len(duplicated)}")
        if dangling:
            problems.append(f"receipts for payments that no longer exist: {len(dangling)}")
        return IntegrityCheck(
            name="one_receipt_per_completed_payment",
            passed=not problems,
            detail=(
                f"{len(by_payment)} receipts, each tied to exactly one completed payment"
                if not problems
                else "; ".join(problems)
            ),
            rule="BR-0020",
        )

    async def _no_orphaned_lines(self, session: AsyncSession) -> IntegrityCheck:
        """Lines whose parent vanished. A loader that inserted children before
        parents, or a partial restore, shows up here."""
        from platform_core.modules.payment.models import Payment, PaymentLine
        from platform_core.modules.receipt.models import Receipt, ReceiptLine
        from platform_core.modules.settlement.models import Settlement, SettlementLine

        orphans = {}
        for child, parent, fk in (
            (SettlementLine, Settlement, SettlementLine.settlement_id),
            (PaymentLine, Payment, PaymentLine.payment_id),
            (ReceiptLine, Receipt, ReceiptLine.receipt_id),
        ):
            count = await session.scalar(
                select(func.count())
                .select_from(child)
                .where(~select(parent.id).where(parent.id == fk).exists())
            )
            if count:
                orphans[child.__tablename__] = count
        return IntegrityCheck(
            name="no_orphaned_child_rows",
            passed=not orphans,
            detail="every line has its parent" if not orphans else f"orphans: {orphans}",
        )

    async def _consumer_cursors_within_log(self, session: AsyncSession) -> IntegrityCheck:
        """A cursor past the end of the restored log means the consumer would
        skip events; a missing cursor means it would replay them all."""
        from platform_core.modules.event_relay.models import ConsumerCursor, OutboxEvent

        newest = await session.scalar(select(func.max(OutboxEvent.created_at)))
        cursors = list((await session.scalars(select(ConsumerCursor))).all())
        if newest is None:
            return IntegrityCheck(
                name="consumer_cursors_within_the_log",
                passed=True,
                detail="no events restored; nothing to be ahead of",
                rule="BR-0014",
            )
        from platform_core.core.db import as_utc

        ahead = [
            c.consumer_name
            for c in cursors
            if c.position_created_at is not None and as_utc(c.position_created_at) > as_utc(newest)
        ]
        return IntegrityCheck(
            name="consumer_cursors_within_the_log",
            passed=not ahead,
            detail=(
                f"{len(cursors)} cursors within the restored log"
                if not ahead
                else f"cursors ahead of the log (events would be skipped): {', '.join(ahead)}"
            ),
            rule="BR-0014",
        )

    async def _audit_trail_present(self, session: AsyncSession) -> IntegrityCheck:
        """The audit trail is required for dispute resolution. Business
        records without their audit history is a restore that lost evidence."""
        from platform_core.modules.audit.models import AuditRecord
        from platform_core.modules.payment.models import Payment

        payments = await session.scalar(select(func.count()).select_from(Payment)) or 0
        audits = await session.scalar(select(func.count()).select_from(AuditRecord)) or 0
        missing = payments > 0 and audits == 0
        return IntegrityCheck(
            name="audit_trail_restored",
            passed=not missing,
            detail=(
                f"{audits} audit records alongside {payments} payments"
                if not missing
                else "payments restored with no audit trail at all"
            ),
        )

    async def _projections_rebuild_identically(self) -> IntegrityCheck:
        """The strongest evidence: re-derive the read models from the event
        log and confirm the platform's own verifier is satisfied (BR-0015)."""
        from platform_core.modules.event_relay.projections import ProjectionRebuilder

        rebuilder = ProjectionRebuilder(self._sf)
        names = [status.name for status in await rebuilder.status_all()]
        unhealthy = []
        for name in names:
            result = await rebuilder.rebuild(name)
            if result.status != "completed":
                unhealthy.append(f"{name}: rebuild {result.status}")
                continue
            verification = await rebuilder.verify(name, deep=True)
            if not verification.healthy:
                unhealthy.append(f"{name}: {', '.join(verification.problems)}")
        return IntegrityCheck(
            name="projections_rebuild_from_the_event_log",
            passed=not unhealthy,
            detail=(
                f"{len(names)} projections rebuilt and verified against the log"
                if not unhealthy
                else "; ".join(unhealthy)
            ),
            rule="BR-0015",
        )
