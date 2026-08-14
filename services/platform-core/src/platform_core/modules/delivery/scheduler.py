"""The round goes out without anybody pressing a button (DEMO-017).

DEMO-016 made generation idempotent and left it on demand. This makes it
automatic, and it does so by adding a **fifth background loop** beside the four
the platform already runs — relay, consumers, idempotency sweep, health
sampling — rather than a cron container, a systemd timer, an AWS EventBridge
rule, or a scheduling framework.

**Why that mechanism.** The alternatives each buy something and cost more than
it is worth here:

* *cron / systemd on the host* — needs a credential to call the API with, and
  a credential that generates a dairy's day is a credential sitting on a box.
  It also lives outside the deployment unit, so a rollback moves the code and
  leaves the schedule behind.
* *EventBridge / a managed scheduler* — an AWS resource, recurring cost, and a
  second place to look when the round did not go out. §17 of the standing
  instructions and this milestone both say not to add resources casually.
* *a scheduling framework (Celery beat, APScheduler)* — a dependency, a broker,
  and a second definition of "what runs when" for one job that runs once a day.

The loop costs nothing new: it is registered in `core/workers`, so a scheduler
that dies is already reported by the `background_workers` health probe that
DEMO-OBS built — which is §11's visibility requirement, met by construction.

**The loop polls; it does not sleep until 05:00.** It wakes every minute and
asks each tenant a question it can answer from the tenant's own clock: *is it
past the generation hour where you are, and has today's round been made?* That
is what makes per-tenant timezones fall out for free (§6) — a single cron
expression cannot be 05:00 in Bengaluru and 05:00 in Nairobi at once, and this
never has to be. It is also what makes a restart harmless: the question is
answered from the database, not from a timer that was lost.

**Missed days are not backfilled** (§8). The question is always about the
CURRENT business date. If the platform was down all of Tuesday, Wednesday's
loop generates Wednesday — because a delivery record is a claim that milk
moved, and inventing Tuesday's round on Wednesday would put a day of milk
nobody carried onto a customer's bill.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.business_time import zone
from platform_core.core.db import get_session_factory, utcnow
from platform_core.core.rls import platform_session, rebind_tenant
from platform_core.modules.delivery.generation import generate_for_day
from platform_core.modules.delivery.models import MAX_ATTEMPTS, DeliveryGenerationRun

log = structlog.get_logger("delivery.scheduler")


@dataclass(frozen=True)
class Tenant:
    """The two things the scheduler needs to know about an organization."""

    id: uuid.UUID
    slug: str
    timezone: str


def business_date_and_hour(now: datetime, timezone: str | None) -> tuple[date, int]:
    """Where this tenant is in its own day.

    Returns the local calendar date and the local hour — the only two things
    the decision below depends on, and both of them the tenant's rather than
    UTC's.
    """
    local = now.astimezone(zone(timezone))
    return local.date(), local.hour


def should_run(
    *,
    now: datetime,
    timezone: str | None,
    generation_hour: int,
    last: DeliveryGenerationRun | None,
) -> date | None:
    """The business date to generate, or None to do nothing yet.

    Pure: no session, no clock of its own, no I/O. Every rule the scheduler has
    is in these few lines, where they can be tested against a fabricated clock
    rather than by waiting until five in the morning.

    The rules, and why each one:

    * **before the generation hour, do nothing.** A round generated at
      midnight would sit on an operator's screen for five hours looking like
      work already done.
    * **a successful day is finished.** This is what stops a loop that wakes
      every minute from re-running a completed round sixty times an hour.
    * **a failed day is retried, up to `MAX_ATTEMPTS`.** The failures worth
      retrying are transient; a fourth attempt means something retrying will
      not fix, and the row stays `failed` and visible for a person.
    * **a `running` row is left alone.** Another worker — or this one before a
      restart — has it. If that worker died mid-run the row is stale, and the
      next business date will move past it; the deliveries themselves are
      protected by their own constraint either way.
    * **an older row never causes a backfill.** The answer is always today's
      date or nothing.
    """
    today, hour = business_date_and_hour(now, timezone)
    if hour < generation_hour:
        return None
    if last is None or last.business_date != today:
        return today
    if last.status == "success":
        return None
    if last.status == "running":
        return None
    return today if last.attempts < MAX_ATTEMPTS else None


async def active_tenants() -> list[Tenant]:
    """Every organization the scheduler should consider.

    Read under the PLATFORM binding, because "list the tenants" is
    definitionally cross-tenant — the same reason the relay and the consumer
    runner use it. Everything after this point runs inside one tenant's own
    binding (see `run_for_tenant`), so this is the only cross-tenant read in
    the whole scheduler.
    """
    from platform_core.modules.organization.models import Organization

    async with platform_session("delivery scheduler: which tenants have a day today") as session:
        rows = (
            await session.execute(
                select(Organization.id, Organization.slug, Organization.timezone).where(
                    Organization.status == "active"
                )
            )
        ).all()
    return [Tenant(id=r[0], slug=r[1], timezone=r[2]) for r in rows]


async def _last_run(session: AsyncSession, tenant_id: uuid.UUID) -> DeliveryGenerationRun | None:
    return await session.scalar(
        select(DeliveryGenerationRun)
        .where(DeliveryGenerationRun.tenant_id == tenant_id)
        .order_by(DeliveryGenerationRun.business_date.desc())
        .limit(1)
    )


async def run_for_tenant(
    tenant: Tenant,
    *,
    now: datetime | None = None,
    generation_hour: int,
    trigger: str = "scheduler",
    force_date: date | None = None,
) -> DeliveryGenerationRun | None:
    """Generate one tenant's round, if it is due, and record what happened.

    **Runs inside the tenant's OWN binding.** `rebind_tenant` sets both the
    context variable and the PostgreSQL setting the row-level policies read,
    so the generation query is filtered by the database exactly as it would be
    for a request from that tenant's own manager. The scheduler is not
    privileged here and does not need to be — which is §12, and the reason
    "the scheduler generated another tenant's deliveries" is not a failure
    this design can have.

    Returns the run row, or None when nothing was due.
    """
    now = now or utcnow()
    async with get_session_factory()() as session:
        await rebind_tenant(session, tenant.id)

        last = await _last_run(session, tenant.id)
        day = force_date or should_run(
            now=now,
            timezone=tenant.timezone,
            generation_hour=generation_hour,
            last=last,
        )
        if day is None:
            return None

        return await record_run(
            session,
            tenant_id=tenant.id,
            day=day,
            trigger=trigger,
            label=tenant.slug,
            now=now,
        )


async def record_run(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    day: date,
    trigger: str,
    label: str = "",
    now: datetime | None = None,
) -> DeliveryGenerationRun:
    """Generate one day's round and record what happened, on a caller's session.

    The one implementation both paths use. The scheduler calls it with a
    session it opened and bound itself; the manual endpoint calls it with the
    request's session, already bound to the caller's tenant by the ordinary
    middleware. §9 asks for manual generation to remain available and
    DEMO-016's idempotency to keep both safe — sharing this function is how
    "both are safe" stops being a claim about two code paths.
    """
    now = now or utcnow()
    existing = await session.scalar(
        select(DeliveryGenerationRun).where(
            DeliveryGenerationRun.tenant_id == tenant_id,
            DeliveryGenerationRun.business_date == day,
        )
    )
    if existing is None:
        run = DeliveryGenerationRun(
            tenant_id=tenant_id,
            business_date=day,
            status="running",
            trigger=trigger,
            started_at=now,
        )
        session.add(run)
    else:
        # Reuse the row and count the attempt, so an operator can see that a
        # green day took three tries.
        run = existing
        run.status = "running"
        run.trigger = trigger
        run.attempts += 1
        run.started_at = now
        run.error = ""
    # Flush the claim before the work. Two workers racing here both write
    # `running` and one loses on the unique constraint — but even if both
    # proceeded the delivery constraint makes the outcome identical. The claim
    # is for legibility and load, not for safety.
    await session.flush()

    started = time.monotonic()
    try:
        result = await generate_for_day(session, tenant_id=tenant_id, day=day, actor_id=None)
    except Exception as exc:
        # The failure has to be recorded in a transaction of its own: the
        # caller's transaction is about to be rolled back with the error in it.
        await session.rollback()
        await rebind_tenant(session, tenant_id)
        failed = await session.scalar(
            select(DeliveryGenerationRun).where(
                DeliveryGenerationRun.tenant_id == tenant_id,
                DeliveryGenerationRun.business_date == day,
            )
        )
        if failed is None:
            # The claim itself was rolled back — record the attempt anyway, or
            # a failure that happens on a tenant's first ever run leaves no
            # trace at all.
            failed = DeliveryGenerationRun(
                tenant_id=tenant_id, business_date=day, trigger=trigger, started_at=now
            )
            session.add(failed)
        failed.status = "failed"
        failed.error = str(exc)[:500]
        failed.finished_at = utcnow()
        failed.duration_ms = int((time.monotonic() - started) * 1000)
        await session.commit()
        log.warning(
            "delivery_generation_failed",
            tenant=label or str(tenant_id),
            business_date=str(day),
            attempts=failed.attempts,
            error=str(exc)[:200],
        )
        return failed

    run.status = "success"
    run.plans_due = result.due
    run.created = result.created
    run.already_present = result.already_present
    run.not_due = result.not_due
    run.inactive_customers = result.inactive_customers
    run.finished_at = utcnow()
    run.duration_ms = int((time.monotonic() - started) * 1000)
    await session.commit()

    log.info(
        "delivery_generation_completed",
        tenant=label or str(tenant_id),
        business_date=str(day),
        due=result.due,
        created=result.created,
        already_present=result.already_present,
        duration_ms=run.duration_ms,
        trigger=trigger,
    )
    return run


async def run_once(
    *, generation_hour: int, now: datetime | None = None
) -> list[DeliveryGenerationRun]:
    """One pass over every active tenant.

    A tenant that raises does not stop the pass: the whole point of processing
    tenants independently (§6) is that one dairy's bad day is not every
    dairy's. `run_for_tenant` already records its own failure, so this only
    has to keep going.
    """
    runs: list[DeliveryGenerationRun] = []
    for tenant in await active_tenants():
        try:
            run = await run_for_tenant(tenant, now=now, generation_hour=generation_hour)
        except Exception:
            log.exception("delivery_scheduler_tenant_error", tenant=tenant.slug)
            continue
        if run is not None:
            runs.append(run)
    return runs
