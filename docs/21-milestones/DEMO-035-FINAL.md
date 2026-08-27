---
id: DEMO-035-FINAL
title: DEMO-035 — Route-driven Delivery Generation
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-17
last-updated: 2026-08-17
related: [DEMO-034-FINAL, DEMO-016-FINAL, DEMO-022-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-035 — Route-driven Delivery Generation

The change that makes DEMO-034's route layer **load-bearing** rather than
descriptive: a configured route with ordered stops now produces its own day's
deliveries. **No new generator, no new constraint, and no schema change.**

---

## 1. What already existed

| Concern | What was there |
| --- | --- |
| Who receives a delivery | `_due_plans_query(tenant_id, day)` in `delivery/generation.py` — active, in-date, unpaused `DeliveryPlan` rows joined to `Customer`, with the weekday mask applied in Python. |
| The generator | `generate_for_day(session, tenant_id, day, actor_id, is_working)` — builds rows, batches them, returns counts. |
| Idempotency | **`uq_delivery_customer_date_slot`** plus `_insert_ignoring_conflicts()`, an `INSERT … ON CONFLICT DO NOTHING` written for whichever dialect is bound. Already the guard that made the scheduler safe against four uvicorn workers. |
| Working days | `WorkingDayResolver.is_working(center_id)`, passed into the generator as a callable. |
| The day's record | `DeliveryGenerationRun`, unique on **(tenant, business_date)**, claimed by `record_run()`. |
| The route layer | DEMO-034's `route`, `route_stop`, `vehicle`, `driver`, `delivery_run` — with a run already carrying route, business date and slot. |
| Composition seam | `DeliveryService.status_by_customer()` and `CustomerService.directory()`. |

## 2. What was actually missing

**One thing: a way to scope the round.** The only generator produced the whole
tenant's round, so "generate this route" had no meaning — and DEMO-034's run
could describe a round it had no way to create.

Everything else the work order asked for already existed and was reused
verbatim: idempotency, holiday suppression, tenant isolation, business dates,
and the delivery domain's rules about quantity, rate and `scheduled`.

## 3. What DEMO-035 changed

Four files, no migration.

1. **`delivery/generation.py`** — `_due_plans_query` and `generate_for_day`
   gained two optional narrowings, `customer_ids` and `slot`. `None` means "no
   restriction", so the scheduler's call is byte-for-byte unchanged.
2. **`delivery/service.py`** — `generate_for_customers(...)`, the delivery
   module's own scoped entry point, audited as
   `sales.delivery.generated_for_route`.
3. **`logistics/service.py`** — `generate_for_run(run_id)`: validates, resolves
   the route's stops, and asks the delivery module. It computes no quantity, no
   price and no date arithmetic.
4. **`api/routes.py`** — `POST /v1/delivery-runs/{run_id}/generate`, behind
   `logistics.run.manage`.

Plus a **one-line fix to a pre-existing defect** in `customer/service.py` — see §5.

## 4. Architectural decisions

### Narrow the existing generator; do not fork it

A route round is the tenant's round restricted to the households on one route,
in one slot. Every other rule still applies, which is exactly why the narrowing
lives in `_due_plans_query` rather than in a second generator that would compute
its own quantities and prices and disagree within a milestone.

### Route generation deliberately does NOT go through `record_run`

This is the defect the milestone would otherwise have shipped, and it is worth
stating plainly:

> `record_run()` **claims the tenant's DATE** via `uq_generation_run_tenant_date`
> and hands whoever loses the claim a `GenerationResult` of `created: 0`.
> Correct for the scheduler, where a day has one whole-tenant round. Routed
> through it, the **first route of the day would claim the date and every later
> route would silently generate nothing while reporting success.**

So route generation calls `generate_for_day` directly.
`DeliveryGenerationRun` stays what it is: the record of the tenant's day, not
of one route. Idempotency is not weaker for skipping it — it never came from
there. It comes from `uq_delivery_customer_date_slot`.

Proven twice: `test_two_routes_on_the_same_day_both_generate` (SQLite) and
`test_two_routes_generating_at_once_do_not_block_each_other` (real PostgreSQL,
concurrent connections).

### Slot is part of the narrowing

A `DeliveryPlan` carries its own slot. Without narrowing on it, a **morning** run
would generate the evening round too — and the evening run would then report
`created: 0`, a whole slot delivered on paper by the wrong van.

### The architectural gap: no route reference on a delivery — and none was added

`milk_delivery` has no place for a route. The work order asked for the gap to be
reported before any schema field was invented, so: **the smallest justified
extension is none.**

The run view already joins stops to deliveries on `(customer, date, slot)`,
which is *unique* — so a `route_id` column would be a **second answer** to
"which route served this delivery", derivable from `route_stop` and able to
disagree with it the moment a stop moves between routes. A test,
`test_no_route_reference_was_added_to_the_delivery_table`, now fails if anybody
adds one without revisiting this decision.

The cost is real and worth naming: a delivery cannot be attributed to the route
that generated it *after* its stop has been reassigned. No requirement for that
exists in the repository today.

### Refusals reuse the existing error conventions

`ConflictError` → 409 for an inactive route, an empty route, a closed run and a
non-working day; `NotFoundError` → 404 for another dairy's run, never 403.

The working-day check runs **again** at generation, not only at run creation: a
holiday can be declared between planning a round and generating it.

## 5. Defects discovered

### 1. Pre-existing — `set_plan` superseded across slots

**Classification: pre-existing defect**, in DEMO-016's territory, found by
*executing* DEMO-035 rather than by reading.

`CustomerService.set_plan()` deactivated every active plan matching
`(tenant, customer, product)` — **ignoring `slot`**. So agreeing an evening rate
silently stopped the morning deliveries, and a household on a twice-daily round
stopped receiving its morning milk with nothing anywhere saying so.

`DeliveryPlan`'s own docstring had said for two milestones that *"a customer
taking milk twice a day has two plans"*. The service made that impossible to
express through the API.

It surfaced here because a slot-scoped generator is meaningless if a customer
can never hold two slots. **Fixed** by adding `DeliveryPlan.slot == plan.slot`
to the supersede query — necessary for this milestone, and not expanded beyond
it. Two regression tests were added in `test_standing_orders.py`, one for the
new behaviour and one asserting a rate change still supersedes *within* a slot.
Mutation-checked: removing the line fails both.

### 2. Test defect — two portal tests were timing-dependent

**Classification: test defect**, written by me in DEMO-034. Two tests waited on
a *static* heading and then reached for a run-dependent button, so they passed
when the machine was fast and failed when it was busy. They now wait for the
element they actually need. This is the third instance of the same mistake in
this file; the pattern is now consistent throughout it.

### 3. Avoided, not shipped — the `record_run` claim

**Classification: would have been a defect introduced by DEMO-035.** Caught in
design by reading `record_run`'s claim semantics, and locked down by two tests
before any code was written to depend on it.

No defect was found in the logistics, calendar, notification or financial
domains.

## 6. Test results

**Backend** — `tests/test_route_generation.py`, **23 tests**: the normal round;
route order end to end; only the route's households; morning-does-not-generate-
evening; generate-twice; two routes in one day; whole-tenant generator
compatibility; empty route refused; inactive route; 404 run; cross-tenant 404
with nothing generated; holiday declared after planning; completed and cancelled
runs refused; grant separation; 401; inactive customer skipped; not-due
reported; the round worth 0.00 with no invoice; no route column on
`milk_delivery`; statement budget; a future-dated run; and an empty customer set
generating nothing rather than everything.

Plus **2 regression tests** in `test_standing_orders.py` for the plan fix.

**Every guard mutation-checked:**

| Guard disabled | Tests that fail |
| --- | --- |
| empty route refused | 1 |
| closed run refused | 2 |
| holiday refused at generation | 1 |
| slot narrowing | 1 |
| supersede is per slot | 2 |
| empty set ≠ whole dairy | 1 |

The last one **survived the first mutation run** — the API refuses an empty
route earlier, so nothing exercised the claim the code made. A direct test of
`generate_for_day(customer_ids=set())` was added; the mutation now fails.

**Portal** — 3 new tests (generation counts, `created: 0` reported as
*already there* rather than a bare zero, no generate button on a closed run),
one portal mutation checked. Full portal suite **296 passed**, `tsc` and
`eslint` clean.

**Mobile** — **no change**, deliberately. Generation is an office action, and
the round screen already reads generated deliveries as ordinary ones.
`flutter analyze`: no issues.

**Backend suite** — result recorded in §8 below.

## 7. Concurrency and idempotency proof

`tests/test_route_generation_postgres.py` — **7 tests**, wired into
`infra/ci/postgres-proof.sh`:

* a route round generates on the real engine, `scheduled` and worth `0.00`;
* **three concurrent connections generating the same round create it once** —
  the `created` counts sum to exactly one round however they interleave;
* **two routes generating simultaneously both land** — the proof that the
  tenant-day claim is not in the path;
* `uq_delivery_customer_date_slot` asserted **present by name**, because no new
  constraint was invented for this milestone;
* a generated round is invisible to another dairy;
* another dairy's customer ids generate **nothing** (the generator filters on
  `tenant_id` as well as the set, and RLS refuses the read besides);
* generation writes nothing financial.

```
./infra/ci/verify-postgres.sh   →   242 passed
                                    POSTGRESQL PROOF PASSED
```

(235 before this milestone.)

## 8. Production verification

Deployed `main-2732244` to **https://dev.phoenixsoft.in**. A pre-deployment
backup was taken first: `pre-demo035-20260817T094117Z.dump`, 3.1 MB.

**No migration, and the deploy said so** — the schema stayed at
`b5d1e07a4c39` and no "the schema moved" notice was printed. That is the
correct outcome: this milestone changed four Python files and added no table
and no column.

| Check | Result |
| --- | --- |
| `/health/live`, `/health/ready` | **200** |
| `POST /v1/delivery-runs/{id}/generate` in the live schema | present |
| The same, unauthenticated | **401** |
| Schema version | `b5d1e07a4c39` — unchanged |

**The deployed code, inspected in the running container:**

```
generate_for_day narrowings: ['customer_ids', 'slot']
delivery scoped entry point:  True
logistics generate_for_run:   True
logistics does NOT call record_run: True
logistics computes no price:  True
supersede is per slot:        True
```

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

### What could NOT be proven in production, and why

**Production holds 0 routes, 0 stops and 0 runs.** Route generation therefore
could not be exercised there at all, and **no route, stop, run or delivery was
manufactured to make it look as though it had been.** The work order is
explicit on this point and it is the right call: creating fake households on a
fake round would have written 1,303 → 1,3xx into the delivery table of a
system whose financial totals this report claims are untouched.

So the production evidence is: the endpoint exists, refuses an anonymous
caller, the deployed code has the right shape, the schema did not move, and no
figure changed. **The behaviour itself is proven only by the test suite and the
PostgreSQL proof** — see §11.

### The deploy failed once first, and the cause was mine

The first attempt failed at step 3 of 6 with **`No space left on device`**. The
production disk was at **100%** (196 MB free). Production was unaffected — it
stayed on `main-483bca8` and kept serving throughout, which is the deploy
script's rollback behaviour working.

The cause: since DEMO-033 my `rsync` to the host had been shipping
**`apps/mobile/build/`** — 2.2 GB of Flutter artifacts created by running the
mobile tests locally. Release directories grew from ~877 MB to **3.4 GB each**.

`infra/deploy/disk-guard.sh` exists precisely for this (written after "the disk
reached 100% twice during DEMO-009"), its systemd timer was **active and had
run two hours earlier**, and it was working exactly as designed — it keeps 3
releases, which had silently become a 10 GB commitment instead of a 2.6 GB one.
**The guard did not fail; I broke its assumption.**

Fixed both halves: `--force` reclaimed to 89%, and the sync now excludes
`build/`, `.dart_tool/`, `.next/` and the Python caches, with
`--delete-excluded` so what had already been shipped was removed. Staging fell
from **3.4 GB to 714 MB** and the disk to **82%, 7.1 GB free**. Releases are
back to their intended size, so the guard's arithmetic holds again.

Recorded here rather than quietly fixed, because a deploy pipeline that fills a
production disk is worth one paragraph in the milestone that did it.

## 9. Financial safety

Generation creates `scheduled` deliveries with `amount = 0.00`. `scheduled` is
absent from `BILLABLE_STATUSES`, which is the single omission that makes
generation safe to deploy at all — a generator producing billable rows would
invoice a dairy's whole round every morning whether the milk arrived or not.

Asserted three ways: an end-to-end test comparing invoice counts and summed
delivery amounts across a generation; the same on real PostgreSQL; and the
production before/after comparison in §8.

## 10. Known limitations

1. **A delivery cannot be attributed to the route that generated it** after its
   stop is reassigned — the deliberate consequence of adding no `route_id`
   column (§4).
2. **Generation is manual.** The scheduler still generates the whole tenant's
   round; it does not walk routes. Both paths are safe together (a test proves
   it), but a dairy adopting routes gets its round from the scheduler unless
   somebody presses the button.
3. **No partial regeneration.** A stop added to a route after generation needs
   the endpoint called again — which is safe and idempotent, but there is no
   notification that the round has changed.
4. **One slot per run.** A route serving both slots needs two runs, which is by
   design but means two button presses.
5. **`skipped_holiday` is always 0 in practice** on this path, because the
   working-day check refuses the whole call first. It is reported for symmetry
   with the scheduler's result shape.

## 11. REAL versus TEST versus NOT PROVEN

**REAL** — in the deployed product:

* route-scoped, slot-scoped delivery generation through the existing generator;
* idempotency by the existing unique constraint and ON CONFLICT;
* refusals for inactive route, empty route, closed run, non-working day, and
  another dairy's run;
* the per-slot plan supersede fix;
* the portal button and its counts.

**TEST** — proven here, not in production traffic:

* concurrent generation (three connections; two routes at once) — proven on
  real PostgreSQL, **not observed in production**;
* the full operator flow from route to generated round;
* every refusal path.

**NOT PROVEN — and not claimed:**

* **No production round was generated.** Verification was read-only — see §8.
* **No real driver, no real customer delivery**, no GPS, no maps, no
  optimization, no capacity planning.
* The largest round exercised anywhere is **three stops**.
* Nothing here has been used at scale or by a dairy.

## 12. Recommended DEMO-036

**Not started.** Smallest first:

1. **Teach the scheduler about routes** — generate route by route where routes
   exist, falling back to the whole-tenant round where they do not. This is the
   change that makes route generation the *normal* path rather than a button.
2. **Report the round by route** — extend `DeliveryReport` with a route
   breakdown, so "why was the round short?" has a per-route answer.
3. **Let a rider move the run from the phone**, through the existing offline
   queue.

---

## Change Log

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | 2026-08-17 | DEMO-035 delivered — route-scoped delivery generation. |
