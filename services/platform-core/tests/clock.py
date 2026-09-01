"""The one date the suite agrees on (WO-58 · LACTEVA-QA-008).

WHAT WENT WRONG. Eight suites went red the morning August became September.
Not one of them had a bug: their fixtures froze a date — `TODAY = date(2026,
8, 12)`, `OCTOBER = {"period_from": "2026-08-01", ...}` — while the platform
read the wall clock. One file said so in a comment: "matches utcnow().date()
in this test run window". They agreed for as long as the calendar sat inside
the frozen month, and a settlement whose period excludes its own collection
has no lines and cannot be finalized.

THE FIX IS DERIVATION, NOT FREEZING. Every fixture takes today from here, and
every window is computed from it. The suite then runs on whatever day it is,
including the awkward ones, and a period always contains the collections it
settles.

WHY THE CLOCK IS NOT FROZEN INSTEAD. That was tried first: shift `utcnow()`
so the whole platform believes it is a chosen day. It does not work, and the
reason is worth writing down. `utcnow()` is the platform's clock but not the
process's: PyJWT validates `exp` and `iat` against the real system clock, so
every token minted by a shifted clock reads as expired or not-yet-valid and
every request 401s. Widening the JWT leeway hides that one symptom and the
failures simply move — 5 at a two-week shift, 85 at nine months, each one
something comparing a shifted time to a real one. A clock that half the
process believes is not a clock. Derivation needs no such fiction.
"""

from __future__ import annotations

from datetime import date, timedelta


def reference_date() -> date:
    """Today, as the platform sees it.

    Deliberately the real date: fixtures and the product must agree, and the
    product reads the wall clock. Anything else reintroduces the drift this
    module exists to remove.
    """
    return date.today()


#: Import this instead of writing a date literal in a fixture.
TODAY = reference_date()


def month_start(day: date | None = None) -> date:
    """The first of the month `day` falls in — today's, by default."""
    return (day or reference_date()).replace(day=1)


def month_end(day: date | None = None) -> date:
    """The last day of that month, without a calendar dependency."""
    first = month_start(day)
    return (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def days_ago(n: int, *, day: date | None = None) -> date:
    """`n` days before today.

    Use this rather than arithmetic on a literal: a window reaching back
    across a month boundary is exactly the case that broke, and it should be
    ordinary rather than special.
    """
    return (day or reference_date()) - timedelta(days=n)
