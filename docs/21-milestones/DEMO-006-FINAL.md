---
id: DEMO-006-FINAL
title: DEMO-006 — Settlement & Payment Operations
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-12
last-updated: 2026-08-12
related: [DEMO-005-FINAL, DEMO-004-FINAL, DEMO-002-FINAL, BR-REGISTER]
baseline: ARCH-BASELINE-V1
---

# DEMO-006 — Settlement & Payment Operations

The demonstration could follow milk from a supplier's can to a completed,
priced, accepted collection — and then stopped. This work order carries it the
rest of the way: **completed collection → settlement → payment → receipt**,
clickable in both directions, with no dead links and nothing invented.

The single sentence that governs every decision below: **the portal displays
what the platform computed, and offers only what the platform will accept.**
Everything else here is a consequence of it.

---

## 1. The existing financial contracts, as found

The first task was to read, not to build. What was already there:

| Contract | Already supported |
|---|---|
| `GET /v1/settlements` | `q`, `supplier_id`, `center_id`, `status`, `overlapping_on`, `limit`, `offset` |
| `GET /v1/settlements/{id}` | `{settlement, lines[], totals_match_lines}` |
| `POST /v1/settlements/{id}/collect` | sweeps eligible collections; returns `{added, skipped}` |
| `POST …/calculate`, `…/finalize`, `…/cancel` | the lifecycle, with its own guards |
| `GET /v1/settlements/{id}/balance` | `payable / allocated / paid / outstanding / fully_paid` |
| `GET /v1/payments` | `q`, `supplier_id`, `settlement_id`, `status`, `method`, paging |
| `GET /v1/payments/{id}` | `{payment, lines[], attempts[], totals_match_lines}` |
| `POST …/submit,execute,retry,complete,fail,cancel` | the real transitions |
| `GET /v1/payments/balances` | finalized settlements with what is still owed |
| `GET /v1/receipts`, `…/{id}/download` | receipt history and rendering |
| `GET /v1/reports/settlements`, `/reports/payments` | the aggregates the dashboard already used |

**Nothing new was added to the backend.** One client-side gap was closed:
`listSettlements()` never sent `center_id`, although the API had always
accepted it. The portal was the thing that was missing.

Permissions found in place: `settlement.read`, `settlement.manage`,
`settlement.finalize`, `payment.read`, `payment.manage`, `payment.retry`,
`payment.cancel`.

---

## 2. The settlement list

`/settlements`, rebuilt.

Search, status, centre and supplier are **query parameters**, applied by the
database over the whole table. The KPI row is `/v1/reports/settlements` — the
platform's own grouping — not a count of what happens to be on screen.

That last point was a real defect, not a stylistic preference. The page this
replaced computed its status summary like this:

```ts
// Dashboard summary from the visible page.
const counts: Record<string, number> = {};
for (const s of page?.items ?? []) counts[s.status] = (counts[s.status] ?? 0) + 1;
```

Ten rows per page, 52 settlements: every number above the table was wrong, and
looked authoritative.

---

## 3. The settlement detail page

`/settlements/[id]` — new.

* **Header** — number, period, status, and a lock when finalized.
* **Financial summary** — gross, adjustments, net: three stored strings printed
  side by side. Adjustments are labelled *fixed at zero by BR-0011*, because
  they are zero **by rule**, not by omission.
* **Integrity** — `totals_match_lines` is the platform's own answer to "do the
  stored totals still equal the lines?", shown as a tick, or in red with
  *recalculate before finalizing* when false.
* **Payment position** — for a finalized settlement, `payable / allocated /
  paid / outstanding` from `/balance`, with the note that *allocated* counts
  live drafts too, so a settlement can never be paid twice.
* **Payments and receipts** — every payment allocated here, each linking to its
  detail page; receipts fetched per payment (the domain hangs a receipt off a
  payment, not off a settlement — no link was invented) with a working
  download.
* **Collections included** — date, collection, quantity, rate, gross, trace
  reference; **each row links to `/transactions/[id]`**, the DEMO-004 detail
  page.

No arithmetic anywhere. The portal never sums the lines to "check" the total,
because a browser agreeing with itself would hide a platform that disagreed.

---

## 4. Lifecycle and immutability

`allowed()` on the page mirrors `SettlementService` exactly:

| Action | Offered when |
|---|---|
| Collect period | `draft` or `calculated` |
| Calculate totals | `draft` or `calculated` |
| Finalize | `calculated` **and** `line_count > 0` |
| Cancel | `draft` or `calculated` |

So a **finalized settlement shows no lifecycle controls at all** — not greyed
out, not disabled, *absent* — under the sentence:

> This settlement is finalized. BR-0010 makes it immutable — it cannot be
> edited, recalculated, or cancelled.

That is immutability rendered honestly. A disabled button still claims the
operation exists.

Finalizing is the one irreversible step here, and it asks first, naming what
cannot be undone rather than saying "are you sure":

> Finalizing STL-2026-000050 is permanent. Once finalized this settlement
> cannot be edited, recalculated, or cancelled — a correction has to be a new
> settlement or an adjustment. Its net payable of 7,280.00 KES becomes what the
> supplier is owed.

Every action re-reads the settlement afterwards, **including after a refusal**.
The platform is the authority on state; a portal that kept its own copy after
being told "no" would render buttons for a world that no longer exists.

---

## 5. The payment detail page

`/payments/[id]` — new.

The amount and its allocations (each linking back to the settlement it
discharges), the payment's own facts, **every attempt including the failed
ones**, the operations that are actually available, and the receipt with a
download link.

`allowed()` mirrors `PaymentService`:

| Action | Offered when |
|---|---|
| Approve for execution | `draft` |
| Execute | `pending` |
| Retry | `failed` |
| Record success | `processing` |
| Record failure | `processing` |
| Cancel | `draft`, `pending`, `failed` — **never** `processing` |

The last row carries its own explanation on screen:

> A processing payment cannot be cancelled — money may already be in flight.
> Record the failure first, then cancel.

A completed payment shows no operations at all.

---

## 6. The failure path — real, not simulated

This platform **records** money movement; it does not perform it. Execute opens
an attempt against a provider; a human or an integration then reports back, and
`complete` or `fail` records that answer.

So the failure path uses the platform's own transition. `POST /fail` carries the
reason **the operator typed** — the portal invents nothing and requires the
field — and the platform stores it on the payment *and* on the attempt that
failed, releasing the allocation so the settlement is payable again. Retry opens
attempt N+1; the previous attempt is kept exactly as it ended (BR-0019). The
attempt list is the audit trail, not a summary of it.

A failed payment shows what the platform recorded, in place:

> **This payment failed on 2026-08-04 09:12:44**
> mobile money wallet not reachable
> The allocation has been released — the settlement is payable again, either by
> retrying this payment or by raising a new one.

---

## 7. Receipts

Receipts are generated from the platform's own `payment.completed` event by a
consumer, not by any page. The portal shows the ones that exist and says plainly
when none does — *"A receipt appears once this payment completes."*

View and download use the contract that already existed:
`GET /v1/receipts/{id}/download?format=…` via `receiptDownloadUrl()`. The
receipts page gained cross-links so nothing is a dead end: receipt number →
its payment, each covered settlement → its settlement page.

---

## 8. The complete financial timeline

The DEMO-004 collection detail page already showed the chain — settlement,
payment, receipt — from `/v1/reports/collection/{id}/chain`. Its three cards
linked to `/settlements`, `/payments` and `/receipts`: the **list** pages,
because no detail page existed to link to. That was recorded as known
limitation 3 of DEMO-004.

Fixed. Each card now opens the exact record. Verified live:

```
collection 5cfc2625
  settlement -> STL-2026-000001 finalized   id 94bfbebb
  payment    -> PAY-2026-000001 completed   id d38113ae
  receipt    -> RCP-2026-000001 generated   id 502d3c0b
```

Both directions work: collection → settlement → payment → receipt, and receipt
→ payment → settlement → collection.

---

## 9. Dashboard aggregates

Confirmed unchanged and shared. `/` reads `report.settlements` and
`report.payments` from the single `/v1/reports/dashboard` round trip built in
DEMO-002. `/settlements` reads `/v1/reports/settlements` and `/payments` reads
`/v1/reports/payments` — the same service methods behind the same aggregates.
There is one place in this platform that adds money up, and it is the reporting
module.

---

## 10. Centre readiness — resolved, not papered over

DEMO-005 had to report honestly that demo centres showed **WARNING** with two
checks failing. The investigation:

```
device.milk_analyzer   warning   0 devices found
device.printer         warning   0 devices found
```

Both are *warning* severity; every blocking check already passed. The cause was
mundane — the seeder registered a scale and nothing else, so equipment that a
real centre has had simply never been registered.

The fix was to register it, through the real `/v1/devices` API, on all five
demo centres, and to teach `make_center` to fit all three device categories so
future seeds do the same. Result, read back from the platform:

```
KB-C1    READY - all 6 checks pass
KH-C1    READY - all 6 checks pass
LR-C1    READY - all 6 checks pass
NL-C1    READY - all 6 checks pass
NV-C1    READY - all 6 checks pass
```

No rule was weakened, no threshold moved, nothing hard-coded. The missing
equipment was registered.

---

## 11. Demo data — period C

Every settlement in the dataset was already finalized, which meant the
demonstration could only ever show the *end* of the lifecycle: no Calculate, no
Finalize, no irreversibility warning, because the platform correctly refuses all
three on a frozen settlement.

So the seeder gained a **period C** (D-7 … D-1) that creates a settlement for
the first three suppliers, sweeps their real collections into it, calculates the
totals, and **stops before finalize**. The rest of that window is deliberately
left unswept, so a live *Collect period* has real collections to find.

The same thing was then done to the deployed dataset, through the real API — no
row was hand-written:

```
STL-2026-000050  calculated  5 collections  7,280.00 KES
STL-2026-000051  calculated  4 collections  4,704.00 KES
STL-2026-000052  calculated  5 collections  3,640.00 KES
```

Fourteen collections that were genuinely completed, priced and unsettled. This
is not a fake record made for a screenshot; it is the platform doing its job on
data it already held.

---

## 12. Financial reconciliation, verified independently

Twelve checks, run **by PostgreSQL against the deployed database** in exact
`NUMERIC` — not read back from the API that produced the numbers. Every check is
written to return rows only on failure.

| # | Check | Result |
|---|---|---|
| 1 | settlement gross ≠ sum of its lines | 0 rows |
| 2 | net ≠ gross + adjustments (BR-0011) | 0 rows |
| 3 | settlement line gross ≠ its collection's gross | 0 rows |
| 4 | a collection settled more than once | 0 rows |
| 5 | payment amount ≠ sum of its allocations | 0 rows |
| 6 | live allocations exceed what a settlement is payable | 0 rows |
| 7 | a payment allocated to a non-finalized settlement | 0 rows |
| 8 | receipt net ≠ its payment's amount | 0 rows |
| 9 | a receipt for a payment that never completed | 0 rows |
| 10 | receipt net ≠ sum of its lines | 0 rows |
| 11 | any row crossing a tenant boundary (4 joins) | 0, 0, 0, 0 |
| 12 | money stored with more than 2 decimal places | 0, 0, 0 |

Totals, before and after period C:

```
finalized_net 233,892.00   line_gross 233,892.00   completed_paid 101,749.50   receipted 101,749.50
finalized_net 233,892.00   line_gross 249,516.00   ...
```

The second `line_gross` moves by exactly 15,624.00 — 7,280.00 + 4,704.00 +
3,640.00, the three new calculated settlements. It reconciles to the cent.

`infra/demo/seed_demo.py verify` now performs the same reconciliation in
Python rather than merely counting rows, so a future seed cannot go green on
numbers that do not add up.

---

## 13. Authorization

`settlement.finalize` is declared separately from `settlement.manage` precisely
so that freezing money can be a different job. Proven in both directions, at the
API:

* a user with `settlement.read` + `settlement.manage` **can** calculate and
  **is refused 403** on finalize — and the settlement is still `calculated`
  afterwards, so the refusal changed nothing;
* a user with `settlement.read` + `settlement.finalize` **can** finalize, and is
  refused 403 on `collect`.

Existing coverage confirmed rather than duplicated: a tenant-viewer reads
payments but is refused every payment operation, and an outsider with no payment
permission is refused even the reads.

---

## 14. Tenant isolation

Settlements now have the coverage payments already had. From a second
organization: the list returns `total: 0`, detail returns **404**, and every
lifecycle action — collect, calculate, finalize, cancel, add-calculation —
returns **404**. Never 403: a 403 would confirm the row exists.

Confirmed live against the deployed platform, using the isolation
organization's real settlement id and the demo tenant's token:

```
404  GET  /v1/settlements/<other tenant>     settlement not found
404  POST /finalize on it                    settlement not found
```

This surfaced accidentally first: an early probe ordered rows by number across
the whole database, picked the isolation org's settlement, and every refusal
came back 404 instead of the expected 409. The probe was wrong; the platform was
right.

---

## 15. Tests

**Backend** — `services/platform-core/tests/test_financial_operations_demo.py`,
9 new tests. Each one makes the platform *refuse*, because a mirror of a guard
is a claim and a claim about a guard is worth nothing until the guard says no:

* a finalized settlement rejects collect, calculate, finalize, cancel,
  add-line and remove-line — six refusals — and nothing moved afterwards;
* finalize refused from `draft`, from `calculated`-with-no-lines, and after a
  line drops it back to draft;
* `settlement.manage` without `settlement.finalize` is refused, and the mirror
  image;
* settlements and payments are invisible and inert across tenants;
* a processing payment refuses cancellation, accepts failure with the operator's
  reason, releases the allocation, and *then* accepts cancellation;
* a retry opens attempt 2 and keeps attempt 1 exactly as it failed;
* a completed payment refuses all six operations.

**Portal** — `apps/admin-portal/src/app/financial-pages.test.tsx`, 14 tests:
server-side filtering for both lists, KPIs proven to come from the aggregate
(the assertions use figures that appear in *no* visible row), stored totals
printed not summed, finalize offered only from `calculated`, **no lifecycle
button at all once finalized**, the confirmation wording, a refusal shown
verbatim followed by a re-read, the payment transitions available from
`processing`, the fail call carrying the typed reason, and the receipt download
URL.

**Full suites, all green:**

```
backend   1,224 tests — 1,150 passed, 74 skipped (PostgreSQL-only), 0 failed
portal      135 tests — 135 passed (11 files)
ruff check + ruff format --check          clean
eslint src --max-warnings 0               clean
tsc --noEmit                              clean
npm run build                             clean (both new dynamic routes present)
validate_docs.py                          168 files, all checks passed
```

Three of my own bugs were caught by these tests before deployment: a missing
mock setup that made a detail test render nothing, two buttons sharing the
accessible name "Record failure" (the submit is now "Confirm failure"), and an
assertion that matched three elements because gross, net and the allocated
payment are all 3,600.00 — scoped to the financial-summary card.

---

## 16. Live verification on the deployed platform

`https://dev.phoenixsoft.in`, release `demo006-a767497`. Routes served:

```
200  /settlements          200  /settlements/{id}
200  /payments             200  /payments/{id}
```

and the served HTML is the DEMO-006 build ("What each supplier is owed for a
period…", "Settlements awaiting payment", "Loading settlement…").

Every refusal below was produced **live over HTTPS** against the deployed API:

```
A FINALIZED settlement refuses every mutation (BR-0010)
  409  POST /collect      finalized settlements are immutable
  409  POST /calculate    finalized settlements are immutable
  409  POST /finalize     only calculated settlements can be finalized — calculate totals first
  409  POST /cancel       finalized settlements are immutable

A COMPLETED payment refuses every further operation
  409  submit / execute / complete / fail / cancel   completed payments are immutable
  409  retry     only a failed payment can be retried — this one is completed

A PROCESSING payment refuses cancellation — fail first
  409  POST /cancel       a processing payment cannot be cancelled — record the failure first

A FAILED payment refuses complete, and its reason is stored
  409  POST /complete     a failed payment cannot become completed — expected processing
  payment PAY-2026-000008 failed | reason: mobile money wallet not reachable
   attempt 1 failed       | mobile money wallet not reachable
```

Aggregates and server-side filtering, live:

```
settlements: 52  lines: 237  finalized net: 223,744.50  by status: {calculated: 3, finalized: 49}
payments: 25  completed: 21 (91,602.00)  failed: 2  processing: 2  outstanding: 9,926.00

/v1/settlements?status=finalized    total=49
/v1/settlements?status=calculated   total=3
/v1/settlements?center_id=a2ad4fce  total=8
```

The deployment ran the standard pipeline: pre-deployment backup, migration,
`repoint_nginx`, verification (RLS forced, `lacteva_app` NOSUPERUSER/NOBYPASSRLS,
projections healthy) and smoke test — all green, no rollback.

**One gap, stated plainly:** the Chrome extension used for interactive browser
verification in earlier work orders was not connected in this session, so the
pages were verified by their served HTML and by driving the same endpoints the
pages call, not by clicking through them. Everything asserted above was executed;
nothing was inferred from reading code.

---

## 17. AWS impact

| | |
|---|---|
| AWS resources created | **0** |
| AWS resources resized | **0** |
| Managed services created | **0** |
| Terraform infrastructure changes | **0** |
| AWS cost impact | **0** |

Two container images were built on the existing host and pushed to the existing
ECR repositories — the same repositories every previous release used. The ECR
authorization token had expired and was refreshed; no policy, role or resource
was changed.

Nothing was deleted: no PILOT data, no demo organizations, no reseed, no
settlement, payment or receipt removed, and no bulk financial data generated.
The only rows added are the three period-C settlements of §11 and their 14
lines, all built by the platform from collections it already held.

---

## 18. Known limitations

1. **Partial payments are supported but not showcased.** The create-payment form
   defaults to the full outstanding balance and accepts a smaller figure, which
   the platform allocates correctly — but no demo settlement is deliberately
   part-paid, so the "outstanding after a partial payment" state is reachable
   only by typing a smaller amount.
2. **Multi-settlement payments are creatable only via the API.** The payment
   model allocates one payment across several finalized settlements of one
   supplier; the portal's form raises a payment against exactly one. The detail
   page renders multiple allocations correctly when they exist.
3. **The receipts page is still the pre-DEMO scaffold.** It works — search,
   view, render, download, deliver, archive — and it now cross-links to payments
   and settlements, but it has not been rebuilt in the DEMO-002 house style.
4. **Settlement adjustments are fixed at zero.** BR-0011 pins them there until
   the bonus/penalty/tax engines exist. The UI shows the field and says why,
   rather than hiding a concept the domain has.
5. **No settlement was finalized during verification.** Finalization is
   irreversible, and the three open settlements exist so the demonstration can
   take that step live. The guarantee is proved instead by making the platform
   refuse it on an already-finalized settlement, and in the test suite where
   finalizing is free.
6. **Browser verification was non-interactive**, as stated in §16.

---

## 19. Recommended DEMO-007

**Mobile field application** — the one client in the tree with no demonstration
behind it. The Flutter app at `apps/mobile` exists, analyzes and tests clean,
and the offline sync module (`/v1/sync`, with its monitor page) was built for
exactly this: an operator at a collection centre with no signal, capturing
collections that reconcile when the connection returns.

It is the right next step for two reasons. It is the only remaining part of the
product story a customer will ask about and cannot currently be shown; and it
exercises the one guarantee this platform has that nothing else demonstrates —
that a collection captured offline, on a device that was disconnected for hours,
arrives exactly once, priced by the rate card in force **at the moment of
collection**, not at the moment of sync.

The same rule as every work order since DEMO-001 would apply: no simulated
offline mode, no fabricated sync results, and the reconciliation proved in
PostgreSQL rather than asserted in a UI.

---

## Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-08-12 | Platform Engineering | DEMO-006: settlement and payment operations — settlement list rebuilt on server-side filtering and the reporting aggregate, new settlement and payment detail pages mirroring the service guards exactly (no button the backend would reject; immutability shown as an absence of controls), irreversible finalization behind a confirmation that names what cannot be undone, the real payment failure path with the operator's own reason, receipts linked and downloadable, the DEMO-004 chain cards repointed at the exact records, centre readiness resolved by registering the missing equipment, a period-C settlement left open so the lifecycle can be finished live, financial reconciliation verified independently in PostgreSQL across twelve checks, and authorization and tenant isolation proved by refusal. Deployed as `demo006-a767497`. |
