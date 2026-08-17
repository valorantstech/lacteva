---
id: DEMO-034-FINAL
title: DEMO-034 — Operations Foundation: Routes, Vehicles, Drivers & Delivery Runs
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-17
last-updated: 2026-08-17
related: [DEMO-033-FINAL, DEMO-016-FINAL, DEMO-022-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-034 — Operations Foundation: Routes, Vehicles, Drivers & Delivery Runs

The smallest operational route layer that connects existing delivery plans to
real daily execution. **No GPS, no maps, no route optimization, no fleet
management** — and no second source of delivery truth.

---

## 1. What already existed

The survey found far more than the work order assumed, and it changed the design.

| Concern | What was already there |
| --- | --- |
| Standing orders | `customer/models.py:DeliveryPlan` — product, rate, currency, `effective_from/to`, a seven-character `weekdays` mask, a pause window, per-weekday quantity overrides, **`center_id`** and **`slot`**. Superseded, never edited. |
| Delivery records | `delivery/models.py:MilkDelivery` — unique on (tenant, customer, date, slot), with `plan_id` and `invoice_id`. |
| A delivery state machine | **Already existed**: `scheduled → delivered / skipped / returned / cancelled`, with `BILLABLE_STATUSES = ("delivered",)` and recording-over-a-`scheduled`-row *filling it in*. |
| A daily operational report | **Already existed and is rich**: `DeliveryReport` — deliveries, customers_served, quantities, `planned`, `planned_quantity`, skipped, returned, cancelled, by-day and by-customer. |
| Generation and scheduling | `delivery/generation.py` + `scheduler.py`, with `DeliveryGenerationRun` — one row per tenant per business date, retried up to three times. |
| Business dates | `core/business_time.py` (`business_today`, `business_date_of`, `month_bounds`) and `core/org_context.py:tenant_timezone`. |
| Working days | `business_calendar/service.py:WorkingDayResolver.is_working(center_id)` — the one resolution path (DEMO-022). |
| A mobile round | **`apps/mobile/lib/src/deliveries.dart:DeliveryRoundScreen` already existed** — today's round, every customer, offline queue, big thumb targets, asks the platform which day it is. |
| Audit | `AuditService.record(...)`, one mechanism, injected as `deps.Audit`. |
| Membership shape | `SupplierCenterAssignment(supplier_id, center_id)` — the pattern a route's stops should imitate. |
| Asset + person shape | `Device` and `OperatorAssignment` in `operational_readiness`. |

## 2. What was missing

1. **Route** — no ordered grouping of stops at all. `DeliveryPlan.center_id` is a *centre*, not a round.
2. **Vehicle** — nothing. No column, no table, no reference.
3. **Driver** — nothing.
4. **A daily execution record** for distribution. `DeliveryGenerationRun` is a *scheduler job log*, not an operational run.
5. **Ordering** — `MilkDelivery` has no sequence; a round had no first or last stop, so the mobile app loaded every active customer in whatever order the listing returned.

Searched and confirmed **absent**: any route/vehicle/driver/fleet reference (every grep hit was HTTP routing), any latitude/longitude/geo concept, and any GPS infrastructure.

## 3. What DEMO-034 added

A new `logistics` bounded context — five tenant-owned tables, one service, one
router, and the minimum client surface.

| Table | Holds |
| --- | --- |
| `route` | code (unique per tenant), name, nullable `center_id`, `active`, notes |
| `route_stop` | route + `customer_id` + `position`; unique on **(route, customer)** |
| `vehicle` | registration (unique per tenant), label, nullable `center_id`, `active` |
| `driver` | code, full name, phone, **nullable `user_id`**, nullable `center_id`, `active` |
| `delivery_run` | business date, route, slot, vehicle, driver, status, timestamps; unique on **(tenant, route, business_date, slot)** |

Six permissions — `logistics.{route,fleet,run}.{read,manage}` — granted to
`tenant-admin`, `ORGANIZATION_MANAGER` (full), `SALES_OFFICER` (reads plus
`run.manage`), `tenant-viewer` and `AUDITOR` (reads only).

**13 operations across 9 paths**, and no more: route create/list/get, stops
replace, vehicle create/list, driver create/list, run create/list/get,
assignment, status.

## 4. Domain and architectural decisions

### The decisive constraint came from the governed docs, not the code

`CAP-0006 CMA.DST.01` (Distribution & Fulfillment) declares a dependency on
`CAP-0003 MCL.LGX.01` — **"transport capability, *shared with collection*"**.

So **vehicles and drivers are direction-neutral**. A tanker that fetches milk in
the morning and a van that delivers it in the afternoon are the same kind of
thing to this module. A delivery-only `vehicle` table would have contradicted
the capability register on the day it shipped, and a future collection route
would have needed a second one. The *route* is delivery-side; the *fleet* is not.

### `assigned` was deliberately not implemented

The work order suggested `PLANNED → ASSIGNED → IN_PROGRESS → COMPLETED`. The
implemented states are **`planned → in_progress → completed`, plus
`cancelled`**, and `assigned` is absent because it is *derivable*: a run with a
`driver_id` and a `vehicle_id` is assigned. A status repeating a derivable fact
drifts the first time somebody clears a driver without moving the status back.

What a dairy actually needs is the guarantee that a run cannot **start**
unassigned — a guard, not a state, and now **BR-0028**. Repository precedent
supports it: `DeliveryGenerationRun`'s own comment says "deliberately three
states and not a workflow".

`completed` and `cancelled` are terminal. Reopening a closed round would let
this module disagree with the deliveries it describes.

### The route layer composes; it never restates

Every figure on a run view is read at request time:

* a stop's outcome is `MilkDelivery.status`, fetched through
  `DeliveryService.status_by_customer()` — a **new batch method on the module
  that owns the table**;
* a stop's name and code come from `CustomerService.directory()`, which already
  existed for exactly this shape.

The first draft of the service imported `Customer` and `MilkDelivery` directly
— the same boundary violation DEMO-030 was caught committing. It was corrected
before any test ran, and an **AST test now fails if any logistics file imports
another module's models**.

Consequences the design buys: a delivery recorded *after* a run starts appears
the next time anybody looks; a run can never carry a stale copy of what
happened; and completing a run cannot create a financial event because the
module has no way to reach a financial table.

### Deliberately not built

No stop-level status (the delivery domain has the only one that matters), no
vehicle capacity (unused without load planning; `MCL.LGX.02` covers fleet
utilization and is out of scope), no GPS, no maps, no optimization, no
maintenance, no payroll, no attendance, no geofencing.

### Smaller choices worth recording

* **`position` is not unique.** Making it unique turns "swap stop 3 and 4" into
  a dance around the constraint; the tiebreak is `position, created_at`, which
  is deterministic. Uniqueness is on **(route, customer)** — the constraint a
  duplicate-association race must lose to.
* **Stops are replaced, not added and removed.** The *order is the payload*, so
  the endpoint is a `PUT` of a list. Two endpoints would have needed a third to
  reorder.
* **A driver need not have a login.** `user_id` is nullable because a hired
  tanker driver often has no account, and requiring one would mean either
  inventing logins for contractors or being unable to record who drove.
* **A run is refused on a non-working day**, resolved through
  `WorkingDayResolver` at the route's centre — consistent with generation, which
  already skips those days.

## 5. Defects found

**One, in this milestone's own code, found by a test rather than by reading.**

The duplicate-run conflict escaped as a **500 instead of a 409**. The service
matched the constraint by name:

```python
if "uq_delivery_run_route_date_slot" in str(exc):
```

That is a PostgreSQL habit. SQLite reports `UNIQUE constraint failed:
delivery_run.tenant_id, delivery_run.route_id, …` and **names no constraint at
all**, so the branch never fired and the `IntegrityError` propagated. Worse, the
failed flush poisoned the session.

Fixed three ways at once: a pre-check `SELECT` for the ordinary case (a clear
message rather than a database error), the insert moved **inside**
`begin_nested()` so the transaction survives losing the race (the DEMO-025
lesson), and the catch narrowed to `IntegrityError` — which has exactly one
meaning on this table, on either engine.

**One test of mine was passing for the wrong reason.** The portal's
"a completed run is terminal" test asserted after a *static* heading rather than
after the run arrived, so it also passed with an empty list — and a mutation
that offered "Start" on a completed run **survived it**. Caught by mutation
testing, not by reading. The test now waits for the run itself.

No pre-existing defect was found in the delivery, customer, calendar or
notification domains.

## 6. Tests

`tests/test_logistics.py` — **29 tests**, all passing. Route ordering and
reordering, duplicate-stop refusal, cross-tenant stop refusal, code uniqueness,
the business-date default, the same route twice in a day (refused) and twice in
two slots (allowed), the start-without-driver guard, the full walk, terminality
in three directions, unknown status, inactive vehicle, the delivery-domain
composition, the no-money schema assertion, the end-to-end financial check, the
module-boundary AST check, business dates in **India and Kenya**, non-working-day
refusal, 401 on all eight endpoints, cross-tenant **404 not 403**, the
`run.manage` ≠ `route.manage` separation, and six audit properties.

**Every guard was mutation-checked** — disabling it fails exactly the tests that
claim it:

| Guard disabled | Tests that fail |
| --- | --- |
| start without driver/vehicle | 1 |
| non-working day refused | 1 |
| duplicate stop refused | 1 |
| illegal transition refused | 3 |
| inactive vehicle refused | 1 |

Portal: **7 new tests**, three portal mutations each caught by exactly one test
(terminal-run actions, verbatim refusal, no client-side date). Full portal suite
**293 passed**.

Mobile: **4 new tests** on the pure ordering rule, including that a customer
*not* on the route is kept rather than hidden — dropping them would be the app
quietly deciding not to deliver to somebody who pays. `flutter analyze`: no
issues; full `flutter test`: all passed.

## 7. PostgreSQL proof

`tests/test_logistics_postgres.py` — **20 tests**, wired into
`infra/ci/postgres-proof.sh`'s explicit file list so it runs in the pipeline
rather than beside it.

* RLS **enabled and FORCED** on each of the five tables (parametrised).
* A policy with **both** `USING` and `WITH CHECK` on each of the five.
* Route, vehicle, driver, stop and run all invisible to another dairy.
* Another dairy cannot **write** a route into this one (the `WITH CHECK` half, which a read-only proof would miss).
* Another dairy's `UPDATE` of this dairy's run affects **zero rows**.
* Three concurrent "create today's run" attempts → **one row, two refusals**.
* Two concurrent stop insertions for one customer → **one row**.
* Two concurrent completions → **the transition applies once** (CAS).
* The live schema carries **no financial column** on any logistics table.
* **No foreign key** joins the route layer to any other table, in either direction.

```
./infra/ci/verify-postgres.sh   →   235 passed
                                    POSTGRESQL PROOF PASSED
```

(215 before this milestone.) Real PostgreSQL from the `pgserver` wheel, no
Docker, no root.

## 8. Portal

One new page, `/routes` — "Routes and runs" — using the existing shell, cards,
tiles and status badges. **No visual redesign, and no UI polish work.**

It shows the routes with their stop counts, today's runs with only the
transitions each run is actually allowed, vehicle and driver assignment, and
three small register cards. The platform's refusals are shown **verbatim**,
because "a run needs both a driver and a vehicle before it can start" is the
sentence an operator has to act on.

**No figure of money appears anywhere on the page**, asserted by a test that
scans the rendered DOM. Navigation entry gated on `logistics.route.read`.

## 9. Mobile

The round screen **already existed** and was not redesigned. Two minimal
additions:

1. `ApiClient.listDeliveryRuns()` — the date deliberately omitted, so the
   platform answers for the dairy's today.
2. The round is now walked in the **route's order**, and a banner names the
   route, driver, vehicle and run status.

Both degrade cleanly: a dairy that has not adopted routes, or a rider without
the grant, gets exactly the round they got before. A customer not on the route
is shown **after** the route rather than hidden.

**No GPS, no map, no background location.** Nothing was added to the offline
queue: a run is read-only on the phone in this milestone.

## 10. API

Existing FastAPI conventions throughout: `logistics_router` with
`IdempotentRoute`, `require_permission` per endpoint, services built only in
`api/deps.py`, `NotFoundError`/`ConflictError` rendering as RFC-9457
problem+json. 13 operations across 9 paths, and no per-stop endpoint — the
delivery domain already owns what happened at a stop.

## 11. RLS and security

Five tenant-owned tables, each with `tenant_id`, so `core/rls.py`'s
metadata-derived `tenant_tables()` covers them automatically — a table that
forgot its policy fails a build check rather than shipping. Policies created in
the migration with the standard statements, `ENABLE` **and** `FORCE`.

Proven live in §7 and §6: cross-tenant read, cross-tenant write, cross-tenant
update, 401 unauthenticated, 404 (never 403) for another dairy's route, and no
tenant role holding a platform-wide grant. No privileged shortcut was
introduced. `run.manage` does not imply `route.manage` — a driver who can start
today's round cannot redraw tomorrow's.

A driver's phone number is **not** copied into the audit detail: an audit trail
is read by more people than the record it describes.

## 12. Production verification

Deployed `main-483bca8` to **https://dev.phoenixsoft.in** through the existing
path. **The schema moved** — the deploy said so and printed the rollback caveat
— and landed on `b5d1e07a4c39`. A pre-deployment backup was taken first:
`pre-demo034-20260817T084827Z.dump`, 3.1 MB. Deploy checks all green, smoke test
passed.

**The five new tables, live:**

```
delivery_run | rls=t | forced=t | policies=1
driver       | rls=t | forced=t | policies=1
route        | rls=t | forced=t | policies=1
route_stop   | rls=t | forced=t | policies=1
vehicle      | rls=t | forced=t | policies=1
rows: 0 / 0 / 0 / 0 / 0
```

**Zero rows in every one of them.** No production delivery run, route, van or
driver was manufactured to demonstrate the feature — the work order asked for
safe, read-only verification and that is what was done.

**The domain rules, read off the deployed code:**

```
run statuses:        ('planned', 'in_progress', 'completed', 'cancelled')
assigned is absent:  True
terminal:            completed -> [],  cancelled -> []
logistics permissions: 6
driver cannot redraw routes: True
financial columns on the route layer: []
```

**Existing functionality unchanged, verified rather than assumed:**

| Check | Result |
| --- | --- |
| `milk_delivery` statuses | `('scheduled','delivered','skipped','returned','cancelled')` — unchanged |
| `BILLABLE_STATUSES` | `('delivered',)` — unchanged |
| `milk_delivery` route/run/vehicle/driver columns | **0** — the delivery domain gained nothing |
| Foreign keys joining the route layer to any table | **none, in either direction** |
| Notification template registry | **57**, `ready_whatsapp = 0` — DEMO-033 intact |
| `messaging_mode` | `test` |
| Notifications created since the deploy | **0** |

**The live API:** 9 paths, 13 operations, exactly as designed. `/health/live`
and `/health/ready` both **200**. Every logistics endpoint answers **401**
unauthenticated (four GETs and a POST checked individually).

**Financial safety — the before and after files are byte-identical:**

| Table | Count | Sum |
| --- | --- | --- |
| `settlement` | 84 → 84 | 353,417.50 → 353,417.50 |
| `customer_invoice` | 31 → 31 | 809,038.00 → 809,038.00 |
| `customer_payment` | 24 → 24 | 444,105.00 → 444,105.00 |
| `customer_receipt` | 24 → 24 | 444,105.00 → 444,105.00 |
| `payment` | 42 → 42 | 168,675.50 → 168,675.50 |
| `receipt` | 36 → 36 | 138,903.00 → 138,903.00 |
| `milk_delivery` | 1,303 → 1,303 | 821,667.00 → 821,667.00 |
| `delivery_plan` | 34 → 34 | — |

**The full suite found one failure, and it was the process working.**
`test_every_tenant_owned_table_is_covered_by_a_policy` refused the five new
tables. The migration *did* install their policies from its own snapshotted
list — what it had not done was say so in that test's deliberately
hand-written union, which exists precisely so a new tenant table cannot become
protected by accident. Registering `DEMO034_TABLES` fixed it, and the
registration was mutation-checked: removing it makes the guard fail again, so
the drift guard is still live rather than satisfied by an edit. That test has
now earned its keep six times — IDM-001, PROD-001, DEMO-009, DEMO-012,
DEMO-026 and DEMO-034.

**The portal page and the mobile round were NOT verified in a browser or on a
device.** The Chrome extension is not connected in this session and no handset
is attached, so both were verified by their own tests and by the API. Same gap
as the previous eight milestones, stated rather than glossed.

## 13. Financial safety

No existing table was altered; no financial table is read or written by the
migration or by anything it enables. Asserted three ways rather than asserted
once: a model-level check that no logistics column name looks financial, a
**live-schema** check of the same on real PostgreSQL, a check that no foreign
key joins the route layer to anything, and an end-to-end test that completes a
run and compares invoice counts and delivery amounts before and after.

## 14. Known limitations

1. **A run is read-only on mobile.** A rider can see the route order and who is
   driving; they cannot start or complete a run from the phone. That is a
   deliberate scope line, not an oversight.
2. **One run per route per slot per day.** A route that goes out twice in one
   slot (a second van covering half the round) is not representable. No dairy
   requirement for it was found in the repository.
3. **No stop-level timing.** Arrival and departure times per stop are not
   recorded, so "on-time %" — a KPI `MCL.RTE.01` names — cannot be computed yet.
4. **Vehicle capacity is absent**, so load planning and `MCL.RTE.02` capacity
   balancing are not possible.
5. **`position` allows ties.** Two stops can share a position; the order is
   still deterministic (`position, created_at`) but a UI that permits it would
   look odd.
6. **The Hindi and Arabic navigation labels** (`मार्ग और फेरे`,
   `المسارات والجولات`) are standard dictionary renderings of "routes and runs"
   and have **not been reviewed by a native speaker**. Every other user-facing
   string in this milestone is English only.
7. **The route layer is not yet wired into generation.** Deliveries are still
   generated for every due plan in the tenant, not per route. A run *describes*
   the round; it does not yet drive it.

## 15. What is real versus test-only

**REAL** — in the deployed product:

* the `logistics` module and its five tables, with RLS enforced by PostgreSQL;
* routes with ordered stops; direction-neutral vehicles and drivers;
* the daily run, its unique-per-(route, date, slot) identity, and its state machine;
* the start-unassigned guard (BR-0028) and CAS transitions;
* business-date resolution through the organization's timezone;
* the six permissions and their role grants;
* audit entries for route, fleet, run creation, assignment and status change;
* the portal page and the mobile route ordering.

**TEST-ONLY** — proven here, not in production traffic:

* concurrent run creation and concurrent completion (proven on real PostgreSQL, not observed in production);
* the full operator workflow end to end;
* the mobile ordering rule (a pure function, proven without a device).

**NOT PROVEN — and not claimed:**

* **No real driver has used this.** No dairy operator, roundsman or driver has run a real round through it.
* **No real customer delivery** has been executed against a route.
* **No GPS, no map, no live tracking, no geofencing** exists — none was built and none is implied.
* **No route optimization** of any kind.
* No production delivery run was manufactured to demonstrate the feature.
* Nothing here has been used at scale; the largest exercised round is three stops.

## 16. Recommended next milestone

**Not started.** For consideration only, smallest first:

1. **Generate per route.** Let the generator produce a day's deliveries route
   by route, so a short round can be explained by which route was short. This
   is the change that makes the route layer *load-bearing* rather than
   descriptive.
2. **Let a rider move the run from the phone** — start and complete, through the
   existing offline queue and its idempotency keys.
3. **Stop-level timestamps**, which unlock the on-time and adherence KPIs
   `MCL.RTE.01` already specifies.
4. **Collection routes**, reusing the same vehicles and drivers exactly as
   `MCL.LGX.01` intends — the reason the fleet was built direction-neutral.

---

## Change Log

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | 2026-08-17 | DEMO-034 delivered — routes, ordered stops, shared fleet, daily runs. |
