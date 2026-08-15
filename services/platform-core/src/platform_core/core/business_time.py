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

from sqlalchemy import func

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


def month_bounds(day: date) -> tuple[date, date]:
    """The calendar month containing `day`, as inclusive dates.

    A billing period is a month of the dairy's calendar, not of UTC's — so
    `day` must already BE a business date, from `business_today()` or
    `business_date_of()`. Pure calendar arithmetic from there; no zone is
    involved, because the conversion has already happened.

    DEMO-020 removed a `timezone_name` parameter this function never read. It
    was inert and it invited exactly one mistake: `month_bounds(utcnow().date(),
    tz)` reads like it converts, converts nothing, and yields UTC's month under
    a local-looking name. For an Indian dairy in the first five and a half
    hours of the 1st that is the PREVIOUS month — the whole of the wrong
    month's billing. A parameter that cannot affect the answer must not be in
    the signature.
    """
    first = day.replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return first, next_month - timedelta(days=1)


def previous_month_bounds(day: date) -> tuple[date, date]:
    """The month before the one containing `day`, as inclusive dates.

    `day` is a business date. Month-end billing asks this question every 1st,
    and asking it by subtracting thirty days gets February wrong.
    """
    first, _ = month_bounds(day)
    return month_bounds(first - timedelta(days=1))


def business_year(timezone_name: str | None, *, now: datetime | None = None) -> int:
    """The year it is *for this organization*, right now.

    Separate from `business_today().year` only so that the call site reads as
    a decision rather than an accident. It is the one a document series needs:
    a receipt handed over at 04:00 on 1 January in Bengaluru is a January
    receipt, and UTC still says December for another ninety minutes.
    """
    return business_today(timezone_name, now=now).year


def format_in_zone(instant: datetime, timezone_name: str | None) -> str:
    """A stored instant, written in the organization's own clock.

    ISO 8601 with the offset kept, so the reader can see that 04:30+05:30 and
    23:00Z are the same moment rather than having to trust it.
    """
    return as_utc(instant).astimezone(zone(timezone_name)).isoformat()


# --- the same rule, inside SQL (DEMO-019) ------------------------------------


def local_date_sql(column, timezone_name: str | None, dialect: str):
    """A stored UTC timestamp, bucketed by the ORGANIZATION's calendar date.

    Everything above answers "which local day is this instant?" in Python. A
    report that GROUPS BY day has to ask the same question inside SQL, and
    until DEMO-019 the reporting module asked a different one — `date(col)`,
    which truncates in UTC. Its window was already local, so a collection
    recorded after local midnight fell inside the range and landed on the
    wrong bucket: the chart disagreed with the total above it.

    **PostgreSQL gets the native operation.** `timezone(tz, col)` on a
    `timestamptz` renders the instant in `tz` and hands back a naive local
    timestamp, reading the IANA database the server ships with — so it is
    correct across DST transitions and for any zone, not just the fixed-offset
    ones this platform happens to support today. (The paragraph that used to
    sit here described a two-step `timezone(tz, timezone('UTC', col))`, which
    is the draft the PostgreSQL test rejected; the reasoning below survived the
    fix and the summary above it did not. A docstring describing an expression
    the code does not use is a trap for the next reader — DEMO-020.)

    **SQLite gets a fixed offset**, because SQLite has no timezone database at
    all. That is a real difference and it is confined to the test stack, so
    the guarantee is proven where it runs: `test_business_date_sql_postgres.py`
    asserts the PostgreSQL expression against a real engine, including a zone
    that observes DST. This is the same split the platform already makes for
    RLS, which SQLite cannot express either.

    The offset is resolved for `now`, which is exact for every fixed-offset
    zone and can be an hour out for a DST zone inside a window that spans a
    transition — on SQLite only, in tests only.
    """
    if dialect == "postgresql":
        # ONE conversion, not two. `timezone(tz, tstz)` renders the instant in
        # `tz` and returns a naive local timestamp, which is what the date is
        # then taken from.
        #
        # The first draft was `timezone(tz, timezone('UTC', col))`, which looks
        # symmetrical and is wrong in its second step: applied to a NAIVE
        # timestamp, `timezone(tz, ...)` INTERPRETS it as local and converts
        # the other way. It was caught by `test_business_date_sql_postgres.py`
        # on a real engine and by nothing else — SQLite takes a different
        # branch entirely, so the whole suite would have stayed green.
        return func.date(func.timezone(timezone_name or "UTC", column))

    offset = utcnow().astimezone(zone(timezone_name)).utcoffset() or timedelta(0)
    seconds = int(offset.total_seconds())
    # SQLite's `date()` takes modifiers; seconds keeps half-hour zones like
    # Asia/Kolkata exact rather than rounding them to an hour.
    return func.date(column, f"{seconds} seconds")
