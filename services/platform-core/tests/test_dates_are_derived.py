"""The suite must not care what month it is (WO-58 · LACTEVA-QA-008).

Eight suites went red the morning August became September. Every one of them
had frozen a date in a fixture while the platform read the wall clock, and the
two agreed only for as long as the calendar sat inside the frozen month.

This is the guard that stops it returning. It is a lint with a reason: a
settlement period, an invoice period or a report window written as a literal
is a test that passes until the date it was written for goes past, and then
fails for a reason that has nothing to do with the code under test.
"""

import re
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

#: A full-calendar-month literal in a period field. This exact shape is the
#: "this month" idiom every broken fixture used.
PERIOD_LITERAL = re.compile(
    r'"period_(from|to)":\s*"\d{4}-\d{2}-\d{2}"',
)

#: A module-level TODAY pinned to a literal date.
FROZEN_TODAY = re.compile(r"^TODAY\s*=\s*date\(\d{4},", re.MULTILINE)

#: Files whose literal dates are the SUBJECT rather than an assumption — a
#: period-boundary test has to name boundaries, and a timezone test has to
#: name an instant. Each is listed with why, so the list cannot quietly grow.
DELIBERATE = {
    # Asserts behaviour AT specific period edges; the dates are the fixture.
    "test_settlements.py": "period-boundary behaviour is the subject",
    "test_financial_periods.py": "opening and closing named periods is the subject",
    # Sets the instant it then queries, so it is self-consistent.
    "test_reporting.py": "pins a UTC instant and the local day it belongs to",
    "test_closed_period_protection.py": "a closed period must be named to be closed",
    # This file's own patterns.
    "test_dates_are_derived.py": "the guard itself",
    # A window deliberately OUTSIDE any data (2020) and an inverted range —
    # both are the subject, and deriving them would delete the test.
    "test_contact_repair.py": "an empty historical window and an inverted range are the subject",
    # Two named periods that must not overlap each other; deriving both to
    # this month would collide them and assert nothing.
    "test_settlement_lifecycle.py": "two distinct periods are the subject",
    # These date their own data into the period they name, so the pair moves
    # together. Worth a second look if either ever goes red.
    "test_localization.py": "dates its own data into the period it names",
    "test_receipt_pdf.py": "dates its own data into the period it names",
}


def _directives(text: str) -> str:
    """The file without its prose. Comments explain the literals they replaced,
    and a guard that matched its own explanation would be unfixable."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _sources():
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name in DELIBERATE:
            continue
        yield path, _directives(path.read_text())


@pytest.mark.parametrize("path,text", list(_sources()), ids=lambda v: getattr(v, "name", ""))
def test_no_fixture_hard_codes_a_settlement_period(path, text):
    """A period must contain the collections it settles, and those happen now.

    Written as a literal, it contains them until the month turns over.
    """
    offenders = PERIOD_LITERAL.findall(text)
    assert not offenders, (
        f"{path.name} hard-codes a period date. Derive it: "
        "`month_start().isoformat()` / `month_end().isoformat()` from tests.clock — "
        "a literal period stops containing today's collections when the month changes."
    )


@pytest.mark.parametrize("path,text", list(_sources()), ids=lambda v: getattr(v, "name", ""))
def test_no_fixture_freezes_today(path, text):
    """`TODAY = date(2026, 8, 12)` is a suite that only works in August."""
    assert not FROZEN_TODAY.search(text), (
        f"{path.name} pins TODAY to a literal. Use `reference_date()` from tests.clock, "
        "so the fixture and the platform agree on what day it is."
    )


def test_the_clock_helper_follows_the_platform():
    """The fixtures' today and the platform's must be the same day.

    This is the whole defect in one assertion: they were allowed to differ.
    """
    from platform_core.core.db import utcnow
    from tests.clock import reference_date

    assert reference_date() == utcnow().date()


def test_a_derived_window_survives_a_month_boundary():
    """The arithmetic itself, at the edges that broke."""
    from datetime import date

    from tests.clock import month_end, month_start

    for day, first, last in (
        (date(2026, 9, 1), date(2026, 9, 1), date(2026, 9, 30)),
        (date(2026, 9, 30), date(2026, 9, 1), date(2026, 9, 30)),
        (date(2025, 12, 31), date(2025, 12, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 31)),
        (date(2028, 2, 29), date(2028, 2, 1), date(2028, 2, 29)),  # a leap February
    ):
        assert month_start(day) == first, day
        assert month_end(day) == last, day
