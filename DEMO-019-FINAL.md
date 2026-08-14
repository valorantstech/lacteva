---
id: DEMO-019-FINAL
title: DEMO-019 — Dairy Customer Operations, Daily Reports & Monthly Billing Readiness
type: reference
status: Approved
version: "1.1"
owner: Platform Engineering
created: 2026-08-15
last-updated: 2026-08-15
related: [DEMO-018-FINAL, DEMO-017-FINAL, DEMO-016-FINAL, DEMO-015-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-019 — Dairy Customer Operations, Daily Reports & Monthly Billing

The survey found the customer workflow largely built across DEMO-009 to
DEMO-018, so this milestone connected four things that were genuinely missing
and then spent most of its effort on something nobody had asked for: **the
platform's collection reports read zero for a dairy that had collected milk.**

It was found because the test suite went red at midnight in Nairobi and stayed
red for three hours — nineteen failures, none of them caused by this
milestone's code, proven by stashing the change and watching them fail on the
previous commit.

**Three defects, all about the same thing: which day a dairy's work belongs
to.** The third was found in the browser *after* deployment, which is the
argument for §11 of the work order being a step and not a formality.
**AWS cost: none.**

---

## 1. What already existed

Customers, delivery plans, the scheduler, deliveries, the daily report with
per-customer rows and CSV export, invoices, payments, receipts, the customer
statement, the dashboard, the mobile operator round, RBAC, RLS, three
languages and the currency/timezone architecture. Nothing here was rebuilt.

## 2. What DEMO-019 changed

**"How much milk was supposed to go out today?"** — §5's headline question,
which the report answered only in counts. `planned_quantity` is now every row
the round intended, whatever became of it, excluding only `cancelled`, which
means recorded in error — milk nobody intended to send. `returned` and
`cancelled` are reported beside `skipped`, so "which deliveries failed?" has
an answer.

**The CSV totals row carries the planned figure**, because an accountant
reading that file asks the shortfall question and a totals row with only the
achieved number makes them add up a column.

**The statement says how much milk the money is for** — "124 L, ₹7,440 billed,
₹5,000 paid, ₹2,440 outstanding" on one screen, where the litres used to come
from a different one.

**Month-end bills are DRAFTED automatically, never issued.** That distinction
is the whole safety argument for calling it §8's "smallest safe mechanism": a
draft is absent from `PAYABLE_INVOICE_STATUSES`, so it moves nobody's balance
and appears on nobody's statement, and it can be cancelled — while *issuing*
is the irreversible act BR-0010 governs and stays with a person who can look
at the month first. A job that issued would be a machine posting receivables
into a dairy's books on a schedule, and the first anyone would hear of a
mistake is a customer disputing a bill nobody read.

It reuses `generate_invoice` exactly — the same function an operator calls,
called on a schedule — so there is no second billing path. Its refusals *are*
the idempotency: a customer already billed for the period is declined and
counted. It rides DEMO-017's existing tenant loop on the 1st of each dairy's
own month, so there is no second scheduler to look at when bills do not
appear.

## 3. The defect that took the milestone over

**Every procurement report resolved its dates as the organization's business
date — correctly, since DEMO-013 — and then built the SQL window from the
NAIVE UTC MIDNIGHTS of that date.**

Those are not the same instant for any dairy that is not on UTC. For a Nairobi
cooperative at 00:24 local — 21:24 UTC the previous day — the window began
three hours in the *future*, so the daily collection report read **zero for a
day on which milk had been collected**. An Indian dairy lost five and a half
hours of every day. The same bug sat in the payment summary's window.

DEMO-013 built `range_bounds` for exactly this and the delivery side has used
it since; procurement was never converted.

**And the trend chart bucketed by `date(created_at)` — UTC's day — while its
window was already local**, so a collection recorded after local midnight was
counted in a total it was not drawn in.

**And the portal's reports screen defaulted its own window with
`new Date().toISOString()`** — UTC. This one was found by looking at it: the
deployed page opened on **14 August while Nairobi was on the 15th**. DEMO-015
had corrected exactly this in the dashboard's date picker and this screen kept
its own copy, so the fix never reached it. `todayIn` is now exported from
`date-range.tsx` and both screens call it, because the defect was not the
arithmetic — it was that the arithmetic existed twice.

The same UTC date labelled guided-capture sessions, so a session opened at
00:30 in Nairobi was named after the previous day.

## 4. The fix

One rule, in one place, and it now holds inside SQL as well as in Python.
`core/business_time.py` gains `local_date_sql(column, timezone, dialect)`:

* **PostgreSQL gets the native operation** — `timezone(tz, col)`, which reads
  the IANA database the server ships with, so it is correct across DST and for
  any zone rather than the fixed-offset ones the platform happens to support
  today;
* **SQLite gets a fixed offset**, because SQLite has no timezone database at
  all. That difference is confined to the test stack and stated where it lives.

Every procurement window now uses `range_bounds` with the tenant's zone,
threaded through a `_timezone()` helper so a report's bounds and its notion of
"today" come from one clock. In the portal there is now one exported `todayIn`
rather than a copy per screen.

**The PostgreSQL test caught my own first draft.** I wrote `timezone(tz,
timezone('UTC', col))`, which looks symmetrical and is wrong in its second
step: applied to a naive timestamp, `timezone(tz, …)` *interprets* it as local
and converts the other way. SQLite takes a different branch, so the entire
suite would have stayed green while production bucketed every chart wrongly.
That is the argument for `test_business_date_sql_postgres.py` in one incident.

## 5. Settlement semantics

**Unchanged, deliberately.** A settlement period remains a range of business
dates and a collection's business date remains the dairy's — which is what
`test_settlement_late_collection.py` has asserted since PILOT-F03. No
historical financial record was altered.

What changed is that two *tests* had derived their period from
`utcnow().date()` while the domain answers in the dairy's date, so they asked
about days the milk was not collected on. Corrected to ask the platform. That
is a premise fix rather than a weakening: the behaviour they were silently
assuming is now asserted explicitly, twice, in tests that do not depend on
when the suite runs.

## 6. Regression tests

22 new tests pin the rule at the boundary rather than at the wall clock:

| | |
|---|---|
| One instant, three dairies | 20:00 UTC — India on the 15th, Kenya and Qatar on the 14th |
| All three past midnight | 21:30 UTC — every dairy on the 15th while UTC is still the 14th |
| Local midnight → UTC | 18:30 UTC for Bengaluru, 21:00 for Nairobi and Doha |
| The seam | a day covered completely and exactly once; the boundary instant belongs to the next day |
| Financial period ends | August in Bengaluru runs 31 Jul 18:30 UTC → 31 Aug 18:30 UTC; a UTC-built period would swallow 5½ hours of July and lose 5½ of August at **both ends of every period** |
| Post-midnight collection | a collection stamped 22:30 UTC appears on the next local day's report and not on UTC's |
| On a real engine | six PostgreSQL tests including **Europe/London**, whose August and January answers differ and which a fixed offset cannot express |
| In the browser | seven portal tests at frozen instants — the three zones, the exact turnover second, the month boundary, and the UTC fallback. `resolveRange` had **no test at all** before this, which is how DEMO-015's correction failed to spread |

Plus the milestone's own: 10 month-end drafting tests, 5 report/statement
tests, and a reconciliation and performance pair.

## 7. Reconciliation and performance

**§22 reconciliation, executed:** one household, a realistic August — most
days delivered, Sundays skipped, one returned — driven through the real
endpoints, then all five identities asserted. The skipped and returned days
are billed to nobody, which is the assertion that catches a report and a bill
disagreeing about what "delivered" means.

**§23 performance as a query count, not a stopwatch:** three hundred
customers, and the daily report issues fewer than twenty SELECTs. A timing
threshold flakes on a busy machine and passes on a fast one while an N+1 hides
inside it; a fixed statement count is the property that actually matters.

## 8. Known limitations

* **SQLite's branch of `local_date_sql` uses a fixed offset.** Correct for
  every zone the platform supports and an hour out for a DST zone inside a
  window that spans a transition — in tests only. The PostgreSQL path, which
  is what production runs, is exact.
* **Deliveries are not centre-scoped**, so §6's optional "centre" CSV column
  has nothing to carry. `delivery_plan.center_id` exists and generation does
  not copy it onto the delivery.
* **A customer has no preferred language of their own.** A customer-portal
  *user* has one; a household with no login does not, so a printed bill cannot
  yet be addressed in Hindi on a per-customer basis.
* **Month-end drafting runs on the 1st only.** A dairy that wants a mid-month
  bill uses the manual endpoint with an explicit period.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-15 | Platform Engineering | The portal's reports screen and guided-capture label were still on UTC; found in post-deployment browser verification. One exported `todayIn`, seven boundary tests. |
| 1.0 | 2026-08-15 | Platform Engineering | DEMO-019: the round's intended quantity, the litres behind the money, month-end drafts that are never issued — and the business-date rule made consistent from Python into SQL after the collection report was found reading zero for a dairy that had collected milk. |
