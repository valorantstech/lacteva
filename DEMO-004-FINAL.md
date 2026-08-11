---
id: DEMO-004-FINAL
title: DEMO-004 — Collections, Pricing and Transaction Workflow
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-11
last-updated: 2026-08-11
related: [DEMO-003-FINAL, DEMO-002-FINAL, BR-REGISTER]
baseline: ARCH-BASELINE-V1
---

# DEMO-004 — Collections, Pricing & Transaction Workflow

**Work order:** DEMO-004
**Deployed to:** https://dev.phoenixsoft.in — release `demo004-091af33`
**Status:** COMPLETE

---

## 1. Collections

`/transactions` rebuilt as a transaction-management screen.

- **Every filter is a query parameter**: status, centre, supplier and the date
  window are applied by the database. Nothing is narrowed in the browser.
- **KPI row** from `/v1/reports/collection/daily` over the *same* window, so the
  figures above the table and the rows inside it answer the same question,
  computed once and in the same place.
- Columns: collected date/time and id, supplier (linked), centre (linked),
  quantity, rate, value, status, actions.
- Presets (today / yesterday / 7d / 30d / custom), a **Clear filters** control
  that appears only when something is filtered, pagination, and empty states
  worded for the situation — "no collection matches these filters" reads
  differently from "no collections in this period".
- Rows use `Money` and `Quantity`; the amount shown is the amount the pricing
  engine wrote.

## 2. Pricing

`/transactions/[id]` carries the pricing breakdown, and it is the part of this
work order most worth stating precisely:

**The calculation is PRINTED, not recomputed.** `quantity × rate = value` is
rendered from three separate strings the platform sent, placed side by side:

```
10.0 × 45.5000
= 455.00 KES
```

The portal never evaluates that expression. Multiplying in React would be a
second pricing engine, and a second engine is a second answer — if the two ever
disagreed, this page would show the disagreement rather than hide it behind a
browser's arithmetic. No `parseFloat`, no `Number()` on money, no `toFixed()`
as a calculation anywhere in the page.

The band that resolved the price (`RC-2026-MAIN v1 band [4.0, 5.0)`) is shown
alongside, so an operator can see *why* that rate applied.

## 3. Rate cards

New `/rate-cards/[id]` showing what a customer actually asks to see: **the
bands**. A rate card without its bands is a name and a date; with them it is
the rule that decided every amount in the product.

- Card metadata: status, effective period, currency, version, publication date.
- Scope: products and the collection centres it applies to (linked).
- **Rate bands** per matrix, rendered as stored — `45.5000` keeps four
  decimals rather than becoming `45.5`.
- Coverage gaps are surfaced: a reading falling in a gap cannot be priced, and
  the page says so rather than leaving it to be discovered at the gate.
- A short explanation that bands are half-open, so no reading matches two prices.

The lifecycle (draft → submitted → approved → published) and its actions stay
on the list page, which already implements them. Duplicating the actions here
would have created two places to keep correct and only one of them tested.

## 4. Collection detail

Header (id, status, recorded time), collection facts (quantity, gross/tare,
milk type, container, supplier, centre), quality readings (fat, SNF, CLR,
pricing status, rejection reason if any), the pricing breakdown above, and
three chain cards for settlement, payment and receipt.

Each chain card shows either the real record or an honest statement of where
the collection has got to — "the settlement has not been paid yet", "payment
follows settlement".

## 5. Event timeline

The real trail, from `/v1/milk-transactions/{id}/events` — the nine events the
platform records:

```
TransactionCreated → SupplierIdentified → MilkReceived → WeightCaptured →
QualityCaptured → PricingRequested → PricingCompleted → TransactionAccepted →
TransactionCompleted
```

The four money stages that follow (included in settlement, settlement
finalized, payment processed, receipt generated) come from the chain aggregate
and are drawn **as pending until they have actually happened**. No stage is
inferred, and none is invented — a collection that is priced but unsettled must
not look like one that was paid.

## 6. Settlement / payment / receipt integration

One new backend endpoint: `GET /v1/reports/collection/{transaction_id}/chain`.

It lives in **reporting**, which is the module the architecture explicitly
allows to SELECT across boundaries — it owns no data, writes nothing, and
derives every field from columns the owning modules wrote. Putting it in
`milk_collection` would have meant that module querying three others' tables,
which the module-boundary rule forbids.

It follows `settlement_line` → `settlement` → `payment_line` → `payment` →
`receipt`, four keyed lookups filtered by tenant as well as by key. Each stage
is `null` until it happens.

Also added: **date filtering on the collection list** (`date_from` / `date_to`,
applied in SQL). Without it, a portal wanting "last 7 days" would have to pull
every collection a dairy has ever taken and narrow it in the browser — slow
today and wrong at the page boundary once a real dairy has a year of history.

## 7. UI/UX

Existing design system throughout; no new dependency. KPI cards, the shared
`DataTable`, status badges from one vocabulary, breadcrumbs on both detail
pages, loading skeletons, empty and error states per region, and responsive
grids (3 → 2 → 1 columns; wide tables scroll inside their own container).

The timeline is a simple two-column rail — a filled marker for what happened, a
dashed one for what has not — with no animation.

Accessibility: table `<caption>`s, `role="alert"` on errors, labelled filter
controls, status always rendered as a word.

## 8. Tests

| Suite | Result |
| --- | --- |
| Backend (`pytest tests/`) | **1,134 passed, 74 skipped, 0 failed** (was 1,128; **+6**) |
| Portal (`vitest`) | **111 passed** (was 98; **+13**) |
| Portal typecheck | clean |
| Portal lint (`--max-warnings 0`) | clean |
| Portal production build | succeeds — `/transactions/[id]` and `/rate-cards/[id]` present |
| Backend lint + format | clean |

**Backend** (`test_reporting_dashboard.py`): the chain is empty for an
unsettled collection; the chain follows a collection to its receipt with every
hop carrying the same money; the chain stops at the settlement when nothing has
been paid; **another tenant's transaction id reveals nothing**; the date filter
narrows in SQL; the date filter composes with centre, supplier and state.

**Portal** (`collection-pages.test.tsx`): the list renders platform figures;
**every filter and the date window go to the server**; "Clear filters" appears
only when filtered; empty and error states; the pricing calculation is
**printed** with its operands and four-decimal rate intact; the real event
trail renders; the chain shows settlement, payment and receipt; **unhappened
stages are marked pending, never done**; an unpriced collection says "Not
priced" rather than showing a zero; supplier and centre links; the page stays
usable when the trail fails; and a collection that cannot load offers the way
back.

One real bug the tests caught: `humanise` produced Title Case
("Transaction Created") where sentence case was intended. Fixed in the page,
not papered over in the test.

No existing test was weakened or skipped.

## 9. Financial reconciliation

**The demonstration transaction: `8b303dd2-5d6b-4676-ba4f-037a59382207`**

Verified live through the deployed API, and independently in PostgreSQL:

| Step | Value |
| --- | --- |
| Quantity | **10.0 kg** |
| Fat | 4.4 % → band `[4.0, 5.0)` on `RC-2026-MAIN v1` |
| Rate | **45.5000 KES/kg** |
| **Arithmetic** | 10.0 × 45.5000 = **455.00000** — matches the backend's `455.00` exactly |
| Collection value | **455.00 KES** |
| Settlement | `STL-2026-000033`, finalized — this collection contributed **455.00**, settlement net **1,820.00** |
| Payment | `PAY-2026-000017`, completed, MOBILE_MONEY, allocated **1,820.00**, ref `MPESA-STL-2026-000033` |
| Receipt | `RCP-2026-000014`, generated, **1,820.00 KES** |
| Event trail | 9 events, complete |

The chain is real: the settlement line equals the collection's gross amount,
the payment allocation equals the settlement net, and the receipt equals the
payment. Nothing was faked and nothing was created for the demonstration — this
transaction came from the deterministic DEMO-001 seed.

## 10. Live verification

All against https://dev.phoenixsoft.in after deployment.

| # | Check | Result |
| --- | --- | --- |
| 1 | Login (demo manager) | 204 |
| 2 | Dashboard | 200 |
| 3 | Collections list | 200 |
| 4 | Date filter | today → 14 collections; yesterday → 19 — the database narrowed |
| 5 | Supplier filter | 15 collections |
| 6 | Centre filter | 58 collections |
| 7 | Status filter | `REJECTED` → 0 in the demo org |
| 8 | Collection detail | 200 |
| 9 | Pricing breakdown | 10.0 × 45.5000 = 455.00, band shown |
| 10 | Event timeline | 9 real events |
| 11 | Rate cards list | 200 |
| 12 | Rate card detail | 200, 1 matrix with its bands |
| 13 | Settlement / payment / receipt | all three resolved through the chain endpoint |
| 14 | **Tenant isolation** | another org gets **404** on the collection and **all-null** on its chain; sees only its own 3 collections |
| 15 | Served bundle | contains "Lifecycle", "Not priced", "Pricing", "has not been settled yet", "Clear filters", "Calculation" |

## 11. AWS impact

| | |
| --- | --- |
| AWS resources created | **0** |
| AWS resources resized | **0** |
| AWS managed services added | **0** |
| Terraform infrastructure changes | **0** |
| EC2 | `c7i-flex.large`, running — unchanged |
| EBS | 40 GB + 50 GB gp3 — unchanged |
| RDS / ElastiCache / Amazon MQ / ECS / EKS / ALB / NAT Gateway | none exist; none created |

PostgreSQL, Redis and RabbitMQ remain in Docker Compose on the existing EC2.
No demo data was created or deleted by this work order — the PILOT and DEMO
organizations are exactly as DEMO-003 left them.

## 12. Known limitations

1. **No create-collection form.** The work order asked for one "if the existing
   backend supports collection creation". It does — but as a **six-step state
   machine** (create → identify → milk → weight → quality → accept → complete)
   tied to an open collection session at a ready centre, not a single POST. A
   faithful UI is a guided multi-step flow, which is a work order of its own;
   a single form pretending to be one call would have misrepresented how the
   platform works. §13 recommends it as the next piece.
2. **Consequently, live validation-failure checks are partial.** Backend
   refusals are surfaced verbatim wherever the portal mutates (supplier
   activation, centre create/edit from DEMO-003), and the collection pages are
   read-only, so there is no collection-creation failure path to demonstrate yet.
3. **Settlement/payment/receipt links go to the list pages**, not to
   `/settlements/{id}`, because those detail routes do not exist. No dead links,
   but the navigation stops one level short.
4. **Rate-card detail issues one request per matrix** for its bands. Bounded by
   the domain (a card carries a handful), not by data volume — but it is an N+1
   in shape, and a `?include=rows` on the matrix list would remove it.
5. **No sorting on the collections table.** Ordering is the platform's
   (newest first). Adding client-side sort would sort only the page in view and
   lie about the rest; server-side sort needs a backend parameter.
6. **No rate-card → collections link.** No existing contract filters
   collections by rate card, and inventing one was out of scope.
7. **The demo org has no rejected collection in recent windows**, so the
   rejection path shows as 0 in the default view. One exists in the seeded
   history (2026-07-22).

## 13. Recommended DEMO-005

**DEMO-005 — Guided collection capture (the six-step flow).**

This is the one genuinely missing piece of the story and the most persuasive
thing left to build: a stepper that walks an operator through the real state
machine, calling the platform at each step —

1. open or join a session at a **ready** centre (readiness already surfaces the
   reasons when it is not);
2. identify the supplier (manual, code or QR — all three exist);
3. milk type and container;
4. weight, **manual entry only** — never mock hardware;
5. quality, which triggers pricing, then **show the resolved rate and value
   returned by the platform** before accepting;
6. accept or reject, then complete.

Every refusal along the way is already a real business message worth showing:
centre not ready, supplier not active, wrong state, invalid milk type. That
delivers the create-collection workflow and the validation demonstration
together, and it makes the event timeline something a customer watches being
written rather than reads after the fact.

Second priority: **settlement and payment detail pages**, which would complete
the navigation in limitation 3.

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-11 | Platform Engineering | DEMO-004: collections list with server-side filtering and a date window; collection detail with a printed (never recomputed) pricing breakdown, the real nine-event trail and the settlement→payment→receipt chain; rate-card detail with bands; one new reporting endpoint for the chain; deployed as `demo004-091af33`. |
