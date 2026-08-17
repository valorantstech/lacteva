---
id: DEMO-036-FINAL
title: DEMO-036 — Route-aware Scheduled Generation
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-17
last-updated: 2026-08-17
related: [DEMO-035-FINAL, DEMO-034-FINAL, DEMO-017-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-036 — Route-aware Scheduled Generation

The scheduler now generates route by route where a dairy has routes, and
exactly as before where it does not. **No migration, no new table, no new
column, and no portal or mobile change.**

---

## 1. What already existed

| Concern | What was there |
| --- | --- |
| Scheduler entry | `run_once(generation_hour, now)` → `run_for_tenant(tenant, …)` → `record_run(…)`. A polling loop registered in `core.workers`, because one timer cannot be 05:00 in Bengaluru and 05:00 in Nairobi at once. |
| Tenant clock | `should_run(now, timezone, generation_hour, last)` and `business_date_and_hour()`. |
| Business dates | `core/business_time.py`, per organization timezone. |
| Working days | `WorkingDayResolver.is_working(center_id)`, **passed into generation as a callable** so the delivery module gains no calendar dependency (DEMO-022). |
| The claim | `_claim()` on `DeliveryGenerationRun`, unique on **(tenant, business_date)** — what stops two of four uvicorn workers doing the same dairy twice (DEMO-018). |
| Idempotency | `uq_delivery_customer_date_slot` + `INSERT … ON CONFLICT DO NOTHING`. |
| Tenant isolation | `run_for_tenant` runs inside `rebind_tenant`, so the generation query is filtered by RLS as if it were the dairy's own manager asking. |

## 2. What DEMO-035 provided

`generate_for_day(..., customer_ids=None, slot=None)` — the narrowing seam —
and the finding that route generation must **not** go through `record_run`,
because that function claims the tenant's *date* and hands the loser a
`created: 0`.

## 3. What DEMO-036 actually changed

Four files. **No schema change, no `route_id` on `milk_delivery`, no new source
of truth.**

1. **`delivery/generation.py`** — a `RoundScope` value type (`label`,
   `customer_ids`, `slot`, `center_id`). A frozen dataclass, not a service call.
2. **`delivery/scheduler.py`** — `_generate_the_day(...)`, which either iterates
   scopes or makes the one pre-existing whole-tenant call; `record_run`,
   `run_for_tenant` and `run_once` gained an optional `route_scopes` provider.
3. **`logistics/service.py`** — `scheduled_round_scopes(session, tenant_id, day)`,
   a module-level function returning the scopes for a dairy's active, non-empty
   routes, ordered by code then by the day's own slot order.
4. **`main.py`** — the composition point passes the provider to `run_once`.

## 4. Scheduler decision flow

```
run_once(route_scopes=scheduled_round_scopes)
  └─ per active tenant, inside rebind_tenant(tenant):
       should_run(tenant clock) ────────────── not due → return
       WorkingDayResolver(tenant, day)
       record_run(tenant, day, is_working, route_scopes)
         └─ _claim(tenant, day) ───────────── lost → return the day's record
              └─ _generate_the_day
                   scopes = await route_scopes()
                   ├─ scopes empty → generate_for_day(whole tenant)   ← unchanged
                   └─ scopes → for each scope, in order:
                        generate_for_day(customer_ids=…, slot=…)
                        a raise here fails the DAY, naming the route
```

### Why the claim stays

DEMO-035's finding was about calling `record_run` **per route**. This milestone
does the opposite: **one claim per tenant-day, many routes underneath it.**

That is the distinction the whole design turns on. The claim is not the problem
— it is what stops two workers generating the same dairy's morning twice. The
problem was letting each route try to own the day. Guarded by
`test_the_tenant_day_is_claimed_once_and_routes_run_underneath_it` (SQLite) and
`test_one_claim_per_tenant_day_however_many_routes` (real PostgreSQL): one run
row, four deliveries, four routes.

### Why a callable rather than an import

`logistics` already imports `DeliveryService`, so `delivery` importing routes
would be a cycle. DEMO-022 settled this exact question when the generator
needed a calendar: it is **handed** `is_working` and knows nothing about
calendars. The route provider is handed the same way, and the delivery module
still does not know routes exist.

The cost is that the wiring lives in `main.py` and nothing else references it —
so a refactor dropping the argument would silently put every dairy back on the
fallback with no other test failing. Two tests exist purely for that:
`test_the_scheduler_loop_is_actually_wired_to_the_provider` and
`test_run_once_passes_the_provider_through`.

### A failing route fails the day

A route that raises is re-raised with its label, so `record_run` marks the day
`failed` and the attempt is retried (up to `MAX_ATTEMPTS`). Recording a partial
round as `success` is the failure mode this milestone must not have: an operator
reading `success` has no reason to go looking for the round that never went out.

## 5. No-route fallback behaviour

A dairy is on the fallback when `scheduled_round_scopes` returns an empty list,
which happens for **no routes, only inactive routes, or only empty routes**.
It then receives the identical `generate_for_day` call it received before this
milestone existed.

**Route adoption is therefore not mandatory and not a migration.** Asserted
three ways: with the provider wired and no routes; with the provider wired and
only empty or inactive routes; and with **no provider at all**, which is how
every existing test and the manual endpoint still call it.

An empty route is *skipped* rather than refused here, deliberately — the
scheduler is generating every route a dairy has, and one unfinished route must
not stop the others going out. DEMO-035's operator-facing endpoint still
refuses it loudly, which is the right behaviour for somebody who asked.

## 6. Concurrency and idempotency proof

On **real PostgreSQL**, separate connections:

* **three concurrent scheduler passes** on the same dairy's morning → **4
  deliveries, 1 run row**, and the `created` counts sum to exactly one round;
* **repeated sequential passes** → second pass creates 0;
* **one claim per tenant-day across four routes** → 1 run row, `created == 4`;
* one dairy's pass generates nothing in another dairy, in both directions.

## 7. Defects found

**None in existing code, and none introduced.** The `record_run` hazard was
already documented by DEMO-035 and was designed around rather than rediscovered.

Two things worth recording that are not defects in shipped code:

1. **A test of mine asserted the wrong ordering.** I first asserted route scopes
   sort alphabetically by label; the actual order is route code then the day's
   own slot order — **morning before evening**. Alphabetical would have sent the
   evening van first. The code was right and the assertion was wrong; the test
   now states the real order.
2. **One mutation was not caught, and the honest reason is that the guard is
   unreachable.** Removing `RouteStop.tenant_id == tenant_id` from the provider
   fails nothing, because the stops are already restricted to routes that were
   themselves tenant-filtered. It is genuine defence-in-depth rather than a
   load-bearing predicate, and it is reported as such rather than covered by a
   test that would only be asserting the redundancy.

## 8. PostgreSQL proof

`tests/test_scheduler_routes_postgres.py` — **9 tests**, wired into
`infra/ci/postgres-proof.sh`: route-aware generation; the no-route fallback; a
mixed dairy where only routed households generate; three concurrent passes;
repeated passes; one claim across four routes; isolation in both directions;
the provider reading only its own dairy's routes; and no financial write.

```
./infra/ci/verify-postgres.sh   →   251 passed
                                    POSTGRESQL PROOF PASSED
```

(242 before this milestone.)

## 9. Full test-suite result

`tests/test_scheduler_routes.py` — **19 tests** covering all thirteen cases the
work order lists.

**Mutation testing — six of seven caught, the seventh explained in §7:**

| Guard disabled | Tests that fail |
| --- | --- |
| no-route fallback taken | 3 |
| route-aware branch taken when routes exist | 2 |
| a failing route fails the day | 1 |
| inactive route excluded | 1 |
| empty route skipped | 1 |
| `main.py` wiring present | 1 |
| provider scopes stops by tenant | **0 — unreachable, see §7** |

Backend suite result recorded in §10. Lint clean under `ruff check --no-cache`.
Docs and xref clean.

**Portal and mobile: no change, and none was required.** The scheduler is a
background loop with no user surface; DEMO-035's operator endpoint and portal
button already cover the manual path. Reported explicitly because the work
order asks for it.

## 10. Production verification

*Recorded after deployment.*

## 11. Financial safety

The scheduler creates `scheduled` deliveries worth `0.00`, which is the same
thing it created before this milestone — route-awareness changes *which*
households are in a round, never what a delivery is worth. Asserted in the
suite, on real PostgreSQL, and by the production before/after in §10.

## 12. Infrastructure and disk findings

Inspected before running heavy tests, per the work order.

* **Local:** 163 GB free of 469 GB (64% used). `apps/mobile/build` holds 2.2 GB
  of Flutter output and `apps/admin-portal/.next` 422 MB. **Nothing was
  deleted** — no cleanup was necessary, and they are legitimate caches whose
  removal only makes the next run slow.
* **Production:** 81% used, 7.3 GB free — comfortable, and the direct result of
  DEMO-035's fix. Release directories are back to ~714 MB from 3.4 GB now that
  the sync excludes `build/`, `.dart_tool/`, `.next/` and the Python caches.
  `disk-guard.sh`'s arithmetic holds again.

**No cleanup was performed in this milestone.** No source, production data, git
history, database or user data was touched.

## 13. REAL versus TEST versus NOT PROVEN

**REAL** — deployed and exercised in production:

* the scheduler loop running with the provider wired;
* **the no-route fallback**, which is the path every production tenant is on,
  because production has no routes;
* the unchanged whole-tenant generation those tenants receive.

**TEST** — proven here, not in production traffic:

* route-aware generation itself;
* three concurrent scheduler passes producing one round (real PostgreSQL);
* one claim per tenant-day across four routes;
* tenant isolation of the provider;
* a failing route failing the day;
* every route fixture — hand-built, two to four routes of one or two households.

**NOT PROVEN — and not claimed:**

* **Route-aware scheduled generation has never run in production**, because
  production contains **zero routes**. No route, stop, run or delivery was
  manufactured to change that.
* No real driver, no real physical delivery, no GPS, no maps, no optimization.
* Nothing at scale: the largest scheduled round exercised anywhere is four
  households across four routes.

## 14. Known limitations

1. **Route-aware production execution is unproven** (§13) and will stay so until
   a dairy adopts routes.
2. **The wiring is a single argument in `main.py`.** Two tests guard it, but a
   deployment that ran the scheduler by another entry point would silently be on
   the fallback.
3. **A route's slots are offered, not derived.** Both `morning` and `evening`
   scopes are produced for every route and the generator's slot narrowing
   discards what is not due. Correct, and two extra queries per route per day.
4. **A failing route fails the whole day**, so one broken route delays the other
   routes' rounds until a retry succeeds. The alternative — partial success —
   was rejected as the more dangerous behaviour, but it does mean one bad route
   can hold up a dairy.
5. **Routes are not centre-filtered against the run's own centre.** A route
   carries `center_id` and it is passed through to the working-day resolver, but
   scheduling does not otherwise use it.
6. **No per-route record.** `DeliveryGenerationRun` remains per tenant-day, so
   "which route created what" is not stored — deliberately, since it is
   derivable and a second record could disagree.

## 15. Recommended DEMO-037

**Not started.** Smallest first:

1. **Report the round by route** — a route breakdown on `DeliveryReport`, so
   "why was the round short?" has a per-route answer. Derived at read time,
   consistent with every decision in DEMO-034 and DEMO-035.
2. **Adopt routes on the dev deployment** using existing customers, so
   route-aware generation moves from TEST to REAL — the only way limitation 1
   ever closes.
3. **Let a rider move the run from the phone**, through the existing offline
   queue.

---

## Change Log

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | 2026-08-17 | DEMO-036 delivered — route-aware scheduled generation with an unchanged no-route fallback. |
