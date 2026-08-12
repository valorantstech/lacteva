---
id: DEMO-007-FINAL
title: DEMO-007 — Transaction Operations & Full Demo Flow
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-12
last-updated: 2026-08-12
related: [DEMO-006-FINAL, DEMO-005-FINAL, DEMO-004-FINAL, BR-REGISTER]
baseline: ARCH-BASELINE-V1
---

# DEMO-007 — Transaction Operations & Full Demo Flow

The demonstration could already follow money from a collection to a receipt.
What it could not do was answer an operations manager's actual question —
*where has each collection got to?* — without opening records one at a time.

This work order makes the transaction the centre of the product, and is the
first one **verified by driving the deployed portal in a real browser**.
DEMO-006 had to report that the Chrome extension was not connected; that gap is
closed, and everything claimed below was seen on screen.

---

## 1. Transaction architecture discovered

Read before anything was written.

| Concept | Where it lives |
|---|---|
| Collection | `milk_collection` — `MilkCollectionTransaction`, `CollectionSession` |
| Lifecycle | 12 states: `NEW → SUPPLIER_IDENTIFIED → MILK_RECEIVED → WEIGHT_CAPTURED → QUALITY_PENDING → QUALITY_CAPTURED → PRICING_PENDING → PRICED → ACCEPTED\|REJECTED → COMPLETED\|CANCELLED` |
| Event trail | `TransactionEvent` — sequence, type, JSON data, **actor**, timestamp |
| Event vocabulary | `TransactionCreated`, `SupplierIdentified`, `MilkReceived`, `WeightCaptured`, `QualityCaptured`, `PricingRequested`, `PricingCompleted`, `PricingUnavailable`, `TransactionAccepted`, `TransactionRejected`, `TransactionCompleted`, `TransactionCancelled` |
| Pricing | resolved by the pricing engine; `unit_price`, `gross_amount`, `calculation_id`, `pricing_detail` stored on the transaction |
| Settlement link | `settlement_line.transaction_id` |
| Payment link | `payment_line.settlement_id` |
| Receipt link | `receipt.payment_id` |

**No new transaction model was created, and no endpoint was duplicated.** Three
gaps were real, and each was closed at its smallest possible size.

### 1.1 The list could not say where a collection had got to

Settlement, payment and receipt live in three other modules.
`GET /v1/reports/collection/{id}/chain` answers this for **one** collection —
fifty rows would be fifty round trips, which §22 forbids and which would have
made the screen unusable anyway.

So the reporting module — the declared exception permitted to SELECT across
module boundaries — gained one endpoint:

```
GET /v1/reports/collection/operational-status?transaction_ids=…&transaction_ids=…
```

The same question, asked for a page, answered in a **fixed number of queries**
regardless of page size. A test asserts exactly that: four times the rows costs
the same number of SQL statements as one.

### 1.2 The API withheld fields the database had stored since MVP-001

`weight_source` and `quality_source` were written on the very first collection
this platform ever recorded, and no client could read them. That mattered more
than it sounds: DEMO-005 built the guided capture wizard on the rule that *the
UI must never pretend a hardware device supplied a value when it did not*, and
until now that claim could not be checked from outside the platform.

`TransactionView` now returns them, along with `quality_remarks`,
`quality_temperature_c`, `arrival_temperature_c`, `arrived_at`, `decided_by`,
`decided_at`, `cancelled_reason` and `milk_type_custom`. No new table, no new
write path — the view stopped hiding what the model already held.

### 1.3 The audit trail was the only list on the platform that was not a page

`GET /v1/audit` returned the newest hundred records and nothing else. The screen
filtered them **in the browser**, so "what did this operator do to that
settlement" quietly meant "…among the last hundred events". The audit service
had carried a `TODO(M2): filters` since it was written.

It is now a page with `q`, `action`, `resource_type`, `actor_id`, `date_from`,
`date_to`, `limit`, `offset` and a `total`, plus `GET /v1/audit/actions` for the
vocabulary actually present in the tenant's history.

**This changed a response shape** from a bare array to
`{items,total,limit,offset}`. Five call sites in the test suite were updated;
not one behavioural assertion was altered.

---

## 2. Transaction list

`/transactions`, rebuilt as an operational view.

Server-side: **status, centre, supplier and the date window** are query
parameters applied by the database over the whole table. The KPI row is the
reporting module's `daily` aggregate over the same window.

Per row: collected date/time and id, supplier, centre, quantity with its
quality beneath, value with its rate beneath, status, **settlement**,
**payment**, and **last activity** from the collection's own event log.

One deliberate omission, stated on the page's own terms in the source:

> Settlement and payment are shown as COLUMNS but not offered as FILTERS. Those
> two facts live in other modules, so the collection list cannot filter on them;
> the only way to offer the control would be to filter the fifteen rows already
> in the browser. A "Settlement: finalized" control that quietly means "…among
> the rows you happen to be looking at" is precisely the dishonesty the
> server-side filters exist to avoid, and it would be worse than nothing here,
> because the pagination total beneath it would still read 360.

The columns never invent a status and never show a settled or paid badge merely
because a row exists — an absence is rendered as an absence ("not settled",
"not paid"), which is only possible because the platform sends `null`.

---

## 3. Transaction detail

`/transactions/[id]` — the primary customer-demo screen.

* **Header** — id, timestamp, **centre name**, **supplier name**, status.
  Identifiers were replaced by names; a screen that says "centre 8f3c1a2b…" is a
  database browser, not a product.
* **Collection** — quantity, gross/tare, **weight source**, milk, container,
  supplier and centre, both linked.
* **Quality** — fat, SNF, CLR, **quality source**, remarks, pricing status, and
  who decided, when.
* **Pricing** — rate card, quantity, rate, and the calculation printed as an
  *expression*: `12 × 42.0000` then `= 504.00 KES`. Three strings the platform
  sent, side by side. The portal never evaluates it.
* **Settlement / Payment / Receipt** cards, each opening the exact record.
* **Money trail** — §6, below.
* **Lifecycle** — §4, below.

Capture source is rendered honestly: `manual` carries the label *"entered by an
operator"*. It is the domain's own word, it is not a failure, and it is not
hidden.

---

## 4. Event timeline

The platform's own `TransactionEvent` log, in order, with:

* the real event names, sentence-cased (`WeightCaptured` → "Weight captured");
* the timestamp;
* **the actor**, resolved to a person's name from the staff roster — and an
  unattributed event reads "the platform" rather than guessing;
* a summary built only from keys the domain actually writes (`net 10`,
  `fat 4.2`) — an event that carried nothing shows nothing.

Settlement, payment and receipt stages follow from the chain aggregate and
appear **only once they have happened**. A stage that has not happened is drawn
as pending. Nothing is inferred and nothing is fabricated.

---

## 5. Audit activity

`/admin/audit`, rebuilt on the filtered endpoint.

| Column | Content |
|---|---|
| When | timestamp |
| Actor | the person's name, with the raw id beneath |
| Action | "Role granted", "Weight captured" — with the module path beneath |
| Entity | "Settlement", linked to `/settlements/{id}` where a page exists |
| Result | the recorded state, or `failed` / `cancelled` where the action says so |

Two details worth naming. The action label keeps the noun when the verb is bare
(`authz.role.granted` → "Role granted") but not when the event already names its
own subject (`collection.transaction.WeightCaptured` → "Weight captured") —
"Granted" alone tells an auditor nothing. And the Entity column links **only**
where a route exists: an audit row for a configuration entry is text, not a dead
link. A test asserts both.

The filter dropdown is built from `/v1/audit/actions`, so it cannot drift from
what the modules actually record.

---

## 6. Financial reconciliation on the transaction

The money trail shows collection value → settlement contribution → payment
allocation → receipt, each linked to its record.

**It compares; it never computes.** `sameAmount()` normalises two exact-decimal
strings in string space — no `Number`, no `parseFloat` — so `450.00` and `450.0`
are recognised as the same money. That is the comparison DEMO-002 got wrong, and
the reason this helper exists rather than a subtraction.

When they agree the page says so. When they do not, it says so louder:

> The settlement recorded 449.00 KES for a collection worth 450.00 KES. These
> should be identical.

A test drives exactly that case and asserts the alert appears; another asserts
that `450.0` and `450.00` are *not* reported as a mismatch.

---

## 7. Navigation / link graph

Verified in the browser, both directions, no dead links:

```
transaction ──► centre            transaction ──► supplier
transaction ──► settlement ──► collections (each back to its transaction)
settlement  ──► payment    ──► settlements paid (back to each settlement)
payment     ──► receipt (download)
audit row   ──► the entity it changed, where a page exists
```

---

## 8. Dashboard reconciliation

Confirmed rather than changed: every transaction KPI already came from
`/v1/reports/dashboard`, and the date filter is applied to the same aggregate the
tables read. Nothing on the dashboard counts rows in React. The one change was
mechanical — the recent-activity strip now reads `.items` from the audit page.

---

## 9. One real settlement finalized

**STL-2026-000052.** Pre-verified in PostgreSQL *before* anything was clicked:

| Check | Result |
|---|---|
| Supplier / centre | S-0EB248 / NL-C1 |
| Period | 2026-08-04 → 2026-08-10 |
| Collections | 5, every one `COMPLETED` and `priced` |
| In period | 5 of 5 |
| Quantity / rate | 5 × 16.000 kg @ 45.5000 |
| Stored gross vs sum of lines | 3,640.00 = 3,640.00 ✓ |
| Adjustments / net | 0.00 / 3,640.00 |
| Double-settled collections | 0 |
| Overlapping period (BR-0009) | none — adjacent to STL-2026-000048 |
| Operator authorization | holds `settlement.finalize` explicitly |

Then finalized **through the actual UI**, in Chrome. 18/18 browser checks:

* the confirmation named what cannot be undone before anything happened;
* status became `finalized`, the header marked it *immutable*;
* the amount was unchanged at 3,640.00;
* **every lifecycle control disappeared** — Finalize, Calculate totals, Collect
  period and Cancel settlement are all absent, replaced by the sentence
  *"BR-0010 makes it immutable — it cannot be edited, recalculated, or
  cancelled."* Immutability rendered as an absence, not a greyed-out button.

Exactly one settlement was finalized. Two remain open for the live demonstration.

---

## 10. One real payment completed

Against that settlement, through the UI. 24/24 checks:

```
draft ──► pending ──► processing ──► completed
```

* the settlement appeared in the platform's own payable list at 3,640.00;
* the form said the payment starts as a draft, and it did;
* on the draft only *Approve for execution* was offered — recording success was
  not;
* executing opened **attempt 1** against provider `mpesa-b2c`;
* while processing, **no Cancel control was offered** — the truthful sequence is
  fail-then-cancel;
* completing left `PAY-2026-000026` terminal, with every operation gone.

Nothing was forced in front-end code. Each step was the platform's own
transition.

---

## 11. Receipt verification

`RCP-2026-000022`, generated by the receipt consumer from the platform's own
`payment.completed` event — not by any page.

| Field | Value |
|---|---|
| Receipt | RCP-2026-000022 |
| Payment | PAY-2026-000026 (completed 2026-08-12 14:13:44 UTC) |
| Settlement | STL-2026-000052 (finalized 2026-08-12 14:11:39 UTC) |
| Amount / currency | 3,640.00 KES |
| Status | generated |

Downloaded in the browser: **HTTP 200, `application/json`, 1,172 bytes.** Not a
link that looked right — a file that arrived.

The settlement then reported itself **fully paid**.

---

## 12. Financial reconciliation

Computed by PostgreSQL against the deployed database, in exact `NUMERIC`:

| Stage | Amount |
|---|---|
| 5 collections | 3,640.00 |
| Settlement lines | 3,640.00 |
| Settlement net | 3,640.00 |
| Payment allocation | 3,640.00 |
| Payment amount | 3,640.00 |
| Receipt net | 3,640.00 |

| Difference | |
|---|---|
| collections − lines | **0.00** |
| lines − settlement | **0.00** |
| settlement − payment | **0.00** |
| payment − receipt | **0.00** |

---

## 13. Tenant isolation

The isolation organization asking for the demo organization's records, live over
HTTPS:

```
404  GET  /v1/milk-transactions/{demo tx}
404  GET  /v1/settlements/{demo settlement}
404  GET  /v1/payments/{demo payment}
404  GET  /v1/receipts/{demo receipt}
404  GET  /v1/settlements/{demo}/balance
404  POST /v1/settlements/{demo}/finalize
404  POST /v1/payments/{demo}/cancel

list totals seen by the isolation tenant:
  milk-transactions  total=3      (its own)
  settlements        total=0
  payments           total=0
  receipts           total=0
audit rows mentioning the demo settlement: 0
```

**404 everywhere, never 403** — a 403 would confirm the record exists.

No existence leak through error differences either: the chain endpoint returns
an identical all-null body for a *foreign* transaction and for a *nonexistent*
one, and `operational-status` returns every field null rather than an error.
Both were checked byte-for-byte.

---

## 14. Authorization

```
200  GET  /v1/milk-transactions          (viewer — allowed)
403  POST /v1/settlements                (viewer)  settlement.manage
403  POST /v1/settlements/{id}/finalize  (viewer)  settlement.finalize
403  POST /v1/payments                   (viewer)  payment.manage
401  GET  /v1/milk-transactions          (no token)
401  GET  /v1/audit                      (no token)
403  GET  /v1/audit                      (authenticated, no audit.read)
```

The refusal names the permission that was missing.

---

## 15. Negative tests

All five required cases, live, with the platform's real business errors:

```
1. Finalize an already-finalized settlement
   409  only calculated settlements can be finalized — calculate totals first
   409  finalized settlements are immutable            (cancel)
   409  finalized settlements are immutable            (collect)

2. Modify a completed payment
   409  completed payments are immutable               (submit/execute/complete/fail/cancel)
   409  only a failed payment can be retried — this one is completed

3. Unauthorized access            403 with the missing permission named
4. Cross-tenant access            404, never 403
5. Invalid transaction operation
   409  expected state PRICED, transaction is COMPLETED
   409  transaction is COMPLETED and immutable
   404  transaction not found
   422  Input should be a valid UUID
```

No business error was replaced by a generic message.

---

## 16. Browser verification

**Real Chrome, real HTTPS, real session cookie** — driven with `puppeteer-core`
against the system Chrome. Not served HTML, not endpoint probes.

All 22 required steps, **26/26 checks**, against `demo007-0af5414`:

```
 1 login page rendered                     12 returned to the transaction
 2 signed in                               13 centres listed
 3 dashboard KPIs, trend, activity         14 centre detail
 4 transaction list w/ settlement+payment  15 readiness ready, 6 checks pass
 5 status filter applied                   16 suppliers listed
 6 transaction opened                      17 supplier detail
 7 pricing shown as an expression          18 collections list
 8 event timeline from the real log        19 completed collection
 8b capture source visible                 20 guided capture reachable
 9 settlement opened                       21 signed out (204 → /login)
10 payment opened                          22 signed in again
11 receipt shown with number
```

Plus 18/18 for the finalization and 24/24 for the payment flow. Screenshots for
every step are attached to this work order's evidence.

One check failed on the first run and the *check* was wrong, not the platform:
it looked for "READY" in capitals while the badge lowercases the platform's
status. It now matches case-insensitively **and** asserts all six named
readiness checks pass.

---

## 17. Responsive verification

Measured in the browser at three widths, asserting the document does not scroll
horizontally:

| Viewport | Result |
|---|---|
| Desktop 1440×900 | no overflow |
| Tablet 834×1112 | no overflow |
| Mobile 390×844 | no overflow |

The transactions table was condensed as part of this: eleven columns clipped the
last one off a 1440px screen — the width the demonstration runs at — so quality
now sits under quantity and the rate under the value it produced. Both remain
the platform's exact strings.

---

## 18. Performance — a real defect found and fixed

Instrumenting the browser for §22 turned up something no screen revealed: **every
page issued every one of its requests twice, about 200 milliseconds apart, on
every single load.**

```
+214ms /v1/collection-centers      +417ms /v1/collection-centers
+215ms /v1/milk-transactions       +420ms /v1/milk-transactions
+300ms /v1/reports/…/operational-status  +503ms /v1/reports/…/operational-status
```

The cause was in `AppShell`. The session probe is asynchronous, so the shell
early-returned a structurally different tree while the answer was unknown —
`{children}` sat in one position before the probe answered and another after, so
React **unmounted and remounted the page** rather than reconciling it. Every
page's effects ran twice.

Fixed by keeping `<main>` in one position and varying only the chrome around it.
The regression test counts a child's mounts; reintroducing the early return makes
it fail with `expected 2 to be 1`. Re-measured on the deployed portal:

```
1 × /v1/collection-centers   1 × /v1/milk-transactions   1 × /v1/reports/…/operational-status
1 × /v1/suppliers            1 × /v1/reports/collection/daily
rows rendered: 15     status calls: 1     per-row chain calls: 0
```

This predates DEMO-007 and affected every screen in the portal.

---

## 19. Security

| Check | Result |
|---|---|
| `document.cookie` visible to script | `""` — empty |
| `localStorage` / `sessionStorage` | empty; no JWT anywhere |
| `lacteva_session` cookie | HttpOnly, Secure, SameSite=Strict |
| `lacteva_refresh` cookie | HttpOnly, Secure, SameSite=Strict |
| Unauthenticated API | 401 |
| Session revocation | logout 204, then the app redirects to `/login` |
| Tenant isolation | §13 |
| Secrets in source | none added; no credential reaches the browser |

No security boundary was weakened. The portal still holds no token: it goes
same-origin to `/api/proxy`, which attaches the cookie server-side.

---

## 20. Automated test results

```
backend    1,249 tests — 1,164 passed, 74 skipped (PostgreSQL-only), 0 failed
PostgreSQL   74 tests — 74 passed against a real engine (verify-postgres.sh)
portal       150 tests — 150 passed (12 files)
ruff check + ruff format --check      clean (208 files)
eslint src --max-warnings 0           clean
tsc --noEmit                          clean
npm run build                         clean (29 routes)
validate_docs.py                      169 files, all checks passed
```

Every skip is a PostgreSQL-only suite with no `LACTEVA_TEST_POSTGRES_URL` —
expected on a laptop, and a collection **error** in a pipeline via
`LACTEVA_REQUIRE_POSTGRES=1`. They were enumerated rather than assumed:
`test_rls_postgres` (35), `test_payment_concurrency_postgres` (12),
`test_disaster_recovery_postgres` (10), `test_exact_aggregation_postgres` (6),
`test_consumer_concurrency_postgres` (6), `test_pricing_precision_postgres` (5).
`./infra/ci/verify-postgres.sh` was then run against a real engine from the
`pgserver` wheel — no Docker, no root — and **all 74 passed**, with the nine-step
proof reporting `POSTGRESQL PROOF PASSED`, RLS forced and the application role
confirmed `NOSUPERUSER, NOBYPASSRLS`. The skipped count and the passed count are
the same 74 tests.

**New tests — 26.**

*Backend* (`tests/test_transaction_operations_demo.py`, 13): the operational
status follows a collection to its receipt; an unsettled collection reports
absence not zero; **a page costs a fixed number of queries** (four rows, same
statement count as one); unknown and foreign ids come back empty rather than
erroring; tenant scoping; a cancelled settlement does not count as settled; the
id list is bounded (422 past 100); capture source survives both the detail and
the list endpoints; audit search, paging, vocabulary, tenant scoping and
permission.

*Portal* (`src/app/transaction-operations.test.tsx`, 13): one call per page and
**zero** per-row chain calls; settlement and payment shown where they exist and
as an absence where they do not; last activity from the event log; every filter
sent to the server; no settlement/payment filter offered; the list survives the
financial call failing; names not identifiers; both capture sources; the money
trail agreeing, **disagreeing**, and treating `450.0` as `450.00`; actor
attribution; and the three links.

Plus the `AppShell` mount-count regression test of §18, and three rewritten
audit tests that now assert server-side filtering instead of browser filtering.

---

## 21. Data changes

Deliberately minimal, and every one is the platform acting on data it already
held.

| Change | Count |
|---|---|
| Settlements finalized | **1** (STL-2026-000052, §9) |
| Payments created and completed | **1** (PAY-2026-000026, §10) |
| Receipts generated | **1** (RCP-2026-000022, by the consumer) |
| Transactions created | 0 |
| Records deleted | 0 |
| Reseeds | 0 |

No PILOT data was touched, no demo organization was deleted, nothing was
reseeded, and no bulk data was generated. Two settlements remain open so the
demonstration can take the irreversible step live.

Two throwaway smoke-test users were created by the deployment pipeline itself,
as it does on every deploy and by design.

---

## 22. AWS impact

| | |
|---|---|
| AWS resources created | **0** |
| AWS resources resized | **0** |
| Managed services created | **0** |
| Terraform infrastructure changes | **0** |
| Additional AWS cost | **0** |

PostgreSQL, Redis and RabbitMQ remain in Docker Compose on the existing EC2
instance. Two container images were built on that host and pushed to the ECR
repositories every previous release has used.

---

## 23. Known limitations

1. **Settlement and payment cannot be filtered server-side.** They are columns,
   not filters, for the reason given in §2. Filtering by settlement status
   belongs on the settlements screen, which can do it properly.
2. **The receipts list page is still the pre-DEMO scaffold.** It works and it
   cross-links, but it has not been rebuilt in the house style. Unchanged since
   DEMO-006 recorded it.
3. **Actor names cost one request per staff member.** `listPeople()` joins
   `/v1/members` to `/v1/identity/users/{id}`; it is bounded by headcount, not by
   rows, and is fetched once per screen — but a hundred-person cooperative would
   want a batched endpoint.
4. **`/v1/audit` changed shape.** Any external consumer of the bare array would
   break. Nothing outside this repository consumes it today.
5. **Audit search is exact-match, not full text.** The original `TODO(M2)` also
   proposed an OpenSearch projection; that remains the right home for free-text
   search and is not built.
6. **Partial and multi-settlement payments are still API-only**, as DEMO-006
   recorded.
7. **The browser verification runs headless.** It is real Chrome driving the real
   deployed portal, but it does not exercise a human's rendering path — fonts,
   GPU compositing and printing are unverified.

---

## 24. Recommended DEMO-008

**Mobile field application.** Unchanged from DEMO-006's recommendation, and now
the only substantial part of the product with no demonstration behind it.

The Flutter app at `apps/mobile` analyzes and tests clean, and the offline sync
module (`/v1/sync`, with its monitor page) was built for exactly this: an
operator at a collection centre with no signal, capturing collections that
reconcile when the connection returns.

It exercises the one guarantee this platform has that nothing else demonstrates
— that a collection captured offline, on a device disconnected for hours,
arrives **exactly once**, priced by the rate card in force **at the moment of
collection** rather than at the moment of sync.

The same rules would apply: no simulated offline mode, no fabricated sync
results, the reconciliation proved in PostgreSQL, and the whole thing driven in a
real browser and a real emulator rather than described.

---

## Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-08-12 | Platform Engineering | DEMO-007: the transactions list rebuilt as an operational view with settlement, payment and last activity per row, fed by one bulk reporting endpoint rather than an N+1; capture source exposed after being stored and withheld since MVP-001; the audit trail made a filtered, paged, readable operations screen, closing its own `TODO(M2)`; a money trail that compares the platform's figures and never computes them; the complete flow verified by driving real Chrome against the deployed portal — 26/26 steps, one real settlement finalized, one real payment completed, one receipt generated and downloaded, and every amount reconciled to 0.00 in PostgreSQL; and a pre-existing defect found by instrumentation that made every page in the portal issue every request twice. Deployed as `demo007-0af5414`. |
