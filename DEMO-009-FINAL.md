---
id: DEMO-009-FINAL
title: DEMO-009 — Customer Management & Sales
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-12
last-updated: 2026-08-12
related: [DEMO-008-FINAL, DEMO-007-FINAL, CAP-0006, BR-REGISTER]
baseline: ARCH-BASELINE-V1
---

# DEMO-009 — Customer Management & Sales

The procurement half of this platform was complete: supplier → collection →
settlement → payment → receipt. This work order builds the mirror image, which
is what the waiting dairy customers actually asked for:

**customer → delivery → daily report → monthly bill → payment → receipt**

---

## 1. What was built

Three new bounded contexts under the governed **CAP-0006 (Commerce & Market
Access)** capability — `customer` (SLS.02 Buyer Relationship Management),
`delivery` (DST.01 Distribution & Fulfillment) and `billing` — plus five portal
screens and a permission-gated Sales navigation group.

**The central architectural decision: this is not a reuse of the procurement
tables.** The direction of money is the whole reason. A settlement is what the
organization *owes* a supplier and a payment is money going *out*; an invoice is
what a customer owes the organization and a customer payment is money coming
*in*. Forcing the sales side through `settlement`/`payment` would have produced
a payment whose "supplier" is a customer, and an `outstanding` balance meaning
the opposite of what it says.

What *is* reused, entirely: authentication, RBAC, tenant isolation and RLS, the
transactional outbox and Relay, `Decimal` money with one rounding policy,
document numbering, the audit trail, notifications, and every UI component.

---

## 2. Customer domain

| Table | Holds |
|---|---|
| `customer` | code, name, type, phone, alternate phone, address, notes, status, billing mode, billing day, currency |
| `delivery_plan` | the agreed product, standing quantity and **selling rate** |

`CUSTOMER_TYPES` are household, shop, hotel, institution and distributor —
reporting information, not a behaviour switch.

**The rate lives on the plan, and the pricing engine was deliberately not
reused.** That engine prices *procurement*: it resolves a rate card by
collection centre and quality band, because what a cooperative pays a farmer
depends on the fat in the churn. What a customer pays is an agreed selling price
(CAP-0006 CMA.PRI.02), and pushing it through the fat-band matrix would have
produced a number nobody agreed to.

A rate change **supersedes** the plan rather than editing it, so a delivery
priced last week can still be explained — and each delivery records which plan
priced it.

---

## 3. Delivery workflow

`milk_delivery`: customer, date, **slot**, product, quantity, unit price,
amount, status, notes, the plan that priced it, and the invoice that billed it.

Recording a delivery is the busiest thing this side of the platform does — a
dairy with three hundred households does it six hundred times a day — so the
call is small:

```json
{ "customer_id": "…", "delivery_date": "2026-08-12", "slot": "morning", "quantity": "2.000" }
```

Everything else is the domain's:

* **the rate comes from the customer's active plan, never from the client.** A
  round-book operator does not type prices, and a client that could send one
  could sell milk at any price it liked. A portal test asserts the request body
  contains neither `unit_price` nor `amount`;
* **the amount is computed once, here, in `Decimal`,** and stored.

Rules the platform enforces, each proven by a test that makes it refuse:

| Rule | Why |
|---|---|
| One delivery per customer, day and **slot** | A second morning delivery is a correction, not another sale — and would double the bill. The evening round is a different delivery and is accepted. |
| A customer with no plan cannot receive a delivery | A rate has to be agreed before milk is sold at it. |
| An inactive customer cannot receive a delivery | |
| A skipped or returned delivery is worth **0.00** | Only milk that arrived is billable. |
| A **billed** delivery cannot be amended | It is a line on a statement the customer already has. |

---

## 4. Daily delivery report

`GET /v1/deliveries/report?date_from=…&date_to=…&customer_id=…`

Answers the two questions asked by name — "what milk was delivered to this
customer today?" and "…over this period?" — in **four grouped queries**,
whatever the size of the window: deliveries, customers served, total quantity,
total value, skipped count, and a per-day breakdown.

The delivery **list** additionally returns `total_quantity` and `total_amount`
for the *whole filtered set*, cast to unconstrained `NUMERIC` inside the
aggregate the way every other exact sum on this platform is. The screen says so
in as many words — *"Across all 36 matching deliveries"* — because a report that
adds up one page is not a report.

Date filters: Today, Yesterday, Last 7 days, Last 30 days and a custom range,
all applied by the database.

---

## 5. Monthly billing

`customer_invoice` + `customer_invoice_line`.

An invoice is **generated from deliveries, never typed**. Its lines are copies
of real delivery rows — copied for the same reason a settlement line copies its
calculation: a statement handed to a customer must still say what it said, even
if the delivery is later corrected. Generating it stamps each delivery with the
invoice id, so the same milk cannot be billed twice.

It carries **`previous_balance`** — the dairy's "brought forward" line — stored
rather than derived, so the statement reads the same a year later.
`amount_due = total + previous_balance`, and `adjustments` is fixed at zero
exactly as BR-0011 fixes settlement adjustments, so the arithmetic already
carries the term.

**Issuing is irreversible** and the page says what cannot be undone before it
happens — the same rule BR-0010 applies to a finalized settlement. An issued
invoice cannot be edited or cancelled; a correction is a new document. The
detail page shows the platform's own `totals_match_lines` verdict rather than
summing the lines in the browser, and shows a mismatch in red rather than
hiding it.

---

## 6. Payment and receipt handling

`customer_payment` + `customer_payment_allocation` + `customer_receipt`.

A customer payment is **money already received**, so unlike a supplier payment
there is no provider to execute against and no attempt to retry: the lifecycle
is one step. Allocations apply it to the oldest unpaid bills first — which is
what a dairy does — and a remainder stays as credit on the account, reducing the
next invoice's brought-forward figure rather than being discarded.

The **receipt is generated by a consumer** from
`sales.customer-payment-recorded.v1`, exactly as BR-0020 requires on the
procurement side: no billing code knows receipts exist, and a redelivered event
finds the receipt already there rather than minting a second proof of the same
money. A test runs the consumer three times and asserts one receipt.

---

## 7. RBAC

Ten permissions registered in the existing registry, and composed into the
existing roles the DEMO-008 way — **no new authorization mechanism**:

```
sales.customer.read/manage   sales.delivery.read/record
sales.invoice.read/manage/issue   sales.payment.read/record   sales.receipt.read
```

`sales.invoice.issue` is separated from `sales.invoice.manage` for the same
reason `settlement.finalize` is separated from `settlement.manage`: issuing is
the irreversible one, and it belongs to `FINANCE_MANAGER`.

| Role | Sales grant |
|---|---|
| `tenant-admin` / `ORGANIZATION_ADMIN` | all ten |
| `ORGANIZATION_MANAGER` | read + record deliveries; no issue, no payments recorded |
| `FINANCE_OFFICER` | read, prepare bills, record payments — **not** issue |
| `FINANCE_MANAGER` | officer + `sales.invoice.issue` |
| **`SALES_OFFICER`** *(new)* | the milk round and the customer book: customers, deliveries, bills, payments — nothing on the procurement side |
| `AUDITOR` / `tenant-viewer` | the five reads |

The right to record a milk **delivery** is deliberately not the right to record
a milk **collection**. A test asserts a principal without `sales.*` is refused
every sales endpoint.

---

## 8. Database migrations

| Revision | Change |
|---|---|
| `b3e18f736894` | the eight sales tables, purely additive |
| `c8a4d2f10b73` | **row-level security policies for those tables** — see §13 |

Both verified up → down → up. The unique constraints are the load-bearing part:
one delivery per customer/day/slot; one **live** invoice per customer and period
(partial, excluding cancelled — §13); one invoice line per delivery; one receipt
per payment.

---

## 9. Demo data

Additive. **Nothing was reseeded and nothing deleted** — every supplier,
collection, settlement, payment and receipt from DEMO-001…008 is untouched.

Six customers across all five types, thirty days of deliveries each with
deterministic skipped days, and a ledger chosen to show the states a dairy
actually has:

| Customer | Delivered | Invoiced | Paid | Receipt | State |
|---|---|---|---|---|---|
| Mama Njeri Household | 3,658.00 | 3,658.00 | 3,658.00 | ✓ | fully paid |
| Kilima Tea House | 12,992.00 | 12,992.00 | 6,496.00 | ✓ | part paid |
| Ngong View Hotel | 30,800.00 | 30,800.00 | 0.00 | — | unpaid |
| St. Mary's School | 51,030.00 | 51,030.00 | 51,030.00 | ✓ | fully paid |
| Wanjala Distributors | 84,240.00 | 0.00 | 0.00 | — | delivered, not yet billed |
| Achieng Household | 2,697.00 | 0.00 | 0.00 | — | delivered, not yet billed |

The seeder's `verify` now reconciles the sales side too — invoice against its
lines, `amount_due` against `total + previous_balance`, receipt against its
payment — so a future seed cannot go green on figures that do not add up.

---

## 10. Financial reconciliation

Ten checks, run **by PostgreSQL against the deployed database**, each written to
return rows only on failure. **All ten returned zero rows.**

| # | Check | Result |
|---|---|---|
| 1 | invoice subtotal ≠ sum of its lines | 0 |
| 2 | invoice line ≠ the delivery it billed (amount, quantity, rate) | 0 |
| 3 | a delivery billed on more than one invoice | 0 |
| 4 | delivery amount ≠ quantity × unit price | 0 |
| 5 | a skipped or returned delivery worth money | 0 |
| 6 | `amount_due` ≠ `total + previous_balance` | 0 |
| 7 | payments allocated beyond an invoice total | 0 |
| 8 | receipt ≠ its payment | 0 |
| 9 | rows crossing a tenant boundary (3 joins) | 0, 0, 0 |
| 10 | money stored with more than 2 decimal places | 0, 0, 0 |

---

## 11. Tests

**Backend — `tests/test_sales_workflow.py`, 25 tests.** Customer registration
and plan supersession; database-side search; a delivery priced by the platform;
the standing order; the per-slot uniqueness (and the evening round being
allowed); skipped worth nothing; refusals for no-plan and inactive customers;
the report totalling the whole period in SQL and counting skips without billing
them; the list's totals covering the filtered set; **the invoice reconciling
exactly with its deliveries**; the same milk refused twice; issued-invoice
immutability; a billed delivery refusing amendment; cancellation releasing
deliveries; payment settling and part-settling; the receipt generated from the
event; consumer idempotency; brought-forward balance; sales permissions; and
cross-tenant invisibility.

**Portal — `src/app/sales-pages.test.tsx`, 15 tests.** Customer list and
server-side filters; the account summary from the backend's figures; **a
delivery recorded without sending a price**; **no computed amount preview**; the
history and platform totals; bill and receipt links; payment recording; the
report rendered day by day; totals stated as covering the whole set; the
statement and its reconciliation verdict; a reconciliation **failure** shown
rather than hidden; no lifecycle control on an issued bill; and the
irreversibility confirmation.

---

## 12. Live verification

Deployed to **https://dev.phoenixsoft.in** as `demo009-edf6382`, then driven in
**real Chrome**: 23 of 24 checks passed on the first corrected run.

Verified on screen: the customer list with codes; the account summary
(outstanding / invoiced / paid / not-yet-billed); the delivery form stating
*"The amount is computed by the platform from that rate — it is never typed
here"*; delivery history with **1.500 L at 62.0000 = 93.00 KES** and a skipped
day at **0.00**; totals of 48.000 L / 2,697.00 KES matching the database
exactly; the bill INV-2026-000001 over 28 deliveries at 3,658.00, paid, with
receipt CRC-2026-000001; the per-day report; the statement's *"still equals the
28 lines below — verified by the platform"*; and the brought-forward line.

**Existing workflows confirmed intact**: `/transactions`, `/settlements`,
`/suppliers`, `/centers` all still render. Responsive at 1440×900, 834×1112 and
390×844 with no horizontal overflow.

The one remaining failure was my own test assertion, not the product: it opened
the first customer alphabetically (Achieng Household), who is *deliberately* one
of the two with no bill. Opening a billed customer directly showed everything
expected.

---

## 13. Defects found and fixed

Four, three of them found by the platform's own guards rather than by review.

1. **The new tenant-owned tables had no row-level security.** On this platform
   RLS is installed *by migrations*, not at startup, so a migration that adds a
   tenant-owned table and stops there leaves it protected by application filters
   alone. **The deployment verifier caught it and failed the deploy** — exactly
   what SEC-002 built it for. Fixed in `c8a4d2f10b73`; the PostgreSQL proof now
   reports **61 policies present**. The exposure was latent rather than live:
   the rolled-back image had no sales endpoints, so nothing could reach the
   tables.
2. **A cancelled invoice would have blocked its own billing period forever.**
   The unique constraint on (tenant, customer, period) counted cancelled rows,
   so an operator who cancelled a draft with the wrong dates could never
   re-issue it. Now a **partial** unique index on `status <> 'cancelled'`.
3. **Cancelling a draft left its lines behind**, holding the per-delivery
   uniqueness and making the released deliveries unbillable — the opposite of
   what cancelling is for. A cancelled draft was never issued, so its lines are
   working material and are now deleted with it.
4. **`/customers?q=…` ignored the URL**, so a deep link silently showed the
   unfiltered list — which looks like a filter that does not work. The page now
   reads its filters from the URL.

---

## 14. Known limitations

1. **This is not a general ledger.** No accounts, journals, tax engine or
   revenue recognition. An invoice here is the statement a dairy hands a
   household; production accounting remains to be designed.
2. **Adjustments are fixed at zero.** Discounts, penalties and credit notes have
   no mechanism yet — the field exists and carries the term through the
   arithmetic, but nothing can write it. A correction to an issued bill is
   therefore a new bill, and the platform says so.
3. **No customer-facing portal.** Everything is the dairy's staff view; a
   customer cannot log in to see their own statement.
4. **Delivery is single-product.** A plan covers one product per customer, which
   is right for raw milk and wrong the moment a dairy sells yoghurt as well.
5. **No delivery scheduling or route planning.** The plan is a standing
   quantity, not a round with an order and a driver — CMA.DST.01's fulfilment
   half is not built.
6. **Payments cannot be cancelled through the API.** The model has the state;
   no endpoint writes it. A mistaken payment currently needs a correcting entry
   that this domain does not yet have.
7. **Invoice generation is per-customer.** Billing a hundred households at
   month end is a hundred calls; a bulk run is the obvious next step.
8. **No PDF.** Receipts and statements are JSON/HTML; the procurement receipt
   module has rendering that this side does not yet reuse.

---

## 15. AWS impact

| | |
|---|---|
| AWS resources created | **0** |
| AWS resources resized | **0** |
| Managed services created | **0** |
| Terraform infrastructure changes | **0** |
| Additional AWS cost | **0** |

PostgreSQL, Redis and RabbitMQ remain in Docker Compose on the existing EC2.

**Two host issues were resolved at zero cost**, and both are worth recording:

* **The portal build ran out of memory** (`spawn ENOMEM`) once the app passed
  ~30 routes. Next.js fans static generation out to one worker per CPU and each
  worker is a full Node heap; the host also runs `vm.overcommit_memory=2`
  (strict accounting), under which forking from a large heap is refused. Fixed
  with `experimental.cpus: 2` and `webpackMemoryOptimizations` — **cheaper and
  more honest than resizing the instance for a build that does not need the
  room.**
* **The disk reached 100%.** Accumulated Docker images and build cache; 11 GB
  reclaimed, now at 76%. This will recur — see the recommendation below.

---

## 16. Recommended DEMO-010

**Customer-facing demonstration and end-to-end story**, per the roadmap. The
pieces now exist on both sides of the business; DEMO-010 should be the run
through them that a dairy owner watches without an engineer present:

supplier delivers → collection priced → settlement → supplier paid → **milk
delivered to a customer → daily report → monthly bill → customer pays →
receipt** — with the money reconciled at every hop.

Two operational items to fold in, both found here:

* **a disk-space guard on the build host.** Prune-on-deploy, or a check that
  fails the deploy before the disk does. It filled twice during this work order
  and a full disk takes the platform down;
* **bulk month-end billing**, since a hundred households at one call each is the
  first thing a real dairy will hit.

---

## Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-08-12 | Platform Engineering | DEMO-009: the receivable half of the business — customer, delivery and billing as three new bounded contexts under CAP-0006, deliberately not a reuse of the procurement tables because the direction of money is the whole distinction; delivery priced by the customer's agreed plan and computed once in `Decimal` by the domain; a daily report aggregated in SQL; a monthly bill generated from deliveries that reconciles exactly with them and is immutable once issued; customer payments with allocations and a receipt generated by a consumer from the payment event; ten `sales.*` permissions and a `SALES_OFFICER` role composed from the existing registry; 40 new tests; ten PostgreSQL reconciliation checks all clean; verified in a real browser. Four defects fixed, three of them caught by the platform's own guards — including missing RLS on the new tenant-owned tables, which failed the deploy exactly as intended. Deployed as `demo009-edf6382`. |
