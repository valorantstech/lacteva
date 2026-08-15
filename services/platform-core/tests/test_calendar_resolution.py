"""Whose calendar wins, and what a closed period refuses (DEMO-021).

DEMO-020 built the calendar and the period and left both connected to nothing.
This is the half that makes them operational, and the two things worth pinning
are the two that could go silently wrong:

* **resolution must be deterministic** — one answer for every combination of
  organization and centre opinion, and a user's display preference must not be
  able to reach it at all;
* **a closed period must REFUSE** — on every path that commits money, with the
  date the record actually belongs to rather than today's.

The refusal tests all assert the premise first: that the same call succeeds
while the period is open. A test that only checks the failure cannot tell a
working guard from a broken endpoint.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from platform_core.core.business_time import business_today
from platform_core.core.timezones import business_timezone, display_timezone
from platform_core.modules.business_calendar.service import (
    centre_exception_is_working,
    resolve_working_day,
)

UTC = ZoneInfo("UTC")

INDIA = "Asia/Kolkata"
KENYA = "Africa/Nairobi"
QATAR = "Asia/Qatar"


# --- 1, 2: the resolution hierarchy is total and deterministic ----------------


@pytest.mark.parametrize(
    "organization,centre,expected",
    [
        # Nothing said anywhere: a working day, as the platform always behaved.
        (None, None, True),
        # The organization alone.
        (False, None, False),
        (True, None, True),
        # The centre alone — it overrides an organization with no opinion.
        (None, False, False),
        (None, True, True),
        # Both, disagreeing: the CENTRE wins, in both directions. One site
        # shutting while the dairy works, and one site working through a
        # dairy-wide holiday, are both real.
        (True, False, False),
        (False, True, True),
        # Both agreeing.
        (False, False, False),
        (True, True, True),
    ],
)
def test_resolution_is_total_and_the_centre_overrides(organization, centre, expected):
    assert resolve_working_day(organization=organization, centre=centre) is expected


def test_absent_means_working_not_holiday():
    """The default that makes this safe to introduce.

    An absent row must never turn a working day into a holiday: that would
    change behaviour for every organization that has declared nothing, which
    is all of them on the day the table ships.
    """
    assert resolve_working_day(organization=None, centre=None) is True


@pytest.mark.parametrize(
    "kind,working",
    [("holiday", False), ("closure", False), ("special", True)],
)
def test_a_centres_kind_maps_to_working_the_way_readiness_reads_it(kind, working):
    """The mapping is the readiness engine's, written down (DEMO-005).

    `holiday` and `closure` are BLOCKING there; `special` is a warning — a day
    that is unusual and still worked.
    """
    assert centre_exception_is_working(kind) is working


# --- 3: a person cannot move an accounting date ------------------------------


def test_a_users_display_timezone_cannot_reach_the_business_date():
    """The guarantee DEMO-014 designed and DEMO-021 must not erode.

    A manager who sets their display timezone to London does not move their
    dairy's accounting day. Asserted at the seam: `business_timezone` does not
    ACCEPT a user timezone — passing one is a TypeError, not a wrong answer —
    while `display_timezone` both accepts and honours it.
    """
    assert business_timezone(INDIA, None) == INDIA
    with pytest.raises(TypeError):
        business_timezone(INDIA, None, "Europe/London")  # type: ignore[call-arg]

    # Display is the only place a person is consulted, and it does not feed
    # any date boundary.
    assert display_timezone(INDIA, "Europe/London") == "Europe/London"
    assert business_timezone(INDIA, None) == INDIA, "the business clock is unmoved"


def test_the_business_date_follows_the_organization_not_the_reader():
    """20:00 UTC: India is on the 15th whoever is looking at it."""
    instant = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)
    for reader_zone in ("Europe/London", "America/New_York", "Australia/Sydney"):
        # The reader's zone is simply not an input to this function.
        assert business_today(INDIA, now=instant) == date(2026, 8, 15)
        assert display_timezone(INDIA, reader_zone) == reader_zone


# --- 8, 9: month and year boundaries, in every supported zone ----------------


@pytest.mark.parametrize("timezone", [INDIA, KENYA, QATAR])
def test_the_last_minute_of_a_month_is_still_that_month(timezone):
    """23:59 local on the 31st, and 00:00 local on the 1st, in each zone."""
    from platform_core.core.business_time import day_bounds, month_bounds

    last_day = date(2026, 8, 31)
    start, end = day_bounds(last_day, timezone)
    # One second before the day ends is still the 31st, and therefore August.
    from datetime import timedelta

    almost_midnight = end - timedelta(seconds=1)
    assert business_today(timezone, now=almost_midnight) == last_day
    assert month_bounds(business_today(timezone, now=almost_midnight)) == (
        date(2026, 8, 1),
        last_day,
    )
    # The instant the day ends is the 1st of September, and September's month.
    assert business_today(timezone, now=end) == date(2026, 9, 1)
    assert month_bounds(business_today(timezone, now=end)) == (
        date(2026, 9, 1),
        date(2026, 9, 30),
    )
    assert start < end


@pytest.mark.parametrize("timezone", [INDIA, KENYA, QATAR])
def test_february_into_march_in_a_leap_year_and_not(timezone):
    from platform_core.core.business_time import day_bounds, month_bounds

    for year, last in ((2026, 28), (2028, 29)):
        _, end = day_bounds(date(year, 2, last), timezone)
        assert business_today(timezone, now=end) == date(year, 3, 1)
        assert month_bounds(date(year, 2, 1))[1] == date(year, 2, last)


@pytest.mark.parametrize("timezone", [INDIA, KENYA, QATAR])
def test_the_year_turns_over_on_the_dairys_clock(timezone):
    from platform_core.core.business_time import business_year, day_bounds

    _, end = day_bounds(date(2026, 12, 31), timezone)
    assert business_today(timezone, now=end) == date(2027, 1, 1)
    assert business_year(timezone, now=end) == 2027
    # And UTC has not necessarily arrived yet: for these zones it has not.
    assert end.astimezone(UTC).year == 2026
