---
id: DEMO-018-FINAL
title: DEMO-018 — Production Scheduler Deployment & Real-World Verification
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-15
last-updated: 2026-08-15
related: [DEMO-017-FINAL, DEMO-016-FINAL, DEMO-015-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-018 — Production Scheduler Deployment & Real-World Verification

DEMO-017 built the scheduler and proved it in development. This deployed it and
watched it run.

**The watching was the point.** The first real execution found a defect that
every development test had missed and could not have found, because it depends
on a fact about the deployment rather than about the code: **production runs
uvicorn with `--workers 4`.** Four scheduler loops woke together, all four
generated the same round, and the last one to finish overwrote the record of
what the first had done.

The deliveries were never at risk — the constraint DEMO-009 added did exactly
its job. The *record* was wrong, and with four workers it would have been wrong
every single day.

**Two defects found in production. AWS cost: none.**

---

## 1. Deployment

Through the existing path — git → GitHub Actions → ECR → `deploy.sh` on the
host. No new mechanism.

| Release | Deployed | Contents |
|---|---|---|
| `main-870292c` | 2026-08-14T20:25:07Z | DEMO-017: the scheduler, the run table, the portal line |
| `main-0fed279` | 2026-08-14T20:45:06Z | the four-worker fix found by the first run |

Both verified by `deploy.sh`'s own checks: schema at `e93b5d1c72af`, RLS
enforced, every readiness probe healthy, smoke test passed. Automatic rollback
was armed for both and needed for neither.

## 2. Backup

`/opt/lacteva/backups/pre-demo017-20260814T200838Z.dump` — **3.0 MB**, taken at
2026-08-14T20:08:38Z, before any deployment. Verified present and sized before
proceeding.

Baseline recorded at 20:19:33Z: 1,223 deliveries, 33 active plans, 31 invoices,
24 customer payments, 24 customer receipts, 84 settlements, 42 supplier
payments, 36 supplier receipts.

## 3. Scheduler architecture as deployed

A fifth background loop inside the API process, registered in `core/workers`.
Confirmed in production: **four** `delivery-scheduler` worker registrations at
20:24:54Z, one per uvicorn worker, and `background_workers: healthy` on
`/health/ready`.

## 4. The execution that was observed

**Unprompted, one second after the process started**, and through the real
configured mechanism — no endpoint was called:

```
20:24:55.061Z  lacteva-demo            business_date 2026-08-14  due 16  created 16   66ms
20:24:55.092Z  lacteva-isolation-demo  business_date 2026-08-14  due 0   created 0     1ms
20:24:55.111Z  lacteva-demo            business_date 2026-08-14  due 16  created 0    37ms  ← a second worker
```

The Indian tenants are absent from that log and correctly so: it was 01:54 IST,
before the 05:00 generation hour.

## 5. Timezone verification (§4)

At one UTC instant, **2026-08-14T20:54:09Z**, read from the production
database:

| Tenant | Zone | Local time | Business date |
|---|---|---|---|
| `lacteva-demo` | Africa/Nairobi | 23:54 | **2026-08-14** |
| `lacteva-isolation-demo` | Africa/Nairobi | 23:54 | **2026-08-14** |
| `lacteva-india-demo` | Asia/Kolkata | 02:24 | **2026-08-15** |
| `phoenix-demo` | Asia/Kolkata | 02:24 | **2026-08-15** |
| `isolation-probe` | Asia/Kolkata | 02:24 | **2026-08-15** |
| *(Asia/Qatar)* | Asia/Qatar | 23:54 | **2026-08-14** |

India and Kenya legitimately held **different dates at the same moment**, and
the scheduler generated Kenya's 2026-08-14 while leaving India's 2026-08-15
alone. That is the requirement, verified against production rather than a
fixture.

**Qatar: no tenant exists in production** (`SELECT count(*) … WHERE timezone =
'Asia/Qatar'` → 0), so there was nothing for the scheduler to schedule. What is
verified is that the registry resolves `QA → QAR, Asia/Qatar` on the deployed
platform, that the same clock rule gives Asia/Qatar 2026-08-14 at 23:54 at the
instant above, and that the unit tests assert Qatar's behaviour — including
that Kenya and Qatar, both UTC+3, must **agree**. Creating a Qatari tenant
purely to have one in a report would not have added evidence.

## 6. Data safety (§8)

Before (20:19:33Z) and after the scheduler ran:

| | Before | After | Δ |
|---|---|---|---|
| deliveries | 1,223 | 1,239 | **+16** |
| — of them `scheduled` | 79 | 95 | **+16** |
| invoices | 31 | 31 | 0 |
| customer payments | 24 | 24 | 0 |
| customer receipts | 24 | 24 | 0 |
| settlements | 84 | 84 | 0 |
| supplier payments | 42 | 42 | 0 |
| supplier receipts | 36 | 36 | 0 |

**The scheduler created deliveries and nothing else.** Every generated row is
`scheduled`, which is absent from `BILLABLE_STATUSES`, so all sixteen are worth
0.00 until a person says the milk arrived.

## 7. The chain still works on a generated round

Verified against the deployed API as `sales@lacteva-demo.example.com`, the
delivery-rider role:

1. sign in → org `lacteva-demo`, KES, Africa/Nairobi;
2. ask for the round with no dates → business date **2026-08-14**, planned 16,
   pending 16;
3. confirm one with the ordinary record call — the same call the phone makes —
   → `delivered 1.500 L`, **priced by the server at 93.00 KES**;
4. the report moves to planned 16, pending 15, completed 1, value 93.00 KES.

No Generate button was pressed by the operator, which is the requirement.

## 8. Security and RLS (§12)

| Check | Result |
|---|---|
| unauthenticated `GET /v1/deliveries/generation-runs` | **401** |
| viewer (read grant) `GET …/generation-runs` | **200** |
| viewer `POST /v1/deliveries/generate` | **403** |
| India's run history visible to India | 0 rows (had not run) |
| Kenya's run history visible to Kenya | 1 row, its own |
| tenant tables with RLS enabled / forced | **62 / 62** |
| `lacteva_app` superuser / bypassrls | **false / false** |

The scheduler holds no privilege: `rebind_tenant` puts each pass inside the
tenant's own binding, so the database filters its queries exactly as it filters
a request from that tenant's manager.

## 9. Portal (§10)

Verified in real Chrome against production. The scheduler line renders as one
line above the round:

> **Last generation: 2026-08-14 · successful · automatic · attempt 2 · 0 deliveries generated · 16 already existed**

Status and trigger are translated, not machine tokens. Currency KES, dates in
the dairy's own calendar, English for the Kenyan user and Hindi throughout for
the Indian one. No raw catalog keys, no duplicate deliveries.

Those counts are the **pre-fix** record for 14 August, displayed faithfully.
The fix does not rewrite history, and should not: the day is closed.

## 10. Defects found and fixed

**1. Four workers raced and the last one blanked the day's record.**

Production runs `uvicorn --workers 4`. Four scheduler loops woke together, all
four claimed the same tenant and business date — because `record_run` did
SELECT-then-INSERT, the very pattern this codebase refuses everywhere else and
which I had written a docstring *above* explaining why the delivery insert must
not do. All four generated; the constraint made the deliveries safe; the last
writer's `created: 0` overwrote the first's `created: 16`.

Three changes:

* the claim is now `INSERT … ON CONFLICT DO NOTHING`, with a **CAS update**
  for a retry — the platform's own concurrency convention. Losing the claim is
  a return, not a race to redo the work;
* `created` **accumulates** for the day while the returned `GenerationResult`
  reports what *this call* did. They answer different questions and were
  conflated: a caller needs `created: 0` to know idempotency held; an operator
  needs the day's 16 to know the round went out;
* a lost race at commit re-reads the winner's record instead of raising.

**2. The concurrency test could not be written where it was first put.**

On SQLite the test stack shares one connection through a StaticPool, so four
"concurrent" sessions are one transaction and a rollback in any of them
discards the others' work. `tests/test_scheduler_concurrency_postgres.py` now
proves it on a real engine — four workers, 25 plans, 25 deliveries, one run
row, `created: 25` — following the precedent
`test_payment_concurrency_postgres.py` set for exactly this reason.

**3. A build check the deployment would not have caught.** The full suite
failed on `test_every_tenant_owned_table_is_covered_by_a_policy`: the new table
was protected in the database (the nine-step proof passed with 63 policies) but
unaccounted for in the *static* check, which asks whether a migration
*declares* the policy. Both checks were right about different things.

## 11. AWS infrastructure and cost

**No resource created, resized, replaced or deleted. Recurring cost: $0.00.
One-time cost: $0.00.** No Terraform change.

The scheduler is a loop inside a process that was already running. That was the
reason for choosing it over EventBridge or a host timer, and the bill is where
that choice shows up.

## 12. Known limitations

* **One generation hour platform-wide**, applied in each tenant's own zone.
  Per-organization hours are a column away and deliberately not built.
* **A stale `running` row blocks that business date** until the next day. If a
  worker dies mid-run the claim is never released; the manual endpoint remains
  available and cannot duplicate. A lease is a bigger idea than this needs.
* **The pre-fix record for Kenya's 2026-08-14 keeps its misleading counts.**
  History is not rewritten.
* **No push alert on failure** — the failure is in the logs, the run record,
  the portal line, and the `background_workers` probe if the loop itself dies.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-15 | Platform Engineering | DEMO-018: the scheduler deployed and observed in production, where a four-worker race that no development test could have found overwrote the day's record on the very first run. |
