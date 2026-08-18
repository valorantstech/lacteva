---
id: LACTEVA-PRODUCT-CAPABILITY-VISIBILITY-AUDIT
title: Product Capability Visibility Audit
type: reference
status: Approved
version: "1.0"
owner: Product
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-MASTER-PRODUCT-ROADMAP, LACTEVA-FIRST-DAIRY-SALES-AND-PILOT-PACKAGE, LACTEVA-COMMERCIAL-MODEL-AND-PACKAGING, LACTEVA-HARDWARE-CONNECTOR-DISCOVERY, LACTEVA-REGULATORY-APPLICABILITY-AUDIT]
baseline: ARCH-BASELINE-V1
---

# Lacteva — Product Capability Visibility Audit (P0-PRODUCT-VISIBILITY-001)

## 1. Purpose

Audit the shipping product — backend, admin portal, mobile app, marketing
site — against the canonical roadmap, and make the **application itself**
communicate what is available today versus what is on the roadmap, without
ever blurring the two. Statuses use the established vocabulary: **FACT ·
CONFIG · PILOT · COMING SOON · ENTERPRISE · TO CONFIRM.**

**Headline finding: the shipping product was already honest.** The sweep for
false or inflated claims (AI, GPS, SAP, hardware, analyzer, real-time,
prediction, forecast, automation, farmer/customer app, SSO, federation,
government, compliance, IoT) found **zero overclaims in any shipping UI** —
the product's honesty is actively *enforced* (marketing `claims.test.ts` bans
overclaim phrases; mobile compiles mock hardware out of release builds;
production refuses mock readings; portal copy explicitly says when a value was
NOT device-supplied). What the product lacked was the other half of honesty:
**no surface said what is coming**. That is the one gap this milestone closed.

## 2. Repository evidence — the capability matrix

Backend `services/platform-core/src/platform_core/` (26 modules); portal
`apps/admin-portal` (26 nav destinations, every one a real API-backed page,
zero stubs); mobile `apps/mobile` (persona-routed, all screens API-backed);
canonical classification `LACTEVA-MASTER-PRODUCT-ROADMAP.md` §9/§13/§16.

| Capability | Repository evidence | Status | User-visible today? | Role/portal | Business/config dependency | Evidence required | Notes |
|---|---|---|---|---|---|---|---|
| Collection capture (weight, cow/buffalo) | `modules/milk_collection/` + portal wizard `transactions/new` + mobile `collection_wizard.dart` | **FACT** | Yes | Operator (mobile+portal) | Centre + open session | — | kg; manual entry |
| Quality FAT/SNF/CLR | wizard steps; `service.py` capture; source attribution | **FACT** | Yes | Operator | — | — | Manual; source recorded honestly |
| Rate — dairy's own chart | `modules/pricing/` (matrix/calculator/resolution) | **FACT + CONFIG** | Yes | Pricing roles | **Requires a published rate card** — `resolution.py:157` `status=="published"`, refusal `:227` "no published rate card covers…" | — | Draft→review→approved→published workflow (`service.py:3`) |
| Parchi / slip | `api/routes.py:1905` `GET /milk-transactions/{id}/slip`; `slip_number` + tenant-unique constraint `models.py:63,119`; bilingual EN/HI `service.py:321` | **FACT** | Yes | Operator/manager | Org language for Hindi labels | — | Numbered, print/share |
| Settlement | `modules/settlement/` + portal settlements pages + mobile screen | **FACT + CONFIG** | Yes | Finance | Free `period_from`/`period_to` cycles | — | Immutable when finalized |
| Outlets/customers + CSV import | `modules/customer/` + `POST /v1/customers/import` + portal import UI | **FACT** | Yes | Sales | — | — | Duplicate guard names the existing customer |
| Delivery, routes, runs | `modules/delivery/`, `modules/logistics/` + portal + mobile driver/delivery screens | **FACT** | Yes | Sales/Driver | Routes/orders configured | — | Proven on-glass (P0-PILOT-004) |
| Billing/invoices, payments, receipts, receivables | `modules/billing/`, `payment/`, `receipt/` + portal pages | **FACT** | Yes | Finance | — | — | Invoices drafted, person issues |
| Reporting + dashboard | `modules/reporting/` + portal reports (467L) + dashboard (914L) | **FACT** | Yes | reporting.read | — | — | 12 report views |
| Offline capture + sync | `offline_client.dart`, `sync_engine.dart`, portal `/sync` | **FACT** | Yes | Operator/Driver | — | — | Never invents prices offline (`pricing_status: pending_sync`) |
| RBAC + RLS tenancy | `modules/authz/permissions.py` (`module.entity.action`), `core/rls.py` | **FACT** | Yes (roles UI) | Admin | — | — | Foreign resource = 404 |
| Audit trail | `modules/audit/` + portal `/admin/audit` | **FACT** | Yes | Auditor | — | — | |
| Subscription & 30-day trial (entitlement) | `subscription/plans.py:49-72` — `LACTEVA_TRIAL`/`LACTEVA_STANDARD`, per-centre (`included_centres`, "priced per collection centre"), **no price in code** (`PRICE_CONFIG_PREFIX`, "Absent until somebody decides"); `service.py:48` `TRIAL_DAYS = 30` | **FACT + TO CONFIRM (price)** | Yes (`/admin/subscription`) | Owner/Admin | Price via config `subscription.price.<PLAN>.<CCY>` | Commercial decision | Entitlement engine; not per-user, not per-litre |
| **Taking payment** | `providers.py:183` `DisabledPaymentProvider` ("no payment provider is configured"); `core/config.py:281` `Literal["disabled","test"] = "disabled"`, `"test"` **refused in prod** (`config.py:548-550`) | **COMING SOON / TO CONFIRM** | Machinery invisible | — | A contracted gateway | Gateway contract | Platform **cannot take money today** — matches DEMO-026 |
| Supplier FAT/SNF deviation flag (the only "AI") | `milk_collection/service.py:114-123,638-649` — ≥3σ AND ≥0.5 abs, last-20 same-milk-type, min 5; "Statistics, not ML"; non-blocking event; never on the parchi | **FACT** | Indirect (event trail) | — | Supplier history ≥5 readings | — | |
| Notifications / messaging | `modules/notification/` + portal page; WhatsApp adapter exists, portal copy: "8 WhatsApp not mapped to a provider", "not that WhatsApp will reach it" | **FACT (email templating) + COMING SOON (send)** | Yes | notification.read | **No BSP/DLT contracted** | Vendor paperwork | Honest copy already shipped |
| Automated scale/analyzer capture | Adapter seam + device registry only; `service.py:63-74` `_refuse_mock_source` refuses mock in prod; mobile `build_flags.dart:22` compiles mocks out of release | **COMING SOON** (V1, discovery-gated) | No (correctly) | — | Device-discovery visit (P0-HW-002) | Hardware evidence | Manual-first is the shipped truth |
| QR supplier scanning | Absent; helper text "QR scanning arrives with device integration" (`collection_wizard.dart:162`) | **COMING SOON** | Label only | — | — | — | |
| Receipt/invoice PDF | `receipts.dart:239-254` clipboard placeholder, "no PDF engine yet" | **COMING SOON** | Placeholder labelled | — | — | — | |
| GST/FSSAI doc fields | Not built (roadmap §9 "V1 · NOT BUILT") | **COMING SOON** | No | — | — | — | Dairy owns its regulatory duties |
| Anomaly detection / forecasting | Roadmap: anomaly V1, forecasting V2 "NOT BUILT" | **COMING SOON** | No | — | Real data history | — | |
| Chilling/BMC, procurement transport, plant | Roadmap §12 — all "V2 · NOT BUILT" | **COMING SOON** | No | — | — | — | |
| SAP/ERP, enterprise SSO, global identity, federation | Roadmap §6/§11/§13 — "ENTERPRISE · NOT BUILT"; "No vendor chosen; DO NOT BUILD" | **ENTERPRISE** | No | — | Signed enterprise engagement | — | |
| Farmer app | Absent (no supplier login anywhere) — roadmap "FUTURE OPTION" | **COMING SOON (future option)** | No | — | Commercial need | — | Farmer = record + parchi |
| Customer experience | **Mobile customer home SHIPPED** (`customer_portal.dart:40`, routed `home.dart:131`); **web outlet portal NOT BUILT** (roadmap "FUTURE OPTION", scoped to web) | **FACT (mobile) / COMING SOON (web)** | Yes (mobile) | Customer | — | — | Terminology reconciled — see §10 |
| GPS / route intelligence | No location/map/geolocation code or dependency anywhere | **COMING SOON (future)** | No (correctly) | — | — | — | "Never a pilot dependency" |
| Litres / FAT×SNF-grid pricing | kg + FAT-band engine only | **TO CONFIRM** | — | — | Chart-dependent engineering | The dairy's actual chart | Flagged in sales pack |

## 3. Available Today (FACT)

The full honest lifecycle, exactly as the sales package claims it:
**Collection → Quality → Dairy's own rate → Parchi → Settlement → Outlets →
Delivery → Billing → Reporting** — every stage implemented, routed, permission-
gated and page-backed (evidence above), plus offline capture/sync, RBAC + RLS,
audit, notifications (email templating), subscription entitlement + 30-day
trial, CSV imports, and the statistical deviation flag. Nothing in the
lifecycle needed downgrading — **all nine stages are FACT.**

## 4. Configuration-dependent (CONFIG)

Rate cards (must be **published**; pricing refuses otherwise — the honest
refusal is the guard), settlement cycles (free periods), org/branches/centres/
users/roles, org language (Hindi parchi labels), business calendar, standing
orders/routes, subscription price (config key, deliberately absent from code).

## 5. Pilot (PILOT)

The bounded pilot workflow: imports (suppliers/customers), rate-card build +
paisa reconciliation, Day-0 verification, trial subscription. All served by
shipped functionality; nothing pilot-specific was added or faked.

## 6. Coming Soon

Per the canonical roadmap (never shown as operational): messaging send
(WhatsApp/SMS — vendor paperwork), automated scale/analyzer capture
(discovery-gated), QR scanning, PDF documents, GST/FSSAI fields, anomaly
detection (V1) / forecasting (V2), chilling/BMC, procurement transport,
plant/processing, farmer app (future option), web outlet portal (future
option), advanced AI (future option), GPS (future).

## 7. Enterprise

SAP/ERP integration, enterprise SSO, global identity, org-to-org/federation,
enterprise integration layer — all "NOT BUILT", reserved for a signed
enterprise engagement, never presented as generally available.

## 8. To Confirm

| Item | What is undecided |
|---|---|
| Subscription price per centre | No INR/KES/QAR value exists anywhere in code or config |
| Payment gateway | Only `disabled`/`test` providers exist; no real gateway contracted |
| Litres / FAT×SNF-grid pricing | Engineering decision pending a real dairy's chart |
| Pilot length vs 30-day trial | Trial is 30 days in code; pilot duration is a business call |
| Sales qualification thresholds | Centre/farmer/volume numbers undefined in the repository |

## 9. UI changes made

**One change, in the admin portal only** — the single justified gap:

- **New `/roadmap` page** (`src/app/roadmap/page.tsx`) — "What you can use
  today, and what's on the roadmap." Two visibly separate halves: *Available
  today* (each card links to its real page, badge "Available") and the roadmap
  (*Coming soon* / *Enterprise* / *Future options* — inert cards, no links, no
  controls, badges `secondary`/`outline` from the existing design system).
  Calls **no API**, shows **no data**, classification copied verbatim from
  `LACTEVA-MASTER-PRODUCT-ROADMAP.md` and cited in the page footer. Explicitly
  allowed by the roadmap's Coming-Soon policy (§13: non-interactive labels).
- **Nav entry** "Roadmap" in the Platform group (`app-shell.tsx`), always
  visible via a `*`-sentinel (the dashboard's own pattern, generalized from
  `=== "*dashboard"` to `startsWith("*")`) — knowing what is coming is not a
  privileged act.
- **i18n**: `nav.roadmap` added to all three catalogs (en/hi/ar); page body is
  inline English, the established pattern for platform/admin pages.
- **Test** `src/app/roadmap-page.test.tsx` (5 tests): fetches nothing; the two
  categories are separately labelled; an available capability is a real link;
  every roadmap capability is **inert** (no link); the AI card states "No AI
  vendor and no ML model exist in the product today."

**Deliberately unchanged:** mobile (already carries honest inline placeholders
— mock hardware compiled out of release, "QR scanning arrives with device
integration", "no PDF engine yet" — adding a roadmap surface to a minimal
field app would be decoration); marketing site (guarded by `claims.test.ts`);
backend (no code claim to correct). No fake screens, APIs, data, readings,
predictions, or integrations were created.

## 10. Misleading claims corrected

**None were found, so none were corrected** — the honest result of the sweep
(§1). One terminology tension was found and reconciled *in the new page's own
wording* rather than by rewriting a governed doc: the roadmap's
"Customer/Outlet Portal — FUTURE OPTION" row is scoped to a **web** portal,
while a **mobile** customer home is already shipped (`customer_portal.dart`,
DEMO-012) and the marketing site truthfully says customers use the app. The
roadmap page states both halves precisely. *Recommendation:* add one
clarifying sentence to the roadmap doc's row at its next scheduled revision
(owner's call; not edited unilaterally here).

## 11. Test / validation results

| Gate | Result |
|---|---|
| Portal vitest (full) | **24 files, 318 passed, 0 failed** (includes the 5 new roadmap tests; catalog-parity test green with the 3 new keys) |
| Portal eslint (`--max-warnings 0`) | **Clean** |
| Portal `next build` | **Green** — `/roadmap` prerendered static |
| Backend / mobile / marketing suites | **Not run — those trees untouched** (per gate policy: run when changed) |
| `validate_docs.py` / `generate_xref.py` | Green (this doc + xref) |

No pre-existing failures were encountered; nothing unrelated was modified.

## 12. Remaining gaps

- Roadmap-page body is English-only (precedented; the tri-lingual catalogs
  translate only the nav label). Translate if the roadmap page proves to be
  read by Hindi/Arabic operators.
- Mobile has no roadmap surface (deliberate; revisit only if field users ask).
- The claims-discipline test exists for the marketing site
  (`claims.test.ts`); the portal and mobile have no equivalent automated
  overclaim guard — today they are clean by inspection, not by test.
- The roadmap-doc customer-portal row clarification (§10).
- DEV deployment of the portal change is pending the next deploy cycle.

## 13. Recommended next milestone

The pilot's critical path remains **business-gated, not engineering-gated**:
send the onboarding request pack, receive the four artifacts + licences +
signed agreement, then execute the P0-PILOT-008 runbook. The one small
engineering hardening this audit motivates, if wanted before that:
**extend the marketing site's executable claims-guard pattern to the portal
and mobile** (an automated test banning overclaim phrases in UI copy), so the
honesty verified here by inspection stays true by construction.

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product | Full capability-visibility audit: matrix over 27 capabilities with file:line evidence; all nine lifecycle stages proven FACT; zero misleading claims found in any shipping UI (honesty already enforced by claims.test.ts, mock refusals, compile-time flags); the one gap — no roadmap visibility — closed with an honest, non-interactive /roadmap page in the admin portal (nav + i18n + 5 tests); payment-taking confirmed impossible today (disabled provider); TO CONFIRM register; next-milestone recommendation (P0-PRODUCT-VISIBILITY-001). |
