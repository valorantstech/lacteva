"""Which clock a business date is measured on (DEMO-014 §4).

Three timezones existed and nothing said which one won. The tests below are
about the RULE, not about any country: an organization always has a clock, a
centre may override it, and a person may change what they READ without
changing what the platform counted.

That last one is the boundary worth guarding, and it is guarded structurally:
`business_timezone()` does not take a user at all.
"""

import inspect
from datetime import date, datetime
from zoneinfo import ZoneInfo

from platform_core.core.business_time import business_today
from platform_core.core.timezones import business_timezone, describe, display_timezone


def test_a_centre_without_an_opinion_uses_its_organizations_clock():
    assert business_timezone("Asia/Kolkata", None) == "Asia/Kolkata"
    assert business_timezone("Africa/Nairobi", None) == "Africa/Nairobi"


def test_a_centre_may_override_for_a_cooperative_that_spans_a_border():
    assert business_timezone("Africa/Nairobi", "Africa/Kampala") == "Africa/Kampala"


def test_a_broken_centre_zone_falls_back_rather_than_failing():
    """A report drawn on a hand-edited zone is worse than one drawn on the
    organization's, and a report that refuses to draw is worst of all."""
    assert business_timezone("Asia/Kolkata", "Mars/Olympus") == "Asia/Kolkata"
    assert business_timezone("Asia/Kolkata", "") == "Asia/Kolkata"


def test_an_organization_with_no_clock_is_utc_not_a_guess():
    assert business_timezone(None, None) == "UTC"


def test_a_person_changes_what_they_read_and_nothing_else():
    # They see London...
    assert display_timezone("Asia/Kolkata", "Europe/London") == "Europe/London"
    # ...and the dairy's day is still the dairy's day.
    assert business_timezone("Asia/Kolkata", None) == "Asia/Kolkata"


def test_a_business_date_cannot_be_moved_by_a_user_preference():
    """Structural, not conventional: `business_timezone` has no parameter a
    user preference could be passed to. A future caller cannot get this wrong
    by accident, only by editing this function's signature.
    """
    parameters = set(inspect.signature(business_timezone).parameters)
    assert parameters == {"organization_timezone", "center_timezone"}
    assert "user" not in str(parameters)


def test_without_a_preference_people_read_what_the_platform_counted():
    assert display_timezone("Asia/Kolkata", None) == "Asia/Kolkata"
    assert display_timezone("Africa/Nairobi", None, "Africa/Kampala") == "Africa/Kampala"


def test_the_hierarchy_changes_which_day_it_is():
    """The whole reason the hierarchy exists, in one assertion.

    Kolkata is UTC+5:30 and Nairobi UTC+3, so they disagree about the date
    for two and a half hours a day — between 18:30 and 21:00 UTC. Picking
    20:00 rather than a round-looking 22:00 is the point: at 22:00 both are
    already tomorrow and the assertion would pass while proving nothing.
    """
    instant = datetime(2026, 8, 13, 20, 0, tzinfo=ZoneInfo("UTC"))
    india = business_timezone("Asia/Kolkata", None)
    kenya = business_timezone("Africa/Nairobi", None)
    assert business_today(india, now=instant) == date(2026, 8, 14)
    assert business_today(kenya, now=instant) == date(2026, 8, 13)


def test_describe_says_where_the_clock_came_from():
    """An operator looking at a centre should not have to guess whether a zone
    was chosen or inherited — which is exactly what `'UTC'` as a default made
    impossible."""
    assert describe("Asia/Kolkata", None) == "Asia/Kolkata (organization)"
    assert describe("Africa/Nairobi", "Africa/Kampala") == "Africa/Kampala (centre override)"
