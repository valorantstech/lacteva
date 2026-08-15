---
id: DEMO-022-FINAL
title: DEMO-022 — Holiday-Aware Delivery Scheduling
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-15
last-updated: 2026-08-15
related: [DEMO-021-FINAL, DEMO-020-FINAL, DEMO-017-FINAL, CON-0001]
baseline: ARCH-BASELINE-V1
---

# DEMO-022 — Holiday-Aware Delivery Scheduling

DEMO-021 left holidays advisory: recorded, resolved, and enforced nowhere.
This makes them operational for automatic delivery generation, and does it by
adding **one filter and one optional argument** — not a scheduler, not a
calendar, not a rule engine.

---

## 1. What already existed, and where the extension belongs

The survey found every piece already built:

| Piece | Where | Since |
|---|---|---|
| `organization_calendar_day` with a `working` flag | `business_calendar` | DEMO-020 |
| `center_calendar_entry` with a `kind` | `collection_center` | DEMO-005 |
| `resolve_working_day(organization, centre)` | `business_calendar` | DEMO-021 |
| `centre_exception_is_working(kind)` | `business_calendar` | DEMO-021 |
| The scheduler loop, on each tenant's own clock | `delivery/scheduler.py` | DEMO-017 |
| `run_for_tenant` / `record_run` / `generate_for_day` | `delivery` | DEMO-016/017 |
| Idempotency as a unique constraint | `uq_delivery_customer_date_slot` | DEMO-009 |

**The smallest extension point is the plan loop inside `generate_for_day`, and
that is where suppression went.** The reasoning:

* Suppression cannot live in `should_run`. It is a pure function with no
  session, so it cannot read a calendar — and returning "not due" would leave
  no record of *why* the round was empty, while the loop re-asked every minute.
* It cannot live at the top of `run_for_tenant` as a whole-day short-circuit
  either. That looks right and is wrong: a centre may be **working through an
  organization holiday**, so a day is not suppressible as a unit. The decision
  is per plan, because a plan belongs to a centre.
* It must not live in `record_run` unconditionally, because `record_run` is
  shared with the **manual** endpoint, which must stay unsuppressed.

So `generate_for_day` gained an optional `is_working` callable. Passed one, it
checks each due plan against its own centre. Passed nothing — the manual path —
behaviour is byte-for-byte what it was. **That optionality is the milestone's
boundary, expressed in a default argument.**

## 2. What DEMO-022 changed

**`WorkingDayResolver` (`business_calendar`)** — the one resolution path. It
composes `organization_exception` with the centre's `kind` and hands both to
the existing `resolve_working_day`. No rule is restated; the pure function
underneath is unchanged and still testable without a database. It caches per
centre for the life of one day's run, so three hundred plans across five
centres cost six lookups rather than three hundred.

**`centre_calendar_kind` (`collection_center`)** — a module-level service
function so the resolver can ask the centre's own module for the centre's
opinion. Nothing outside `collection_center` imports `CalendarEntry`.

**`generate_for_day`** counts `skipped_holiday` separately from `not_due`.

**`should_run` treats `holiday` as a finished status** alongside `success`. A
holiday is an answer about the day, not a failure to retry — without this the
loop would re-ask three times and give up, which reads like a broken scheduler
rather than a closed dairy.

**Migration `b8d3e1470f92`** adds one integer column, `server_default="0"`, so
every historical run is populated with the true answer rather than a
placeholder. No table created, no column dropped, no row rewritten.

## 3. Resolution and precedence

Unchanged from DEMO-021, and deliberately so:

    centre override  →  organization calendar  →  a working day

`None` at a level means "no opinion" and is distinct from `False`. A plan with
no centre takes the organization's answer by the same rule rather than a
separate branch. The centre's `special` kind means "unusual, and worked" — the
reading the readiness engine has used since DEMO-005; **no new representation
was invented**, as the work order required.

Verified in both directions: organization working with centre A shut suppresses
only A; organization shut with centre A `special` generates A and suppresses B.

## 4. Scheduler behaviour and missed days

| Situation | Result |
|---|---|
| Working day | Generates exactly as before |
| Organization holiday, no overrides | `created: 0`, status `holiday` |
| Centre A shut, B open | A's plans skipped, B's generated, status `success` |
| Organization shut, centre A working | A generated, B skipped |
| The day after a holiday | Generates **that day only** |
| Holiday declared after the round | Nothing deleted, nothing reversed |
| Manual generation on a holiday | Generates — not calendar-suppressed |

**No backfill, ever.** The scheduler's question is always about the *current*
business date; a suppressed day is terminal, so nothing revisits it.

## 5. Financial safety

Suppression can only ever cause **fewer `scheduled` deliveries to be created**.
It deletes nothing, updates nothing, and touches no invoice, payment, receipt,
settlement or balance. A `scheduled` delivery is worth 0.00 and is absent from
`BILLABLE_STATUSES` until somebody says the milk arrived, so a suppressed round
cannot move money even indirectly.

## 6. Verification

**Tests:** 1,550 backend passing, 0 failures (95 skipped — the PostgreSQL-only
suites, which then ran for real). 252 portal, 125 mobile, lint/format/tsc/build
and docs/xref green.

The 11 new backend tests drive the real scheduler entry point with a fabricated
clock. **Seven fail when the suppression filter is disabled**, and the four
that should not — working day, working exception, no-delete, manual generation
— do not. That discrimination is the point: a suite where everything failed
would not be testing suppression, it would be testing that generation happens
at all.

**PostgreSQL proof PASSED** — 95 PostgreSQL-only tests, **0 skipped**, 65
tables RLS-enabled and forced, migrations from empty. Includes a new
four-worker race on a declared holiday: one run row survives saying `holiday`,
`skipped_holiday` is 25, and no delivery exists. Migration verified
up → down → up with an empty autogenerate diff.

**Production, `main-d03a658`, deployed first attempt** with verification and
smoke test passing. Schema moved `a4f7c19d8b52` → `b8d3e1470f92`; all nine
health checks healthy; 65/65 tables forced.

**Suppression proven on production against both real tenants.** With no
holiday declared, `generate_for_day` would have produced 16 deliveries for the
Kenyan cooperative (Africa/Nairobi) and 17 for the Indian dairy (Asia/Kolkata).
With a holiday declared for the same date, both produced **0**, with
`skipped_holiday` of 16 and 17 respectively. Every probe ran in a rolled-back
transaction and the calendar rows were deleted afterwards; production ended
with zero calendar days, zero financial periods and no delivery beyond the
existing data.

**Financial reconciliation: every count identical** before and after
(collections 534, deliveries 1255, invoices 31, customer payments/receipts
24/24, settlements 84, supplier payments/receipts 42/36), receivables unchanged
at **211,961.00 KES** and **152,972.00 INR**.

**Browser:** the deliveries page reports `Last generation: 2026-08-15 ·
successful · automatic · 16 deliveries generated` with no holiday notice —
correct, since none is declared — and every figure (55 deliveries, 921.500 L,
49,879.00 KES) is unchanged. The business calendar page renders the dairy's
date, month and working-day state. **The holiday notice itself is covered by a
portal test against a stubbed run rather than in the browser**, because showing
it live would mean manufacturing a suppressed run on production, and the
domain-level proof above is the stronger evidence.

**Rollback:** previous release `main-35cc7cd` is on disk and pinned. The schema
moved, so a code rollback also wants `alembic downgrade -1`; the migration is
additive with a server default, so the previous code runs correctly against the
new schema either way.

**AWS: nothing created, nothing modified, no recurring cost change.**

## 6. Known limitations

* **Suppression is per plan via its centre, and most plans have no centre.**
  `delivery_plan.center_id` is nullable and the demo data does not set it, so
  in practice today the organization calendar decides everything. Centre
  precedence is built, tested and correct; it becomes visible when a dairy
  starts assigning plans to centres.
* **Readiness still reads its own centre calendar directly.** DEMO-021 flagged
  this and it remains: `operational_readiness` has its own `CalendarEntry`
  query rather than going through `WorkingDayResolver`. It is a *reader*, not a
  writer of deliveries, so the divergence is cosmetic today — but it is a second
  reader of one rule, which is exactly what CON-0001 says not to have.
* **Collections are not suppressed.** Only delivery generation is automatic;
  milk arriving from a supplier is recorded by a person, and a holiday does not
  stop a farmer turning up.
* **No per-centre run record.** The run row reports one `skipped_holiday` count
  for the tenant; which centres were shut is discoverable from the calendar,
  not from the run.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-15 | Platform Engineering | DEMO-022: holidays suppress automatic delivery generation, per plan via its centre, through one resolver; a suppressed day is terminal and never backfilled; manual generation deliberately unchanged. |
