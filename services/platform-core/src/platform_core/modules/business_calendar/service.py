"""Working days and financial periods (DEMO-020).

The application service over `models.py`. Two responsibilities that share a
module because they share a subject — the organization's calendar — and are
kept apart in the code because they are read by different callers:

* **the calendar** answers "does this dairy work on this day?", for the
  scheduler, delivery and collection operations;
* **the periods** answer "may this day still be written to?", for billing,
  settlement and anything that later posts money.

Every date that enters or leaves is a BUSINESS date, resolved through
`core/business_time.py` from the clock `core/timezones.py` picks. Nothing here
computes a date from `utcnow()` and nothing takes one from a client without
saying so.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_core.core.business_time import (
    business_today,
    month_bounds,
    previous_month_bounds,
)
from platform_core.core.db import utcnow
from platform_core.core.errors import ConflictError, NotFoundError, ValidationError
from platform_core.core.org_context import tenant_timezone
from platform_core.modules.business_calendar.models import (
    CALENDAR_DAY_KINDS,
    PERIOD_STATUSES,
    FinancialPeriod,
    OrganizationCalendarDay,
)

# --- DTOs ---------------------------------------------------------------------


class CalendarDayView(BaseModel):
    id: uuid.UUID
    day: date
    working: bool
    kind: str
    name: str


class CalendarDayInput(BaseModel):
    day: date
    working: bool = False
    kind: str = "holiday"
    name: str = Field(default="", max_length=120)


class FinancialPeriodView(BaseModel):
    id: uuid.UUID
    period_start: date
    period_end: date
    status: str
    label: str
    closed_at: str | None = None


class FinancialPeriodInput(BaseModel):
    period_start: date
    period_end: date
    label: str = Field(default="", max_length=60)


class CalendarView(BaseModel):
    """What the platform believes about this organization's calendar, now.

    Deliberately answers the questions an operator actually asks — what day is
    it *here*, which month am I in, is today a working day — rather than
    exposing the tables. `timezone` is included because every other field is
    meaningless without knowing which clock produced it.
    """

    timezone: str
    business_date: date
    is_working_day: bool
    month_start: date
    month_end: date
    previous_month_start: date
    previous_month_end: date
    current_period: FinancialPeriodView | None = None


@dataclass(frozen=True)
class PeriodGuard:
    """Why a write was refused, or that it was not."""

    allowed: bool
    period: FinancialPeriod | None = None


# --- the service --------------------------------------------------------------


class BusinessCalendarService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def timezone(self) -> str:
        return await tenant_timezone(self._session, self._tenant_id)

    async def today(self) -> date:
        """The organization's own calendar date, right now."""
        return business_today(await self.timezone())

    # --- calendar -------------------------------------------------------------

    async def is_working_day(self, day: date) -> bool:
        """Does this dairy work on `day`?

        The ordinary week is working; only a recorded exception changes that.
        That default is deliberate and it is why this milestone does not alter
        any existing behaviour: with no rows, every day is a working day, which
        is exactly what the platform did before the table existed.

        A weekly non-working pattern (every Sunday) is NOT modelled here. The
        delivery side already has one, per customer, in `delivery_plan.weekdays`
        — a dairy's round is a property of what each household agreed to, not
        of a single organization-wide week — and a second, coarser pattern
        would give two answers to one question.
        """
        entry = await self._session.scalar(
            select(OrganizationCalendarDay).where(
                OrganizationCalendarDay.tenant_id == self._tenant_id,
                OrganizationCalendarDay.day == day,
            )
        )
        return True if entry is None else entry.working

    async def calendar_days(self, date_from: date, date_to: date) -> list[CalendarDayView]:
        if date_to < date_from:
            raise ValidationError("the range ends before it begins")
        rows = await self._session.scalars(
            select(OrganizationCalendarDay)
            .where(
                OrganizationCalendarDay.tenant_id == self._tenant_id,
                OrganizationCalendarDay.day >= date_from,
                OrganizationCalendarDay.day <= date_to,
            )
            .order_by(OrganizationCalendarDay.day)
        )
        return [
            CalendarDayView(id=r.id, day=r.day, working=r.working, kind=r.kind, name=r.name)
            for r in rows
        ]

    async def set_calendar_day(
        self, payload: CalendarDayInput, *, actor_id: uuid.UUID | None = None
    ) -> CalendarDayView:
        """Record — or amend — one day's exception.

        Idempotent by (tenant, day): recording the same day twice updates it
        rather than colliding, because "the 15th is a holiday" is a statement
        about the 15th and a dairy may correct it.
        """
        if payload.kind not in CALENDAR_DAY_KINDS:
            raise ValidationError(f"unknown calendar day kind: {payload.kind}")
        existing = await self._session.scalar(
            select(OrganizationCalendarDay).where(
                OrganizationCalendarDay.tenant_id == self._tenant_id,
                OrganizationCalendarDay.day == payload.day,
            )
        )
        if existing is None:
            existing = OrganizationCalendarDay(
                tenant_id=self._tenant_id, day=payload.day, created_by=actor_id
            )
            self._session.add(existing)
        existing.working = payload.working
        existing.kind = payload.kind
        existing.name = payload.name
        await self._session.flush()
        return CalendarDayView(
            id=existing.id,
            day=existing.day,
            working=existing.working,
            kind=existing.kind,
            name=existing.name,
        )

    async def remove_calendar_day(self, day: date) -> None:
        entry = await self._session.scalar(
            select(OrganizationCalendarDay).where(
                OrganizationCalendarDay.tenant_id == self._tenant_id,
                OrganizationCalendarDay.day == day,
            )
        )
        if entry is None:
            raise NotFoundError("no calendar entry for that day")
        await self._session.delete(entry)
        await self._session.flush()

    # --- financial periods ----------------------------------------------------

    async def periods(self) -> list[FinancialPeriodView]:
        rows = await self._session.scalars(
            select(FinancialPeriod)
            .where(FinancialPeriod.tenant_id == self._tenant_id)
            .order_by(FinancialPeriod.period_start.desc())
        )
        return [_period_view(r) for r in rows]

    async def period_covering(self, day: date) -> FinancialPeriod | None:
        """The period `day` falls in, if the organization has declared one."""
        return await self._session.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.tenant_id == self._tenant_id,
                FinancialPeriod.period_start <= day,
                FinancialPeriod.period_end >= day,
            )
        )

    async def open_period(
        self, payload: FinancialPeriodInput, *, actor_id: uuid.UUID | None = None
    ) -> FinancialPeriodView:
        if payload.period_end < payload.period_start:
            raise ValidationError("the period ends before it begins")
        # Overlap is checked here rather than by a constraint so the refusal
        # can name the period it collides with. A dairy told only "conflict"
        # has to go looking for which month it already declared.
        clash = await self._session.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.tenant_id == self._tenant_id,
                FinancialPeriod.period_start <= payload.period_end,
                FinancialPeriod.period_end >= payload.period_start,
            )
        )
        if clash is not None:
            raise ConflictError(f"overlaps the period {clash.period_start} to {clash.period_end}")
        period = FinancialPeriod(
            tenant_id=self._tenant_id,
            period_start=payload.period_start,
            period_end=payload.period_end,
            label=payload.label,
            status="open",
        )
        self._session.add(period)
        await self._session.flush()
        return _period_view(period)

    async def close_period(
        self, period_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> FinancialPeriodView:
        period = await self._get_period(period_id)
        if period.status == "closed":
            raise ConflictError("the period is already closed")
        period.status = "closed"
        period.closed_at = utcnow()
        period.closed_by = actor_id
        await self._session.flush()
        return _period_view(period)

    async def reopen_period(
        self, period_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> FinancialPeriodView:
        """Deliberately possible, deliberately explicit.

        A period closed by mistake on the wrong month would otherwise be
        unbillable forever, which is a worse failure than the one closing
        prevents. It is a separate permission and it clears the closure
        record, so a reopened period never looks like one that was never shut.
        """
        period = await self._get_period(period_id)
        if period.status == "open":
            raise ConflictError("the period is already open")
        period.status = "open"
        period.closed_at = None
        period.closed_by = None
        await self._session.flush()
        return _period_view(period)

    async def _get_period(self, period_id: uuid.UUID) -> FinancialPeriod:
        period = await self._session.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.id == period_id,
                FinancialPeriod.tenant_id == self._tenant_id,
            )
        )
        if period is None:
            # Another tenant's period is a 404, never a 403 — the platform rule.
            raise NotFoundError("financial period not found")
        return period

    # --- the guard ------------------------------------------------------------

    async def check_open(self, day: date) -> PeriodGuard:
        """May a business date still be written to?

        Permissive when nothing has been declared, which is what makes this
        safe to introduce into an already-running platform: an organization
        with no periods has none closed, so every date passes and no existing
        behaviour changes. The guard only ever refuses a day somebody
        deliberately shut.
        """
        period = await self.period_covering(day)
        return PeriodGuard(allowed=period is None or period.status != "closed", period=period)

    async def assert_open(self, day: date, *, operation: str) -> None:
        """`check_open`, as a refusal.

        The message names the period and the operation, because the person who
        meets this is usually not the person who closed the month.
        """
        guard = await self.check_open(day)
        if not guard.allowed and guard.period is not None:
            raise ConflictError(
                f"{operation} refused: {day} falls in the closed financial period "
                f"{guard.period.period_start} to {guard.period.period_end}"
            )

    # --- the overview ---------------------------------------------------------

    async def overview(self) -> CalendarView:
        timezone = await self.timezone()
        today = business_today(timezone)
        month_start, month_end = month_bounds(today)
        previous_start, previous_end = previous_month_bounds(today)
        current = await self.period_covering(today)
        return CalendarView(
            timezone=timezone,
            business_date=today,
            is_working_day=await self.is_working_day(today),
            month_start=month_start,
            month_end=month_end,
            previous_month_start=previous_start,
            previous_month_end=previous_end,
            current_period=_period_view(current) if current else None,
        )


def _period_view(period: FinancialPeriod) -> FinancialPeriodView:
    return FinancialPeriodView(
        id=period.id,
        period_start=period.period_start,
        period_end=period.period_end,
        status=period.status,
        label=period.label,
        closed_at=period.closed_at.isoformat() if period.closed_at else None,
    )


__all__ = [
    "PERIOD_STATUSES",
    "BusinessCalendarService",
    "CalendarDayInput",
    "CalendarDayView",
    "CalendarView",
    "FinancialPeriodInput",
    "FinancialPeriodView",
    "PeriodGuard",
]
