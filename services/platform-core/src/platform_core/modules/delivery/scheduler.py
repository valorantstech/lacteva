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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from platform_core.core.business_time import zone
from platform_core.core.db import get_session_factory, utcnow
from platform_core.core.rls import platform_session, rebind_tenant
from platform_core.modules.business_calendar.service import WorkingDayResolver
from platform_core.modules.delivery.generation import (
    GenerationResult,
    RoundScope,
    generate_for_day,
)
from platform_core.modules.delivery.models import MAX_ATTEMPTS, DeliveryGenerationRun

log = structlog.get_logger("delivery.scheduler")

#: Statuses that mean "this business date is settled — do not run it again".
#: `holiday` joins `success` because both are answers, not failures.
FINISHED_STATUSES = ("success", "holiday")


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
    * **a day the CALENDAR suppressed is finished too** (DEMO-022). A holiday
      is a final answer about the day, not a failure to retry — without this
      the loop would re-ask three times and then give up, which reads like a
      broken scheduler rather than a closed dairy.
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
    if last.status in FINISHED_STATUSES:
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
    route_scopes: RouteScopeProvider | None = None,
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

        # DEMO-022: the AUTOMATIC path resolves the calendar; the manual
        # endpoint does not, and that asymmetry is the milestone's boundary.
        # An operator asking for a round on a declared holiday knows something
        # the calendar does not; the scheduler is nobody and does not.
        resolver = WorkingDayResolver(session, tenant.id, day)
        run, _result = await record_run(
            session,
            tenant_id=tenant.id,
            day=day,
            trigger=trigger,
            label=tenant.slug,
            now=now,
            is_working=resolver.is_working,
            # DEMO-036: handed the same way `is_working` is — a callable that
            # answers "which routes has this dairy planned for this day?", so
            # this module still knows nothing about routes.
            route_scopes=(
                (lambda: route_scopes(session, tenant.id, day))
                if route_scopes is not None
                else None
            ),
        )
        return run


async def _run_for(
    session: AsyncSession, tenant_id: uuid.UUID, day: date
) -> DeliveryGenerationRun | None:
    return await session.scalar(
        select(DeliveryGenerationRun).where(
            DeliveryGenerationRun.tenant_id == tenant_id,
            DeliveryGenerationRun.business_date == day,
        )
    )


async def _claim(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    day: date,
    trigger: str,
    now: datetime,
) -> DeliveryGenerationRun | None:
    """Take ownership of one tenant's business date, or return None.

    Atomic, because SELECT-then-INSERT is exactly the pattern this codebase
    refuses everywhere else and DEMO-018 caught it here in production: four
    uvicorn workers all looked, all found nothing, and all proceeded.

    Two mechanisms, both already the platform's conventions:

    * a first claim is `INSERT … ON CONFLICT DO NOTHING` against
      `uq_generation_run_tenant_date` — the winner is whoever the database
      says inserted a row;
    * a re-claim after a failure is a **CAS update** (`UPDATE … WHERE status =
      'failed'` with a rowcount check), which is how this platform does
      concurrency everywhere rather than `SELECT FOR UPDATE`.

    A MANUAL run always takes the day, even from a successful row: an operator
    who presses the button has asked for it, and DEMO-016's constraint means
    the worst case is a round that finds everything already there.
    """
    dialect = session.get_bind().dialect.name
    maker = postgres_insert if dialect == "postgresql" else sqlite_insert
    row_id = uuid.uuid4()
    inserted = await session.execute(
        maker(DeliveryGenerationRun)
        .values(
            id=row_id,
            tenant_id=tenant_id,
            business_date=day,
            status="running",
            trigger=trigger,
            plans_due=0,
            created=0,
            already_present=0,
            not_due=0,
            inactive_customers=0,
            attempts=1,
            error="",
            started_at=now,
            duration_ms=0,
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "business_date"])
    )
    if inserted.rowcount:
        return await _run_for(session, tenant_id, day)

    existing = await _run_for(session, tenant_id, day)
    if existing is None:  # pragma: no cover - the conflict says it exists
        return None
    claimable = ("failed",) if trigger == "scheduler" else ("failed", "success", "running")
    if existing.status not in claimable:
        return None
    if trigger == "scheduler" and existing.attempts >= MAX_ATTEMPTS:
        return None
    won = await session.execute(
        update(DeliveryGenerationRun)
        .where(
            DeliveryGenerationRun.id == existing.id,
            DeliveryGenerationRun.status == existing.status,
        )
        .values(
            status="running",
            trigger=trigger,
            attempts=DeliveryGenerationRun.attempts + 1,
            started_at=now,
            error="",
        )
    )
    if not won.rowcount:
        return None
    # Expire and re-read rather than `refresh`. The CAS above is a Core
    # UPDATE, so the ORM's copy of this row is stale the moment it lands —
    # and a stale copy with pending changes makes the next flush raise
    # `StaleDataError` about a row it thinks vanished. Found by the four-way
    # concurrency test written for this defect.
    session.expire_all()
    return await _run_for(session, tenant_id, day)


async def _generate_the_day(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    day: date,
    is_working: Callable[[uuid.UUID | None], Awaitable[bool]] | None,
    route_scopes: Callable[[], Awaitable[list[RoundScope]]] | None,
) -> GenerationResult:
    """The day's round — route by route where routes exist (DEMO-036).

    **This runs INSIDE `record_run`'s claim, and that is the whole point.**
    DEMO-035 found that calling `record_run` per ROUTE makes the first route
    claim the tenant's date and every later route silently generate nothing.
    The fix is not to abandon the claim — it is what stops two scheduler
    workers doing the same dairy's day twice — but to claim the day ONCE and
    iterate routes underneath it. One claim per tenant-day, many routes within.

    **No routes means no change.** A tenant that has not adopted routes gets
    exactly the call it got before this function existed, byte for byte, which
    is what makes route adoption optional rather than a migration.

    A route that raises does NOT let the others report success by omission: the
    exception propagates, `record_run` marks the day `failed` with the route's
    label in the message, and the attempt is retried. Recording a partial round
    as a success is the failure mode this milestone must not have — an operator
    reading `success` has no reason to look for the round that never went out.
    """
    scopes = await route_scopes() if route_scopes is not None else []
    if not scopes:
        # The pre-DEMO-036 path, unchanged.
        return await generate_for_day(
            session, tenant_id=tenant_id, day=day, actor_id=None, is_working=is_working
        )

    totals = GenerationResult(
        business_date=day,
        due=0,
        created=0,
        already_present=0,
        not_due=0,
        inactive_customers=0,
        skipped_holiday=0,
    )
    for scope in scopes:
        try:
            result = await generate_for_day(
                session,
                tenant_id=tenant_id,
                day=day,
                actor_id=None,
                is_working=is_working,
                customer_ids=set(scope.customer_ids),
                slot=scope.slot,
            )
        except Exception as exc:
            # Named, so the failure says WHICH round did not go out. Re-raised
            # rather than swallowed: a day with one broken route is a failed
            # day, not a successful one with a footnote.
            raise RuntimeError(f"route {scope.label!r} failed to generate: {exc}") from exc
        totals = GenerationResult(
            business_date=day,
            due=totals.due + result.due,
            created=totals.created + result.created,
            already_present=totals.already_present + result.already_present,
            not_due=totals.not_due + result.not_due,
            inactive_customers=totals.inactive_customers + result.inactive_customers,
            skipped_holiday=totals.skipped_holiday + result.skipped_holiday,
        )
    return totals


async def record_run(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    day: date,
    trigger: str,
    label: str = "",
    now: datetime | None = None,
    is_working: Callable[[uuid.UUID | None], Awaitable[bool]] | None = None,
    route_scopes: Callable[[], Awaitable[list[RoundScope]]] | None = None,
) -> tuple[DeliveryGenerationRun | None, GenerationResult]:
    """Generate one day's round and record what happened, on a caller's session.

    Returns BOTH, because they answer different questions and DEMO-018 found
    them conflated:

    * the `GenerationResult` is what THIS invocation did — a second run
      reports `created: 0`, which is how a caller knows idempotency held;
    * the run RECORD is what the DAY did — `created` accumulates across
      attempts, because an operator reading it asks "did the round go out?"
      and the answer is about the day, not about one attempt.

    Returning one and calling it both is what made a four-worker production
    deployment report a day as having generated nothing.

    The one implementation both paths use. The scheduler calls it with a
    session it opened and bound itself; the manual endpoint calls it with the
    request's session, already bound to the caller's tenant by the ordinary
    middleware. §9 asks for manual generation to remain available and
    DEMO-016's idempotency to keep both safe — sharing this function is how
    "both are safe" stops being a claim about two code paths.
    """
    now = now or utcnow()
    run = await _claim(session, tenant_id=tenant_id, day=day, trigger=trigger, now=now)
    if run is None:
        # Another worker owns this day. DEMO-018 found this in production on
        # the first real run: uvicorn runs FOUR workers, so four scheduler
        # loops woke together and all four generated. The deliveries were
        # safe — the unique constraint saw to that — but the last writer's
        # `created: 0` overwrote the first's `created: 16`, so the record said
        # a day had generated nothing when it had generated everything.
        #
        # Losing the claim is now a return, not a race to redo the work.
        existing = await _run_for(session, tenant_id, day)
        log.info(
            "delivery_generation_already_claimed",
            tenant=label or str(tenant_id),
            business_date=str(day),
        )
        return existing, GenerationResult(
            business_date=day,
            due=existing.plans_due if existing else 0,
            created=0,
            already_present=existing.plans_due if existing else 0,
            not_due=existing.not_due if existing else 0,
            inactive_customers=existing.inactive_customers if existing else 0,
        )
    created_before = run.created

    started = time.monotonic()
    try:
        result = await _generate_the_day(
            session,
            tenant_id=tenant_id,
            day=day,
            is_working=is_working,
            route_scopes=route_scopes,
        )
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
        return failed, GenerationResult(
            business_date=day,
            due=0,
            created=0,
            already_present=0,
            not_due=0,
            inactive_customers=0,
        )

    # DEMO-022: a day on which the calendar suppressed EVERY due plan and
    # nothing was created is recorded as `holiday` rather than `success`.
    # Both are finished — neither is retried — but an operator asking why the
    # round is empty gets the reason from the status rather than having to
    # infer it from three zeroes.
    run.status = (
        "holiday"
        if result.skipped_holiday > 0 and result.created == 0 and result.due == 0
        else "success"
    )
    run.skipped_holiday = result.skipped_holiday
    run.plans_due = result.due
    # ACCUMULATED across attempts, not assigned. A retry that creates the four
    # deliveries a failed attempt missed must show four created for the day,
    # not four for the attempt — an operator reads this row to answer "did the
    # round go out", and the answer is about the day.
    run.created = created_before + result.created
    run.already_present = result.already_present
    run.not_due = result.not_due
    run.inactive_customers = result.inactive_customers
    run.finished_at = utcnow()
    run.duration_ms = int((time.monotonic() - started) * 1000)
    try:
        await session.commit()
    except StaleDataError:
        # Another worker finished this day underneath us. The deliveries are
        # safe either way — that is the unique constraint's job — so losing
        # here is a return, not an error: re-read what the winner recorded and
        # report what THIS call did, which is nothing new.
        await session.rollback()
        await rebind_tenant(session, tenant_id)
        winner = await _run_for(session, tenant_id, day)
        log.info(
            "delivery_generation_superseded",
            tenant=label or str(tenant_id),
            business_date=str(day),
        )
        return winner, GenerationResult(
            business_date=day,
            due=result.due,
            created=0,
            already_present=result.due,
            not_due=result.not_due,
            inactive_customers=result.inactive_customers,
        )

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
    return run, result


#: How the scheduler is told about routes (DEMO-036).
#:
#: `(session, tenant_id, day) -> [RoundScope, …]`, empty when the dairy has no
#: routes — which is the fallback and the ordinary case. Supplied by the
#: composition point in `main.py`, never imported here: `logistics` depends on
#: `delivery`, so the reverse import would be a cycle, and DEMO-022 already
#: settled the shape of this problem by passing `is_working` in.
RouteScopeProvider = Callable[[AsyncSession, uuid.UUID, date], Awaitable[list[RoundScope]]]


async def run_once(
    *,
    generation_hour: int,
    now: datetime | None = None,
    route_scopes: RouteScopeProvider | None = None,
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
            run = await run_for_tenant(
                tenant,
                now=now,
                generation_hour=generation_hour,
                route_scopes=route_scopes,
            )
        except Exception:
            log.exception("delivery_scheduler_tenant_error", tenant=tenant.slug)
            continue
        if run is not None:
            runs.append(run)
        # DEMO-019 §8: the month's bills are DRAFTED on the same pass, in the
        # same tenant loop, rather than by a second scheduler. One loop that
        # asks each tenant "is anything due for you?" is the shape this
        # platform already has; a second one would be a second place to look
        # when a dairy's bills did not appear.
        try:
            await draft_month_end_for_tenant(tenant, now=now, generation_hour=generation_hour)
        except Exception:
            log.exception("month_end_drafting_error", tenant=tenant.slug)
    return runs


async def draft_month_end_for_tenant(
    tenant: Tenant, *, now: datetime | None = None, generation_hour: int
) -> None:
    """Draft last month's bills, once, on the first of the dairy's month.

    The same two questions the delivery round asks — is it past your
    generation hour, and has this already been done? — with the month's
    boundary in place of the day's. Idempotency comes from
    `generate_invoice` itself: a customer with a live invoice for the period
    is refused, so a second pass on the 1st drafts nothing and a pass on the
    5th drafts nothing.

    Deliberately only on the 1st. Drafting on any day of the month would mean
    the previous month's bill is redrafted every morning for a customer whose
    first attempt found nothing to bill, which is thirty pointless passes.
    """
    from platform_core.modules.billing.month_end import draft_month_end

    now = now or utcnow()
    today, hour = business_date_and_hour(now, tenant.timezone)
    if today.day != 1 or hour < generation_hour:
        return
    async with get_session_factory()() as session:
        await rebind_tenant(session, tenant.id)
        await draft_month_end(session, tenant_id=tenant.id, timezone=tenant.timezone)
        await session.commit()
