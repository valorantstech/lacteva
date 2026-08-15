"""The platform's calendar: months, years, working days and periods (DEMO-020).

DEMO-019 pinned the business DATE at local midnight. This pins everything
built on top of it — the month a bill belongs to, the year a document series
counts in, whether a dairy works on a day, and whether a stretch of days is
still open to be written into.

The instants are fixed, in the three countries the platform supports, and
chosen so UTC and the dairy disagree. A test that used the real clock would
pass all afternoon and fail at night, which is exactly how the defects this
milestone fixed survived: the wrong branch is only reachable for part of the
day.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from platform_core.core.business_time import (
    business_today,
    business_year,
    month_bounds,
    previous_month_bounds,
    range_bounds,
)
from platform_core.core.document_numbers import period_for

UTC = ZoneInfo("UTC")

INDIA = "Asia/Kolkata"  # UTC+5:30
KENYA = "Africa/Nairobi"  # UTC+3
QATAR = "Asia/Qatar"  # UTC+3

#: 20:00 UTC on 14 August: 01:30 on the 15th in Bengaluru, 23:00 on the 14th
#: in Nairobi and Doha. India has turned the page; the others have not.
SPLIT_INSTANT = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)

#: 22:00 UTC on 31 December 2026 — 03:30 on 1 January 2027 in Bengaluru and
#: 01:00 on the 1st in Nairobi and Doha, while UTC is still in the old year.
NEW_YEAR_INSTANT = datetime(2026, 12, 31, 22, 0, tzinfo=UTC)

#: 20:00 UTC on 31 July: already 1 August in India, still July elsewhere.
MONTH_TURN_INSTANT = datetime(2026, 7, 31, 20, 0, tzinfo=UTC)


# --- 1, 2, 3, 6: the three countries, and one instant meaning three dates ----


@pytest.mark.parametrize(
    "timezone,expected",
    [(INDIA, date(2026, 8, 15)), (KENYA, date(2026, 8, 14)), (QATAR, date(2026, 8, 14))],
)
def test_same_instant_different_business_dates(timezone, expected):
    assert business_today(timezone, now=SPLIT_INSTANT) == expected
    assert SPLIT_INSTANT.date() == date(2026, 8, 14), "the premise: UTC has not moved"


# --- 7: month boundaries are the ORGANIZATION's -------------------------------


def test_month_boundaries_follow_the_dairys_calendar():
    """At one instant India is in August and Kenya is still in July."""
    india_month = month_bounds(business_today(INDIA, now=MONTH_TURN_INSTANT))
    kenya_month = month_bounds(business_today(KENYA, now=MONTH_TURN_INSTANT))
    assert india_month == (date(2026, 8, 1), date(2026, 8, 31))
    assert kenya_month == (date(2026, 7, 1), date(2026, 7, 31))


def test_month_bounds_handles_february_and_leap_years():
    """The arithmetic that a `timedelta(days=30)` shortcut gets wrong."""
    assert month_bounds(date(2026, 2, 14)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert month_bounds(date(2028, 2, 14)) == (date(2028, 2, 1), date(2028, 2, 29))
    assert month_bounds(date(2026, 12, 9)) == (date(2026, 12, 1), date(2026, 12, 31))


def test_previous_month_crosses_a_year_and_a_short_month():
    assert previous_month_bounds(date(2026, 1, 5)) == (date(2025, 12, 1), date(2025, 12, 31))
    assert previous_month_bounds(date(2026, 3, 1)) == (date(2026, 2, 1), date(2026, 2, 28))


def test_a_months_utc_window_is_not_a_utc_month():
    """August in Bengaluru begins and ends at 18:30 UTC, at BOTH ends.

    A period built from UTC midnights would swallow five and a half hours of
    July and lose five and a half of August — every month, at both ends.
    """
    first, last = month_bounds(date(2026, 8, 15))
    start, end = range_bounds(first, last, INDIA)
    assert start == datetime(2026, 7, 31, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 8, 31, 18, 30, tzinfo=UTC)


# --- 8: the year boundary, and the document series ---------------------------


@pytest.mark.parametrize("timezone", [INDIA, KENYA, QATAR])
def test_business_year_turns_over_before_utc_does(timezone):
    assert business_year(timezone, now=NEW_YEAR_INSTANT) == 2027
    assert NEW_YEAR_INSTANT.year == 2026, "the premise: UTC is still in the old year"


def test_document_series_uses_the_dairys_year():
    """The defect DEMO-020 found: `period_for` defaulted to UTC's year.

    A receipt handed over at 03:30 on 1 January in Bengaluru was stamped with
    the year that had ended ninety minutes earlier — on a sequential financial
    document several jurisdictions require to be exactly that.
    """
    assert period_for(business_today(INDIA, now=NEW_YEAR_INSTANT)) == "2027"
    assert period_for(business_today(KENYA, now=NEW_YEAR_INSTANT)) == "2027"
    # And the wrong answer, named, so the test says what it is defending.
    assert period_for(NEW_YEAR_INSTANT.date()) == "2026"


def test_period_for_requires_a_date():
    """It no longer has a default, because the default was the defect."""
    with pytest.raises(TypeError):
        period_for()  # type: ignore[call-arg]


# --- month_bounds no longer accepts a zone it cannot use ---------------------


def test_month_bounds_rejects_a_timezone_argument():
    """The inert parameter is gone (DEMO-020).

    It never affected the answer, so `month_bounds(utcnow().date(), tz)` read
    like a conversion, converted nothing, and returned UTC's month under a
    local-looking name. A parameter that cannot change the result must not be
    in the signature to be trusted.
    """
    with pytest.raises(TypeError):
        month_bounds(date(2026, 8, 15), INDIA)  # type: ignore[call-arg]


# --- 19: the migration cannot touch a historical financial record ------------


def test_the_migration_is_purely_additive():
    """DEMO-020 adds two tables and modifies nothing.

    Asserted against the migration's own text rather than by running it,
    because the guarantee is about what the file is ALLOWED to contain: a
    later edit that adds an `op.execute("UPDATE settlement ...")` would pass
    an up/down/up test perfectly well and still rewrite a dairy's money.
    """
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "migrations/versions/a4f7c19d8b52_demo_020_business_calendar.py"
    ).read_text()

    created = {"organization_calendar_day", "financial_period"}
    # Nothing that mutates existing rows, anywhere in the file.
    for forbidden in (
        'op.execute("UPDATE',
        'op.execute("DELETE',
        "op.bulk_insert",
        "op.alter_column",
    ):
        assert forbidden not in source, f"the migration contains {forbidden}"

    # And every table it names is one of its own.
    import re

    touched = set(re.findall(r'op\.(?:create_table|drop_table)\(\s*"([a-z_]+)"', source))
    assert touched == created, f"the migration touches tables outside its own: {touched - created}"

    financial = (
        "settlement",
        "payment",
        "receipt",
        "customer_invoice",
        "milk_collection_transaction",
    )
    for table in financial:
        assert f'"{table}"' not in source, f"the migration names the financial table {table}"
