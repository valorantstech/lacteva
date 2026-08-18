---
id: LACTEVA-MASTER-PRODUCT-ROADMAP
title: Master Product Roadmap — Phasing, Ecosystem & Future Capability Register
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-BUSINESS-OPERATING-MODEL, LACTEVA-IDENTITY-ENTERPRISE-ARCHITECTURE-AUDIT, LACTEVA-PRODUCT-GAP-REVIEW, LACTEVA-GO-LIVE-READINESS, LACTEVA-HARDWARE-CONNECTOR-DISCOVERY, LACTEVA-HARDWARE-INTEGRATION-SPEC, LACTEVA-REGULATORY-APPLICABILITY-AUDIT, LACTEVA-PILOT-MASTER-ROADMAP, LACTEVA-PRODUCT-AUDIT]
baseline: ARCH-BASELINE-V1
---

# Lacteva Master Product Roadmap

**Roadmap & architecture definition only — no code, schema, migration, API,
UI, vendor, or protocol.** This consolidates every committed milestone into one
definitive phasing register. It does not restate the source documents — it
references them and resolves them into phases, tables, a dependency map, a
decision register, and an executive roadmap. **Repository evidence wins over
any assumption; unknowns are tagged UNKNOWN / TO CONFIRM.**

Phase taxonomy: **NOW** (deployed/proven) · **PILOT/V1** · **V1+** · **V2** ·
**ENTERPRISE** · **FUTURE OPTION**. Status: **GREEN** (exists) · **CONFIG** ·
**DATA-DEPENDENT** · **DISCOVERY-GATED** · **NOT BUILT**.

---

## 1. Executive verdict

Lacteva is a **deployed, working B2B dairy operations platform** whose core
commercial lifecycle (farmer → collection → quality → rate → settlement →
orders → routes → delivery → billing → payments → reporting/audit) is **GREEN
and proven**, including on a real handset. The immediate objective is
**one real Indian dairy pilot**, gated only on the dairy's business data and
paperwork — not on engineering. Everything beyond the pilot is a **bounded,
additive increment** on the existing modular-monolith architecture, which the
Identity + Enterprise audit verified is **evolvable to enterprise scale without
a rewrite**. This roadmap preserves *every* previously approved future
capability — AI, SAP, GPS, chilling/BMC/plant, procurement transport, messaging,
farmer/customer portals, enterprise SSO/global-identity/federation — as tracked
future work, and converts **none** of them into a present commitment.

## 2. Current product state (NOW — grounded in code + prior milestones)

**GREEN / deployed (`main-2867a55` on DEV):** procurement (farmers/suppliers,
collection sessions, quantity kg, FAT/SNF/CLR quality, rate cards cow/buffalo,
pricing at capture, settlement); **parchi** (numbered slip, print/share,
bilingual); collection-centre operations (operators, readiness, device
registry, offline capture/replay proven on glass); distribution (customers,
outlets, standing orders, routes, vehicles, drivers, delivery runs/outcomes,
billing, receivables — driver run completed on a real handset); reporting (12
endpoints + dashboard); audit trail; **RBAC** (10-role registry, scope-on-grant)
and **RLS** (FORCED, foreign resource = 404); backup/restore (verified chain +
off-site); admin portal; two mobile personas; **subscription/SaaS foundation**;
**AI MVP** (`QualityDeviationFlagged` supplier FAT/SNF deviation flag —
verified in code); the hardware **seam** (source-attributed capture,
production-refused mocks, adapter contracts).

**CONFIG (per dairy):** rate chart, farmer/outlet lists, settlement cycle,
org locations.

**DATA-DEPENDENT (the pilot gate):** the four artifacts + FSSAI/LM copies +
signed agreement + production backup-retention config (see
LACTEVA-GO-LIVE-READINESS).

**DISCOVERY-GATED:** the hardware connector (see
LACTEVA-HARDWARE-CONNECTOR-DISCOVERY §29).

## 3. Target dairy ecosystem

Full potential chain (no dairy uses all of it):
Farmer → Village Collection Point / Collection Centre → BMC → Chilling Centre →
Processing/Dairy Plant → Warehouse/Distribution → Outlet/Customer → Consumer.
Plus the two **distinct transport legs** — *procurement transport* (centre →
chilling → plant) and *distribution transport* (plant/depot → route → outlet),
**never collapsed** (Business Operating Model §11).

**Actor classification** (do not create a login for every actor):

| Actor | A: uses Lacteva | B: record only | C: future portal/app | D: API/SAP integration |
|---|---|---|---|---|
| Farmer / milk producer | — | **Yes (Supplier record)** | Farmer App (FUTURE OPTION) | — |
| Collection operator | **Yes** | — | — | — |
| Collection-centre manager | **Yes** | — | — | — |
| Quality/lab team | future | — | — | — |
| BMC / chilling operator | future (V2) | — | — | — |
| Procurement / plant team | future (V2) | — | — | — |
| Transporter (procurement) | future (V2) | as record first | — | — |
| **Driver** (distribution) | **Yes** | — | — | — |
| Warehouse / distributor | future | — | — | — |
| Sales / logistics / finance | **Yes** | — | — | — |
| Customer / outlet | — | **Yes (Customer record)** | Customer Portal (FUTURE OPTION) | possibly |
| Institutional customer | — | Yes | portal (future) | **possibly (API)** |
| Enterprise HQ / region | **Yes** (future scope) | — | — | dashboards/API |
| Auditor / support | **Yes** | — | — | — |
| Hardware device | — | **Yes (asset)** | — | connector credential (not a login) |

## 4. Lacteva application family (target)

| # | Application | Form | Phase |
|---|---|---|---|
| 1 | Platform Administration | web surface | **GREEN** |
| 2 | Enterprise Portal | web (same portal, enterprise scope) | ENTERPRISE (evolves the existing portal) |
| 3 | Dairy Operations Portal | **the existing admin portal** | **GREEN** |
| 4 | Collection App | mobile (Flutter) | **GREEN** |
| 5 | Driver / Delivery App | mobile (same binary, persona-routed) | **GREEN** |
| 6 | Centre Operations App | **module of Collection App**, not separate | GREEN (as module) |
| 7 | Chilling Centre / BMC app | module or app | V2 |
| 8 | Plant / Processing app | app/module | V2/ENTERPRISE |
| 9 | Farmer App | mobile | FUTURE OPTION |
| 10 | Customer/Outlet Portal | web | FUTURE OPTION |
| 11 | Supplier/Partner Portal | web | FUTURE OPTION |
| 12 | Hardware / Centre Connector | local service/agent | V1 (DISCOVERY-GATED) |
| 13 | Reporting / Analytics | portal module + service | GREEN (basic) → V1+/V2 (advanced) |
| 14 | AI capabilities | service/module | GREEN (MVP) → phased |
| 15 | Enterprise Integration / SAP layer | integration/API service | ENTERPRISE |

**Recommendation:** keep **one portal** (scope-driven) and **one mobile binary**
(persona-routed) as long as possible; add new *modules* before new *apps*.
Chilling/plant become modules first; a separate app only when field reality
demands it.

## 5. User / persona model (identity table)

Login = operates the software. Same identity across apps (auth = identity;
authz = role + org + location + application capability). Onboarding via
invitation (accept sets the credential); **no self-signup** in current
architecture; enterprise SSO is a future overlay.

| Person type | Example role | Org | Scope | Login | Apps | Same identity | Onboarded by |
|---|---|---|---|---|---|---|---|
| Platform admin | PLATFORM_SUPER_ADMIN | platform | all | **Yes** | Platform Admin | yes | Lacteva |
| Dairy owner | (Org Manager today) | org | org-wide | **Yes** | Portal | yes | invite |
| Dairy admin | ORGANIZATION_ADMIN | org | org-wide | **Yes** | Portal | yes | invite |
| Dairy manager | ORGANIZATION_MANAGER | org | org-wide | **Yes** | Portal | yes | invite |
| Branch/region manager | (scoped manager) | org | branch/region (V2) | FUTURE | Portal | yes | invite |
| Procurement manager | (Org Manager today) | org | org/procurement | today via Org Mgr; V1 role | Portal | yes | invite |
| Collection operator | COLLECTION_OPERATOR | org | centre | **Yes** | Collection App | yes | invite |
| Collection-centre manager | CENTRE_MANAGER | org | centre | **Yes** | Portal + Collection App | yes | invite |
| Quality / lab operator | future role | org | centre/lab | FUTURE | Collection/Quality | yes | invite |
| Chilling / BMC operator | future role | org | location | FUTURE (V2) | Chilling app | yes | invite |
| Plant operator | future role | org | plant | FUTURE (V2) | Plant app | yes | invite |
| Logistics manager | (Sales/Ops today) | org | org | **Yes** | Portal | yes | invite |
| Transporter (procurement) | future | org/partner | route | FUTURE (V2) | future app | yes | invite |
| **Driver** (distribution) | DRIVER | org | own runs | **Yes** | Driver App | yes | invite + link |
| Warehouse operator | future | org | warehouse | FUTURE | future | yes | invite |
| Billing / accounts | FINANCE_OFFICER | org | org | **Yes** | Portal | yes | invite |
| Finance / settlement | FINANCE_MANAGER | org | org | **Yes** | Portal | yes | invite |
| Sales user | SALES_OFFICER | org | org | **Yes** | Portal | yes | invite |
| Customer/outlet manager | — | (customer record) | — | **No** (FUTURE OPTION portal) | — | — | dairy import |
| Auditor | AUDITOR | org | org read | **Yes** | Portal | yes | invite |
| Support user | (platform) | platform | gated | future | Platform Admin | yes | Lacteva |
| Enterprise admin | future | enterprise group | group | ENTERPRISE | Enterprise Portal | yes | Lacteva/enterprise |

**Entity vs identity — the distinction that must hold:** **Person** (may be a
login) ≠ **Organization** (tenant/SoR) ≠ **Location** (centre/plant) ≠
**Asset/Device** (connector credential, never a login) ≠ **Farmer/Supplier**
(record; app is FUTURE OPTION) ≠ **Customer/Outlet** (record; portal is FUTURE
OPTION) ≠ **Driver** (a person who *does* log in).

## 6. Identity + SSO model

- **CURRENT (GREEN):** one Lacteva identity per person *within* an org;
  application-specific authorization by role + scope; the same login works on
  Portal, Collection App and Driver App (no per-app credentials). Identity is
  **tenant-scoped** today (baseline §1.5).
- **V1/V2:** same identity across all Lacteva applications (already the pattern)
  and scope generalisation (region/branch, today centre-only).
- **ENTERPRISE:** **global identity** (one person → many orgs via memberships)
  and **enterprise SSO/federation** (customer IdP via SAML/OIDC). Bounded
  increments per the Identity + Enterprise audit §7/§14; **RLS never weakened**
  (a session always binds to one org). **No vendor chosen; DO NOT BUILD.**

## 7. Organization / enterprise model

Per the Identity + Enterprise audit: tenant = `Organization` (org_type
cooperative/private/collector/processor/farm); location hierarchy
Workspace → Branch → Centre (GREEN), extensible to region and new location
*types* (chilling/BMC-as-asset/plant/depot — V2). **Recommended enterprise
model: hybrid** — one org per legal entity keeping its own books/users/RLS + a
light parent/federation group for rollup/SSO; org-to-org trading/dispatch
relationships via **consented projections/events, never widened RLS**
(ENTERPRISE). **Preserve: org-level RLS, per-org books/users, bounded
cross-org relationships.**

## 8. Onboarding model (definition only)

| Entity | Mechanism | Phase |
|---|---|---|
| A. Dairy organization | admin-created (lead → agreement → org) | GREEN |
| B. Enterprise organization | Lacteva-created + federation group | ENTERPRISE |
| C. Branch/region | admin-created | GREEN (branch) / V2 (region) |
| D. Collection centre | admin-created | GREEN |
| E. Chilling centre | admin-created | V2 |
| F. BMC | device/asset under a location | V2 |
| G. Plant | admin-created location type | V2/ENTERPRISE |
| H. Employee/user | **invitation → accept** | GREEN |
| I. Driver | create profile → invite → link → assign vehicle/route | GREEN |
| J. Farmer | **CSV import / admin-created**; future self-registration | GREEN (import); FUTURE OPTION (portal) |
| K. Customer/outlet | **CSV import / admin-created**; future portal | GREEN (import); FUTURE OPTION |
| L. Supplier/partner | admin-created; future API/portal | GREEN (basic); FUTURE |

Self-signup: none today. API/SAP onboarding: ENTERPRISE. **DO NOT IMPLEMENT** —
mechanics for A/H/I/J/K are already GREEN and proven.

## 9. V1 / V2 / Enterprise product roadmap

| Capability | Phase | Status |
|---|---|---|
| Collection, quality, rate, settlement, parchi | NOW | GREEN |
| Routes, delivery, billing, payments, reporting, audit | NOW | GREEN |
| RBAC/RLS, backup/restore, mobile operator + driver | NOW | GREEN |
| Real dairy onboarding, rate chart, farmer/outlet import, settlement rules | NEXT | DATA-DEPENDENT |
| Production hardening (host, SMTP, retention→30d) | NEXT/V1 | CONFIG/NOT BUILT |
| Hardware discovery → Centre Connector | V1 | DISCOVERY-GATED |
| Automated scale/analyzer read-assist | V1+ | NOT BUILT (gated) |
| Printer integration (only if justified) | V1+ | NOT BUILT |
| Supplier trend analytics; advances/loans; FSSAI/GST doc fields | V1 | NOT BUILT |
| First messaging provider (SMTP → SMS/WhatsApp) | V1 | NOT BUILT (vendor paperwork) |
| Chilling centres, BMC, procurement transport, broader centre ops | V2 | NOT BUILT |
| Plant/processing, advanced logistics, broader analytics | V2/ENTERPRISE | NOT BUILT |
| SAP/ERP, enterprise SSO, global identity, parent/federation, org-to-org, enterprise reporting/master data | ENTERPRISE | NOT BUILT |
| Farmer app, customer/outlet portal, consumer capabilities, GPS, advanced AI, forecasting, RFID/QR/camera | FUTURE OPTION | NOT BUILT |

## 10. AI roadmap

| Feature | Phase | Required data | Business value | Why not now |
|---|---|---|---|---|
| Supplier FAT/SNF deviation flag | **CURRENT (GREEN)** | own transaction history | catches adulteration/misreading | already built |
| Supplier trend analysis | NEXT/V1 | existing collection history | procurement insight | needs weeks of real data |
| Quality anomaly detection | V1 | quality readings at volume | trust/fraud | thin at pilot start |
| Operational alerts | V1 | events/metrics | ops efficiency | value grows with volume |
| Settlement anomaly detection | V1 | settlement history | financial integrity | runs weekly; needs cycles |
| Operator anomaly detection | V1 | per-operator metrics | fraud/quality | needs baseline weeks |
| Collection/supply forecasting | LATER/V2 | seasons of history | planning | insufficient data early |
| Demand forecasting | LATER/V2 | sales history at volume | distribution planning | needs sales data |
| Route optimization | LATER/V2 | routes + GPS | logistics cost | needs GPS (FUTURE) |
| Quality prediction, predictive maintenance | LATER | device + quality series | uptime | needs device telemetry |
| Enterprise intelligence | ENTERPRISE | plant/inventory/multi-site | decision support | needs V2 domains |

**No AI vendor. No AI built this milestone.** The deviation flag is statistics,
not ML, and honest about it.

## 11. SAP / ERP roadmap (ENTERPRISE — boundaries only)

```
Lacteva  ↕  Integration / API / Event boundary  ↕  SAP / ERP
```
Likely future domains: master data (suppliers/farmers, customers, materials/
products), procurement, inventory, finance, invoices, payments, settlements,
production, logistics. **System-of-record questions (UNKNOWN / TO CONFIRM per
enterprise):** which system owns customer master, supplier master, materials,
and finance; synchronization direction (one-way vs bidirectional); event vs
batch. **Lacteva remains SoR for its operational records (collection, quality,
settlement, delivery) unless an enterprise contract dictates otherwise.** **Do
not implement, mock, or assume SAP module names / OData / BAPI / IDoc.**

## 12. Chilling / BMC / Plant roadmap (V2 — definition only)

- **Collection Centre (GREEN):** collection, weighing, quality, operator,
  device, local connectivity.
- **BMC (V2):** milk aggregation, temperature, storage, quantity, asset
  monitoring, transfer — **BMC is an ASSET at a location**, via the device
  registry, not a location itself.
- **Chilling Centre (V2):** inbound milk reception, quality, batch/lot,
  storage, dispatch, logistics — a new **location type**.
- **Plant (V2/ENTERPRISE):** receiving, processing, production batches,
  packaging, raw/finished inventory, dispatch, plant quality, batch
  traceability.
- **Preserve the transport distinction:** procurement transport (centre →
  chilling → plant, reconciliation at each hop) is a **separate domain** from
  distribution/delivery transport (GREEN today). **Do not collapse them.**

## 13. "Coming Soon" policy

**Allowed:** non-interactive labels; nav entries marked "Coming Soon"; roadmap
info; role-based visibility of future modules (via the existing nav registry as
a future feature-flag). **Not allowed:** fake API, data, hardware readings, SAP
connection, AI results, GPS, SSO, portals, or buttons that appear operational.

| Feature | Phase | Status | Coming Soon label | Dependency |
|---|---|---|---|---|
| AI Analytics | V1/V2 | NOT BUILT | AI Insights — Coming Soon | real data volume |
| Automated Scale Capture | V1+ | NOT BUILT | Coming Soon | hardware evidence (§P0-HW-002) |
| Automated Analyzer Capture | V1+ | NOT BUILT | Coming Soon | hardware evidence |
| Chilling Centre | V2 | NOT BUILT | Coming Soon | V2 domain |
| BMC | V2 | NOT BUILT | Coming Soon | V2 domain |
| Plant Operations | V2/ENT | NOT BUILT | Coming Soon | V2 domain |
| SAP/ERP Integration | ENT | NOT BUILT | Enterprise | signed enterprise |
| Enterprise SSO | ENT | NOT BUILT | Coming Soon | global identity |
| Global Identity | ENT | NOT BUILT | Coming Soon | multi-org customer |
| Farmer App | FUTURE OPTION | NOT BUILT | Coming Soon | commercial need |
| Customer/Outlet Portal | FUTURE OPTION | NOT BUILT | Coming Soon | commercial need |
| Advanced Analytics | V1+/V2 | NOT BUILT | Coming Soon | data volume |
| GPS | FUTURE | NOT BUILT | Coming Soon | never a pilot dep. |
| Messaging/WhatsApp | V1 | NOT BUILT | Coming Soon | DLT/BSP paperwork |
| Enterprise Reporting | ENT | NOT BUILT | Enterprise | federation |

## 14. Commercial packaging (no prices invented)

Foundation exists (subscription module). Possible packages:

| Package | Contains | Lever |
|---|---|---|
| Dairy Starter / Pilot | core collection + distribution, 1 org, few centres | core subscription (subsidised) |
| Dairy Operations | full lifecycle, single dairy | core subscription |
| Multi-Centre | many centres/branches | per-location |
| Enterprise | multi-site/region/plant + integrations | enterprise-only |
| Hardware Connector | centre connector + adapters | optional module (per connected centre) |
| Analytics / AI | trends, anomaly, forecasting | optional module / add-on |
| Enterprise Integration | SAP/ERP, API layer, SSO | integration/service, enterprise-only |

Capability classes: **core subscription** (lifecycle) · **optional module**
(connector, analytics/AI) · **usage-based** (transaction volume, future) ·
**integration/service** (SAP, implementation, AMC) · **enterprise-only**
(federation, SSO, enterprise reporting). **Prices: TO CONFIRM (business).**

## 15. Dependency map

```
Real dairy pilot ──> real business data ──> COMMERCIAL HARDENING (parallel)
      │                                          │
      └──> hardware discovery ──> Centre Connector ──> multi-centre ops
                                                        │
                                            chilling / BMC ──> plant ──> ENTERPRISE
                                                                            │
                                                        SAP  ·  enterprise SSO / global identity / federation
                                                                            │
                                                              enterprise analytics / AI (advanced)
```
**Parallel independent tracks** (need not serialise behind the pilot):
commercial hardening (SMTP, doc fields, advances/loans); AI-on-existing-data
(supplier trends/anomaly) *after* the pilot generates data; messaging vendor
paperwork (DLT/BSP); the identity scope-generalisation groundwork. **GPS and
SAP are late and independent; neither gates anything earlier.**

## 16. Master "DO NOT BUILD YET" list

SAP/ERP integration · enterprise SSO · global identity · GPS · farmer app ·
customer/outlet portal · chilling centre · BMC · plant/processing · procurement
transport · advanced hardware automation · additional hardware vendors ·
advanced AI · predictive analytics · WhatsApp/SMS provider integration ·
enterprise federation · consumer app · **P0-HW-003 connector before the
§P0-HW-002 evidence gate** · global-identity rework before a real multi-org
customer. *(Nothing here has been implemented; the AI deviation flag and the
subscription foundation are the only "future-adjacent" items already GREEN.)*

## 17. Master decision register

**DECIDED:** tenant = Organization (org_type); Workspace/Branch/Centre
hierarchy; RLS on Organization.id; registry-first RBAC; scope-on-grant; **one
identity per person, app-specific authz**; device = asset (not a login);
manual-first read-assist hardware; distribution driver ≠ procurement
transporter; hybrid parent/federation for enterprise; org-to-org via consented
projections (never widened RLS); AI stays on the roadmap; no compliance module;
"Coming Soon" = labels only; connector gated on evidence.

**TO CONFIRM:** the pilot dairy's operating model (M1 assumed) and rate-chart
shape (drives litres / FAT×SNF increments); settlement cycle; pilot commercial
terms; which V1 dairy first needs branch scope; SSO tier (recommend
ENTERPRISE); master-data SoR for SAP.

**FUTURE DECISION:** federation-vs-internal-hierarchy for the first enterprise
group; farmer/customer-portal commercial triggers; pricing model mix;
GPS adoption; which analyzer/scale families to support after discovery.

## 18. Recommended next milestone

**No new engineering milestone is recommended before the pilot.** The immediate
objective is the **real dairy go-live** (LACTEVA-GO-LIVE-READINESS —
business/data/paperwork gated). The next *engineering* milestone remains
**P0-HW-003 Centre Connector MVP**, strictly gated on the
LACTEVA-HARDWARE-CONNECTOR-DISCOVERY §29 evidence. **Commercial hardening**
(SMTP, doc fields, advances/loans, supplier-trend analytics) is the natural
parallel V1 track once the pilot is live.

---

## Final report

1. **Executive verdict** — GO for the pilot (business-gated); the platform is a
   deployed working system; the enterprise future is additive, not a rewrite;
   all future capabilities preserved, none converted to a present commitment.
2. **Current product state** — §2: full lifecycle GREEN and proven; pilot is
   DATA-DEPENDENT; connector DISCOVERY-GATED.
3. **Target dairy ecosystem** — §3: full chain modeled, two transport legs kept
   distinct; actors classified A/B/C/D (no login sprawl).
4. **Application family** — §4: one portal + one mobile binary today; new
   modules before new apps; connector V1; SAP layer ENTERPRISE.
5. **User/persona model** — §5: definitive identity table; person ≠ org ≠
   location ≠ device ≠ farmer ≠ customer ≠ driver.
6. **Identity + SSO** — §6: one identity per person now; global identity + SSO
   ENTERPRISE, RLS never weakened.
7. **Organization/enterprise** — §7: hybrid parent/federation; org-level RLS,
   per-org books, consented org-to-org.
8. **Onboarding** — §8: invitation/import GREEN and proven; self-signup none;
   API/SAP ENTERPRISE.
9. **V1/V2/Enterprise roadmap** — §9: full phased table.
10. **AI roadmap** — §10: MVP GREEN; the rest phased by data availability; no
    vendor.
11. **SAP/ERP roadmap** — §11: boundaries only; SoR questions UNKNOWN/TO
    CONFIRM; nothing mocked.
12. **Chilling/BMC/Plant** — §12: V2 domains; BMC = asset; transport distinction
    preserved.
13. **Coming Soon policy** — §13: labels only, never fake functionality.
14. **Commercial packaging** — §14: packages + levers; prices TO CONFIRM.
15. **Dependency map** — §15: serial spine + parallel tracks; GPS/SAP late and
    independent.
16. **Do-not-build-yet list** — §16: preserved and explicit.
17. **Decisions vs unknowns** — §17: register.
18. **Recommended next milestone** — §18: dairy go-live (business-gated); then
    P0-HW-003 (evidence-gated); commercial hardening in parallel.

**No previously approved future capability was removed. None was implemented,
mocked, fabricated, or converted into a present commitment. No code, schema,
migration, API, UI, vendor, or protocol was created.**

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Master product roadmap: consolidated NOW/PILOT/V1/V1+/V2/ENTERPRISE/FUTURE phasing; target ecosystem + actor classification; application family; definitive user/identity table; identity/SSO, organization/enterprise, onboarding models; AI/SAP/chilling-BMC-plant roadmaps; Coming Soon policy; commercial packaging; dependency map; do-not-build-yet list; decision register; executive roadmap. Documentation only — grounded in code and prior milestones; nothing built. |
