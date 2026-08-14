---
id: DEMO-016-FINAL
title: DEMO-016 — Delivery Plans, Standing Orders & Daily Delivery Automation
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-14
last-updated: 2026-08-14
related: [DEMO-015-FINAL, DEMO-015-SURVEY, DEMO-009-FINAL, DEMO-014-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-016 — Delivery Plans, Standing Orders & Daily Delivery Automation

DEMO-015 proved the chain and left a dairy typing six hundred deliveries every
morning. This removes that.

The shape of the milestone was decided by what the survey found: **a
`DeliveryPlan` already existed.** It said what a customer takes and at what
price, and it already superseded rather than edited on change. Two of the work
order's requirements were therefore already true, and one of them — §8, that
editing a plan must not rewrite history — needed no code at all.

**Four defects found, three of them by tests written for this milestone.**
**AWS cost: none.**

---

## 1. What was built

| | |
|---|---|
| **The schedule** | weekdays, end date, pause window, per-weekday quantities — added to the plan that already existed |
| **The generator** | one bulk `INSERT … ON CONFLICT DO NOTHING` per round |
| **Confirmation** | recording over a generated delivery fills it in rather than colliding |
| **Planned vs completed** | the operator's "how many are left?" on the daily report |
| **Portal** | plan card with schedule and next delivery, pause/resume, a generate button |
| **Mobile** | nothing, by design — except the status word, which was English |

## 2. Existing functionality reused

Reused rather than rebuilt, and each one is why the change is small:

* **`delivery_plan`** — extended, not replaced. It has carried `tenant_id` and
  a FORCEd policy since DEMO-009, and `core/rls.py` derives the protected set
  from the metadata, so the new columns are covered with **no RLS work**.
* **Superseding** — the module's existing behaviour on a rate change is
  exactly §8's requirement for a schedule change.
* **`uq_delivery_customer_date_slot`** — the DEMO-009 constraint that makes
  idempotency a database property rather than an application check.
* **`BILLABLE_STATUSES`** — every report, balance and invoice already filters
  on it, so leaving `scheduled` out of it was the whole safety mechanism.
* **`business_today()` / `tenant_timezone()`** — DEMO-014's clock.
* **The audit service, the permission registry, the offline queue, the
  delivery/report/billing chain** — all unchanged.

## 3. Database changes

One migration, `d71c4a9f6e28`, on `delivery_plan` only:

| Column | Shape |
|---|---|
| `weekdays` | `String(7) NOT NULL DEFAULT '1111111'` — Monday first |
| `effective_to` | nullable — null is ongoing |
| `paused_from` / `paused_to` | nullable — one holiday window |
| `quantity_overrides` | JSON, nullable, sparse |
| `center_id` | nullable, indexed |
| `slot` | `String(10) NOT NULL DEFAULT 'morning'` |
| `created_by` | nullable |
| `updated_at` | defaulted to now |

Plus `ix_delivery_plan_generation (tenant_id, active, effective_from,
effective_to)` — the generator's own query — and `ix_delivery_plan_center_id`.

**Every column is nullable or server-defaulted**, so no existing plan is
invalidated: one written before today becomes a daily standing order, which is
what it already meant in practice. Verified on real PostgreSQL against a row
inserted at the previous revision, through **up → down → up**.

`alembic --autogenerate` produces an empty diff against the models.

**No financial table is touched in either direction**, so a rollback costs
schedules and nothing else.

## 4. The delivery-plan model

The schedule is **seven characters, Monday first** — `"1111111"` every day,
`"1111110"` Monday to Saturday, `"1111100"` weekdays. Not seven booleans (a
schema change every time somebody wants a different question answered) and not
a bitmask (unreadable in a psql session at 6am, when the question is why a
household got no milk on Tuesday).

`quantity_overrides` is sparse JSON keyed by the same weekday index — a hotel
that takes more at the weekend sets one key and every household sets none.

One pause window, not a list: two overlapping holidays is a calendar, and a
calendar is the scheduling engine §3 says not to build. A second holiday is
set by superseding, like every other change.

The rules live in `modules/customer/schedule.py` as **module-level functions
over plain values** — no session, no ORM, no clock — so they are tested
exhaustively without a database.

## 5. The generation mechanism

`POST /v1/deliveries/generate`, its own permission `sales.delivery.generate`,
separate from `sales.delivery.record`: recording is what a rider does all
morning, and this creates a whole dairy's day.

1. resolve the business date through the organization's timezone;
2. one query for active, in-date, unpaused plans, joined to the customer's
   status;
3. filter the weekday mask in Python — a `substr(weekdays, ?, 1) = '1'` would
   be unindexable and dialect-flavoured;
4. build the rows and insert them in batches of 1,000.

It returns counts rather than rows: `due`, `created`, `already_present`,
`not_due`, `inactive_customers`. `not_due` exists so **"nothing generated" can
be told apart from "nothing was due"**.

**Generated rows are `scheduled`, which is not in `BILLABLE_STATUSES`.** That
single omission is what makes this safe to deploy: a generator producing
billable rows would invoice a dairy's whole round every morning whether the
milk arrived or not, silently, and the first to notice would be a customer
reading their bill. A test asserts that billing a scheduled round is refused.

## 6. Idempotency strategy

**A unique constraint, not a check.** `INSERT … ON CONFLICT DO NOTHING`
against `uq_delivery_customer_date_slot`, which has existed since DEMO-009.

§5 says not to rely only on application-level checks and it is right: a
SELECT-then-INSERT has a window between the look and the leap, and the morning
two operators press the button at once is the morning it matters. Both
dialects support the clause and SQLAlchemy spells it differently for each, so
the code picks by the bind — the guarantee the tests exercise on SQLite is the
same one production gets on PostgreSQL.

A second run reports `created: 0, already_present: N`.

## 7. Portal changes

The plan card becomes a standing order: schedule, start and end, next
delivery, pause/resume with a date range. The schedule reads as a sentence in
the reader's language because the platform sends a **key** —
`schedule.mon_sat` — and the catalog decides the words.

The generate button is deliberately **not** disabled after a run: idempotency
is a database property, and hiding the button would be the screen pretending a
guarantee it does not own.

## 8. Mobile changes

Almost none, which is §11 working. A generated delivery already showed as
"needs action" exactly as an unrecorded one does, and confirming it is the
same call the operator already made — the *server* turns that into a
confirmation rather than a collision, so the phone, the portal and the offline
queue replaying a call made in a village with no signal all use one path.

The one change was a defect: the round printed the raw status string the API
sends, so a Hindi-speaking rider read the English word the column stores.

## 9. Demo data

Every seeded customer now carries a real schedule, applied round-robin across
four shapes so the mix is the one §15 asks for and the one a real dairy has:
daily, Monday–Saturday, weekdays only, and a variable plan whose weekend
quantity is computed from the customer's own standing quantity.

The seeder then **generates today's round twice** and fails if the second run
creates anything — so idempotency is proven against real seeded data on every
seed, not only in the test suite.

## 10. Tests

| Suite | Result |
|---|---|
| Backend | *(recorded at the end of this run)* |
| Portal | **227 passed** |
| Mobile | **125 passed**, `flutter analyze` clean |
| PostgreSQL proof | **PASSED** — 62 policies, FORCEd, app role NOBYPASSRLS |
| Sales chain proof | **the chain holds** |
| Migration | up → down → up on real PostgreSQL, with a pre-existing row |

50 new backend tests, 5 portal, 2 mobile.

## 11. Defects discovered and fixed

**1. The portal's fallback translator ignored its variables.** `useLocale()`
outside a `LocaleProvider` — an error boundary, a page mid-hydration — returned
a `t` that looked up the English string and handed back `{count} deliveries
generated` verbatim. Degrading to English is the design; degrading to
placeholder syntax in front of a reader is a bug.

**2. The generation banner conflated "nothing due" with "nothing new".** A
second run finds six due and creates none — idempotency working, not an empty
day — and the screen said "No standing order is due today".

**3. The mobile round printed the status the database stores.** English, to a
Hindi-speaking rider, on an otherwise fully translated screen. The third
instance of this defect class in three milestones, and the reason both guards
now exist.

**4. `sales-chain-proof.sh` failed when run without an argument.** My own
DEMO-015 script passed `"${1:-}"`, so with no output path it handed the proof
an empty string, which `pathlib.Path("")` reads as the current directory — and
it failed with `IsADirectoryError` *after* doing all the work. It had only
ever been run with a path. Found by running it the way CI does.

## 12. Known limitations

* **One pause window per plan.** A second holiday supersedes the plan. A list
  would be a calendar, which §3 excludes.
* **No recurrence beyond a weekly mask** — no alternating weeks, no
  nth-weekday-of-month, no public-holiday calendar.
* **Generation is on demand, not scheduled.** There is no cron: a dairy presses
  the button, or a caller with the permission posts to the endpoint. Wiring it
  to a scheduler is a deployment decision and the next milestone's work.
* **A plan generates into one slot.** A customer taking milk morning and
  evening has two plans, which is also how they get two rates.
* **`center_id` is stored and indexed but not yet used to scope generation** —
  the column is there for the centre-scoped round a multi-centre dairy will
  want; today generation is per tenant.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-14 | Platform Engineering | DEMO-016 delivered: a schedule on the plan that already existed, idempotent bulk generation guarded by a database constraint, confirmation through the operator's existing call, and four defects. |
