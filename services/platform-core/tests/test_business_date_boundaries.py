"""Local midnight, and where a day's work belongs (DEMO-019).

A business date is the ORGANIZATION's calendar date. Every question the
platform answers about "a day" — a report window, a trend bucket, a settlement
period — has to use that same rule, and DEMO-019 found two places that did
not: the procurement report windows truncated UTC, and the trend chart grouped
by UTC.

The failure mode is invisible for most of the day and unmistakable at the
wrong moment: a Nairobi cooperative's collection report read ZERO for a day it
had collected milk, for the three hours between local midnight and UTC's. An
Indian dairy lost five and a half.

These tests pin the rule at the boundary itself, in the three countries the
platform supports, using instants chosen so that UTC and the dairy disagree.
They do not depend on when the suite runs.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from platform_core.core.business_time import (
    business_date_of,
    day_bounds,
    range_bounds,
)

UTC = ZoneInfo("UTC")

#: One instant, three dairies. 20:00 UTC on 14 August is 01:30 on the 15th in
#: Bengaluru and 23:00 on the 14th in Nairobi and Doha — the window in which
#: India has turned the page and the others have not.
SPLIT_INSTANT = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)

#: 21:30 UTC: now all three have passed local midnight.
ALL_TOMORROW = datetime(2026, 8, 14, 21, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "timezone,expected",
    [
        ("Asia/Kolkata", date(2026, 8, 15)),
        ("Africa/Nairobi", date(2026, 8, 14)),
        ("Asia/Qatar", date(2026, 8, 14)),
    ],
)
def test_one_instant_three_dairies(timezone, expected):
    """India has turned the page; Kenya and Qatar have not."""
    assert business_date_of(SPLIT_INSTANT, timezone) == expected


@pytest.mark.parametrize("timezone", ["Asia/Kolkata", "Africa/Nairobi", "Asia/Qatar"])
def test_after_local_midnight_every_dairy_is_on_the_next_day(timezone):
    """21:30 UTC is past midnight in all three, and UTC is still yesterday."""
    assert business_date_of(ALL_TOMORROW, timezone) == date(2026, 8, 15)
    assert ALL_TOMORROW.date() == date(2026, 8, 14), "the premise: UTC has not moved"


@pytest.mark.parametrize(
    "timezone,utc_midnight",
    [
        # Local midnight, expressed as the UTC instant it actually is.
        ("Asia/Kolkata", datetime(2026, 8, 14, 18, 30, tzinfo=UTC)),
        ("Africa/Nairobi", datetime(2026, 8, 14, 21, 0, tzinfo=UTC)),
        ("Asia/Qatar", datetime(2026, 8, 14, 21, 0, tzinfo=UTC)),
    ],
)
def test_local_midnight_maps_to_the_right_utc_instant(timezone, utc_midnight):
    """The rule a truncated UTC timestamp gets wrong.

    A day begins at local midnight, and that is 18:30 UTC for an Indian dairy
    — not 00:00.
    """
    start, _end = day_bounds(date(2026, 8, 15), timezone)
    assert start == utc_midnight


@pytest.mark.parametrize("timezone", ["Asia/Kolkata", "Africa/Nairobi", "Asia/Qatar"])
def test_a_local_day_is_covered_completely_and_exactly_once(timezone):
    """No gap and no overlap at the seam — the property a report depends on
    when it says a delivery belongs to exactly one day."""
    _first_start, first_end = day_bounds(date(2026, 8, 14), timezone)
    second_start, second_end = day_bounds(date(2026, 8, 15), timezone)
    assert first_end == second_start
    assert second_end - second_start == timedelta(days=1)
    # The last instant of the day is inside it; the boundary itself is not.
    assert business_date_of(first_end - timedelta(microseconds=1), timezone) == date(2026, 8, 14)
    assert business_date_of(first_end, timezone) == date(2026, 8, 15)


@pytest.mark.parametrize("timezone", ["Asia/Kolkata", "Africa/Nairobi", "Asia/Qatar"])
def test_a_range_covers_whole_local_days_at_both_ends(timezone):
    """A report asked for 1 to 31 August must include every minute of both."""
    start, end = range_bounds(date(2026, 8, 1), date(2026, 8, 31), timezone)
    assert start == day_bounds(date(2026, 8, 1), timezone)[0]
    assert end == day_bounds(date(2026, 8, 31), timezone)[1]
    assert business_date_of(start, timezone) == date(2026, 8, 1)
    assert business_date_of(end - timedelta(microseconds=1), timezone) == date(2026, 8, 31)


def test_a_month_of_a_dairys_calendar_is_not_a_month_of_utcs():
    """The settlement and billing period boundary.

    August in Bengaluru begins at 18:30 UTC on 31 July and ends at 18:30 UTC
    on 31 August. A period built from UTC midnights would include five and a
    half hours of July and lose five and a half hours of August — at both ends
    of every financial period.
    """
    start, end = range_bounds(date(2026, 8, 1), date(2026, 8, 31), "Asia/Kolkata")
    assert start == datetime(2026, 7, 31, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 8, 31, 18, 30, tzinfo=UTC)

    # A collection at 19:00 UTC on 31 July is August's milk for this dairy.
    late_july_utc = datetime(2026, 7, 31, 19, 0, tzinfo=UTC)
    assert business_date_of(late_july_utc, "Asia/Kolkata") == date(2026, 8, 1)
    assert start <= late_july_utc < end
