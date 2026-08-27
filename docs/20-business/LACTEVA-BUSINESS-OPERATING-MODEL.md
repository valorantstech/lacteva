---
id: LACTEVA-BUSINESS-OPERATING-MODEL
title: Business Operating Model & Target Architecture
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-PILOT-MASTER-ROADMAP, LACTEVA-PRODUCT-GAP-REVIEW, LACTEVA-GO-LIVE-READINESS, LACTEVA-HARDWARE-INTEGRATION-SPEC, LACTEVA-REGULATORY-APPLICABILITY-AUDIT, ARCHITECTURE_BASELINE_V1]
baseline: ARCH-BASELINE-V1
---

# Lacteva Business Operating Model & Target Architecture

**Definition only — no code, schema, or production change.** This establishes
the target business/enterprise/application architecture *before* the Identity
+ Enterprise Organization audit and before the next implementation milestones.
The repository and prior milestones are the source of truth for what exists;
unknowns are tagged **UNKNOWN / ASSUMPTION / TO CONFIRM / FUTURE OPTION**.

Tag legend for architecture components: **GREEN** (exists, verified) ·
**CONFIG** (exists, per-dairy configuration) · **NEXT** (immediate next
engineering) · **V1** · **V2** · **ENTERPRISE/FUTURE** · **NOT REQUIRED**.

---

## 1. Executive summary

Lacteva is a **B2B dairy operations platform**: it runs the procurement,
collection, quality, pricing, settlement, distribution, billing and reporting
of a dairy business, with a manual-first, offline-capable, hardware-ready
capture layer. **The existing architecture already realises the core of the
target** — the tenant is an `Organization` with an `org_type` that already
distinguishes cooperative / processor / collector / farm; there is a
Workspace → Branch → Collection-Centre location hierarchy, a 10-role RBAC
registry with per-location scope, PostgreSQL RLS tenant isolation, logistics
(routes/vehicles/drivers/runs), a device registry, and a subscription/SaaS
billing module. The evolution to enterprise scale is **additive**, not a
rebuild: new *location types* (plant, chilling centre, BMC, depot), a
*procurement-transport* domain distinct from distribution, and integration
boundaries (SAP, GPS, messaging, AI) that the modular monolith's ports already
anticipate. **Verdict (section E): yes, the existing architecture can evolve
into this target without a rewrite.**

## 2. Real Indian milk-flow models (not one model)

The platform must not hard-code one chain. The realistic variants:

**M1 — Private/collector dairy (today's pilot shape):**
Farmer → Collection Centre → (Dairy-owned Chilling/BMC) → Dairy Plant →
Depot → Route → Customer/Outlet → Consumer.

**M2 — Cooperative three-tier (Anand pattern):**
Farmer → Village Cooperative Society (DCS) → Milk Union → Chilling Centre →
Union Dairy Plant → distribution.

**M3 — Collector-to-processor supply:**
Farmer → Collection Centre → BMC → sold/dispatched to a separate processor
(the collector may not own the plant).

**M4 — Direct-procurement processor:**
Farmer → Company Collection Centre → Company Chilling → Company Plant
(vertically integrated, e.g. large private dairies).

**Two distinct transport legs (never collapse — see §11):**
- *Procurement transport*: Collection Centre → Chilling/BMC → Plant (can/tanker
  movement of raw milk inward, weight/quality reconciled at each hop).
- *Distribution transport*: Plant/Depot → Route → Driver → Customer/Outlet
  (finished/packed product outward, delivery outcomes + billing).

**Ownership varies by model** — a chilling centre may be the dairy's, a union's,
or a third party's; the platform models *who operates a location* and *who owns
the milk at each hop* rather than assuming one owner. **TO CONFIRM WITH DAIRY:**
which model the pilot dairy runs (assumption: M1).

## 3. Lacteva target market

Primary today: **one real Indian dairy firm/operator** (small–medium,
collector/processor). The architecture must *scale up* without premature
enterprise complexity:

| Segment | When | Notes |
|---|---|---|
| Small/private dairy firm | **NOW** (pilot) | single org, few centres, one plant or none |
| Medium dairy business | V1 | multi-centre, one/few plants, depots |
| Dairy cooperative / DCS network | V1–V2 | society layer, member-farmers |
| Milk union | V2 | society → union → plant hierarchy |
| Multi-plant / multi-region enterprise | ENTERPRISE/FUTURE | regions, business units |
| Amul/Nestlé-scale | FUTURE TARGET | not today's implementation target |

Rule: **do not build enterprise levels prematurely; do not architect them out.**
The Organization → Workspace → Branch → Centre hierarchy already gives the
headroom (§7).

## 4. Business entities (classification)

| Entity | Class | Status |
|---|---|---|
| Enterprise / **Organization** (tenant) | Legal/business org | **GREEN** (`Organization`, `org_type`) |
| Business Unit / Region | Legal/operational | CONFIG via **Workspace** (GREEN) or new level (FUTURE) |
| **Branch** | Operational grouping | **GREEN** |
| Cooperative Society / Milk Union | Legal/business org | FUTURE (org_type + hierarchy) |
| Plant / Processing Plant | Operational location | FUTURE (new location type) |
| Chilling Centre | Operational location | FUTURE |
| Bulk Milk Cooler / BMC | Operational location/asset | FUTURE |
| **Collection Centre** | Operational location | **GREEN** (`CollectionCenter` under branch) |
| Procurement Operation | Domain/process | GREEN (milk_collection) |
| Distribution Centre / Depot | Operational location | FUTURE (new location type) |
| **Route** | Reference/operational | **GREEN** (logistics) |
| **Vehicle** | Physical asset | **GREEN** |
| **Driver** | Person | **GREEN** |
| **Hardware Device** | Physical asset | **GREEN** (device registry) |
| **Farmer / Supplier** | Person/business | **GREEN** (`Supplier`, `SupplierProfile`) |
| **Customer** | Business/person | **GREEN** |
| **Outlet / Delivery Location** | Operational location | **GREEN** (customer + address; explicit outlet entity FUTURE) |
| **Product** | Reference | **GREEN** (product codes, e.g. RAW-COW-MILK) |
| **Order / Standing Order** | Transaction/reference | **GREEN** (delivery plan) |
| **Delivery** | Transaction | **GREEN** |
| **Settlement** | Transaction | **GREEN** |
| **Rate Card** | Reference/config | **GREEN** |
| **Milk Collection Transaction** | Transaction | **GREEN** |
| **Quality Reading** | Transaction data | **GREEN** (fat/snf/clr on the transaction) |
| **Parchi / Collection Slip** | Document | **GREEN** (`slip_number`, slip endpoint) |

Classes: *Legal/business organizations* (Enterprise, Society, Union);
*Operational locations* (Region, Branch, Plant, Chilling, BMC, Centre, Depot,
Outlet); *People* (Farmer, Customer, Operator, Driver, staff); *Physical
assets* (Vehicle, Device); *Transactions* (Collection, Delivery, Settlement,
Payment, Invoice); *Reference/config* (Product, Rate Card, Route, Standing
Order). **Not every dairy uses every entity** — the model must degrade to M1.

## 5. Enterprise hierarchy

**Existing (GREEN):** Platform → Organization (tenant) → Workspace → Branch →
Collection Centre → operational users. RLS binds everything to
`Organization.id`; role scope can pin a user to a centre (`center_id`).

**Target (additive):**
```
Lacteva Platform
  └── Enterprise = Organization (tenant, org_type)         GREEN
       └── Business Unit / Region = Workspace              GREEN (rename/role FUTURE)
            └── Branch                                     GREEN
                 └── Location: Collection Centre           GREEN
                             | Chilling Centre / BMC       FUTURE (new location types)
                             | Plant                       FUTURE
                             | Depot / Distribution Centre FUTURE
                      └── Operational users (scoped)       GREEN
```
**No enterprise assumes all levels.** A small dairy is Organization → one
Branch → centres. **ASSUMPTION:** new location types (plant/chilling/BMC/depot)
become subtypes of the existing location pattern rather than parallel trees.

## 6. Procurement model — **GREEN**

Farmer/supplier management, collection sessions (shift), quantity (kg),
FAT/SNF/CLR quality, rate cards (FAT-banded per product, cow/buffalo), pricing
at capture, parchi, settlement — all exist and are proven live and on a real
handset. Manual-first with source attribution; offline capture/replay.
**CONFIG per dairy:** the rate chart, farmer list, settlement cycle.

## 7. Collection-centre model — **GREEN**

Centres under branches; operators; operating hours; readiness checks (active
scale = blocking); device registry with health; collection sessions; the whole
capture wizard (proven on glass). **This is the most complete domain.**

## 8. Chilling-centre model — **FUTURE (V2)**

Not modeled. Would add: chilling-centre location type; **milk reception**
(cans/tankers in, reconciled against dispatching centres — a *procurement
transport* boundary, §11); chilling/temperature telemetry; **milk movement**
(BMC → plant) with weight/quality reconciliation; dispatch. **DO NOT BUILD
NOW.** The device registry + source-attribution seam and the settlement/
reconciliation machinery are the reusable foundations.

## 9. Plant / processing model — **FUTURE (V2/ENTERPRISE)**

Not modeled and a genuine V2 *domain*, not a feature: plant operations,
processing/production, batch management, raw-vs-finished inventory, finished
goods, plant quality management. This is where Lacteva grows from "operations
+ procurement + distribution" into a full dairy ERP-adjacent platform. **DO NOT
BUILD NOW.**

## 10. Distribution model — **GREEN**

Customers, outlets (customer + address; explicit multi-outlet-per-customer is a
FUTURE refinement), standing orders (plans), routes, vehicles, drivers,
delivery runs, delivery outcomes, billing (invoices), receivables — all exist,
proven live and on a real handset (driver run completed on glass).

## 11. Procurement transport vs distribution transport — **the key distinction**

**Do not collapse these into one driver workflow.** They differ in cargo,
direction, reconciliation, and persona:

| | Procurement transport | Distribution transport |
|---|---|---|
| Cargo | Raw milk (cans/tankers) | Finished/packed product |
| Direction | Inward (centre → chilling → plant) | Outward (plant/depot → outlet) |
| Reconciliation | Weight/quality at each hop; shrinkage | Delivery outcome; billing |
| Persona | Procurement transporter / tanker operator | **Delivery driver** (GREEN) |
| Status today | **FUTURE (V2)** — not modeled | **GREEN** |

The current `Driver` + `DeliveryRun` model is **distribution only** — and
correctly so (P0-MOB/P0-PILOT-004 built exactly that persona). Procurement
transport is a separate future domain with its own movement/reconciliation
entities. **Architectural risk if ignored (§C):** reusing the delivery driver
model for tanker movement would corrupt both.

## 12. User/persona model — who needs a login

**Rule: do not create a user because an entity exists.** Login = someone who
*operates the software*.

| Persona | Login today | Login later | Rationale |
|---|---|---|---|
| Enterprise Owner | — | **Yes** | Portal oversight; pilot uses org-manager |
| Enterprise/Org Admin | **Yes** (ORGANIZATION_ADMIN) | Yes | Tenant setup |
| Org Manager | **Yes** (ORGANIZATION_MANAGER) | Yes | Runs the dairy |
| Regional Manager | — | Yes (V2) | Multi-region scope |
| Plant Manager | — | FUTURE | Plant domain (§9) |
| Chilling-Centre Manager | — | FUTURE | Chilling domain (§8) |
| Collection-Centre Manager | **Yes** (CENTRE_MANAGER) | Yes | Centre scope |
| Collection Operator | **Yes** (COLLECTION_OPERATOR) | Yes | Runs capture |
| Procurement Manager | — (use Org Manager) | Yes (V1) | Distinct role later |
| Quality Manager | — | Yes (V1) | Quality oversight |
| Finance Manager / Accountant | **Yes** (FINANCE_MANAGER/OFFICER) | Yes | Settlement/billing |
| Sales / Distribution Manager | **Yes** (SALES_OFFICER) | Yes | Orders/routes |
| Operations Manager | — (use Org Manager) | Yes | Cross-domain |
| **Driver** | **Yes** (DRIVER) | Yes | Mobile run app |
| Auditor / Read-only | **Yes** (AUDITOR) | Yes | Read scope |
| Lacteva Support | — | Yes | Cross-tenant, gated |
| Lacteva Platform Admin | **Yes** (PLATFORM_SUPER_ADMIN) | Yes | Platform ops |
| **Farmer** | **No** | FUTURE OPTION | Imported/created by dairy; app when commercially useful (§19) |
| **Customer** | **No** | FUTURE OPTION | Created/imported; self-service portal is FUTURE |
| **Outlet** | **No** | FUTURE OPTION | A delivery location, not a user |
| **Transporter (procurement)** | **No** | FUTURE (V2) | Comes with §11 |
| **Hardware/device** | **No** (a device credential, not a user) | Yes as *device principal* | Connector auth, not a login (§21) |

## 13. Application model

| Application | Status | Who |
|---|---|---|
| **Enterprise/Admin Portal** (Next.js) | **GREEN** | owners, managers, finance, sales, ops, auditor |
| **Collection Mobile App** (Flutter) | **GREEN** | collection operators |
| **Driver Mobile App** (Flutter, same binary, persona-routed) | **GREEN** | drivers |
| **Platform Admin** | **GREEN** (platform-admin surfaces) | Lacteva platform admins |
| Hardware Connector | NEXT (P0-HW-002, gated) | device integration |
| Farmer App / Portal | FUTURE OPTION | farmers |
| Customer/Outlet Portal | FUTURE OPTION | customers |
| Enterprise Integration / API layer | FUTURE (SAP/ERP) | external systems |

**Persona → access matrix (representative):**

| Persona | Identity | Org scope | Role | Application | Permissions |
|---|---|---|---|---|---|
| Org Manager | 1 Lacteva identity | org-wide | ORGANIZATION_MANAGER | Portal | broad ops |
| Centre Manager | 1 identity | centre | CENTRE_MANAGER | Portal + Collection App | centre ops |
| Collection Operator | 1 identity | centre | COLLECTION_OPERATOR | Collection App | capture only |
| Finance Manager | 1 identity | org-wide | FINANCE_MANAGER | Portal | settlement/billing |
| Sales/Distribution | 1 identity | org-wide | SALES_OFFICER | Portal | customers/orders/routes |
| **Driver** | 1 identity | own runs | DRIVER | Driver App | run execute only |
| Auditor | 1 identity | org-wide read | AUDITOR | Portal | read |

**Key decision (recommended): ONE Lacteva identity per person, with
application-specific authorization** — not separate credentials per app. A
Centre Manager uses *the same login* on Portal and Collection App; the role +
scope decide what each app shows. This already holds today (a user's role
gates both the portal shell and the mobile `experienceFor`).

## 14. Identity model — **GREEN foundation**

One `User` (identity module) ↔ `Membership` in an `Organization` ↔ roles.
Applications authorise against the *same* identity + role + scope. Multi-
location / multi-function: today a user has one membership per org with role
scope (e.g. `center_id`); **a user needing several centres or functions is
represented by role grants, not multiple logins.** **TO CONFIRM (design):**
whether V2 multi-region needs multiple memberships or a scope set on one
membership (recommend the latter — one identity, a scope list).

## 15. SSO target state — **FUTURE, do not implement**

Target: one Lacteva identity, centralized authentication, application-specific
authorization; enterprise customers may want **their** IdP (SAML/OIDC) so their
staff use corporate SSO. The architecture already centralises identity in one
module behind `deps.py`; adding an external IdP is a bounded future increment.
**DO NOT BUILD NOW.** Decision required from us (§B): is enterprise SSO a V1 or
ENTERPRISE-tier feature? (Recommend ENTERPRISE.)

## 16. RBAC / RLS model — **GREEN**

- **RBAC**: a permission registry (`<module>.<entity>.<action>`), named roles
  (10 today), registry-first discipline; `require_permission()` at the
  composition root.
- **RLS**: PostgreSQL row-level security FORCED on `Organization.id`; a foreign
  resource is a 404, verified live. Application filters are defence-in-depth.
- **Scope × RBAC interaction**: role grants can be org-wide or location-scoped
  (`center_id`); driver own-run scoping is enforced at the service. **Target
  refinement (V2):** a general *organizational scope* (region/branch/centre
  set) attached to a membership, so RBAC checks permission and RLS/scope checks
  reach — the pattern exists; generalising it is the enterprise increment.

## 17–21. Onboarding models (definition only — do not implement)

- **Enterprise onboarding (§18):** lead/agreement → create Organization
  (country defaults) → legal/business details → primary admin invite →
  configuration → locations (branches/centres) → rate card → farmers →
  customers/outlets → users → activation. **GREEN mechanics; the four artifacts
  + signatures are the gate (see go-live readiness).**
- **Employee/user onboarding (§17):** invite → accept (sets password/identity)
  → role → org scope → application access follows role → active. **GREEN.**
- **Collection operator:** org → branch → centre → invite operator → role →
  Collection App access. **GREEN.**
- **Driver:** org → create driver profile → invite driver login → link
  (`/drivers/{id}/user`) → assign vehicle/route → Driver App. **GREEN**
  (proven end-to-end, P0-PILOT-004).
- **Farmer (§19):** today **imported by the dairy** (CSV) or created at the
  centre; **no farmer login.** A farmer app becomes commercially useful when
  farmers want self-service parchi history / payment visibility at scale —
  **FUTURE OPTION**, not pilot.
- **Customer/outlet (§20):** CSV import or admin creation; **no login.**
  Customer/outlet self-service portal is **FUTURE OPTION**.
- **Hardware (§21):** device registry → centre assignment → device type →
  credential (per-device, revocable — *not* a user login) → health →
  provenance → connector. **Registry GREEN; connector NEXT (P0-HW-002).**

## 22. SaaS / commercial model — **foundation exists (subscription module)**

A `Subscription` module already exists (plan_code, trial, per-centre payment,
webhook ledger, grace period). Recommended commercial architecture (prices
**not** invented):

| Lever | Tier | Notes |
|---|---|---|
| Enterprise subscription (base) | PILOT→V1 | per organization |
| Per-location (centre/plant/depot) | V1 | scales with the dairy — foundation exists |
| Per-user | V1 option | seat-based for office users |
| Module-based | V1–V2 | procurement / distribution / plant as modules |
| Transaction-based | V2 option | volume pricing |
| Hardware connector | V1 (after P0-HW-002) | per connected centre |
| Analytics / AI add-ons | V2 | premium |
| SAP/enterprise integration | ENTERPRISE | add-on |
| Support / implementation | all tiers | services |

**Separation:** PILOT = simple flat/subsidised offering; V1 = per-location +
modules; ENTERPRISE = multi-site + integrations + analytics + AI. **Decision
required (§B):** the pilot's commercial terms. **DO NOT invent prices.**

## 23. Regulatory boundary — unchanged from P0-REG-001

The **dairy remains the regulated entity.** Lacteva touches only: FSSAI
number on the dairy's sale documents (V1 field), FSSAI record-keeping (Lacteva
*is* the record system — a selling point, not a feature to build), Legal
Metrology scale certificate (dairy's; optional device metadata later), GST
document form (V1 polish; pilot milk is largely exempt). **DPDPA is NOT a
milk-industry regulation** — it is general data-governance: where personal
data is processed, obligations apply to the dairy (fiduciary) and Lacteva
(processor) per their legal roles; core obligations commence 13 May 2027; the
pilot minimum is contractual + a notice/consent line. **No compliance module.**

## 24. Current vs future product architecture

**GREEN/EXISTING:** Identity & Organization; Procurement (farmers, centres,
collection, quality, rate, settlement, parchi); Collection-Centre Operations
(operators, sessions, device registry, offline); Distribution (customers,
outlets, orders, routes, vehicles, drivers, delivery, billing, receivables);
Reporting/Audit; RBAC/RLS; backup/restore; mobile (both personas, on glass);
subscription/SaaS foundation; hardware seam.

**CONFIG:** rate card, farmer/outlet lists, settlement cycle, org locations.

**NEXT:** P0-HW-002 connector (gated on discovery); production hardening (host,
SMTP, retention→30d).

**FUTURE:** chilling/BMC; plant/processing; procurement transport; advanced
analytics; AI (§25); SAP/ERP (§26); GPS/messaging (§27); farmer/customer
portals; enterprise SSO; multi-region hierarchy.

## 25. AI roadmap boundary — part of the product, phased

**AI stays in the architecture.** One MVP is **implemented** (supplier FAT/SNF
deviation flag — statistics, event-only, no vendor). Phasing:

- **Uses existing data (NEXT/V1):** supplier trend analysis; collection quality
  alerts; settlement anomaly detection; operator anomaly — all computable from
  today's transaction + metrics data, no vendor.
- **Needs more data/integration (V2/ENTERPRISE):** demand/procurement
  forecasting (needs sales history at volume); route optimization (needs GPS,
  §27); enterprise decision support (needs plant/inventory, §9).

**DO NOT build the AI roadmap now.** Recommend the existing deviation flag as
the seed and supplier-trend analytics as the first V1 AI add-on.

## 26. SAP / ERP integration boundary — **FUTURE, do not implement**

The UUID-boundary, event-driven modular monolith is integration-ready. Future
boundaries: SAP/ERP for finance/accounting; inventory; procurement; sales;
**customer master / supplier master** (system-of-record decision per
enterprise); settlement/billing document exchange. Direction and middleware
(OData/BAPI/IDoc/BTP) are per-customer. **ENTERPRISE tier, unless a signed
enterprise requires it.** **DO NOT build; DO NOT mock.**

## 27. GPS / messaging integration boundary — **FUTURE**

- **GPS/location:** driver location, vehicle tracking, route adherence, ETA,
  geofencing, and *both* transport legs (§11). **Lacteva is not a GPS-tracking
  company; GPS must never gate the pilot.** Optional future; a driver phone can
  carry it later.
- **Messaging:** WhatsApp (BSP), SMS (DLT), email (SMTP) — **real vendor-less
  adapters already exist**; email is config-only. **Do not implement providers
  now** (no milestone requires it); DLT/BSP are paperwork-led V1.

## 28. Enterprise-scale evolution

The path from pilot to enterprise is additive: (1) more location *types* under
the existing hierarchy (plant/chilling/BMC/depot); (2) a generalised
organizational *scope* on memberships (§16); (3) the procurement-transport
domain (§11); (4) integration ports (SAP/GPS/messaging/AI) behind the existing
adapter pattern; (5) enterprise SSO; (6) module-based commercial tiers. **None
requires discarding what exists.**

## 29. Existing architecture vs target — the map

| Target component | Existing | Gap |
|---|---|---|
| Identity & Organization | Organization/Workspace/Branch/Membership/roles | scope generalisation (V2) |
| Procurement | milk_collection/supplier/pricing/settlement | none (config only) |
| Collection centre | collection_center/operational_readiness | none |
| Chilling/BMC | — | **whole domain (FUTURE)** |
| Plant/processing | — | **whole domain (FUTURE)** |
| Distribution | customer/delivery/logistics/billing | outlet entity, none blocking |
| Procurement transport | — | **domain (FUTURE)** |
| Hardware | device registry + refused mocks | connector (NEXT) |
| Finance/billing | settlement/payment/receipt/billing | advances/loans (V1) |
| Analytics | 12 reports | dashboards/trends (V1–V2) |
| AI | deviation flag | roadmap (phased) |
| Integrations | vendor-less adapters, event bus | SAP/GPS/real vendors (FUTURE) |

## 30. Gaps (prioritised, from the gap review)

**NOW:** four dairy artifacts; signatures; production retention config.
**NEXT:** P0-HW-002 (gated); host hardening; SMTP.
**V1:** advances/loans; supplier trend analytics; FSSAI/GST document fields;
first messaging vendor; outlet entity refinement.
**V2/ENTERPRISE/FUTURE:** chilling/plant/procurement-transport domains;
enterprise scope generalisation; SSO; SAP; GPS; portals; forecasting AI.

## 31. Recommended implementation sequence

1. **P0-PILOT-005 go-live** (gated on the dairy — data, not code).
2. **P0-HW-002** connector MVP (gated on the hardware discovery visit).
3. **V1-COM-001** commercial hardening: advances/loans, FSSAI/GST document
   fields, SMTP + first messaging vendor, supplier-trend analytics, separated
   production host.
4. **Identity + Enterprise Org audit** (the milestone this document precedes) →
   then the enterprise scope generalisation (§16) as its own increment.
5. **V2 domains** (chilling → plant → procurement transport), one at a time,
   only as market demand proves them.

## 32. DO NOT BUILD YET

SSO; AI roadmap beyond the existing flag; SAP/ERP; GPS; WhatsApp/SMS providers;
farmer app; customer/outlet portal; chilling/BMC; plant/processing; procurement
transport; enterprise multi-region hierarchy; hardware connector (until
discovery); any compliance module.

## 33. Decisions requiring business approval

Pilot commercial terms; whether enterprise SSO is V1 or ENTERPRISE; module-vs-
per-location-vs-per-user pricing mix; which enterprise is the system-of-record
for customer/supplier master when SAP enters; whether the pilot dairy runs
model M1 (assumed) or another; the farmer-app trigger (when self-service
becomes commercially worth it).

## 34. Open questions

- **UNKNOWN:** the pilot dairy's exact operating model (M1–M4) and whether it
  owns a plant/chilling centre.
- **TO CONFIRM WITH DAIRY:** rate-chart shape (drives G-04/G-05); settlement
  cycle; whether procurement transport is in scope for the pilot (assumed no).
- **ASSUMPTION:** new location types subtype the existing location pattern;
  enterprise scope becomes a set on one membership.
- **FUTURE OPTION:** farmer/customer portals; enterprise SSO; AI forecasting.

---

## A. Decisions we have already made
One tenant = Organization with org_type; Workspace/Branch/Centre location
hierarchy; RLS on Organization.id; registry-first RBAC; **one identity per
person, application-specific authorization** (not per-app credentials);
manual-first hardware with source attribution; distribution driver ≠
procurement transporter; vendor-less integration adapters; AI stays in the
roadmap; no compliance module.

## B. Decisions still required from us
Pilot commercial terms; SSO tier (V1 vs ENTERPRISE); pricing model mix;
master-data system-of-record for SAP era; enterprise scope representation
(scope-set vs multi-membership — recommend scope-set); farmer-app trigger.

## C. Architectural risks
1. **Collapsing procurement transport into distribution driver** — would
   corrupt both; keep them separate domains (§11).
2. **Premature enterprise levels** — building region/plant now adds complexity
   with no pilot payoff; keep additive.
3. **Per-app credentials creep** — resist; one identity, app-specific authz.
4. **Compliance-module temptation** — the dairy is the regulated entity; do not
   build one.
5. **Farmer/customer login sprawl** — do not create logins for entities that
   do not operate the software.

## D. Recommended next milestone
The **Identity + Enterprise Organization Architecture Audit** this document was
written to precede — auditing the existing Organization/Workspace/Branch/
Membership/role/scope model against §5–§16 and recommending the *scope
generalisation* increment. It is an audit, not an implementation.

## E. Can the existing Lacteva architecture evolve into this target?
**Yes.** The core (identity, org hierarchy, procurement, collection,
distribution, RBAC/RLS, billing, mobile, hardware seam, SaaS foundation) is
already the target's centre. Every enterprise addition — new location types,
scope generalisation, procurement transport, integration ports, SSO, AI,
module-based commerce — is **additive and bounded** by the modular-monolith
seams that exist today. No rewrite is required.

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Business operating model & target architecture: milk-flow models, entities, hierarchy, personas, applications, identity/SSO, onboarding, SaaS, regulatory boundary, AI/SAP/GPS/messaging boundaries, existing-vs-target map, sequence, DO-NOT-BUILD list, decisions/risks (definition only, no code). |
