---
id: PILOT-F03-FINAL
title: PILOT-F03 — Late Collection Settlement
type: reference
status: Approved
version: "1.1"
owner: Platform Engineering
created: 2026-08-11
last-updated: 2026-08-11
related: [BR-REGISTER, PILOT-001-FINAL, CAP-0007]
baseline: ARCH-BASELINE-V1
---

# PILOT-F03 — Late Collection Settlement

**Work order:** PILOT-F03
**Date:** 2026-08-11
**Scope:** correct one business defect found by PILOT-001 — a collection completed
after its period was finalized could never be settled.

---

## 1. Root cause

Three existing rules are individually correct and, in one specific arrangement,
jointly fatal.

1. **A collection's business date is the day it was recorded.** In
   `milk_collection/service.py`, `tx_date = as_utc(tx.created_at).date()`. There
   is no back-dating anywhere in the collection flow, so a new collection can
   only ever carry today's date.
2. **A settlement may be finalized while its period is still running.** Nothing
   in `finalize()` requires the period to have elapsed. PILOT-001's
   `STL-2026-000001` covers 2026-07-11 → 2026-08-10 and was finalized at
   **2026-08-09T21:45Z** — a full day before its own period ended.
3. **A finalized settlement is immutable (BR-0010) and periods may not overlap
   for a supplier (BR-0009).**

The trap follows mechanically. Any collection recorded on 2026-08-10 carries the
date 2026-08-10, which lies inside a period that is already closed. It cannot
join that settlement, because finalized settlements are immutable. It cannot get
a settlement of its own, because any period containing 2026-08-10 would overlap
`STL-2026-000001`. And it could not be carried into a later settlement, because
`add_calculation()` required

```python
settlement.period_from <= tx_date <= settlement.period_to
```

Every door was locked. The milk was collected, priced, accepted and completed —
and the platform had nowhere to put the money. PILOT-001 left exactly one such
collection, worth **1,800.00 KES**, as evidence.

A second, quieter contributor: `collect_period()` bounded its sweep *below* by
`period_from`, so even had a later settlement been willing to accept the line,
the bulk collect would never have offered it.

---

## 2. Existing business rule discovered

This was traced from the repository before any code was written, as the work
order requires. Nothing here is invented.

| Source | What it establishes |
| --- | --- |
| **BR-0009** | "Periods are CLOSED date ranges… the rule keys on the supplier alone. Cancelled settlements release their period." Its own test list includes **`test_adjacent_period_allowed`** — consecutive, non-overlapping periods are explicitly legal. |
| **BR-0010** | Finalization "permanently freezes the settlement: no line changes, no recalculation, no cancellation." |
| **BR-0011** | "Net = gross + adjustments (**adjustments fixed at 0 until the bonus/penalty/tax engines**)." |
| **BR-0008 / BR-0012** | A calculation, and a collection transaction, may each appear on at most one *live* settlement line. |
| **CAP-0007 / PEF.SET.01** | The capability's own business-event order is **"Settlement Period Closed; Settlement Computed; Statement Issued; Settlement Corrected"** — the period closes *before* the settlement is computed, and correction is a recognised part of the settlement lifecycle. |
| **`settlement_line` schema (DBD-0001)** | Every line already stores its **own `transaction_date`**, distinct from the settlement's period. The data model has always been able to express a line whose collection date lies outside the period that pays for it. |

Two of these decide the design. `settlement_line.transaction_date` shows that a
carried-forward line is already representable — no new entity, no new column, no
migration. And `test_adjacent_period_allowed` shows that the *next* period is a
legitimate home for it.

The work order offered a list of candidate concepts. The one the repository
already supports is the first on that list: **late settlement against a
subsequent open period.** No new accounting concept was introduced.

**Registered as [BR-0027](docs/03-architecture/01-business-layer/BUSINESS-RULES.md)**
— *a late collection is carried forward; a closed period is never reopened to
receive it.* Register version 1.16 → 1.17.

---

## 3. Why the old implementation was incorrect

`add_calculation()` treated "the line's date lies in this settlement's period" as
the definition of a valid line. That is right for the ordinary case and wrong for
the only case where it matters: a collection whose rightful period no longer
accepts lines. The rule was written as though every collection would always have
an open period waiting for it, which is true only if no settlement is ever
finalized early — a precondition nothing enforces.

The result was not an error an operator could act on. The collection succeeded,
was priced correctly, showed a perfectly normal `COMPLETED` state, and simply
never appeared on any statement. A supplier would have been underpaid by
1,800.00 KES with nothing in the system marked as wrong.

`collect_period()`'s lower bound compounded it by making the stranded line
invisible to the one operation an operator would naturally reach for.

---

## 4. Exact implementation

One file changed: `services/platform-core/src/platform_core/modules/settlement/service.py`.

**(a) The line-date rule became a named guard**, `_assert_line_date_settleable()`:

- inside the period → admitted, exactly as before;
- **after** `period_to` → always refused ("milk that has not been collected
  cannot be settled"), one-directional by design;
- **before** `period_from` → admitted **only if** a `finalized` settlement for the
  same tenant and supplier already covers that date. That is the precise
  definition of "late": the collection's own period is closed forever.

A collection whose own period is still open is *not* late and is still refused,
so a period's money cannot be scattered across two statements by accident.

The closed-period lookup is scoped by `tenant_id` **and** `supplier_id`, so one
tenant's history can never decide what another may settle.

**(b) `collect_period()` lost its lower bound**, so a stranded collection is
picked up by the ordinary "collect" an operator already uses. `add_calculation()`
remains the sole authority on eligibility — anything it refuses is counted as
`skipped`, exactly as an already-settled transaction always was.

Nothing is filtered out in SQL. An earlier draft excluded already-settled
candidates in the query, which was faster but changed `{"added": 0, "skipped": 2}`
into `{"added": 0, "skipped": 0}` — silently dropping the operator's only signal
that a transaction was seen and passed over. The existing contract won.

**(c) Adjustments.** See §8. `NO_ADJUSTMENTS` is now a named module constant
citing BR-0011, and `calculate_totals()` performs the addition through `Money`
rather than adding a literal zero, so the arithmetic is real rather than assumed.

**What was deliberately NOT done.** The obvious "root-cause" fix — forbidding
finalization of a period that has not yet elapsed — was considered and rejected
for this work order. It would break the legitimate "settle today's collections
today" workflow, it contradicts an existing e2e test that deliberately settles a
period covering today, and it does not help the collection already stranded. More
importantly it is the weaker fix: it reduces how often money is stranded, whereas
BR-0027 makes stranding *recoverable in principle*. It is recorded as a
recommendation in §14, not silently adopted.

---

## 5. Database / migration changes

**None.** No column, table, index or constraint changed.

Proven rather than asserted — `alembic revision --autogenerate` against a
schema migrated from empty produces an empty migration:

```
def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    pass
```

Head remains `8c41f0a7b2d3`, identical to the deployed schema. The probe
migration was deleted. **Deployment therefore involves no database operation at
all**, destructive or otherwise.

---

## 6. API changes

**None.** No endpoint was added, removed or changed shape. The existing surface
already covers the workflow: `POST /v1/settlements`,
`POST /v1/settlements/{id}/collect`, `POST /v1/settlements/{id}/transactions`,
`POST /v1/settlements/{id}/calculations`.

One response *body* changes, in the direction of accuracy: a `409` for a line
dated after the period now names the boundary
(`"…is outside the settlement period — it is after 2026-10-31"`). The
long-standing `"outside the settlement period"` wording that callers and tests
match on is preserved verbatim.

---

## 7. Portal changes

**None required.** `apps/admin-portal/src/app/settlements/page.tsx` already
renders `line.transaction_date` for every line, so a carried-forward line
displays the day the milk actually arrived, alongside the settlement's own
period. That is precisely the intended presentation. The 57 portal tests pass
unchanged.

---

## 8. Adjustments — investigated, not invented

The work order asked whether adjustments are calculated, recorded, derived, or
intentionally zero. The repository answers unambiguously:

> **BR-0011:** "Net = gross + adjustments (**adjustments fixed at 0 until the
> bonus/penalty/tax engines**)."

and the schema comment agrees: *"Placeholder until the bonus/penalty/tax engines
land — always 0 in SET-001."* There is no other legitimate source for an
adjustment anywhere in the domain today — no premium, penalty, deduction or tax
entity exists to derive one from.

So adjustments are **intentionally zero under the current business rules**, and
the correct action was the one the work order prescribes for that case: make the
value explicitly zero rather than invent logic. Concretely:

- `NO_ADJUSTMENTS = Decimal("0.00")` is a named module constant citing BR-0011,
  so the rule has one home instead of a literal that a future edit "fills in"
  locally;
- `calculate_totals()` builds a real `Money` adjustment and computes
  `net = gross.plus(adjustments)`, so the addition genuinely happens. The day
  adjustments become real, this arithmetic already carries them.

No arbitrary adjustment logic was added. `adjustments_amount` is no longer a
placeholder literal; it is a stated rule with a test asserting it.

---

## 9. Money calculation verification

The chain the work order specifies, verified end to end in
`test_money_is_exact_from_collection_through_to_the_receipt`:

| Hop | Value |
| --- | --- |
| Collection quantity | 40.000 kg (45.0 gross − 5.0 tare) |
| Applicable rate (fat 4.2 → band `[4.0, 5.0)`) | 45.0000 KES/kg |
| Line gross | **1,800.00 KES** — and `quantity × unit_price == gross_amount` asserted directly |
| Settlement gross | 1,800.00 |
| Adjustments | 0.00 (BR-0011) |
| Settlement net | 1,800.00 — and `net == gross + adjustments` asserted as an identity |
| `totals_match_lines` (BR-0011 gate) | `True` |
| Payable | 1,800.00 |
| Payment amount | 1,800.00 |
| Paid / outstanding | 1,800.00 / **0.00**, `fully_paid: true` |
| Receipt `net_amount` | **1,800.00** |

Every figure is compared as `Decimal`. Precision is untouched: money remains
`Numeric(16,2)` / `Numeric(12,4)` for unit price, and no float enters the path.

---

## 10. Idempotency and concurrency verification

Existing protections were preserved, not re-implemented:

- `finalize()` keeps its CAS claim (`UPDATE … WHERE status = 'calculated'` with a
  rowcount check) and its BR-0011 integrity gate. Neither was touched.
- `_assert_calculation_unsettled()` (BR-0008) and `_assert_transaction_unsettled()`
  (BR-0012) run **before** the new date rule, so the widened door cannot be used
  to settle anything twice.
- The database unique constraints `(settlement_id, calculation_id)` and
  `(settlement_id, transaction_id)` are unchanged and remain the backstop.

Covered by tests:

- `test_carrying_forward_twice_is_idempotent` — a second `collect` adds nothing
  and re-adding the same transaction is refused 409; the settlement still holds
  exactly one line.
- `test_a_late_line_cannot_be_settled_in_two_open_settlements` — two open
  settlements compete for the same stranded collection; the second gets nothing.
  This is the double-payment case, stated as such.
- The existing payment-concurrency suite (`test_payment_concurrency_postgres.py`)
  and the whole payment suite pass unchanged.

---

## 11. Tenant / RLS verification

The architecture was not touched: no change to `core/rls.py`, no new table, no
change to any policy or to `PlatformSessionFactory`.

The one new query is scoped by `tenant_id` and `supplier_id` in its `WHERE`
clause, on top of the RLS the database enforces underneath. Two tests pin it:

- `test_another_tenants_closed_period_cannot_unlock_a_late_line` — a second
  organization exists; it cannot make this tenant's collection settleable.
- `test_a_late_settlement_is_invisible_to_another_tenant` — another tenant reading
  the carry-forward settlement gets **404, never 403**.

The PostgreSQL pipeline re-proves RLS on a real engine (§12).

---

## 12. Regression tests

New file: `services/platform-core/tests/test_settlement_late_collection.py` —
**11 tests**, all driven through the HTTP surface, because that is the only place
the defect was ever visible.

| # | Work-order requirement | Test |
| --- | --- | --- |
| 1 | Normal in-period collection still settles | existing `test_full_procurement_journey`, `test_collect_period_is_idempotent` (unchanged, still green) |
| 2 | Finalized period remains immutable | `test_a_finalized_settlement_still_refuses_every_mutation`, `test_the_closed_settlement_is_not_touched_by_the_carry_forward` |
| 3 | A legitimate late collection can be settled | `test_a_late_collection_is_carried_forward_into_the_next_period` |
| 4 | A late collection cannot mutate the finalized period | `test_the_closed_settlement_is_not_touched_by_the_carry_forward` — the closed settlement is compared **whole, before and after** (`after == before`) |
| 5 | Duplicate settlement remains idempotent | `test_carrying_forward_twice_is_idempotent` |
| 6 | Concurrent/duplicate settlement produces no duplicate effect | `test_a_late_line_cannot_be_settled_in_two_open_settlements` |
| 7 | Tenant isolation enforced | `test_another_tenants_closed_period_cannot_unlock_a_late_line`, `test_a_late_settlement_is_invisible_to_another_tenant` |
| 8 | Monetary calculations exact | `test_money_is_exact_from_collection_through_to_the_receipt` |
| 9 | Receipt reflects the settled/paid amount | same test — receipt `net_amount == 1,800.00` |
| 10 | Transaction A covered by a regression test | `test_pilot_001_1800_kes_collection_can_now_be_settled` |

Plus two guarding the narrowness of the relaxation:
`test_a_collection_whose_own_period_is_still_open_is_not_late` and
`test_a_collection_after_the_period_is_always_refused`.

**The tests were proven to detect the defect.** Run against the pre-fix service,
**8 of the 11 fail**. The 3 that pass are precisely those asserting behaviour that
already existed (immutability, the untouched closed settlement, the cross-tenant
404) — they are regression guards, and they should pass both before and after.

### Results

| Suite | Result |
| --- | --- |
| Full backend suite | **1,112 passed, 74 skipped, 0 failed** (was 1,101 before this work order; +11 new) |
| Settlement / payment / receipt / procurement suites | all green |
| PostgreSQL pipeline on a real engine (`verify-postgres.sh`) | **PASSED** — migrations from empty, RLS enabled + forced, **RLS enforcement proven (not skipped)**, backup, restore, deep business integrity, source vs restored identical |
| Admin portal (`vitest`) | 57 passed |
| Lint (`ruff check` + `format --check`) | clean, 205 files |
| Docs validation / xref | all checks passed |

No test was weakened, skipped or deleted. Two existing assertions were corrected
where this change legitimately altered a *reported count* or *message wording*,
and in both cases the fix went into the code, not the test:

- `test_transaction_date_outside_period_rejected` matches on the substring
  `"outside"`. My first draft said "after" instead — I changed the **message**
  back to preserve the existing contract rather than edit the assertion. The
  request was correctly refused with 409 throughout.
- `test_collect_period_is_idempotent` pins `{"added": 0, "skipped": 2}`. My first
  draft's SQL exclusion turned that into `skipped: 0`. I removed the exclusion, as
  described in §4(b) — the operator-visible contract was the thing worth keeping.

---

## 13. Deployment verification

**DEPLOYED AND VERIFIED.** Release `f2023fc-f03` is running at
https://dev.phoenixsoft.in.

| Check | Result |
| --- | --- |
| Running API image | `…/lacteva/platform-core:f2023fc-f03` |
| Containers | 11, all healthy |
| Readiness | `status: ok`, **9/9 probes healthy** |
| RLS re-verified on the live database | every tenant-owned table has a policy; policies FORCED; `lacteva_app` is NOSUPERUSER/NOBYPASSRLS |
| Deployment verifier | **DEPLOYMENT VERIFIED — the platform is serving** |
| Smoke test | **PASSED** |
| Schema | unchanged at `8c41f0a7b2d3` (no migration, as §5 predicted) |

### Two defects found by deploying, and fixed

Deployment is where PILOT-F03 stopped being a code change. The first attempt
failed and rolled back, and the rollback failed too — a **real four-minute
outage**, not a false alarm.

**DEP-001 — nginx keeps stale upstream addresses (fixed).** `infra/nginx/conf.d`
declares `upstream lacteva_api` / `lacteva_portal` by container name, and nginx
resolves those **once, at startup**. Every deployment recreates `api` and
`portal`, Docker gives them new addresses, and nginx goes on proxying to the old
ones: **eleven healthy containers behind a 502**. `compose up -d` cannot fix it,
because nginx's own image and config are unchanged, so Compose correctly leaves
it alone. Worse, `rollback_to()` recreated `api` and hit the identical wall, so
the automatic recovery could not recover — it reported "ROLLBACK ALSO FAILED
VERIFICATION" about a platform whose only fault was a stale address. Closed with
`repoint_nginx()`, called after the main deploy **and** inside the rollback.

**DEP-002 — the verifier's default base URL cannot work under TLS.**
`API_URL` defaults to `http://localhost`; nginx correctly 301s that to
`https://localhost`; the certificate is for `dev.phoenixsoft.in`, so curl's
hostname check fails and readiness never passes. AWS-001 had already added
`--location` for this, which made the redirect followable but not verifiable.
Deployments must therefore pass `API_URL`/`SMOKE_URL` — used here as
`API_URL=https://dev.phoenixsoft.in`. Left as a knob rather than defaulted,
because guessing the public hostname inside the verifier is how it got this
wrong once already.

Both were invisible to review and only appeared on execution — the same lesson
this repository keeps relearning.

### Secret exposure and rotation

While reading deployment configuration I ran a broad `grep -iE 'PUBLIC|DOMAIN|…'`
against `/etc/lacteva/.env.production`. It matched `BEGIN PUBLIC KEY` **inside**
`LACTEVA_JWT_KEYS` and printed the platform's RSA **signing private key** into
the session transcript. That key could mint valid tokens for any account.

It was rotated immediately: a fresh RSA-2048 key under a new `kid`
(`f03-rot-20260810T212211Z`), written in place by a script that prints only
metadata, with the previous environment file backed up first. `jwt_keys` reports
healthy and re-authentication succeeds on the new key, which invalidates every
token signed by the exposed one. **Never grep a secrets file with a broad
pattern** — read the single key you need by exact name.

## 14. Transaction A result

**SETTLED AND PAID IN FULL on the deployed environment.** It was never deleted,
altered or hidden; it was carried forward exactly as BR-0027 describes.

| Step | Result |
| --- | --- |
| Carry-forward settlement | `STL-2026-000004`, period **2026-08-11 → 2026-08-11** — adjacent to `STL-2026-000001` (ends 2026-08-10), so no overlap and BR-0009 is satisfied |
| `collect` | `{"added": 2, "skipped": 0}` |
| Totals | gross **3,600.00**, adjustments **0.00**, net **3,600.00**, `totals_match_lines: true` |
| Payment | `PAY-2026-000004`, 3,600.00 KES, MOBILE_MONEY, draft → pending → processing → **completed** |
| Idempotency replay | same `idempotency_key` returned the **same payment id** |
| Balance | payable 3,600.00, paid 3,600.00, **outstanding 0.00**, `fully_paid: true` |
| Receipt | `RCP-2026-000004`, real `%PDF-1.4`, 3,177 bytes, reading **PAID 3,600.00 KES** |

**The fix recovered more unpaid money than PILOT-001 knew about.** The sweep
collected **two** stranded collections, not one:

| Transaction | Collection date | Amount |
| --- | --- | --- |
| `02ee8cd9…` — Transaction A | 2026-08-10 | 1,800.00 KES |
| `160cfa3f…` — previously unknown | 2026-08-09 | 1,800.00 KES |

The second was stranded the same way and had never appeared on any settlement.
It is not a double payment: BR-0012's `_assert_transaction_unsettled()` runs
before any line is written, so a transaction already carrying a live line can
never be collected again. PILOT-001 found the defect; deploying the fix measured
it at **3,600.00 KES**.

**Each line keeps its own collection date.** The settlement covers a single day,
2026-08-11, while its two lines read 2026-08-09 and 2026-08-10 — the statement
shows when the milk arrived, not when it was paid for, which is the whole reason
`settlement_line.transaction_date` exists.

**`STL-2026-000001` is untouched**, verified after the carry-forward: still
`finalized`, `finalized_at` still `2026-08-09T21:45:15.495879Z`, gross still
5,647.50, still exactly **one** line. Nothing reopened it.

## 15. Remaining limitations

1. **Premature finalization is still possible.** A settlement whose period has not
   elapsed can still be finalized, which is how money gets stranded in the first
   place. BR-0027 makes it always *recoverable*; it does not stop it happening.
   **Recommended follow-up:** refuse to finalize a settlement whose `period_to`
   has not passed. Deliberately out of scope here — it changes the
   "settle-today" workflow and contradicts an existing e2e test, so it deserves
   its own work order rather than a quiet ride-along.
2. **`collect_period()` still selects by `created_at`, not the business
   `transaction_date`** (PILOT-F07, deferred). The two are equal today because
   `transaction_date` is derived from `created_at`, so nothing is currently
   wrong. Rule 6 forbids touching unrelated deferred work.
3. **Carry-forward is unlabelled.** A carried line is visible by its
   `transaction_date` falling outside the period, but nothing marks it as "late"
   for reporting. CAP-0007 names a "Settlement Corrected" event and a "correction
   log" — when that lands, a late line should say so explicitly.
4. **No sweep bound.** `collect_period()` now scans a supplier's completed
   transactions at a centre without a lower date bound. Correct, and fine at
   demo and pilot scale; a long-lived tenant will eventually want an index or an
   "unsettled" flag.
5. **Adjustments remain zero** by BR-0011. Not a defect — the rule — but real
   premium/penalty/deduction handling is still unbuilt.

---

## 16. AWS resources changed — ZERO

**No AWS resource was created, modified, resized or deleted.**

| Resource | Action |
| --- | --- |
| EC2 `i-01f37ba08fe01aa84` (c7i-flex.large) | none — not resized, restarted or replaced |
| EBS 40 GB + 50 GB gp3 | none |
| Elastic IP 15.252.65.201 / DNS | none |
| Security groups | read only, while diagnosing SSH |
| RDS / ElastiCache / Amazon MQ / ECS / EKS / ALB / NAT Gateway | none exist; none created |
| IAM roles, serial console | **deliberately not created or enabled**, though either would have unblocked deployment |

PostgreSQL, Redis and RabbitMQ remain inside the Docker Compose stack. DNS, nginx
and TLS are untouched.

The only AWS calls made were read-only `describe-*` / `get-*` queries and
`ec2-instance-connect send-ssh-public-key`, which creates no persistent or
billable resource.

---

## 17. AWS cost impact — ZERO

No billable resource was created or changed, and no deployment ran. Measured
daily unblended cost is unchanged and the account remains within free-plan
allowances (0.00 USD/day; a single 0.01 USD EC2-Other line on 2026-08-09
predates this work order).

---

## Final verdict

**Can a legitimate late collection now be settled?**
**Yes — proven by tests and then on the live deployment.** A collection
whose period was closed before it was recorded is carried forward into the next
open settlement and paid in full, end to end through to a receipt. Eight of the
eleven new tests fail against the previous implementation, so the capability is
demonstrably new rather than assumed.

**Does the finalized period remain immutable?**
**Yes, absolutely and by construction.** Nothing reopens, edits, cancels or
recalculates a closed settlement. BR-0010's guard is untouched, and the
regression test compares the closed settlement *in its entirety* before and after
a carry-forward and asserts `after == before`, including its `finalized_at`
stamp and line set.

**Are settlement / payment / receipt amounts correct?**
**Yes, exactly.** 40.000 kg × 45.0000 = 1,800.00 KES, identical at the line, the
settlement gross, net (= gross + adjustments), the payable, the payment, the
balance and the receipt. All `Decimal`, no float, precision unchanged.

**Are duplicate and concurrent settlements still protected?**
**Yes.** BR-0008 and BR-0012 run before the new rule, the CAS finalize and the
unique constraints are untouched, and two dedicated tests cover repeated
carry-forward and two open settlements competing for the same stranded
collection. The whole payment and concurrency suites pass unchanged.

**Is the 1,800 KES case resolved or preserved with a documented reason?**
**Resolved.** It was carried into `STL-2026-000004` and paid in full, with
receipt `RCP-2026-000004`. Deploying the fix also surfaced a **second** stranded
collection nobody knew about, so 3,600.00 KES of unpaid milk was recovered rather
than 1,800.00. `STL-2026-000001` was verified untouched afterwards.

**Is the platform ready for a real controlled supplier pilot?**
**Closer, and this blocker is closed — but not yet.** The defect that could
underpay a supplier with nothing marked as wrong is fixed, deployed, and proven
on real money. What remains is PILOT-001's notification gap (PILOT-F04): no
supplier notification has ever been delivered, because SMS dispatch is disabled,
so a real pilot would pay people correctly and tell them nothing. Deployment also
exposed two release-process defects (§13) that had never been executed, one of
which made the automatic rollback unable to roll back — both now fixed, and
worth one more clean deployment rehearsal before trusting the pipeline with a
live pilot. **Ready to demonstrate; one notification gap and one rehearsal short
of paying real suppliers.**

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-11 | Platform Engineering | Deployed `f2023fc-f03` and verified. Transaction A settled and paid (RCP-2026-000004); a second stranded collection surfaced, 3,600.00 KES recovered. Two release-process defects found by deploying (DEP-001 stale nginx upstreams, DEP-002 verifier base URL under TLS) and fixed. JWT signing key rotated after accidental exposure. |
| 1.0 | 2026-08-11 | Platform Engineering | PILOT-F03: BR-0027 established and enforced; late collections carried forward into a later open settlement; adjustments restated as an explicit BR-0011 zero; 11 regression tests. |
