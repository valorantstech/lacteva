"""When a standing order is due, as arithmetic (DEMO-016 §3).

Module-level functions over plain values: no session, no ORM, no clock. The
generator asks these questions about six hundred plans a day and every answer
has to be the same one a person would give looking at the row — so the rules
live here, where they can be tested exhaustively without a database.

**A week is seven characters, Monday first.** `"1111111"` every day,
`"1111110"` Monday to Saturday, `"1111100"` weekdays. Monday-first matches
`date.weekday()`, which is what the code actually calls; ISO's Monday-first
convention is also what a dairy's own roster is written in.

Deliberately NOT here: recurrence rules, nth-weekday-of-month, alternating
weeks, public-holiday calendars. §3 says not to build a scheduling engine, and
the shape of a real dairy round is a weekly rhythm with holidays.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

#: Monday first, matching `date.weekday()`.
WEEK = 7

EVERY_DAY = "1" * WEEK
WEEKDAYS_ONLY = "1111100"
MONDAY_TO_SATURDAY = "1111110"


def normalise_weekdays(mask: str | None) -> str:
    """A seven-character mask, or a refusal.

    Accepts what a caller plausibly sends — `"1111111"`, or a shorter string
    padded — and refuses anything else rather than silently generating on the
    wrong days. A mask that is quietly wrong is a household that stops getting
    milk on Tuesdays and nobody knowing why.
    """
    # `None` is "not given" and defaults; `""` is a caller that sent the field
    # and got it wrong, and is refused. Collapsing the two would let a client
    # bug become a silent every-day round.
    text = (EVERY_DAY if mask is None else mask).strip()
    if len(text) != WEEK or any(c not in "01" for c in text):
        raise ValueError(f"weekdays must be {WEEK} characters of 0 or 1, e.g. {EVERY_DAY}")
    if "1" not in text:
        raise ValueError("a plan that delivers on no day of the week would never deliver")
    return text


def delivers_on_weekday(weekdays: str, day: date) -> bool:
    """Does this mask include the day of the week `day` falls on?"""
    return weekdays[day.weekday()] == "1"


def within_dates(day: date, effective_from: date, effective_to: date | None) -> bool:
    """Inclusive at both ends, and open-ended when there is no end.

    Inclusive because a plan starting on the first of August should deliver on
    the first of August; a half-open range here would silently skip a customer's
    first day, which is the one they would notice.
    """
    if day < effective_from:
        return False
    return effective_to is None or day <= effective_to


def is_paused(day: date, paused_from: date | None, paused_to: date | None) -> bool:
    """Is the plan on holiday on this day?

    Both ends inclusive, and both ends optional independently: `paused_from`
    with no `paused_to` is "paused until further notice", which is what an
    operator means when a customer leaves without saying when they are back.
    A `paused_to` alone is meaningless and reads as not paused.
    """
    if paused_from is None:
        return False
    if day < paused_from:
        return False
    return paused_to is None or day <= paused_to


def quantity_for(
    day: date,
    default_quantity: Decimal | str | int,
    overrides: dict | None,
) -> Decimal:
    """What this day takes.

    Overrides are keyed by weekday index as a STRING, because that is what
    survives a JSON round trip — `{"5": "30.000"}` is Saturday. A key that is
    not a plausible weekday, or a value that is not a number, falls back to the
    standing quantity rather than raising: the plan's own default is always a
    safe answer, and refusing to generate a whole round because one key was
    mistyped is worse than generating it at the ordinary amount.
    """
    base = Decimal(str(default_quantity))
    if not overrides:
        return base
    raw = overrides.get(str(day.weekday()))
    if raw is None:
        return base
    try:
        value = Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return base
    return value if value >= 0 else base


def due_on(
    day: date,
    *,
    weekdays: str,
    effective_from: date,
    effective_to: date | None,
    paused_from: date | None,
    paused_to: date | None,
) -> bool:
    """The whole question, in one call.

    Order matters only for readability — all four must hold — but it is written
    cheapest-first so the common answer for a superseded or out-of-season plan
    comes back without touching the rest.
    """
    return (
        within_dates(day, effective_from, effective_to)
        and delivers_on_weekday(weekdays, day)
        and not is_paused(day, paused_from, paused_to)
    )


def next_due(
    after: date,
    *,
    weekdays: str,
    effective_from: date,
    effective_to: date | None,
    paused_from: date | None,
    paused_to: date | None,
    horizon: int = 366,
) -> date | None:
    """The next day this plan delivers, at or after `after`.

    Answers "when does this customer next get milk?", which is the one thing
    a plan screen has to say that cannot be read off the row (§9).

    Bounded by a year. A plan whose next delivery is more than a year away —
    a long pause, or a mask that only matches inside a window that has closed
    — returns None rather than looping: "not in the foreseeable future" is the
    honest answer, and an unbounded search on a bad row would hang a page.
    """
    from datetime import timedelta

    day = max(after, effective_from)
    for _ in range(horizon):
        if effective_to is not None and day > effective_to:
            return None
        if due_on(
            day,
            weekdays=weekdays,
            effective_from=effective_from,
            effective_to=effective_to,
            paused_from=paused_from,
            paused_to=paused_to,
        ):
            return day
        day += timedelta(days=1)
    return None


def describe(weekdays: str) -> str:
    """A mask as a key a client can translate — never as English.

    Returns `schedule.daily`, `schedule.weekdays`, `schedule.mon_sat` or
    `schedule.custom`. The platform does not send sentences to a screen
    (DEMO-013): it sends a key, and the catalog decides what a Hindi-speaking
    manager reads.
    """
    if weekdays == EVERY_DAY:
        return "schedule.daily"
    if weekdays == WEEKDAYS_ONLY:
        return "schedule.weekdays"
    if weekdays == MONDAY_TO_SATURDAY:
        return "schedule.mon_sat"
    return "schedule.custom"
