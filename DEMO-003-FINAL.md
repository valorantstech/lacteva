---
id: DEMO-003-FINAL
title: DEMO-003 — Demo Environment, Suppliers and Collection Centres
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-11
last-updated: 2026-08-11
related: [DEMO-002-FINAL, DEMO-001-FINAL, DEMO-SEED]
baseline: ARCH-BASELINE-V1
---

# DEMO-003 — Demo Environment + Supplier & Centre Management

**Work order:** DEMO-003
**Deployed to:** https://dev.phoenixsoft.in — release `demo003-5a6a686`
**Status:** COMPLETE

---

## 1. Demo dataset deployed

**The DEMO-001 dairy is now in the deployed PostgreSQL database.**

DEMO-002 reported this blocked: the seeder drives the app in process and needed
`httpx`, which is a **dev** dependency the production image correctly installs
`--no-dev`. Rather than bloat the runtime image or build a second one to hold a
single library, the dependency was **removed**: the seeder's surface is four
verbs and a JSON body, so the ASGI call is now written out directly
(`AsgiClient`, ~60 lines). There is no connection, no pooling and no wire
format — the app is a coroutine and the client hands it a scope.

Result: the seeder runs **inside the unmodified production image**, and it
produced byte-identical figures to the local run, on a different engine.

### Verified in the deployed PostgreSQL, by independent SQL

| Expected | Found in PostgreSQL | |
| --- | --- | --- |
| 2 organizations | **2** (`lacteva-demo`, `lacteva-isolation-demo`) | ✓ |
| 5 centres | **5** | ✓ |
| 24 suppliers | **24** | ✓ |
| 354 completed collections | **351** in the demo cooperative + **3** in the isolation org = **354** | ✓ |
| 1 rejection | **1** | ✓ |
| 49 finalized settlements | **49** | ✓ |
| 25 payments | **25** | ✓ |
| 21 receipts | **21** | ✓ |

### Financial reconciliation (deployed PostgreSQL)

| Metric | Value |
| --- | --- |
| Collection value | **353,234.00 KES** |
| Quantity | **7,868 kg** |
| Settlement net total (finalized) | **223,744.50 KES** |
| Payments completed | **91,602.00 KES** |

Every figure is identical to the local SQLite run reported in DEMO-002 —
deterministic across two engines. The seeder's own `verify` also passes on the
deployment: `problems: []`, `ok: true`.

**This is DEMO data.** It is generated deterministically through the real domain
services — pricing engine, settlement engine, payment lifecycle — and no total
was written directly. See `infra/demo/README.md`.

## 2. Demo data isolation (Phase B)

**PILOT data was not deleted.** The database now holds four organizations:

| Organization | Slug | Origin |
| --- | --- | --- |
| Phoenix Demo Dairy | `phoenix-demo` | **PILOT** — preserved evidence |
| Isolation Probe Dairy | `isolation-probe` | **PILOT** — created for PILOT-001's cross-tenant test |
| Lacteva Demo Cooperative | `lacteva-demo` | **DEMO** — the dairy to show a customer |
| Lacteva Isolation Demo | `lacteva-isolation-demo` | **DEMO** — exists so isolation can be demonstrated |

Organizations are selected through the **existing** mechanism: a tenant-scoped
login (email + password + organization id) or, for a platform session, the
organization selector already in the application shell. Nothing new and nothing
less safe was introduced.

**Isolation verified live on the deployment.** Signed in to
`Lacteva Isolation Demo`, the dashboard reports 3 collections, 3 suppliers, 1
centre and 0 settlements — its own data only. Fetching the demo cooperative's
supplier or centre by id from that session answers **404, never 403**, so the
other organization's existence is not even disclosed.

## 3. Collection centre features (Phase C)

**List** — server-side search (`q`), status filter, pagination. Columns: centre
name and code, status, timezone, collections, quantity, value, last activity,
actions. Activity comes from `/v1/reports/collection/by-center`, aggregated in
SQL; nothing is totalled in the browser. Loading, empty (worded differently for
"no centres" vs "no match"), and error-with-retry states throughout.

**Detail** — overview and status, **readiness**, operating hours, collection
statistics, quantity trend, suppliers delivering there, settlement summary, and
recent collections. Every panel is an existing contract filtered by `center_id`;
no endpoint was invented to fill a screen. Each loads independently.

**Readiness is the platform's own evaluation**, check by check, with the reason
each failing one gives — not a green badge inferred from the record existing. A
live centre currently reports `WARNING` with 2 of 6 checks failing, and the UI
names them.

**Create / edit** — client validation on name, code (immutable after creation),
timezone (IANA form) and branch, with per-field messages, required markers and
`aria-invalid`. Client validation exists to give a fast, specific message and
**never** to decide what is allowed: the platform's refusal is displayed
verbatim, because a form that invents its own reason will eventually invent a
wrong one.

## 4. Supplier features (Phase D)

**List** — server-side search, status filter and **centre filter** (the platform
already supported `center_id`; the portal simply had no way to ask). Columns:
name and code, status, phone, collections, quantity, value, last collection,
actions.

**Detail** — profile, assigned centres (linked), collection statistics,
switchable quantity/value trend, settlement summary, payment summary and recent
collections. All from existing contracts filtered by `supplier_id`.

**Activation respects the business rule.** The UI does not bypass it and does not
hide the button: it asks the platform, and when the platform refuses —
*"cannot activate a supplier without a collection center assignment"* — that
sentence is shown to the operator. A draft supplier with no centre also carries
a note explaining what is missing before they try.

## 5. Backend changes

Deliberately minimal — almost everything needed already existed.

| Change | Why |
| --- | --- |
| `last_collection_at` added to `CenterSummaryRow` and `SupplierSummaryRow` | "Last activity" was the one figure the list pages needed and no aggregate had. One `MAX(created_at)` in the existing grouped query — an operator scanning a list needs "is this still working?", and a quantity alone cannot say: a busy centre and one that stopped a fortnight ago look identical. |
| `AsgiClient` in the seeder | Removes the `httpx` dependency so the seeder runs in the production image (§1). |
| Portable `sys.path` bootstrap in the seeder | Runs from the repository or from inside the image without requiring the other's layout. |

**No new endpoints were created.** Centre and supplier detail pages are built
from `/v1/collection-centers/{id}`, `/readiness`, `/v1/suppliers/{id}`,
`/v1/milk-transactions`, and the reporting aggregates filtered by `center_id`
or `supplier_id` — filters those contracts already accepted.

## 6. Dashboard integration (Phase E)

"Top suppliers" and "Centre performance" rows now link to the detail pages,
carrying the correct entity id. `BarBreakdown` gained an optional `href`, used
only where a real route exists — the no-dead-links rule from DEMO-002 still
holds.

Adding the detail routes also made an existing lint rule fire on
`/reports`, where `<a href="/centers">` pointed at a list page. Those are now
`<Link>` elements pointing at the **entity**, so the reports table links to the
same places the dashboard does.

Verified live: `/centers/{id}` and `/suppliers/{id}` both return 200 with real
ids taken from the demo dataset.

## 7. Tests

| Suite | Result |
| --- | --- |
| Backend (`pytest tests/`) | **1,128 passed, 74 skipped, 0 failed** |
| Portal (`vitest`) | **98 passed** (was 80; **+18**) |
| Portal typecheck | clean |
| Portal lint (`--max-warnings 0`) | clean |
| Portal production build | succeeds — `/centers/[id]` and `/suppliers/[id]` present |
| Backend lint + format | clean |
| Demo seed → verify (deployed) | `ok: true`, `problems: []` |

New portal tests (`entity-pages.test.tsx`, 18) cover: centre and supplier lists
with aggregated activity; **search and filters going to the server** rather than
narrowing in the browser; empty states worded for the situation; error with
retry; form validation blocking an invalid POST; links carrying the right id;
readiness rendering the platform's verdict *and the reason each check failed*;
operating hours, including the "none set" warning; every panel failing at once;
**the platform's activation refusal being repeated verbatim**; supplier empty
states; and a detail page that cannot load offering the way back.

Two things worth recording about writing them:

- The detail pages read route params with React's `use()`, which **suspends**.
  Without a `<Suspense>` boundary the tests queried an empty document and timed
  out; the first fix (adding the boundary) was not enough, because the promise
  had to settle inside `act()` for React to retry the suspended render.
- A mock override keyed on `/collection-centers/c1?` never matched, because the
  detail request carries no query string — the test was passing for the wrong
  reason until the key was corrected.

No existing test was weakened or skipped.

## 8. Live verification (Phase I)

All performed against https://dev.phoenixsoft.in after deployment.

| # | Check | Result |
| --- | --- | --- |
| 1 | Login as the demo manager | 204 |
| 2 | Demo organization selected via tenant-scoped login | works |
| 3 | Dashboard | 351 collections · 7,868.0 kg · **353,234.00 KES** · 24 suppliers · 5 centres · 49 settlements · 21 paid / 2 failed · 3 rate bands · 2 attention items |
| 4 | Centres list | 5 centres, all active |
| 5 | Centre detail | detail, readiness (`WARNING`, 2 of 6 failing), daily and trend reports all 200 |
| 6 | Suppliers list | 24 suppliers |
| 7 | Supplier detail | Amina Njoroge — 15 collections, 168.0 kg, 7,056.00 KES; settlements, payments and transactions all 200 |
| 8 | Dashboard → centre link | `/centers/{id}` → 200 |
| 9 | Dashboard → supplier link | `/suppliers/{id}` → 200 |
| 10 | Search / filter | `q=kilima` → 1 centre; `q=amina` → 1 supplier; `status=active` → 5; `center_id` → 4 suppliers |
| 11 | Create/edit validation | invalid form blocked before any request (tested); platform refusals surfaced verbatim |
| 12 | Tenant isolation | isolation org sees only its own 3 collections / 3 suppliers / 1 centre; demo org's supplier and centre both **404** |

Served bundle confirmed to contain the new UI ("Collection centres", "Last
activity", "New centre", "Readiness", "Operating hours").

## 9. Data reconciliation

See §1. Dashboard figures on the live deployment equal the independent SQL
totals, and both equal the local run:

- collections 351, quantity 7,868 kg, value **353,234.00 KES**
- settlements 49 finalized, net **223,744.50 KES**
- payments 25 (21 completed, 2 failed, 2 processing), completed **91,602.00 KES**
- receipts 21

## 10. AWS impact

| | |
| --- | --- |
| AWS resources created | **0** |
| AWS resources resized | **0** |
| AWS managed services added | **0** |
| Terraform infrastructure changes | **0** (`git status infra/terraform/` clean) |
| EC2 | `c7i-flex.large`, running — unchanged |
| EBS | 40 GB + 50 GB gp3 — unchanged |
| Elastic IP / DNS | unchanged |
| RDS / ElastiCache / Amazon MQ / ECS / EKS / ALB / NAT Gateway | none exist; none created |

PostgreSQL, Redis and RabbitMQ remain inside the existing Docker Compose stack
on the single EC2 host. 11 containers healthy. The demo data went into the
**existing** database; no new database was created.

## 11. Known limitations

1. **The demo cooperative has no settlements in the "calculated" state.** All 49
   are finalized, so the dashboard's "settlements awaiting finalization"
   attention item never fires on demo data. The path is tested; the dataset just
   does not exercise it.
2. **Centre "location" is timezone only.** The domain has no address or
   coordinates on a centre, so the list shows the timezone. Inventing a location
   field would have been inventing a business concept.
3. **A supplier's assigned centres show as truncated ids** on the detail page.
   `/v1/suppliers/{id}` returns `center_ids`, not names; resolving them would
   need either an N+1 fetch or a backend change, and neither is justified for a
   link that already works.
4. **The rejected collection is not separately listed.** It is counted in the
   attention item and excluded from value, but there is no "rejections" view.
5. **Seeding is manual and slow** (~4 minutes on the deployment). It is copied
   into the container with `docker cp` and run there. Baking `infra/demo/` into
   the image would make it a one-liner.
6. **No confirmation dialog on destructive actions yet.** Supplier suspension
   and centre status changes apply immediately. Nothing in these pages deletes
   anything, so this is a polish item rather than a risk.
7. **Both PILOT organizations remain visible to a platform session.** That is
   deliberate per §19 of DEMO-002 and the work order's instruction not to delete
   evidence — but a customer demonstration should sign in as the demo manager,
   who sees only the demo cooperative.

## 12. Recommendation for DEMO-004

**DEMO-004 — Collections & Pricing workflow.** The dashboard and the two entity
areas are now real; the transaction list is still the original basic table, and
it is the screen a customer will ask about first after seeing 351 collections.

1. **Rebuild `/transactions`** on `DataTable` with server-side state filter,
   centre and supplier filters, and links into both detail pages.
2. **Add a collection detail view** showing the nine-event trail the platform
   already records — it is the most convincing artifact in the product and
   nothing currently surfaces it.
3. **Rate cards and matrices**: show which card is in force, its bands, and the
   approval state. The demo dataset deliberately includes a superseded card and
   a draft awaiting approval, and neither is visible yet.
4. **Consider baking `infra/demo/` into the image** (limitation 5) so reseeding
   a demo environment is one command.

---

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-11 | Platform Engineering | DEMO-003: demo dataset seeded into the deployed PostgreSQL after removing the seeder's `httpx` dependency; supplier and centre management pages with detail views, readiness reasons and server-side filtering; dashboard links wired; deployed as `demo003-5a6a686`. |
