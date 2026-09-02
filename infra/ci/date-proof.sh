#!/usr/bin/env bash
# The date guarantee, executed (WO-62 · LACTEVA-QA-009).
#
# "The suite does not care what day it is" was a claim WO-58 could argue for
# and not demonstrate: every fixture derives its dates, but the calendar only
# ever sat on one day at a time, so the awkward days went untested. WO-58's own
# tail is the argument for this script — three further date defects surfaced
# inside a single batch, each visible only in a particular hour or month.
#
# WHY THIS WORKS WHERE THE FIRST ATTEMPT DID NOT. Shifting the platform's own
# `utcnow()` moves the platform's clock and nothing else, so PyJWT went on
# validating `exp`/`iat` against the real system clock and every token minted
# under the shifted clock read as expired. `time-machine` patches CPython's
# `datetime` and `time` hooks, so the platform, PyJWT and everything else read
# one clock and agree about it.
#
# The days are chosen for what they can break:
#
#   mid-month     an ordinary day, the control — a failure here is the harness
#   month start   a window reaching "a week back" leaves the month
#   month end     a month-end bill, and the last day a period can contain
#   New Year      31 December and 1 January, the year rollover from both sides
#   leap day      29 February, the date that does not exist in three years out of four
#
# No infrastructure: the same in-memory SQLite the ordinary suite uses.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CORE="$ROOT/services/platform-core"
# An array, because CI passes `PYTHON="uv run python"` — three words, and a
# quoted scalar would be looked up as one filename with spaces in it.
read -r -a PY <<< "${PYTHON:-$CORE/.venv/bin/python}"

# The suites whose fixtures speak about dates. Not the whole suite: this runs
# five times, and a test with no date in it proves nothing five times over.
SUITES=(
  tests/test_dates_are_derived.py
  tests/test_settlements.py
  tests/test_settlement_lifecycle.py
  tests/test_financial_periods.py
  tests/test_closed_period_protection.py
  tests/test_reporting.py
  tests/test_reporting_dashboard.py
  tests/test_daily_operations.py
  tests/test_month_end_billing.py
  tests/test_day_book.py
  tests/test_procurement_e2e.py
  tests/test_sales_reporting.py
  tests/test_sales_workflow.py
  tests/test_customer_scope.py
  tests/test_subscription.py
  tests/test_reprice.py
  tests/test_milk_type_reporting.py
  tests/test_aggregate_currency.py
)

DAYS=(
  "2026-06-15T09:00 mid-month"
  "2026-12-01T09:00 month start"
  "2026-12-31T09:00 month end, and the last day of the year"
  "2027-01-01T09:00 New Year's Day"
  "2028-02-29T09:00 a leap day"
)

cd "$CORE"
FAILED=()
for entry in "${DAYS[@]}"; do
  day="${entry%% *}"
  why="${entry#* }"
  printf '\n\033[1m── %s — %s ──\033[0m\n' "$day" "$why"
  if LACTEVA_TEST_FREEZE_DATE="$day" "${PY[@]}" -m pytest "${SUITES[@]}" -q --no-header -p no:cacheprovider; then
    printf '\033[32m   green on %s\033[0m\n' "$day"
  else
    printf '\033[31m   FAILED on %s\033[0m\n' "$day"
    FAILED+=("$day")
  fi
done

echo
if [ ${#FAILED[@]} -eq 0 ]; then
  cat <<'EOF'
╭──────────────────────────────────────────────────────────────╮
│  DATE PROOF PASSED                                           │
│                                                              │
│  mid-month ................... green                         │
│  month start ................. green                         │
│  month end / year end ........ green                         │
│  New Year's Day .............. green                         │
│  leap day .................... green                         │
│                                                              │
│  The clock is patched at the INTERPRETER level, so PyJWT     │
│  and the platform read the same day and agree about it.      │
╰──────────────────────────────────────────────────────────────╯
EOF
  exit 0
fi
printf '\033[31mDATE PROOF FAILED on: %s\033[0m\n' "${FAILED[*]}"
exit 1
