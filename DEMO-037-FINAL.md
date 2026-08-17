---
id: DEMO-037-FINAL
title: DEMO-037 — Route-level DeliveryReport and dev route adoption
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-17
last-updated: 2026-08-17
related: [DEMO-036-FINAL, DEMO-035-FINAL, DEMO-034-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-037 — Route-level DeliveryReport and dev route adoption

Closing the two gaps DEMO-036 named honestly: the report could not answer
"which routes ran?", and no deployment had a route for the route-aware path to
run on. **No migration, no schema change, no new generation engine.**

---

## 1. What already existed

| Concern | What was there |
| --- | --- |
| `DeliveryReport` | `DeliveryService.report()` — five grouped queries: headline, skipped, scheduled, by-status, intended litres, by-day, by-customer, plus `CustomerService.directory()` for names. |
| Route relationships | `route` → `route_stop(customer_id, position)`; `delivery_run(route_id, business_date, slot)`; `milk_delivery(customer_id, delivery_date, slot)` — joined on the customer, because DEMO-035 declined to add a `route_id`. |
| Scheduler after DEMO-036 | `run_once(route_scopes=…)` → `run_for_tenant` → `record_run` → `_claim(tenant, day)` → `_generate_the_day`, which iterates scopes or falls back. |
| Route APIs and permissions | Nine paths, `logistics.{route,fleet,run}.{read,manage}`. |
| **A seeding mechanism** | **`infra/demo/seed_demo.py`** — deterministic, drives the platform's own API in process, `seed`/`verify`/`purge`/`reset`/`consumers`, scoped to two named demo organizations. `purge()` derives its table list from `core/rls.py`, so it already covered `route`, `route_stop`, `vehicle`, `driver` and `delivery_run` without being edited. |

**No migration was required, and none was written.** Confirmed by asking the
question the work order asks: the report needs route *membership*, which
`route_stop` already stores, and the join key `(customer, date, slot)` is
already unique. The schema head stays `b5d1e07a4c39`.

## 2. What was actually missing

1. **A route dimension on the report.** Every figure was per customer, per day
   or per status — nothing grouped a round by the round.
2. **Any route on any deployment.** DEMO-036 reported route-aware scheduling as
   NOT PROVEN in production for exactly this reason.

## 3. What changed

Five files, no migration.

1. **`delivery/service.py`** — `RouteMembership` (a frozen value), `DeliveryRouteRow`,
   `DeliveryReport.routes` / `.unrouted` / `.by_route`, and an optional
   `route_membership` callable on `report()`.
2. **`logistics/service.py`** — `route_memberships(session, tenant_id)`.
3. **`api/routes.py`** — the report handler composes the two, passing a callable.
4. **`apps/admin-portal`** — a "By route" card on the existing deliveries page,
   plus the TypeScript types. Additive; absent when there are no routes.
5. **`infra/demo/seed_demo.py`** — `ROUTES`, `build_routes()` for a fresh seed,
   and **`adopt-routes`** for a host seeded before DEMO-037 existed.

## 4. Decision flow and architecture

```
GET /v1/deliveries/report
  └─ handler composes:  membership = () -> route_memberships(session, tenant)
       └─ DeliveryService.report(route_membership=membership)
            ├─ the five pre-existing grouped queries      (unchanged)
            └─ memberships empty? → routes=0, by_route=[]  (unchanged report)
               memberships → ONE extra grouped query:
                             (customer_id, status) -> count, quantity, amount
                             folded into route rows in Python
```

### Derived, never stored

`milk_delivery` still has no `route_id`. The report joins a route to its
deliveries through `route_stop.customer_id`, so **moving a stop between routes
moves the report with it** — guarded by
`test_moving_a_stop_moves_the_report_with_it`. A stored attribution would have
kept crediting the old route forever.

### One extra query, not one per route

Folding in Python rather than issuing a query per route keeps the report's cost
independent of how many rounds a dairy runs.
`test_the_breakdown_costs_one_extra_query_whatever_the_route_count` compares a
one-route dairy with a three-route one and requires the same statement count.

### The callable again

`logistics` imports `delivery`, so the reverse would be a cycle. The membership
is handed in, exactly as DEMO-022 handed `is_working` and DEMO-036 handed the
round scopes. The delivery module still does not know routes exist.

### What "route-level success/failure" means here

The delivery domain already owns the only per-stop state there is:
`delivered` → `deliveries`, `scheduled` → still outstanding, plus `skipped`,
`returned`, `cancelled`. No separate route outcome was invented. A route's
**litres and money count delivered rows only** — DEMO-019's distinction between
what a round intended and what it achieved — asserted after a mutation survived
the first pass without it.

## 5. Dev route adoption

Used the existing mechanism rather than building another.

`ROUTES` declares three rounds as **contiguous slices** of the seeder's own
sixteen-customer list — R-01 the first six, R-02 the next five, R-03 three more
— so a route is a recognisable neighbourhood run and reading the customer table
tells you who is on which round. **Two customers are deliberately left off every
route**: a dairy does not finish adopting routes in one afternoon, and
`unrouted` only means something if something is unrouted.

`adopt-routes` exists because `seed` cannot run twice — slugs are unique — and
every host with the demo on it was seeded before DEMO-037. It:

* creates **no customer and invents no identity** — the households are the ones
  already on the books, ordered by **code** so the rounds survive a restore;
* is **idempotent** — a route whose code exists is left alone;
* writes nothing financial: a route and a stop are operational records;
* is removed by the existing `purge()` without that function being touched.

`verify` was extended to assert the routes exist, that no stop points at a
non-existent customer, and that no customer appears twice on one route.

Results recorded in §10.

## 6. Tests and PostgreSQL proof

`tests/test_route_report.py` — **14 tests**: no routes; one route; several
routes; totals reconciling with `unrouted`; a route counting only its own stops;
**a moved stop moving the report**; outstanding-versus-delivered including
litres; tenant isolation; 401; code ordering; an inactive route absent while its
deliveries remain; the pre-existing figures unchanged; and the query-count
budget.

`tests/test_route_report_postgres.py` — **7 tests**, wired into
`infra/ci/postgres-proof.sh`: the breakdown on the real engine; off-route
households as `unrouted`; another dairy invisible; **the membership provider
filtered by RLS rather than by its own argument**; the report agreeing with a
concurrently generated round; reporting twice giving the same answer; and the
report writing nothing.

```
./infra/ci/verify-postgres.sh   →   258 passed
                                    POSTGRESQL PROOF PASSED
```

(251 before this milestone.)

**Mutation testing — four guards, all caught:**

| Guard disabled | Tests that fail |
| --- | --- |
| a route counts only its own stops | 4 |
| "participated" means it actually ran | 1 |
| only billable rows carry litres and money | 1 *(after a test was added — see §13)* |
| an inactive route is not reported | 1 |

Plus one portal mutation: showing the card unconditionally fails 2.

## 7. Concurrency and idempotency

Reading a report cannot corrupt anything, so the question worth proving is
whether it **agrees** with what concurrent generation produced — the 06:00
question while vans are loading.
`test_the_report_agrees_with_a_concurrently_generated_round` runs six concurrent
generations across two routes on real connections and requires the report to say
four deliveries, with a raw `SELECT count(*)` confirming four rows exist.
`test_reporting_twice_gives_the_same_answer` covers idempotency.

DEMO-036's guarantees were re-run unchanged and still pass.

## 8. Portal, mobile and API impact

* **API:** one existing endpoint gained three additive response fields. No new
  endpoint, no permission change.
* **Portal:** a "By route" card on the deliveries page, shown only when
  `by_route` is non-empty — an empty table is a question an operator has to
  answer. Two tests cover the absent case, one of them simulating an API older
  than the page, which is the rolling-deploy state DEMO-013 spent an outage in.
* **Mobile: untouched.** `git status apps/mobile` is clean. A rider's round
  already shows the stops in route order (DEMO-034); a per-route management
  report is an office screen.

## 9. Security and RLS verification

No new table, so no new policy. The membership provider is scoped by
`tenant_id` **and** by RLS, and
`test_the_membership_provider_is_filtered_by_the_database` proves the policy is
what answers: bound to dairy B, asking for dairy A's routes by id returns
nothing. The report endpoint keeps `sales.delivery.read`; unauthenticated is
**401**.

## 10. Production and dev verification

*Recorded after deployment.*

## 11. REAL versus TEST versus NOT PROVEN

*Completed after deployment — see §10.*

## 12. Known limitations

1. **`unrouted` is 0 when a dairy has no routes**, not "every delivery". With no
   memberships there is nothing to be unrouted *relative to*, and reporting the
   whole round as unrouted would be a change to a report that dairies already
   read.
2. **A route's slots are not separated** in the breakdown. A route serving
   morning and evening reports one row; the run view separates them.
3. **No per-route history.** The breakdown is a window query, so "how has R-01
   trended?" needs the caller to ask for several windows.
4. **An inactive route disappears from the report** while its deliveries remain
   in the totals — correct, and it means a retired route's past rounds can no
   longer be attributed.
5. **The seeded routes are slices, not geography.** They are deterministic and
   plausible, not real neighbourhoods.

## 13. Defects found

1. **A hazardous default in the seeder — pre-existing, fixed.**
   `python seed_demo.py` with **no argument defaulted to `seed`**, so a typo or
   a forgotten argument would begin writing a demo dataset into whatever
   database was configured. I found it by running the script against the
   deployment: it attempted a full seed and was stopped only because the
   organizations already existed and the create returned 409. It now prints
   usage. Every documented invocation names its command, so nothing depended on
   the default.
2. **A stale documented command — pre-existing, corrected.**
   `DEMO-001-FINAL.md` said to run `python /app/infra/demo/seed_demo.py seed`
   inside the container. The image copies `src`, `migrations`, `alembic.ini` and
   `pyproject.toml` — **there is no `/app/infra`**, so that command has never
   worked. This was **already known and documented**: `infra/demo/README.md`
   carries the working `docker cp` form and DEMO-010 and DEMO-013 both recorded
   it. Only the older DEMO-001 text was stale, and it now matches.
3. **A mutation that survived, then didn't.** Nothing asserted that a route's
   litres count *delivered* rows only, so counting scheduled ones too passed
   every test. Since a scheduled delivery has litres and no money, that would
   have reported a round as having sold milk still sitting in the van. A test
   was added; the mutation now fails.
4. **Two portal query mistakes of mine.** "By route" appears twice — card title
   and screen-reader caption — so `findByText` was ambiguous. Fixed to
   `findAllByText`, matching the existing "By customer" tests.

No defect was found in the route, run, generation or scheduler code from
DEMO-034 through DEMO-036.

## 14. Commits and build

*Recorded after deployment.*

## 15. Recommended DEMO-038

**Not started.** Smallest first:

1. **Let a rider move the run from the phone** — start and complete, through the
   existing offline queue and its idempotency keys. The last piece of the
   operational loop that still requires a desk.
2. **Per-route trend** on the reports page, once somebody has run routes for a
   few weeks and there is a trend to show.
3. **Separate the slots in the route breakdown**, if a two-slot dairy asks for it.

---

## Change Log

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | 2026-08-17 | DEMO-037 delivered — route-level report, dev route adoption. |
