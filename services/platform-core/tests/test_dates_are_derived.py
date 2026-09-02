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

#: WO-63: a module-level WINDOW pinned to literal dates, under ANY name.
#:
#: The two patterns above look for a specific key and a specific variable, and
#: `test_dairy_reconciliation.py` was neither: `MONTH = (date(2026, 8, 1),
#: date(2026, 8, 28))`. It passed this guard for a month and then failed for
#: the same reason everything else in WO-58 failed — its window stopped
#: containing "now". A frozen window is a frozen window whatever it is called.
#:
#: THE DISTINCTION THAT DECIDES AN EXEMPTION, because this pattern catches
#: both and only one of them is a defect: a literal is fine when the test both
#: CREATES and QUERIES the data on that date — it is then self-consistent, and
#: the calendar moving underneath it changes nothing. It is a defect when the
#: window has to contain SOMETHING THAT HAPPENS NOW: a settlement collecting
#: today's milk, a statement covering an invoice raised in the test. Every
#: entry below was checked by running that file under a frozen 2027-01-01 and
#: 2028-02-29 — the exemptions are evidence, not opinion.
FROZEN_WINDOW = re.compile(r"^[A-Z_]+\s*=\s*\(?\s*date\(\d{4},", re.MULTILINE)

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
    # WO-63. Each names a DAY it then creates data on and queries — proven
    # self-consistent by running them frozen on 2027-01-01 and 2028-02-29.
    "test_route_report.py": "a named delivery day, created and reported on",
    "test_route_report_postgres.py": "same fixture as its SQLite twin",
    "test_scheduler_routes.py": "a named generation day, created and asserted",
    "test_scheduler_routes_postgres.py": "same fixture as its SQLite twin",
    "test_scheduler_concurrency_postgres.py": "one generation day, run twice at once",
    "test_route_generation_postgres.py": "a named generation day",
    "test_standing_orders.py": "the weekday IS the subject — a Monday must be a Monday",
    "test_contact_repair_postgres.py": "pins the instants it then repairs",
    "test_month_end_billing.py": "AUGUST is what previous_month() is asserted ABOUT",
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
def test_no_fixture_freezes_a_window_under_another_name(path, text):
    """`MONTH = (date(2026, 8, 1), date(2026, 8, 28))` is the same defect as a
    frozen TODAY, wearing a name the earlier guard did not know to look for."""
    offenders = FROZEN_WINDOW.findall(text)
    assert not offenders, (
        f"{path.name} pins a window to literal dates. Derive it from tests.clock "
        "— `previous_month(TODAY)`, `month_start()`, `days_ago(n)` — so it still "
        "contains the data the test creates when the calendar moves."
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
