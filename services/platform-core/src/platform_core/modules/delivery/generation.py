"""Turning standing orders into a day's round (DEMO-016 §4, §5, §20).

A dairy with three hundred households does not type three hundred deliveries
every morning. It has three hundred standing orders and a round that goes out.
This is the thing that turns one into the other.

**Three properties, and each one is load-bearing.**

*Idempotent, at the database.* Running the generator twice must not deliver
twice, and the guard is the `uq_delivery_customer_date_slot` constraint that
has existed since DEMO-009 — `INSERT … ON CONFLICT DO NOTHING`, not a SELECT
followed by an INSERT. An application-level check has a window between the
look and the leap, and the one morning two operators press the button at once
is the morning it would matter. §5 asks for exactly this and says not to rely
only on application-level checks.

*Bulk.* One INSERT for the whole round, not one per customer. §20's example of
what not to write is `for customer in customers: create delivery`, and at
three hundred plans that is three hundred round trips before anyone has had
tea.

*Worth nothing until it happens.* Generated rows are `scheduled`, which is not
in `BILLABLE_STATUSES` — so a generated round carries 0.00 and appears on no
invoice until an operator confirms it. A generator that produced billable rows
would invoice a dairy's whole round every morning whether the milk arrived or
not, and would do it silently, and the first person to find out would be a
customer reading their bill.

**The business date is the dairy's**, resolved through the organization's
timezone (DEMO-014). Generating "today" at 00:30 IST must produce the Indian
day that has just begun, not the UTC day that is still yesterday — which is
§6, and the exact defect DEMO-015 found in the portal's date picker.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.db import utcnow
from platform_core.modules.customer.models import Customer, DeliveryPlan
from platform_core.modules.customer.schedule import delivers_on_weekday, quantity_for
from platform_core.modules.delivery.models import MilkDelivery

#: How many rows go into one INSERT. Large enough that a three-hundred-house
#: round is a single statement, small enough that a dairy with fifty thousand
#: plans does not build one statement with fifty thousand parameter sets and
#: exhaust the driver's limits.
BATCH = 1_000


class GenerationResult(BaseModel):
    """What the generator did, in the terms an operator would ask.

    `created` and `already_present` are reported separately and that is the
    whole point of running it twice: the second run's `created: 0,
    already_present: 300` is the proof that idempotency held, and it is the
    number §23's browser journey checks.
    """

    business_date: date
    #: Plans whose schedule says they deliver today.
    due: int
    #: Rows this run actually inserted.
    created: int
    #: Due plans whose delivery already existed — generated earlier, or
    #: recorded by hand before the round went out. Not an error; the ordinary
    #: outcome of a second run.
    already_present: int
    #: Plans in date and active whose weekday mask excludes today, or whose
    #: pause covers it. Reported so "nothing generated" can be told apart from
    #: "nothing was due".
    not_due: int
    #: Plans skipped because the customer is no longer active. A suspended
    #: customer keeps their plan and stops receiving milk.
    inactive_customers: int


def _due_plans_query(tenant_id: uuid.UUID, day: date) -> Select:
    """Active, in-date, not-paused plans for one tenant.

    The weekday test is deliberately NOT in SQL. A seven-character mask
    indexed by `date.weekday()` is trivial in Python and would be a
    `substr(weekdays, ?, 1) = '1'` in SQL — unindexable, dialect-flavoured,
    and unreadable in a query plan. The date and status predicates do the
    narrowing that matters (they are what `ix_delivery_plan_generation`
    covers); the mask filters what survives.
    """
    return (
        select(DeliveryPlan, Customer.status)
        .join(Customer, Customer.id == DeliveryPlan.customer_id)
        .where(
            DeliveryPlan.tenant_id == tenant_id,
            DeliveryPlan.active.is_(True),
            DeliveryPlan.effective_from <= day,
            or_(DeliveryPlan.effective_to.is_(None), DeliveryPlan.effective_to >= day),
            # Not paused: either no pause is set, or today falls outside it.
            or_(
                DeliveryPlan.paused_from.is_(None),
                DeliveryPlan.paused_from > day,
                and_(DeliveryPlan.paused_to.is_not(None), DeliveryPlan.paused_to < day),
            ),
        )
        .order_by(DeliveryPlan.customer_id)
    )


def _insert_ignoring_conflicts(session: AsyncSession, rows: list[dict]):
    """`INSERT … ON CONFLICT DO NOTHING`, in whichever dialect is present.

    Both dialects support it and SQLAlchemy spells it differently for each, so
    this picks by the bind rather than by an environment flag — the tests run
    on SQLite and production runs on PostgreSQL, and the guarantee has to be
    the same one in both or the tests are testing something else.
    """
    dialect = session.get_bind().dialect.name
    maker = postgres_insert if dialect == "postgresql" else sqlite_insert
    statement = maker(MilkDelivery).values(rows)
    return statement.on_conflict_do_nothing(
        index_elements=["tenant_id", "customer_id", "delivery_date", "slot"]
    )


async def generate_for_day(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    day: date,
    actor_id: uuid.UUID | None,
) -> GenerationResult:
    """Produce one day's scheduled deliveries from the active standing orders.

    Reads every due plan once, builds the rows in memory, and inserts them in
    batches. Returns counts rather than the rows themselves: a round of three
    hundred is not something a caller wants serialised back, and the deliveries
    are readable through the ordinary delivery endpoints the moment this
    returns — which is §4's requirement that generated rows be normal rows.
    """
    due_rows = (await session.execute(_due_plans_query(tenant_id, day))).all()

    candidates: list[dict] = []
    not_due = 0
    inactive = 0
    for plan, customer_status in due_rows:
        if not delivers_on_weekday(plan.weekdays, day):
            not_due += 1
            continue
        if customer_status != "active":
            inactive += 1
            continue
        quantity = quantity_for(day, plan.default_quantity, plan.quantity_overrides)
        if quantity <= 0:
            # A weekday override of zero is how a plan says "not on Sundays"
            # without changing its mask. Nothing to deliver, nothing to
            # record — and emphatically not a zero-litre delivery, which would
            # sit on the round asking an operator to confirm nothing.
            not_due += 1
            continue
        candidates.append(
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "customer_id": plan.customer_id,
                "delivery_date": day,
                "slot": plan.slot,
                "product": plan.product,
                "quantity": quantity,
                "quantity_unit": plan.quantity_unit,
                "unit_price": Decimal(plan.unit_price),
                "currency": plan.currency,
                # Zero, and it stays zero until somebody says the milk arrived.
                # See BILLABLE_STATUSES.
                "amount": Decimal("0.00"),
                "status": "scheduled",
                "notes": "",
                "plan_id": plan.id,
                "invoice_id": None,
                "recorded_by": actor_id,
                "created_at": utcnow(),
                "updated_at": utcnow(),
            }
        )

    created = 0
    for start in range(0, len(candidates), BATCH):
        batch = candidates[start : start + BATCH]
        result = await session.execute(_insert_ignoring_conflicts(session, batch))
        # `rowcount` after ON CONFLICT DO NOTHING is the number actually
        # inserted, which is exactly the distinction this function exists to
        # report. Guard against a driver that declines to say (-1) by falling
        # back to counting, rather than reporting a negative round.
        created += result.rowcount if result.rowcount is not None and result.rowcount >= 0 else 0

    return GenerationResult(
        business_date=day,
        due=len(candidates),
        created=created,
        already_present=len(candidates) - created,
        not_due=not_due,
        inactive_customers=inactive,
    )


async def scheduled_count(session: AsyncSession, *, tenant_id: uuid.UUID, day: date) -> int:
    """How many of the day's generated deliveries are still waiting.

    One aggregate. Used by the daily report to say `284 completed, 8 skipped,
    8 pending` — which is §13's whole requirement, and the number an operator
    checks before going home.
    """
    return (
        await session.scalar(
            select(func.count())
            .select_from(MilkDelivery)
            .where(
                MilkDelivery.tenant_id == tenant_id,
                MilkDelivery.delivery_date == day,
                MilkDelivery.status == "scheduled",
            )
        )
    ) or 0
