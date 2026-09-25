"""The month's bills, drafted without anybody remembering (DEMO-019 §8).

A dairy that has to remember to bill on the first of the month eventually
does not, and the milk it delivered in February is still unbilled in April.
This drafts the bills.

**It drafts them. It does not issue them.** That distinction is the entire
safety argument and the reason this is the "smallest safe mechanism" §8 asks
for rather than a cautious version of something bigger:

* a DRAFT is not money owed. It is absent from `PAYABLE_INVOICE_STATUSES`, so
  it appears on no statement, in no receivable total, and in no customer's
  outstanding balance. It can be cancelled, and cancelling it releases its
  deliveries to be billed again;
* ISSUING is the irreversible act — the invoice becomes immutable and payable
  the moment it happens, and BR-0010 says so. That belongs to a person, who
  can look at the month before handing it to a household.

So the automation removes the clerical work and leaves the commitment. A
month-end job that issued bills would be a machine posting receivables into a
dairy's books on a schedule, and the first anyone would hear of a mistake is a
customer disputing a bill nobody read.

**It reuses `BillingService.generate_invoice` exactly.** No second billing
path, no second definition of what a month's bill contains: the same function
an operator calls, called on a schedule. If it refuses — no unbilled
deliveries, a bill already exists for the period — that refusal is the answer
and this records it rather than working around it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.business_time import business_today, previous_month_bounds
from platform_core.core.errors import ConflictError, NotFoundError
from platform_core.modules.billing.service import BillingService, GenerateInvoiceCommand
from platform_core.modules.customer.models import Customer

log = structlog.get_logger("billing.month_end")


@dataclass
class DraftingResult:
    """What one month-end pass did, for one tenant."""

    period_from: date
    period_to: date
    #: Active customers considered.
    customers: int
    #: Drafts actually created.
    drafted: int
    #: Customers the platform declined to bill, and why — almost always
    #: "nothing to bill" or "already billed", both of which are correct
    #: answers rather than failures.
    skipped: int
    reasons: dict[str, int] = field(default_factory=dict)


def previous_month(today: date) -> tuple[date, date]:
    """The month that has just ended, in the dairy's own calendar.

    Drafting runs for the month BEFORE the one we are in: a bill for August
    cannot be complete until August is over. Running on the 1st of September
    drafts August, and running again on the 5th drafts nothing new because the
    period already has a live invoice.

    DEMO-020: this is now one line over the platform's own month arithmetic.
    It used to walk back to the previous month by hand, which is a second
    implementation of a rule that has one authority — and the kind of
    duplicate that stays right until February.
    """
    return previous_month_bounds(today)


#: WO-86. Namespace for the nudge's event id: one notice per administrator per
#: tenant per period, however many mornings the scheduler runs on the 1st.
MONTH_END_NUDGE_NAMESPACE = uuid.UUID("6f1e6c1a-6e0d-4d5b-9f7a-2b3c4d5e6f70")


async def notify_month_end_drafted(
    session: AsyncSession, *, tenant_id: uuid.UUID, result: DraftingResult
) -> int:
    """Tell the dairy's administrators that drafts are waiting (WO-86 §4).

    A draft is not a bill: nothing reaches a household until someone presses
    Issue, and on a platform that drafts automatically the failure mode is a
    stack of drafts nobody knew about. So the pass that drafted them leaves an
    in-app notice for every `tenant-admin`, once per period (the event id is
    derived, so a second pass on the same 1st re-sends nothing). Nothing is
    sent when nothing was drafted — there is nothing to review.

    Returns how many notices were created this time.
    """
    if result.drafted <= 0:
        return 0
    from platform_core.modules.authz.service import AuthzService
    from platform_core.modules.notification.service import (
        NotificationRequest,
        NotificationService,
    )

    service = NotificationService(session)
    created = 0
    for user_id in await AuthzService(session).users_with_role("tenant-admin", tenant_id):
        notification = await service.dispatch(
            NotificationRequest(
                event_id=uuid.uuid5(
                    MONTH_END_NUDGE_NAMESPACE, f"{tenant_id}:{result.period_from}:{user_id}"
                ),
                event_name="billing.month-end-drafted.v1",
                tenant_id=tenant_id,
                template_key="month_end_drafted",
                channel="inapp",
                recipient_ref=user_id,
                variables={
                    "drafted": result.drafted,
                    "skipped": result.skipped,
                    "period": f"{result.period_from} - {result.period_to}",
                },
            )
        )
        created += notification is not None
    return created


async def draft_month_end(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    timezone: str | None,
    actor_id: uuid.UUID | None = None,
    period: tuple[date, date] | None = None,
) -> DraftingResult:
    """Draft last month's bill for every active customer of one tenant.

    Runs inside the caller's binding — the scheduler rebinds to the tenant
    before calling, so the customer query is filtered by the database exactly
    as it would be for that tenant's own manager.

    A customer the platform declines to bill is counted and the reason kept.
    `generate_invoice` raises `ConflictError` for the two ordinary cases —
    nothing unbilled in the period, or a live invoice already covering it —
    and both mean "correctly nothing to do" rather than "something went
    wrong", which is why they are counted rather than raised.
    """
    period_from, period_to = period or previous_month(business_today(timezone))
    billing = BillingService(session, bus=_NullBus(), audit=_audit(session))

    customers = (
        await session.scalars(
            select(Customer.id).where(Customer.tenant_id == tenant_id, Customer.status == "active")
        )
    ).all()

    result = DraftingResult(
        period_from=period_from,
        period_to=period_to,
        customers=len(customers),
        drafted=0,
        skipped=0,
    )
    for customer_id in customers:
        try:
            invoice = await billing.generate_invoice(
                GenerateInvoiceCommand(
                    customer_id=customer_id, period_from=period_from, period_to=period_to
                ),
                actor_id=actor_id,
            )
        except (ConflictError, NotFoundError) as refusal:
            result.skipped += 1
            reason = str(refusal)
            # Bucketed, not accumulated verbatim: three hundred customers with
            # nothing to bill must not become three hundred distinct strings
            # in a log line.
            key = "already billed" if "already has invoice" in reason else "nothing to bill"
            result.reasons[key] = result.reasons.get(key, 0) + 1
            continue
        result.drafted += 1
        log.debug(
            "month_end_draft_created",
            invoice=invoice.invoice_number,
            customer=str(customer_id),
            total=str(invoice.total),
        )

    log.info(
        "month_end_drafting_completed",
        tenant_id=str(tenant_id),
        period_from=str(period_from),
        period_to=str(period_to),
        customers=result.customers,
        drafted=result.drafted,
        skipped=result.skipped,
        reasons=result.reasons,
    )
    return result


class _NullBus:
    """Drafting emits nothing.

    `generate_invoice` does not publish — issuing does — so this is never
    called. It exists because the service takes a bus, and passing the real
    one from a background job would be a way for a future change to start
    emitting events from a scheduler without anyone noticing.
    """

    async def publish(self, envelope):  # pragma: no cover - defensive
        raise RuntimeError("month-end drafting does not publish events")


def _audit(session: AsyncSession):
    from platform_core.modules.audit.service import AuditService

    return AuditService(session)
