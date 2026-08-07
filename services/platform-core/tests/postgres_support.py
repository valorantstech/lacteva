"""Shared guard for the PostgreSQL-only suites (OPS-001).

The platform has accumulated guarantees that SQLite structurally cannot
evaluate — row-level security, exact numeric aggregation, a scaled numeric
column rounding on store, migrations applied to an empty database. Each one
lives in a module that skips when no PostgreSQL is reachable.

**A skip is the dangerous outcome, not the failure.** A skipped security proof
is worse than an absent one, because it is green. CI-001 handled that by
grepping pytest's output for "N skipped" after the fact; this module makes the
skip impossible in the first place.

Two modes, one switch:

- `LACTEVA_TEST_POSTGRES_URL` set        → the suite runs.
- unset, locally                         → the suite skips, which is the
                                           correct outcome on a laptop with no
                                           database.
- unset, with `LACTEVA_REQUIRE_POSTGRES=1` → **collection fails.** The
                                           verification pipeline sets this, so
                                           a misconfigured job cannot report
                                           success by quietly running nothing.

The distinction matters because the two situations are genuinely different: a
developer without PostgreSQL should not be blocked, and a pipeline whose whole
purpose is PostgreSQL must not pass without it.
"""

import os

import pytest

POSTGRES_URL = os.environ.get("LACTEVA_TEST_POSTGRES_URL", "")
REQUIRED = os.environ.get("LACTEVA_REQUIRE_POSTGRES") == "1"

if REQUIRED and not POSTGRES_URL:
    # A module-level raise is a COLLECTION ERROR, which fails the run. Raising
    # here rather than asserting inside a test is deliberate: an error that
    # happens before any test runs cannot be mistaken for a passing suite.
    raise RuntimeError(
        "LACTEVA_REQUIRE_POSTGRES=1 but LACTEVA_TEST_POSTGRES_URL is empty. "
        "This pipeline exists to execute the PostgreSQL-only guarantees; "
        "running it without a database would report success for work that "
        "never happened."
    )

requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL,
    reason=(
        "no PostgreSQL configured (LACTEVA_TEST_POSTGRES_URL). "
        "Expected locally; a skip in the verification pipeline is a "
        "configuration failure and is prevented by LACTEVA_REQUIRE_POSTGRES=1."
    ),
)


# --------------------------------------------------------------------------
# VER-001 — the schema owner, kept separate from the application role.
#
# The application connects as an unprivileged role: it must not be a
# superuser (a superuser IGNORES every row-level security policy), and it has
# no DDL rights, because nothing it does at runtime creates a table.
#
# Some fixtures below DO need DDL — the RLS probe table is built and dropped
# per test. Those use this URL instead. Keeping the two apart is not
# bookkeeping: it is what makes the isolation assertions meaningful, since a
# role that can `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` is not a role
# whose confinement proves anything.
#
# Falls back to the application URL, so pointing a laptop at a single
# development database still works.
# --------------------------------------------------------------------------

ADMIN_URL = os.environ.get("LACTEVA_TEST_POSTGRES_ADMIN_URL") or POSTGRES_URL
