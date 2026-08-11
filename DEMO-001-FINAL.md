---
id: DEMO-001-FINAL
title: DEMO-001 — Demo Data Foundation and UX Architecture
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-11
last-updated: 2026-08-11
related: [DEMO-SEED, PILOT-F03-FINAL, BR-REGISTER]
baseline: ARCH-BASELINE-V1
---

# DEMO-001 — Data Foundation + UX Architecture

**Work order:** DEMO-001 (first phase of the demo program)
**Date:** 2026-08-11
**Scope:** a repeatable demo dataset, and a shared UI foundation. Not a redesign
of every page.

---

## 1. Files changed

**Added**

| File | What it is |
| --- | --- |
| `infra/demo/seed_demo.py` | The demo dataset — seed / verify / purge / reset / consumers |
| `infra/demo/README.md` | How to seed, verify, reset and remove it |
| `apps/admin-portal/src/components/app-shell.tsx` | Sidebar + top bar application shell |
| `apps/admin-portal/src/components/data-table.tsx` | Reusable table with its four states, plus pagination |
| `apps/admin-portal/src/components/money.tsx` | `Money` / `Quantity` — format, never calculate |
| `apps/admin-portal/src/components/status-badge.tsx` | One status vocabulary across every lifecycle |
| `apps/admin-portal/src/components/states.tsx` | Loading, skeleton, empty and error states |
| `apps/admin-portal/src/components/page-header.tsx` | `PageHeader` with breadcrumbs, and `StatTile` |
| `apps/admin-portal/src/components/foundation.test.tsx` | 15 tests for the above, most of them about money |

**Changed**

| File | Change |
| --- | --- |
| `apps/admin-portal/src/app/layout.tsx` | Renders `AppShell` instead of the flat `Nav` |
| `apps/admin-portal/src/app/page.tsx` | Dashboard rebuilt on the platform's `/v1/reports/*` aggregates |
| `apps/admin-portal/src/app/admin/admin-pages.test.tsx` | NAV-001 / PERM-001 / TENANT-001 tests re-pointed at `AppShell` |
| `apps/admin-portal/src/app/home-page.test.tsx` | Same DASH-001 guarantees, wording matched to new copy |

**Removed**

| File | Why |
| --- | --- |
| `apps/admin-portal/src/components/nav.tsx` | Replaced by `AppShell`. Deleted rather than left behind, because its tests would then have guarded a component the product no longer renders. |

No backend module, migration, API contract or business rule was modified.

---

## 2. Demo data architecture

`infra/demo/seed_demo.py` drives the platform's **own API in process** — the
same endpoints an operator uses, through the same authorization, the same
pricing engine, the same settlement rules. It calculates nothing. If the demo
dashboard shows 1,800.00 KES, that number came out of `pricing/calculator.py`.

Three properties were designed for deliberately:

**Deterministic.** No randomness anywhere. Quantities, quality readings, names
and dates come from fixed tables indexed by row number, so two runs a week
apart build the same dairy relative to the day it is run, and a screenshot
taken today still matches the demo tomorrow.

**Real.** Centres are made genuinely READY (hours, active, an operator, a live
scale) because the platform refuses to open a collection session at a centre
that is not. Suppliers are assigned to a centre *before* activation because the
platform refuses to activate a supplier with nowhere to deliver. Rate cards are
submitted, approved and then published rather than appearing published by fiat.
Each of those is governance a customer is being shown; skipping it in a seeder
would demo a product that does not exist.

**Scoped.** Everything lives in two named organizations, and `purge` deletes by
`tenant_id` using `core/rls.py`'s own declaration of which tables are
tenant-owned — so a table added later is covered without editing the seeder, and
pilot data in other organizations cannot be caught by it.

### The one direct write, stated plainly

A collection's business date **is** its creation date
(`tx_date = as_utc(tx.created_at).date()`), and the platform has no back-dating
API — rightly, since an operator must not be able to move milk through time. But
a demo with only today's data has nothing to settle and looks dead.

So the seeder stamps `created_at` on the transaction row immediately after
creation and **before** pricing. The domain then prices, settles and pays it as
a genuine collection on that day. That timestamp is the only value written
directly to a business table, and it is written before any money exists.

---

## 3. How to seed / 4. How to reset

```bash
python infra/demo/seed_demo.py seed       # build
python infra/demo/seed_demo.py verify     # assert present and consistent (exit 1 if not)
python infra/demo/seed_demo.py purge      # remove — demo organizations only
python infra/demo/seed_demo.py reset      # purge, then seed
python infra/demo/seed_demo.py consumers  # relay + drain: mint receipts and notifications
```

Locally, against a scratch database:

```bash
cd services/platform-core && .venv/bin/alembic upgrade head
cd ../.. && LACTEVA_DATABASE_URL=sqlite+aiosqlite:///./demo.db \
  services/platform-core/.venv/bin/python infra/demo/seed_demo.py seed
```

On the deployed host, inside the API container (it already has the app and the
database URL):

```bash
sudo docker compose -f docker-compose.production.yml --env-file /etc/lacteva/.env.production \
  exec -T api python /app/infra/demo/seed_demo.py seed
```

Full detail in [`infra/demo/README.md`](infra/demo/README.md).

---

## 5. Demo organizations

| Organization | Slug | Purpose |
| --- | --- | --- |
| Lacteva Demo Cooperative | `lacteva-demo` | The dairy the customer is shown |
| Lacteva Isolation Demo | `lacteva-isolation-demo` | Deliberately small — exists so tenant isolation can be *demonstrated*: sign in here and the other organization's 24 suppliers are not merely hidden, they answer 404 |

## 6. Demo users and roles

| Email | Role | Organization |
| --- | --- | --- |
| `manager@lacteva-demo.example.com` | tenant-admin | Lacteva Demo Cooperative |
| `viewer@lacteva-demo.example.com` | tenant-viewer | Lacteva Demo Cooperative |
| `manager@lacteva-isolation.example.com` | tenant-admin | Lacteva Isolation Demo |
| `demo-admin@lacteva.example.com` | platform-admin | none (platform session) |

Password from `DEMO_PASSWORD`, default `Demo-Lacteva-2026!`. Every account is
created through the real invitation flow — invite, capture the token from the
delivered message, accept — so the demo cannot contain an account the platform
would not have issued.

The whole dairy is then built **as the manager**, not as the platform admin, so
the audit trail names a person with the permissions to have done the work.

## 7. Demo suppliers and centres

- **5 centres** in the main organization — Kilima Hill, Ngong Valley, Limuru
  Ridge, Naivasha Lakeside, Kiambu Highlands — each hours-configured, active,
  operator-assigned and with an active scale. One more in the second organization.
- **24 suppliers** with believable Kenyan names, each assigned to a centre and
  activated. Three more in the second organization.
- Each supplier has a fixed fat percentage straddling the band boundaries, so
  the demo shows all three rates rather than one repeated number.

## 8. Demo transactions and money

Measured on a full local run:

| | |
| --- | --- |
| Completed collections | **354** across 22 days |
| Rejected collection | 1 — real dairies reject milk |
| Open session | today's, left open, so the demo shows work in progress |
| Settlements | **49**, all finalized |
| Payments | **25** — completed, processing and failed |
| Receipts | **21**, generated by the consumer |

Rate cards: a superseded 2025 card, the published 2026 card in force, and a
2027 draft awaiting approval — so price history and the approval workflow are
both visible.

**BR-0027 is demonstrated, not described.** A collection is recorded into a
period *after* that period was finalized, is stranded exactly as PILOT-001 found,
and is carried forward into a later open settlement and paid. On the verified
run: a collection dated 2026-07-24 carried into `STL-2026-000049`, net 1,008.00.

---

## 9. UI/UX components created

| Component | What it establishes |
| --- | --- |
| `AppShell` | Grouped sidebar (Operations / Pricing / Finance / Platform), top bar with organization, user, role and sign-out, mobile drawer, active-route highlighting |
| `DataTable` | One table pattern: toolbar, loading skeleton, empty state, error state with retry, server-side pagination, horizontal scroll for wide financial tables |
| `Money` / `Quantity` | Formatting only — see §11 |
| `StatusBadge` | One vocabulary across supplier, transaction, settlement, payment, receipt, rate card and device lifecycles |
| `LoadingState` / `TableSkeleton` / `EmptyState` / `ErrorState` | The four states every data view has |
| `PageHeader` / `StatTile` | Page title, description, breadcrumbs, actions; and the dashboard's unit of currency |

**Accessibility, built in rather than retrofitted:** every table carries a
`<caption>` naming what it holds; errors use `role="alert"`; the loading state
uses `role="status" aria-live="polite"`; the active nav item sets
`aria-current="page"`; the mobile drawer toggle carries `aria-expanded`; icons
are `aria-hidden` so meaning lives in text; focus rings are explicit; and status
is **always** rendered as a word, never colour alone.

**Responsive:** the sidebar collapses to a drawer below `lg`; stat tiles reflow
4 → 2 → 1; secondary table columns hide below `md`; wide tables scroll inside
their own container rather than being crushed.

No new UI dependency was added. Everything uses the existing shadcn/Base UI
primitives, Tailwind tokens (including the `--sidebar-*` tokens already defined)
and `lucide-react`.

## 10. Routes affected

Only `/` (the dashboard) changed. The shell now wraps every route, so all
eighteen destinations render inside it, but no other page's markup was touched —
this work order was explicitly not a redesign of every business page.

Navigation maps only to routes that exist. There are no dead links.

---

## 11. Business rules preserved

- **No calculation was moved into the browser.** `Money` splits an exact decimal
  *string* and groups the digits with a regular expression — no `Number`, no
  `parseFloat`, no `toFixed`. Four tests pin this, including `45.0000` keeping
  its significant trailing zeros and a 17-digit value surviving intact, because
  `0.1 + 0.2 !== 0.3` and a settlement that disagrees with its own lines by a
  cent is one no cooperative will sign.
- **The dashboard asks the platform for its totals.** It reads
  `/v1/reports/collection/daily` and `/v1/reports/settlements`, where the sums
  are exact `Decimal` inside the database. It previously counted rows from five
  list endpoints; it now reports money the platform computed.
- **Nothing is hard-coded.** No fabricated totals anywhere. Where a figure is
  unavailable the page shows an error or an em dash — never a plausible number.
- NAV-001, PERM-001, TENANT-001 carried over intact and still tested. DASH-001's
  "check the status before believing the body" carried over, and was reinforced
  (§12).
- BR-0027, BR-0011, BR-0009, BR-0010 all exercised by the seed and asserted by
  `verify`.

## 12. Tests executed

| Suite | Result |
| --- | --- |
| Backend (`pytest tests/`) | **1,112 passed, 74 skipped, 0 failed** |
| Admin portal (`vitest`) | **72 passed** (was 57; +15 new) |
| Portal typecheck (`tsc --noEmit`) | clean |
| Portal lint (`eslint --max-warnings 0`) | clean |
| Portal production build | succeeds, all 20 routes |
| Demo seed → verify → purge → verify | full lifecycle exercised; purge removed 14,217 rows across 2 organizations and nothing else |
| Docs validation / xref | 163 files, all checks passed |
| Mobile (Flutter) | not run — no mobile code touched |

**A test caught a real bug in this work order's own code.** The first draft of
the rebuilt dashboard read `settlements.data.by_status.map(...)` on a body whose
shape it had merely *cast*. The DASH-001 regression test — which feeds the page a
response that is 200 but the wrong shape — crashed it immediately. That is the
identical defect class DASH-001 recorded (`Object.entries(undefined)`), caught
this time before it shipped. Every field read from a response body is now
guarded.

Two existing test files were edited. Neither was weakened:

- `admin-pages.test.tsx` — the NAV-001/PERM-001/TENANT-001 tests now render
  `AppShell` instead of the deleted `Nav`. Same assertions, pointed at the
  component the product actually renders.
- `home-page.test.tsx` — same four DASH-001 guarantees, with the text matchers
  updated to the new copy.

## 13. AWS resources changed

**ZERO**, as required.

| | |
| --- | --- |
| EC2 instance type / state | unchanged (`c7i-flex.large`, running) |
| EBS volumes | unchanged (40 GB + 50 GB gp3) |
| Elastic IP / DNS | unchanged (`15.252.65.201`, dev.phoenixsoft.in) |
| RDS / ElastiCache / Amazon MQ / ECS / EKS / ALB / NAT Gateway | none exist; none created |
| Terraform | not run, not modified |
| Cost impact | none — no resource created or changed |

The existing dev deployment remained functional throughout; `dev.phoenixsoft.in`
answered 200 at the end of the work order.

## 14. Known limitations

1. **Not deployed.** The new UI and the demo dataset exist in the repository and
   are proven locally, but `dev.phoenixsoft.in` still runs `f2023fc-f03` with the
   PILOT dataset. This work order's AWS-safety section says "Production
   deployment: NONE", so deploying was left out deliberately rather than
   forgotten. It is the first task of DEMO-002.
2. **Seeding is slow** — several minutes, because it walks ~350 collections
   through the full state machine one HTTP call per step. That slowness is the
   price of the numbers being real.
3. **Only the dashboard was restyled.** The other seventeen pages render inside
   the new shell but still use their original layouts. That is the work order's
   intent, not an oversight — DEMO-003 onward converts them.
4. **The dashboard shows one currency tile.** `payable_by_currency` is a map;
   the tile shows the first entry and a "+N more" hint. Every demo organization
   is KES-only, so this is not visible today, but a genuinely multi-currency
   tenant needs a better treatment.
5. **No toast/notification system.** Listed in the work order's component
   inventory; the pages that would need it are not yet converted, so adding one
   now would be speculative. DEMO-003 should add it alongside the first
   form-heavy page.
6. **No date picker.** Same reasoning — no converted page needs one yet.
7. **`total_net_weight_kg` is a float in the API.** It is a weight, not money,
   and the platform chose that type; the portal displays it unchanged. Worth
   noting because it is the one figure on the dashboard that is not exact
   decimal end to end.

## 15. Recommended next work order

**DEMO-002 — Dashboard and deployment of the demo environment.**

In this order:

1. **Deploy** the DEMO-001 build to `dev.phoenixsoft.in` and seed the demo
   dataset in the API container, so there is a live demo URL. Use
   `API_URL=https://dev.phoenixsoft.in`, and note that `repoint_nginx` now runs
   automatically (PILOT-F03).
2. **Decide what happens to the PILOT data** already in that database. It is a
   third organization with its own suppliers and settlements. Recommendation:
   leave it — it is real evidence — but confirm, because a customer signing in
   as the platform admin will see it listed.
3. **Complete the dashboard**: collections by centre and by supplier already
   exist as endpoints (`/v1/reports/collection/by-center`, `by-supplier`) and
   would give the demo a chart without any new backend work.
4. **Add the payment aggregate the dashboard cannot show today.** There is a
   settlement summary but no payments summary, so "pending payments" and
   "completed payments" would have to be counted client-side — which this work
   order deliberately refused to do. That is a small, well-scoped backend
   addition to `modules/reporting`.

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-11 | Platform Engineering | DEMO-001: deterministic demo dataset driven through the real API; shared UI foundation (shell, table, states, money, status, page header); dashboard rebuilt on platform aggregates; `Nav` retired into `AppShell` with its guarantees intact. |
