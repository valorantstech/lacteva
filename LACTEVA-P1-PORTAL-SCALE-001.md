---
id: LACTEVA-P1-PORTAL-SCALE-001
title: Portal Scale, Data Integrity & Irreversible-Action Hardening
type: reference
status: Approved
version: "1.0"
owner: Engineering
created: 2026-08-19
last-updated: 2026-08-19
related: [LACTEVA-P0-PRODUCT-008-FULL-PRODUCT-READINESS-AUDIT, LACTEVA-MASTER-PRODUCT-ROADMAP, LACTEVA-PRODUCT-CAPABILITY-VISIBILITY-AUDIT]
baseline: ARCH-BASELINE-V1
---

# Lacteva — Portal Scale, Data Integrity & Irreversible-Action Hardening (P1-PORTAL-SCALE-001)

## A. Executive verdict

The portal's highest-value P1 defects from the readiness audit are closed:
no selector or name map caps at 100 rows any more (a 500-farmer dairy can now
pick farmer #101 and read every name); reports page the platform honestly
instead of dressing 50 rows up as everything; the price of milk travels as the
operator's own decimal string end to end; and every audited one-click
irreversible on the pricing pages now asks first, in words that spell the
consequence. All gates green with true exit codes. **This is functional
hardening only — no redesign, no future capability, no security change.**

## B. Source-of-truth references

`LACTEVA-P0-PRODUCT-008-FULL-PRODUCT-READINESS-AUDIT.md` §§4, 9, 10, 12
(defects D-4, D-5, D-6, D-11 and the P1 portal register). **Contradiction
noted, per instructions:** the milestone order referenced a
`LACTEVA-P0-PRODUCT-009-MOBILE-P0-FIX-PACK.md` — no such document exists;
P0-PRODUCT-009 was delivered as code + tests + CHANGELOG (commit `2687f12`),
and those were used instead. A second housekeeping note: full-project `tsc`
reports pre-existing type errors in `import-pages.test.tsx` (untouched by
this milestone; vitest/eslint/build — the actual gates — do not flag it).

## C. Defects addressed

| Audit ref | Defect | Fix |
|---|---|---|
| D-5 (part 1) | Capture-wizard supplier `<select>` capped at 100 — farmer #101 unpickable | Server-searchable `EntityPicker` (debounced platform search, 20/page, load-more, honest "Showing N of TOTAL") |
| D-5 (part 2) | Filter dropdowns capped at 100 on transactions/settlements/payments/billing/deliveries + the settlement-create supplier select | All six converted to `EntityPicker` |
| D-5 (part 3) | Name maps prefetched 100 rows → UUID fragments for everybody past that | New platform `ids` filter + `useSupplierNames`/`useCustomerNames`: one batch request resolving exactly the ids on the page; unknown/foreign ids keep the honest truncated fallback |
| D-6 | Reports silently truncated to 50 rows; money sorted via `Number()` on the visible slice | Server pagination (limit 50 + offset + the platform's total) with the shared `Pagination` control on both summary tables; the page-local pseudo-sort removed — the platform's own order (milk supplied, desc) is stated instead, per the house DataTable doctrine that a table sorting only the page it can see lies |
| D-4 | Matrices POSTed `unit_price` through `Number()` — floats at the surface that sets the milk price | The operator's decimal string travels untouched (backend `unit_price: Decimal` accepts it exactly); band bounds stay numbers **by the backend's own contract** (`from_value/to_value: float` — boundaries, not money) |
| D-11 | One-click Publish/Archive (rate cards), Delete (matrix, band) | Consequence-spelling confirm panels in the settlement-finalize house style: named entity, spelled effect, busy-guarded confirm, distinct cancel |
| P2-11 (adjacent, required by the fix) | Band-editor inputs had no accessible names | `htmlFor`/`id` pairs and `aria-label`s added |
| i18n (audit §4) | Shared chrome hardcoded English over full hi/ar catalogs | `DataTable` (retry, empty default, "Showing X–Y of Z", Previous/Next) and `LoadingState` now read the catalog; 4 new keys × 3 languages (parity-tested). The 27 English-only pages are deliberately left for **P1-LOCALE-I18N-001** |

## D. Files changed

**Backend (3 + 1 test):** `modules/supplier/service.py`, `modules/customer/service.py` (both: `ids` narrowing composed with the tenant filter), `api/routes.py` (both list endpoints: `ids` query param, ≤100), `tests/test_directory_ids_filter.py` (new, 3 tests).
**Portal (new):** `components/entity-picker.tsx`, `lib/names.tsx`, `components/entity-picker.test.tsx`, `app/portal-scale.test.tsx`, `app/pricing-actions.test.tsx`.
**Portal (modified):** `lib/api.ts` (ids params), `lib/messages.ts` (4 keys ×3), `components/data-table.tsx`, `components/states.tsx`, pages: `transactions/new`, `transactions`, `settlements`, `payments`, `billing`, `deliveries`, `reports`, `matrices`, `rate-cards`; tests adapted to the picker: `capture-wizard`, `collection-pages`, `transaction-operations`, `financial-pages`.

## E. API/backend changes

Exactly one, additive: `GET /v1/suppliers` and `GET /v1/customers` accept
repeated `ids` (max 100). It **narrows** — composed after the tenant filter
(and the DEMO-012 customer scope), so a foreign tenant's id matches nothing.
No schema change, no new endpoint, no permission change.

## F. Portal changes

As §C. The `EntityPicker` reuses existing primitives (Input/Button/Label,
list borders) — no new visual language; loading/searching/empty/no-result/
error+retry states; keyboard escape + outside-click dismissal; combobox/
listbox roles. Reports keep filters and date ranges; continuation state is the
shared Pagination ("Showing X–Y of Z", busy-disabled).

## G. Security / RLS verification

- The `ids` filter is provably tenant-safe: `test_a_foreign_tenants_id_resolves_to_nothing` requests its own id and a foreign tenant's in one call and receives exactly its own row — for suppliers **and** customers.
- No authorization moved to the frontend; the picker and name hooks call the same permission-gated endpoints as before, as the signed-in user.
- Confirm panels are a pause, not a boundary — the backend remains authoritative (pinned: a platform refusal renders verbatim and the panel stays open).
- RLS, identity, tenancy, scopes: untouched. Claims guards ran green inside both suites.

## H–I. Test matrix and exact counts

| Gate | Result |
|---|---|
| Backend full pytest | **1,998 passed / 265 skipped / 0 failed (2,263 collected), exit code 0** (true exit code from file capture) — includes the 3 new ids-filter tests; PG-gated subset skips locally by design (CI-enforced) |
| Backend ruff check + format | Clean on all touched files |
| Portal vitest (complete) | **28 files, 360/360 passed** (345 prior + 15 new: 6 picker, 2 scale/pagination, 7 pricing-actions; 7 pre-existing tests adapted to the picker interaction — same server-parameter assertions, new control) |
| Portal eslint `--max-warnings 0` | **Clean** |
| Portal `next build` | **Green** |
| Docs validation + xref | Green |
| Mobile | **Not run — no shared/mobile code touched** (per milestone testing rule 5) |

## J. Before / after

| Before | After |
|---|---|
| Farmer #101 unpickable in the wizard; filters blind past 100 | Any farmer findable by name/code/phone; 250-record dataset paged in tests |
| UUID fragments in Supplier/Customer columns past row 100 | Names for exactly the page's ids in one request; honest fragment only for a genuinely unknown id |
| "Collection by supplier" = first 50, silently | "Showing 1–50 of 120", Next reaches supplier #51 (pinned in test) |
| `unit_price: Number("46.5050")` | `"46.5050"` — displayed value === submitted value, trailing zeros intact (pinned) |
| Publish/Archive/Delete fired on one click | Ask first, named entity, spelled consequence, double-click-proof, refusal-verbatim |
| "Try again"/"Showing X–Y"/"Loading…" hardcoded English | Catalog-backed in en/hi/ar |

## K. Remaining P1/P2 (untouched, preserved)

From the audit: mobile counter pack (parchi on completion, transaction
history, offline input bounds, rejection reasons, restart-offline, auto-sync)
→ **P1-MOBILE-COUNTER-001**; the 27 English-only pages + CsvImport chrome →
**P1-LOCALE-I18N-001**; real-boundary E2E harness → **P1-E2E-HARNESS-001**;
large-import chunking (`MAX_IMPORT_ROWS=500`) and concurrent-capture race →
**P1-SCALE-RACE-001**; P2 register (UTC 30-day windows, timestamp drift,
Kenya placeholders, RTL physical alignment, subscription `<Money>`,
terminology glossary, remaining one-click state changes outside pricing,
legacy-page pattern debt, capped customer-detail sublists, suppliers-list
top-100 activity annotations).

## L. Explicitly deferred

The Lacteva Design System V1 and any portal/mobile UX redesign — deliberately
untouched; every new control reuses the current design system.

## M. Explicitly preserved roadmap

All 24+ future capabilities (AI/anomaly/forecasting, SAP/ERP + SoR decisions,
enterprise SSO/global identity/federation/org-to-org, GPS, WhatsApp/SMS,
automated scale/analyzer, QR scanning, PDFs, GST/FSSAI fields, chilling/BMC,
plant, procurement transport, farmer app, web outlet portal, advances/loans,
advanced analytics, payment gateway, enterprise integrations) remain roadmap
items — none implemented, none downgraded; the claims guards enforcing this
passed in this milestone's own runs.

## N. Recommended next milestone

**P1-MOBILE-COUNTER-001** — the counter interaction pack (parchi on the
completion step first), per the established sequence.

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-19 | Engineering | Portal scale/integrity/irreversible-action hardening per the P0-PRODUCT-008 P1 register: server-searchable EntityPicker replacing seven capped selectors; platform `ids` filter + page-exact name resolution (tenant-safety proven); reports server pagination with honest totals; matrices Decimal-string money (displayed === submitted, pinned); consequence-spelling confirms on publish/archive/delete; shared-chrome i18n (4 keys ×3 languages); 18 new tests (3 backend + 15 portal), 7 adapted; all gates green with true exit codes; roadmap and security boundaries untouched (P1-PORTAL-SCALE-001). |
