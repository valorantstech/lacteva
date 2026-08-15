"""The organization's calendar and its financial periods (DEMO-020).

Two tables, one idea: **which days a dairy works, and which stretches of those
days are still open to change.**

Everything about *what day it is* already existed and is not repeated here.
`core/business_time.py` converts an instant to a business date and a business
date to a UTC window; `core/timezones.py` decides whose clock that is
(organization, optionally overridden per centre, never the user's). This module
adds the two facts those functions cannot derive, because they are decisions
somebody made rather than arithmetic:

* a **calendar day** that is not what the weekly pattern would suggest — a
  public holiday, a shutdown, or a Sunday somebody chose to work;
* a **financial period** that has been closed, after which the operational
  machinery must stop writing into it.

Both are tenant-owned — they carry `tenant_id`, so `core/rls.py` derives them
into the protected set from the metadata and the policies are installed by the
RLS machinery rather than by hand.

**What this deliberately is not.** Not an HR calendar: no leave, no shifts, no
per-person anything. Not an accounting system: a period has two dates and a
status, and closing one does not post a journal, roll a balance or compute a
trial balance. The work order asked for the smallest foundation the later
things can stand on, and the temptation in both directions is what makes
calendars into ERPs.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from platform_core.core.db import Base, IdMixin, utcnow

#: Why a day departs from the ordinary week. Descriptive, not behavioural —
#: nothing branches on this string, and the `working` flag is what any rule
#: actually reads. Kept because "closed" and "holiday" mean different things
#: to the person reading a calendar, and collapsing them loses that.
CALENDAR_DAY_KINDS = (
    "holiday",  # a public or organizational holiday
    "closure",  # an unplanned or operational shutdown
    "working",  # an exception the OTHER way: open on a day normally closed
)

#: A period is open or it is closed. There is no third state, and resisting one
#: is the point: "locked", "provisional" and "under review" are the states that
#: turn a boundary into a workflow engine.
PERIOD_STATUSES = ("open", "closed")


class OrganizationCalendarDay(Base, IdMixin):
    """One dated exception to the organization's ordinary working week.

    Organization-wide by construction. A centre that shuts on its own already
    has `center_calendar_entry` (DEMO-005), which the readiness engine reads;
    this is the level above it, for the days on which the whole dairy stops.
    The two are deliberately separate tables rather than one with a nullable
    centre: they answer to different owners, are read by different rules, and
    merging them would have made one module query another's rows.
    """

    __tablename__ = "organization_calendar_day"
    __table_args__ = (
        # One ruling per day per organization. A second row for the same day
        # is a contradiction, not an addition.
        UniqueConstraint("tenant_id", "day", name="uq_org_calendar_tenant_day"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    #: **The only field a rule may branch on.** `False` means the dairy does
    #: not work this day; `True` records the opposite exception, a day worked
    #: that normally would not be. Explicit rather than inferred from `kind`,
    #: so that adding a kind can never silently change whether a day is worked.
    working: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(20), default="holiday")
    #: What to call it on a screen. Free text, and optional — a shutdown with
    #: no explanation is still a shutdown.
    name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class FinancialPeriod(Base, IdMixin):
    """A stretch of business dates that may or may not still be written into.

    The dates are **business dates** — the organization's own calendar, from
    `business_time.month_bounds` — never UTC's. For an Indian dairy, August is
    2026-08-01 to 2026-08-31 on the dairy's clock, which begins at 18:30 UTC on
    31 July and ends at 18:30 UTC on 31 August. Storing the local dates and
    converting at the edges is what keeps that true; storing a UTC instant pair
    would bake in the conversion and lose five and a half hours at both ends.

    Inclusive at both ends, matching how a person says "the first to the
    thirty-first" and how `range_bounds` already reads a reporting window.
    """

    __tablename__ = "financial_period"
    __table_args__ = (
        # A tenant may not have two periods starting on the same day. Full
        # overlap prevention is enforced in the service, where the error can
        # say WHICH period it collides with — a constraint can only say no.
        UniqueConstraint("tenant_id", "period_start", name="uq_financial_period_start"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    #: `open` | `closed`. See `PERIOD_STATUSES`.
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    #: "August 2026". Human-facing only; the dates are the truth.
    label: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    #: Who closed it and when — the two questions asked first when somebody
    #: finds they cannot post to a month.
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
