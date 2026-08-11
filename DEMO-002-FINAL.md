---
id: DEMO-002-FINAL
title: DEMO-002 — Customer Dashboard and Analytics
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-11
last-updated: 2026-08-11
related: [DEMO-001-FINAL, DEMO-SEED, BR-REGISTER]
baseline: ARCH-BASELINE-V1
---

# DEMO-002 — Customer Dashboard and Analytics

**Work order:** DEMO-002
**Date:** 2026-08-11
**Deployed to:** https://dev.phoenixsoft.in — release `demo002-972b2a7`
**Status:** COMPLETE

---

## 1. Dashboard features

| Region | What it shows | Source |
| --- | --- | --- |
| KPI tiles | collections, quantity, collection value, weighted average fat, active suppliers, active centres | `/v1/reports/dashboard` |
| Needs attention | failed payments, settlements awaiting finalization, rejected collections, unpriced accepted collections, inactive centres | same |
| Collection trend | quantity **or** value per day, switchable, with a hover/keyboard readout | `/v1/reports/collection/trend` |
| Settlements and payments | settlement status counts, finalized net total, line count; payment counts across completed / processing / pending / failed, with paid and outstanding money | `/v1/reports/dashboard` |
| Quantity by rate | what was bought at each unit price the rate card resolved to | same |
| Centre performance | quantity, value and ranking per centre | `/v1/reports/collection/by-center` |
| Top suppliers | quantity and value per supplier | `/v1/reports/collection/by-supplier` |
| Recent activity | the platform's own audit trail | `/v1/audit` |
| Date range | Today / Yesterday / Last 7 days / Last 30 days / custom from–to | sent as query parameters to all of the above |

Five requests, each an independent region. No list endpoint is counted, no total
is computed in the browser, and nothing is hard-coded.

## 2. New backend reporting endpoints

All four live in the existing `modules/reporting`, which is already the
platform's declared read-only cross-module reader. Each is tenant-scoped
through `require_current_tenant()` and is a fixed number of grouped queries.

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/reports/dashboard` | One round trip for the KPI block — composes the summaries below rather than re-implementing them |
| `GET /v1/reports/payments` | The payment aggregate DEMO-001 recorded as missing |
| `GET /v1/reports/collection/trend` | Quantity and value per day, empty days present as zeroes |
| `GET /v1/reports/collection/by-rate` | Quantity and value at each resolved unit price |

`dashboard()` **composes** `daily_summary`, `settlement_summary`,
`payment_summary` and `rate_distribution` rather than re-deriving them, so
"accepted" has exactly one definition and a second place to keep true was not
created.

`by-center` and `by-supplier` already existed and are reused unchanged.

## 3. Payment aggregate

`ReportingService.payment_summary()` returns, per status and in total:

- `by_status` — count, summed `amount`, and the currency (or `"MIX"`, the
  convention `CenterSummaryRow` already uses when several appear)
- `completed_count` / `processing_count` / `pending_count` / `failed_count`
- `completed_amount`, `outstanding_amount` (draft + pending + processing),
  `failed_amount`
- `total_by_currency` — the exact per-currency answer

Every figure is `SUM(payment.amount)` over the persisted amounts, in SQL.

Two decisions worth stating. Payments are dated by `created_at`, because a
**failed payment never acquires a completion date** — dating by completion
would have hidden exactly the payments somebody needs to act on. And a failed
payment is counted in neither `completed_amount` nor `outstanding_amount`: it
is money that did not move and is not going to without intervention, which is
its own number and its own attention item.

## 4. Date range

`DateRangePicker` resolves a preset or a custom pair to two ISO dates and sends
them as `date_from` / `date_to` **query parameters**. Nothing is filtered
client-side; changing the range re-asks the database.

Dates are computed in **UTC**, matching the clock the platform stamps a
collection with. Using the browser's local day would put "today" a few hours
out for much of the world, and a dashboard that disagrees with the receipts is
worse than one that shows nothing.

A test asserts every region receives the *same* window, so the page cannot
disagree with itself.

## 5. Tenant isolation

Enforced by the existing principal and RLS architecture — every new query
filters on `require_current_tenant()`, and none of them accepts a tenant from
the browser.

**Tested (backend):**
- `test_every_dashboard_aggregate_is_scoped_to_the_signed_in_tenant` — a second
  organization sees 0 payments, 0 collections, 0 suppliers, no rate bands and
  no attention items while the first sees its own.
- `test_a_forged_tenant_header_cannot_reach_another_organizations_totals` — an
  `X-Tenant-ID` header naming someone else changes nothing.
- Every new endpoint refuses an unauthenticated request (401).

**Verified live on the deployment:** signed in as platform admin acting inside
`Lacteva Isolation Demo`, the dashboard returned `collections 0, payments 0,
suppliers 0, settlements 0` while the PILOT organization returned its real
figures.

## 6. Demo-data reconciliation

The dashboard is only worth something if its numbers are the database's
numbers. Both were checked against **independently written SQL** — not by
re-running the same aggregate.

**Against the DEMO-001 dataset (354 collections, local):**

| Metric | Dashboard | Database | |
| --- | --- | --- | --- |
| transactions | 351 | 351 | ✓ |
| accepted | 350 | 350 | ✓ |
| quantity (kg) | 7868.0 | 7868.0 | ✓ |
| collection value (KES) | 353234.00 | 353234.0 | ✓ |
| payments completed | 21 | 21 | ✓ |
| payments completed amount | 91602.00 | 91602.0 | ✓ |
| payments failed | 2 | 2 | ✓ |
| settlements finalized | 49 | 49 | ✓ |
| settlement finalized net | 223744.50 | 223744.5 | ✓ |
| active suppliers | 24 | 24 | ✓ |
| rate bands | 3 | 3 | ✓ |
| **rate bands sum to collection value** | 353234.00 | 353234.0 | ✓ |

**Against the live deployment (PILOT organization):**

| Metric | Dashboard | Deployed database | |
| --- | --- | --- | --- |
| collections | 5 | 5 | ✓ |
| accepted | 4 | 4 | ✓ |
| quantity (kg) | 100.0 | 100 | ✓ |
| collection value (KES) | 4500.00 | 4500.00 | ✓ |
| settlements finalized | 4 | 4 | ✓ |
| settlement net | 10147.50 | 10147.50 | ✓ |
| payments completed | 4 | 4 | ✓ |
| payments completed amount | 10147.50 | 10147.50 | ✓ |
| active suppliers | 4 | 4 | ✓ |
| active centres | 1 | 1 | ✓ |

Result: **RECONCILED**, both datasets.

One note on method: the first reconciliation run reported four "mismatches"
that were `353234.00` versus `353234.0` — the same number rendered with
different trailing zeros, because the comparison was on strings. The
**comparison** was wrong, not the data; it now compares by `Decimal` value.

## 7. UI/UX

- **KPI tiles** in a responsive grid (3 → 2 → 1 columns), each with a label, a
  figure and a supporting hint.
- **Charts without a charting library.** `TrendChart` is inline SVG with a
  gradient area and a hover/focus readout; `BarBreakdown` is a labelled bar
  list. No dependency was added. The rule is written into the component: *the
  numbers used for geometry are never the numbers used for display* — bar
  heights come from `Number(...)` because a pixel is a float, while every
  figure a human reads is rendered by `<Money>` / `<Quantity>` from the exact
  decimal string.
- **Accessibility:** the chart is `role="img"` with a described label and one
  focusable button per day so the series is reachable by keyboard; the date
  presets are a labelled `role="group"` with `aria-pressed`; the metric toggle
  likewise; the live readout is `aria-live="polite"`; status is always a word,
  never colour alone.
- **Responsive:** two-column card grids collapse to one below `lg`; KPI tiles
  reflow 3 → 2 → 1; the date picker wraps; padding tightens on small screens.
- **Empty, loading and error states** on every region, from DEMO-001's shared
  components. "No action required" is a first-class state, not a blank card.

## 8. Tests and results

| Suite | Result |
| --- | --- |
| Backend (`pytest tests/`) | **1,128 passed, 74 skipped, 0 failed** (was 1,112; +16) |
| New backend suite `test_reporting_dashboard.py` | 16 passed |
| Portal (`vitest`) | **80 passed** (was 72; +8) |
| Portal typecheck | clean |
| Portal lint (`--max-warnings 0`) | clean |
| Portal production build | succeeds, 20 routes |
| Backend lint + format | clean, 206 files |
| **PostgreSQL execution check** | all four new aggregates execute on a real PostgreSQL engine |

The PostgreSQL check earns its place: `func.date(...)` is a built-in on SQLite
and a function-style cast on PostgreSQL. That one expression buckets correctly
on both was an assumption until a real engine ran it — the kind this repository
has learned not to leave untested. A throwaway `pgserver` instance was
migrated from empty and every new aggregate executed against it.

Backend tests cover: counts and sums per payment status; failed money kept out
of both completed and outstanding; money still in flight counted as
outstanding; the empty case; one trend point per day including empty days;
the trend costing one query rather than one per day; rate grouping by resolved
price; rejected milk excluded from rate bands; the composite block; "no
attention items when all is well"; real attention states with counts and links;
date-range honouring; tenant isolation; forged-header rejection; permissions.

Portal tests cover: not crashing on 401; asking nothing while signed out; every
aggregate rendering; money formatting and grouping with decimals preserved;
loading; empty chart state; "no action required"; real exceptions; **a 200
response missing the fields it claims**; one failed widget costing only itself;
the date range going to the backend; and every region receiving the same window.

`home-page.test.tsx` was rewritten rather than edited. The old file asserted on
the platform-health card, which this work order moved off the customer
dashboard (it belongs on Operations). The DASH-001 *guarantee* — never trust a
body you have only cast — is unchanged and is now defended by a stronger test
than before: a 200 response with `{}` for every endpoint.

## 9. Deployment result

**Deployed and verified at https://dev.phoenixsoft.in — release `demo002-972b2a7`.**

| Check | Result |
| --- | --- |
| `deploy.sh` verification | **DEPLOYMENT VERIFIED — the platform is serving** |
| Smoke test | **PASSED** in 0.7s |
| Running images | `platform-core:demo002-972b2a7`, `admin-portal:demo002-972b2a7` |
| Containers | 11, healthy |
| Login (`manager@phoenixsoft.in`) | 204 |
| New endpoints unauthenticated | 401 on all four — present and guarded |
| Dashboard aggregate | returns real PILOT figures (above) |
| Trend | 31 points over 30 days, 2 non-empty — 2026-08-09 (40 kg / 1,800.00) and 2026-08-10 (60 kg / 2,700.00) |
| Centre performance | Kilima Center, 100.0 kg, 4,500.00 KES |
| Supplier performance | Amina Njoroge 80.0 kg / 3,600.00, plus two at 10.0 kg / 450.00 |
| Payments | 4 completed, 10,147.50 paid, 0 outstanding |
| Recent activity | audit records returned |
| Date filter | today → 0 collections; yesterday → 3 collections, 2,700.00 KES |
| Tenant isolation | other organization → 0 across every figure |
| Navigation | all 20 portal routes → 200 |
| Served bundle | contains all seven dashboard sections |

## 10. AWS impact

| | |
| --- | --- |
| AWS resources created | **0** |
| AWS resources resized | **0** |
| AWS managed services added | **0** |
| Terraform infrastructure changes | **0** (`git status infra/terraform/` clean) |
| EC2 | `c7i-flex.large`, running — unchanged |
| EBS | 40 GB + 50 GB gp3 — unchanged |
| Elastic IP / DNS | `15.252.65.201`, dev.phoenixsoft.in — unchanged |
| RDS / ElastiCache / Amazon MQ / ECS / EKS / ALB / NAT Gateway | none exist; none created |
| Cost | 0.00 USD/day, unchanged |

PostgreSQL, Redis and RabbitMQ remain inside the existing Docker Compose stack.
Deployment reused the existing ECR repositories.

## 11. Known limitations

1. **The DEMO-001 dataset is not on the deployment.** The seeder drives the app
   in process and needs `httpx`, which the production image deliberately does
   not carry. The deployment therefore shows the **PILOT** organization's real
   data, which exercises every region but is small (5 collections, 2 active
   days). Options for whoever decides the demo dataset: add `httpx` to the
   runtime image, ship a seeder container, or run the seeder over an SSH tunnel
   to PostgreSQL. Deliberately not chosen here — §19 of the work order defers
   that decision.
2. **One currency tile.** `payable_by_currency` is a map; the KPI shows the
   first entry with a "+N more" hint. Every demo organization is KES-only.
3. **`by_status` amounts across currencies.** If one payment status ever holds
   two currencies, `amount` is a cross-currency sum flagged `"MIX"` — the
   convention already in this module. `total_by_currency` is the exact answer
   and is what the dashboard shows.
4. **Rate bands are labelled by unit price, not by band name.** Grouping by the
   price the engine resolved is exact and needs no new concept, but it will not
   read "4.0–5.0% fat". Joining back to the matrix row would give that.
5. **`total_net_weight_kg` is a float** in the API — a weight, not money, and
   the platform's own choice. Displayed unchanged.
6. **Recent activity is unfiltered audit.** It shows the tenant's audit records
   as-is, so administrative actions appear alongside business ones.
7. **No refresh-on-interval.** The dashboard loads on mount and on demand.
   Polling was left out rather than added speculatively.

## 12. Recommendation for DEMO-003

DEMO-003 is Suppliers + Collection Centers. Before the page work:

1. **Decide the demo dataset presentation** (limitation 1). The dashboard now
   makes the difference obvious: the PILOT organization has two days of data,
   and a customer demo wants the 22-day DEMO-001 dairy. This is the single
   highest-value next decision, and it is a business one.
2. **Convert Suppliers and Centers onto `DataTable`** — the component exists
   from DEMO-001 and both pages are the natural first users of its search,
   filter, pagination and status-badge patterns.
3. **Add supplier and centre detail pages**, then link the dashboard's "Top
   suppliers" and "Centre performance" rows to them. They are deliberately
   unlinked today: DEMO-002's rule was no dead links, and those routes do not
   exist yet.
4. **Consider a toast system** alongside the first form-heavy page, as DEMO-001
   recommended.

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-11 | Platform Engineering | DEMO-002: payment/trend/rate/dashboard aggregates in `modules/reporting`; customer dashboard with date range, charts, centre and supplier performance, attention items and recent activity; reconciled against both datasets; deployed as `demo002-972b2a7`. |
