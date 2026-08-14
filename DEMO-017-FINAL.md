---
id: DEMO-017-FINAL
title: DEMO-017 — Automated Daily Delivery Scheduler
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-15
last-updated: 2026-08-15
related: [DEMO-016-FINAL, DEMO-015-FINAL, DEMO-014-FINAL]
baseline: ARCH-BASELINE-V1
---

# DEMO-017 — Automated Daily Delivery Scheduler

DEMO-016 made generation idempotent and left it on demand. This makes it
automatic, and the whole milestone is **one background loop and one table**.

That is the point rather than an apology for it: everything hard about
scheduling a dairy's round — not delivering twice, surviving a restart, being
five in the morning in two countries at once — was already solved by the
constraint DEMO-009 added and the timezone hierarchy DEMO-014 built. The
scheduler's job was to not get in their way.

**Two defects found, one of them in a test that had been passing for a day and
a half without asserting anything.** **AWS cost: none.**

---

## 1. What was built

| | |
|---|---|
| **The loop** | a fifth background worker beside relay, consumers, sweep and health |
| **The decision** | `should_run()` — pure, no session, no clock of its own |
| **The record** | `delivery_generation_run`, one row per tenant per business date |
| **Status** | `GET /v1/deliveries/generation-runs` and a one-line portal indicator |
| **Manual** | unchanged, and now through the *same* code path |

## 2. Scheduler architecture

```
_delivery_scheduler_loop        every 60s, registered in core/workers
  └── run_once()
        ├── active_tenants()     ONE cross-tenant read, platform binding
        └── per tenant:
              rebind_tenant()    the tenant's OWN RLS binding
              should_run()       pure: local date + local hour + last run
              record_run()       claim → generate_for_day() → record
```

`record_run` is shared with the manual endpoint, so a manual run and an
automatic one are the same code with a different `trigger` value. The work
order forbids a second generation implementation; this is what honouring that
looks like at the call site.

## 3. Why this mechanism

The alternatives each buy something and cost more than it is worth here:

| Option | Why not |
|---|---|
| cron / systemd on the host | needs a credential that generates a dairy's day sitting on a box, and lives outside the deployment unit — a rollback moves the code and leaves the schedule behind |
| EventBridge / managed scheduler | an AWS resource, a recurring cost, and a second place to look when the round did not go out |
| Celery beat / APScheduler | a dependency and a broker for one job that runs once a day, plus a second definition of "what runs when" |
| **a fifth background loop** | **the platform already runs four**, with graceful shutdown and a health probe that reports a dead one. Costs nothing new |

Registering in `core/workers` means the `background_workers` probe already
reports a scheduler that died — §11's visibility requirement met by
construction rather than by building a monitor.

## 4. Schedule and timezone behaviour

**It polls; it does not sleep until 05:00.** The loop wakes every minute and
asks each tenant a question it answers from that tenant's own clock: *is it
past your generation hour, and has your round been made?*

That is not a compromise — it is what makes §6 true. 05:00 local is **23:30
UTC in India and 02:00 UTC in Kenya and Qatar**; one cron expression cannot be
all three, and this never has to be. It is also why a restart is harmless: the
question is answered from the database, not from a timer that was lost.

| Setting | Default | Meaning |
|---|---|---|
| `scheduler_enabled` | `true` (off in tests) | an operator can stop automatic generation without stopping the platform |
| `scheduler_poll_seconds` | `60` | a round appears within a minute of the hour rather than up to an hour late |
| `scheduler_generation_hour` | `5` | **local**, in each tenant's zone — the first round leaves around six |

**Missed days are not backfilled** (§8). The question is always about the
current business date: down all Tuesday, Wednesday generates Wednesday. A
delivery record is a claim that milk moved, and inventing Tuesday's round on
Wednesday would put a day of milk nobody carried onto a customer's bill. A
deliberate catch-up remains available as the manual endpoint with an explicit
`for_date`, which is §8's "explicit administrative operation".

## 5. Retry and idempotency

**Two guards, and they are not the same guarantee.**

`uq_delivery_customer_date_slot` (DEMO-009) makes duplicate *deliveries*
impossible, through `INSERT … ON CONFLICT DO NOTHING`. That is the one that is
load-bearing for correctness, and it holds whether the caller is the
scheduler, an operator, both at once, or a retry after a crash.

`uq_generation_run_tenant_date` (this milestone) makes duplicate *work*
unlikely — it is what stops a loop waking every minute from re-running a
finished round sixty times an hour. It is for legibility and load. Being clear
about which does which matters: the second one could be dropped and no milk
would be delivered twice.

A failed run keeps its row, records the error and the attempt count, and is
retried up to `MAX_ATTEMPTS = 3`. After that it stays `failed` and visible,
because a fourth attempt means something retrying will not fix.

## 6. Database changes

One migration, `e93b5d1c72af`: the `delivery_generation_run` table, three
indexes, one unique constraint. **Tenant-owned**, so `core/rls.py` derives it
into the protected set from the model metadata — verified on real PostgreSQL:
`relrowsecurity` and `relforcerowsecurity` both true, one policy present, and
the proof's count moved from 62 to 63.

Purely additive: no column added to and no row touched in any existing table.
The downgrade drops one table and touches no delivery, invoice, payment or
receipt. `--autogenerate` produces an empty diff. Verified **up → down → up**.

## 7. Portal changes

One line above the round, not a dashboard: the last run's date, status,
trigger, attempt count and counts. When the last run failed it adds the notice
that generating manually is safe — because the question an operator has at
06:00 is *"the round did not go out, can I fix it?"*, the answer is always yes,
and the screen should say so.

The history is loaded as context and never blocks: a test asserts the round
still renders when `/generation-runs` returns 403.

12 new keys in English, Hindi and Arabic, including `status.running` /
`status.success` / `status.failed` — which the badge translates through the
catalog mechanism DEMO-016 added.

## 8. Mobile

**No change, and that is the requirement.** §13 asks that an operator open the
app and find today's deliveries without pressing Generate. A generated
delivery has always looked to the phone exactly like an unrecorded one, and
DEMO-016 made confirming it the same call the operator already made. The
scheduler changes who calls the generator, not what the phone sees.

## 9. Tests

| Suite | Result |
|---|---|
| Backend | *(recorded at the end of this run)* |
| Portal | **231 passed** |
| Mobile | **125 passed**, `flutter analyze` clean |
| PostgreSQL proof | **PASSED** — 63 policies, FORCEd, app role NOBYPASSRLS |
| Migration | up → down → up on real PostgreSQL, RLS verified present and forced |

20 new backend tests and 3 portal. The ones that carry the milestone:

* **an injected transient failure**, retried, with the row count asserted
  afterwards — a scheduler that cannot fail safely is worse than one that does
  not run, because the failure mode is duplicated milk on somebody's bill;
* **three countries at one instant**, with the window named: India crosses
  midnight at 18:30 UTC and Kenya and Qatar at 21:00, so they differ for two
  and a half hours a day. 20:00 UTC is inside it; **23:00 is not**, and
  picking 23:00 was this test's first draft;
* **a missed day is not backfilled** — Friday generates Friday when Thursday
  never ran.

## 10. Defects discovered and fixed

**1. A DEMO-016 test had an inert mock and was passing on the real clock.**
`test_generation_uses_the_dairys_day_not_utcs` patched
`business_time.datetime` while `business_today` calls `utcnow()` — so the
patch changed nothing, and the assertion was answered by whatever the real
clock happened to say. It agreed for a day and a half and failed the moment
real UTC crossed Indian midnight, which is the only reason anyone found out.
The patch now targets the right symbol **and asserts that it changed the
answer before the real assertion is trusted**. A test that looks like a
controlled experiment and is not is worse than no test at all: it is green,
and it is cited.

**2. `run_for_tenant` recorded a failure into a rolled-back transaction.**
Found while writing the retry test: the claim and the failure record were in
one transaction, so rolling back to discard the failed generation also
discarded the record of it. The failure is now written in a transaction of its
own, after a fresh binding — otherwise a scheduler that failed left no trace
of failing, which is precisely the shape §4 exists to prevent.

## 11. Known limitations

* **One generation hour for the whole platform**, applied in each tenant's own
  zone. Per-organization hours are a column away and deliberately not built —
  §7 says to keep the design extensible and avoid the complexity now.
* **A stale `running` row blocks that business date.** If a worker dies mid-run
  the row stays `running` and the day is skipped until tomorrow; the manual
  endpoint remains available and cannot duplicate. Detecting and reclaiming a
  stale claim is a lease, and a lease is a bigger idea than this needs.
* **One scheduler per process.** With several API replicas each would poll;
  the claim and the delivery constraint make that safe but wasteful. A single
  replica runs today.
* **No push alert on failure.** §11 permits this: the failure is in the logs,
  in the run record, on the portal line, and — if the loop itself dies — in the
  `background_workers` health probe.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-15 | Platform Engineering | DEMO-017 delivered: a fifth background loop that asks each tenant about its own clock, a run record that is the second of two idempotency guards, manual generation through the same path, and two defects — one of them a test that had been green without asserting anything. |
