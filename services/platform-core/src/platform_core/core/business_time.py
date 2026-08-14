"""What "today" means to a dairy (DEMO-013 §8, §9).

Storage stays UTC. Every timestamp column is `DateTime(timezone=True)`,
`utcnow()` is still how a row is stamped, and none of that changes — a
canonical instant is the only thing that survives a server move, a restore
into another region, or two tenants in different zones sharing a database.

What changes is INTERPRETATION. A day is not an interval of UTC; it is an
interval of somebody's local calendar, and which somebody is a business fact:

* a delivery round at 05:00 in Bengaluru is 23:30 UTC the day BEFORE, so a
  platform that asks UTC what day it is files that round under yesterday and
  bills it in the wrong month;
* the same round in Nairobi is 02:00 UTC the same day, which is why this has
  never bitten the Kenyan demo and would have bitten the first Indian customer
  on their first morning.

DEMO-012 found the reporting side of this and recorded it rather than deciding
it, because the answer belongs to the platform and not to one client. This
module is the decision: **the organization's timezone is authoritative for
business dates.** Not the server's — it is UTC and must stay UTC. Not the
browser's or the handset's — a rider crossing a border, or a phone left on the
wrong setting, must not move a dairy's accounting day.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from platform_core.core.db import as_utc, utcnow

#: What a tenant gets when it has no timezone: the storage timezone. Behaves
#: exactly as the platform did before DEMO-013, so an organization that has
#: not been given a zone is unchanged rather than quietly shifted.
FALLBACK_TIMEZONE = "UTC"


def zone(timezone_name: str | None) -> ZoneInfo:
    """An IANA zone, or UTC.

    Tolerant on purpose. A bad zone name is caught at the boundary where it is
    SET (`core/locales.resolve`), so by the time a report is being drawn the
    only way to get here with a broken value is a hand-edited row — and the
    right response to that is a report in UTC, not a 500 in front of a dairy
    manager who cannot fix it.
    """
    try:
        return ZoneInfo(timezone_name or FALLBACK_TIMEZONE)
    except Exception:
        return ZoneInfo(FALLBACK_TIMEZONE)


def business_today(timezone_name: str | None, *, now: datetime | None = None) -> date:
    """The calendar date it is *for this organization*, right now."""
    instant = now or utcnow()
    return as_utc(instant).astimezone(zone(timezone_name)).date()


def business_date_of(instant: datetime, timezone_name: str | None) -> date:
    """Which business day a stored instant belongs to."""
    return as_utc(instant).astimezone(zone(timezone_name)).date()


def day_bounds(day: date, timezone_name: str | None) -> tuple[datetime, datetime]:
    """The UTC half-open interval `[start, end)` covering one local day.

    Half-open, and that is the whole point: `[00:00, next 00:00)` has no gap
    and no overlap, so a delivery at exactly midnight belongs to exactly one
    day. An inclusive end (`<= 23:59:59`) loses the last second, and a
    `23:59:59.999999` end loses less but still loses — on a table timestamped
    to microseconds, "less wrong" is still a lost row and an unbillable
    delivery.

    Built by localizing midnight rather than by adding 24 hours to the start,
    because a day is not always 24 hours long: on a DST transition it is 23 or
    25. None of the currently supported zones observe DST — India, Kenya, the
    Gulf and East Africa do not — but Europe/London does, it is in the
    registry, and arithmetic that is only correct for the countries we happen
    to have today is the coupling this milestone exists to remove.
    """
    tz = zone(timezone_name)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def range_bounds(
    date_from: date, date_to: date, timezone_name: str | None
) -> tuple[datetime, datetime]:
    """The UTC interval covering an inclusive range of local days.

    Inclusive in the API's terms — `date_from=1st, date_to=31st` means the
    whole month, which is what a person means — and half-open in UTC terms.
    """
    start, _ = day_bounds(date_from, timezone_name)
    _, end = day_bounds(date_to, timezone_name)
    return start, end


def month_bounds(day: date, timezone_name: str | None) -> tuple[date, date]:
    """The local calendar month containing `day`, as inclusive local dates.

    A billing period is a month of the dairy's calendar, not of UTC's.
    """
    first = day.replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return first, next_month - timedelta(days=1)


def format_in_zone(instant: datetime, timezone_name: str | None) -> str:
    """A stored instant, written in the organization's own clock.

    ISO 8601 with the offset kept, so the reader can see that 04:30+05:30 and
    23:00Z are the same moment rather than having to trust it.
    """
    return as_utc(instant).astimezone(zone(timezone_name)).isoformat()
