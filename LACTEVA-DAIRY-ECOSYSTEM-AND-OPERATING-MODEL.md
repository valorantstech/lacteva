---
id: LACTEVA-DAIRY-ECOSYSTEM-AND-OPERATING-MODEL
title: Dairy Ecosystem & Operating Model
type: reference
status: Approved
version: "1.0"
owner: Product & Architecture
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-MASTER-PRODUCT-ROADMAP, LACTEVA-BUSINESS-OPERATING-MODEL, LACTEVA-IDENTITY-ENTERPRISE-ARCHITECTURE-AUDIT, LACTEVA-COMMERCIAL-MODEL-AND-PACKAGING, LACTEVA-PRODUCT-CAPABILITY-VISIBILITY-AUDIT, LACTEVA-P0-PILOT-008-REAL-DAIRY-ONBOARDING-READINESS, LACTEVA-HARDWARE-CONNECTOR-DISCOVERY, LACTEVA-REGULATORY-APPLICABILITY-AUDIT, LACTEVA-FIRST-DAIRY-SALES-AND-PILOT-PACKAGE]
baseline: ARCH-BASELINE-V1
---

# Lacteva — Dairy Ecosystem & Operating Model (P0-BUSINESS-ECOSYSTEM-001)

**Documentation only.** No code, schema, API, UI, demo data, price, customer,
vendor, or regulatory requirement is created here. This document consolidates
how Lacteva fits the complete milk ecosystem — farmer through consumer — from
decisions **already made in the repository**, phased **NOW · V1 · V2 ·
ENTERPRISE · FUTURE OPTION · TO CONFIRM**. Where governing documents disagree,
the contradiction is **named, not silently fixed** (§0). Code outranks prose;
the Master Product Roadmap outranks earlier documents on phasing.

---

## 0. Contradictions found during cross-reference (not silently fixed)

| # | Contradiction | Sources | Resolution used here | Owner action |
|---|---|---|---|---|
| C1 | **BMC: asset or location?** The Business Operating Model types BMC as a future *location type* (§4, §5, §24); the Identity/Enterprise Audit (§11) and Master Roadmap (§12) are categorical: "**BMC is an ASSET at a location** … not a location itself." | BOM §4/§5 vs Audit §11 + Roadmap §12 | **BMC is an asset** (roadmap + audit; also §17 decision register). | Correct BOM wording at its next revision |
| C2 | **Subscription framing.** BOM §22 lever table frames "Enterprise subscription (base) · per organization" for PILOT→V1 with per-location as a V1 lever; the code (DEMO-026 `plans.py`) and the Commercial Model doc are decided: **per collection centre** is today's model. | BOM §22 vs `subscription/plans.py` + Commercial doc §A/§E | **Per centre** (code is authoritative). | Reframe BOM §22 at next revision |
| C3 | **The shipped mobile customer experience is missing from the BOM app matrix.** A customer/household screen ships in the mobile binary (DEMO-012: `User.customer_id`, `Experience.customer` → `CustomerHomeScreen`), but BOM §13 lists customer surfaces only as FUTURE OPTION. | BOM §13 vs `identity/models.py` `customer_id` + `mobile home.dart` | The customer **mobile** experience is **NOW**; the **web** outlet portal is FUTURE OPTION. | Add the shipped screen to BOM §13 |
| C4 | **`org_type` vocabulary.** Code: `cooperative\|processor\|collector\|farm\|other` (`organization/models.py:23`); roadmap §7 phrases it "cooperative/private/collector/processor/farm". | code vs roadmap §7 | **Code values** are authoritative (`other`, not `private`; a private dairy is typically `processor` or `collector`). | Align roadmap wording at next revision |
| C5 | **Owner login wording.** BOM §12 says the Enterprise Owner has no login today ("pilot uses org-manager") while §13 lists "owners" among portal users. | BOM §12 vs §13 | Reconcilable: an owner **may hold** a login with the org-admin/manager role; "Owner" is not itself a role. | Tighten BOM wording |

---

## SECTION 1 — The complete dairy value chain

**Not every dairy runs every stage.** The Business Operating Model (§2) fixes
four real Indian flow variants — M1 private/collector dairy (the pilot
assumption), M2 cooperative three-tier, M3 collector-to-processor, M4
direct-procurement processor — and rules that "the platform must not hard-code
one chain." Which model the pilot dairy runs is **TO CONFIRM** (assumption: M1).

| Stage | What happens physically | Who operates it | Data owner | Lacteva TODAY | Lacteva later | Login? | Lacteva customer or record? | Phase |
|---|---|---|---|---|---|---|---|---|
| **Farmer** | Milks animals; brings milk to the centre | The farmer (household) | The dairy owns the farmer *record*; the farmer owns their animals/milk until sale | Supplier record, per-collection pricing, parchi, settlement | Farmer self-service app (FUTURE OPTION) | **No** | Business record of the dairy — not a Lacteva customer | **NOW** (as record) |
| **Collection Centre** | Weighing, FAT/SNF/CLR, acceptance, parchi | Collection operator, centre manager (dairy staff) | The dairy (tenant) | The most complete domain: sessions/shifts, capture, rate, parchi, settlement — proven on a real handset | Automated read-assist (V1+, discovery-gated), QR scanning | **Yes** (operator/manager) | Part of the dairy tenant; **the billing unit** | **NOW** |
| **Chilling / BMC** | Raw milk cooled/aggregated; temperature and quantity tracked | Dairy, union, or third party (varies by model) | Whoever operates it (per BOM §2 ownership rule) | **Not modeled** | Chilling Centre = new **location type** (V2); **BMC = asset at a location** via the device registry (V2) | Future (V2 personas) | Usually part of the dairy tenant; third-party operator = TO CONFIRM (§18) | **V2** |
| **Procurement / transport** | Cans/tankers move raw milk inward, reconciled at each hop | Transporter (dairy's or third party) | The dispatching/receiving org per hop | **Not modeled — deliberately.** The delivery Driver/Run model is distribution-only | Separate procurement-transport domain (V2); never reuses the delivery driver model | Future (V2) | Record or future org-to-org party | **V2** |
| **Dairy (the business)** | Owns the operation: rates, settlement, money, staff | Owner/managers/finance | The dairy — it IS the tenant | Organization = tenant; dashboard, settlement, payments, receivables, reports, audit, subscription | Regional/branch scope descriptor (V2) | **Yes** (staff) | **The Lacteva customer — the economic buyer** | **NOW** |
| **Processing / plant** | Pasteurisation, production batches, packaging, inventory | Plant staff | The plant's org | **Not modeled** | Plant domain — receiving, batches, traceability (V2/ENTERPRISE) | Future | Part of tenant or separate org (model-dependent) | **V2/ENTERPRISE** |
| **Distribution / route** | Finished product outward: routes, vehicles, drivers, runs | Drivers, sales staff | The dairy | Routes, vehicles, driver runs, outcomes — proven on-glass | Route intelligence needs GPS (**FUTURE**, never a pilot dependency) | **Yes** (driver) | Dairy staff | **NOW** |
| **Outlet / customer** | Shops/households/institutions receive and pay | The outlet (external party) | The dairy owns the *record*; the outlet owns its own business | Customer/outlet records, standing orders, billing, receivables; household **mobile** experience (DEMO-012) | Web outlet portal (FUTURE OPTION) | **No** by default; household customer login **optional today** (speaks for one customer record) | Business record of the dairy | **NOW** (record + optional mobile) |
| **Consumer** | Drinks the milk | The public | — | Out of scope | Consumer app is on the §16 do-not-build list | No | Neither | **FUTURE (explicitly not built)** |

The two transport legs — procurement (inward, raw) and distribution (outward,
finished) — are **distinct domains, never collapsed** (BOM §11, Roadmap §12).

---

## SECTION 2 — Organization types

The tenant is an `Organization` with **`org_type ∈ cooperative | processor |
collector | farm | other`** (code, `organization/models.py:23`) and the
decided hierarchy **Organization (tenant) → Workspace (region/union/business
unit) → Branch (physical facility) → Collection Centre** (a centre belongs to
exactly one branch, same tenant, for life). **Not every entity becomes a
tenant** — the rule is: *a tenant is a legally/operationally distinct business
that keeps its own books, users and RLS* (Audit §12).

| # | Entity | Becomes | Why | Phase |
|---|---|---|---|---|
| 1 | Dairy / milk-procurement company | **Organization (tenant)**, `org_type: processor\|collector` | Keeps its own books; the economic buyer | **NOW** |
| 2 | Cooperative dairy / DCS network | **Organization**, `org_type: cooperative`; internal societies = Workspaces/Branches when one legal entity | One legal entity = one tenant with internal hierarchy | **NOW** (type exists) · V1–V2 (segment) |
| 3 | Private dairy | **Organization**, `org_type: processor\|collector` (no `private` value — C4) | Same as #1 | **NOW** |
| 4 | Collection-centre operator (dairy-owned) | **Collection Centre** under a Branch | A facility, not a business | **NOW** |
| 5 | Chilling centre / BMC operator | Dairy-owned: **future location type (chilling) + asset (BMC)**. Independent third-party business: **TO CONFIRM** — own tenant + future org-to-org relationship, or contracted facility record (§18) | C1 resolution: BMC is an asset | **V2** |
| 6 | Milk-procurement organization (union buying from collectors) | **Own Organization**; interacts via **future org-to-org consented projections — never widened RLS** | Separate books | **ENTERPRISE** |
| 7 | Processing / manufacturing plant | Dairy-owned: future **location type** under the tenant. Separate business: own tenant + org-to-org | Model-dependent (M1 vs M3) | **V2 / ENTERPRISE** |
| 8 | Distributor | Today: a **customer record** (the dairy sells to it). A distributor running Lacteva itself: own tenant | Don't make a record a tenant merely because it exists | **NOW** (record) · ENTERPRISE (tenant) |
| 9 | Outlet / retail customer | **Business record** (customer + standing orders) | Not a user of the software | **NOW** |
| 10 | Farmer / supplier | **Business record** (supplier) | Served by an operator; receives a parchi | **NOW** |
| 11 | Transport/logistics operator | Distribution driver = **person with a login** (dairy staff). Procurement transporter = **V2 record/persona**; third-party firm = future org-to-org | Two legs stay distinct | **NOW** / **V2** |
| 12 | Enterprise dairy group / parent | **Hybrid (decided)**: one Organization per legal entity (own books/users/RLS) + a light **parent/federation group** for rollup and SSO — never a merged tenant | Audit §12 recommendation C; Roadmap §7 | **ENTERPRISE** |

**Placement rule of thumb:** Organization = keeps its own books · Workspace =
internal region/union subdivision · Branch = physical facility · Centre =
collection facility under a branch · Location = branch/centre today (new types
V2) · **Asset** = device row attached to a centre (`Device.center_id`) ·
**Business record** = farmer/customer/outlet · **Org-to-org relationship** =
future `TradingRelationship` (ENTERPRISE, consented, one-directional
projections).

---

## SECTION 3 — Who pays Lacteva?

From the decided commercial model (DEMO-026 code + Commercial doc, verbatim
facts):

- **Buyer:** "the **dairy business** (the tenant `Organization`) — the economic
  buyer is its owner/management."
- **Basis:** subscription **per active collection centre**, monthly —
  "explicitly **not per user, not per litre**." Why not per-user: it
  "penalises correct use; **teaches login-sharing**"; multi-role/multi-centre
  on one identity costs nothing extra. Why not per-litre: seasonal volatility
  is "bad for the dairy."
- **Trial:** `LACTEVA_TRIAL` — **30 days** (code default; any change TO
  CONFIRM), unlimited centres, everything on, **not billable**.
- **Billable:** active collection centres on `LACTEVA_STANDARD`.
- **Not billable:** farmers, customers/outlets, devices, drivers-as-people,
  users as such — records and assets are never seats.
- **Prices:** deliberately absent from source; per-currency config
  (`subscription.price.LACTEVA_STANDARD.INR`) — **TO CONFIRM**. **No payment
  gateway is contracted** (provider `disabled`; `test` refused in prod).
- **Future modules/add-ons** (architecturally anticipated via the plan
  `capabilities` field, **not decided — TO CONFIRM**): Hardware Connector
  (V1, evidence-gated, "per connected centre"), AI/Analytics (V1+), Advanced
  Analytics/Forecasting (V2), SAP/ERP integration service (ENTERPRISE),
  enterprise SSO (enterprise-only), premium support/SLA.
- **Enterprise:** negotiated annual contracts, minimum commitment (**TO
  CONFIRM**), implementation/integration fees, SSO, multiple legal entities
  under the hybrid federation model, **RLS never weakened**. All
  ENTERPRISE-phase; none implemented. Professional services stay off the ARR
  line.

---

## SECTION 4 — Who needs a Lacteva login? (canonical identity table)

Standing rules, preserved verbatim from the decided model: **one Lacteva
identity per person · application-specific authorization (no per-application
credentials, ever) · multiple roles on one identity · the same person can
operate at multiple centres (scope lives on the grant, `UserRole.center_id`) ·
no login merely because an entity exists · no self-signup (invitation → accept
sets the credential).**

| Actor | Org type | Responsibility | Login? | Why | Primary app | Other apps | Roles | Scope | Data access | Onboarding | Phase |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Owner / Org admin | Dairy | Owns the business; approves | **YES** | Operates oversight | Admin Portal | — | ORGANIZATION_ADMIN / manager | Org-wide | Everything in the tenant | Platform admin invites | **NOW** |
| Org manager | Dairy | Day-to-day management | **YES** | Operates the software | Admin Portal | Collection App if hands-on | Manager | Org-wide | Operational + financial | Invite → accept → grant | **NOW** |
| Centre manager | Dairy | Runs one centre | **YES** | Operates centre | Admin Portal | Collection App | CENTRE_MANAGER | `center_id` scoped | Their centre | Invite → grant at scope | **NOW** |
| Collection operator | Dairy | Captures milk | **YES** | Operates capture | Collection App | — | COLLECTION_OPERATOR | Centre-scoped | Capture only | Invite → grant | **NOW** |
| Finance manager/officer | Dairy | Settlements, payments | **YES** | Operates money flows | Admin Portal | — | Finance roles | Org-wide | Financial | Invite → grant | **NOW** |
| Sales officer | Dairy | Customers, orders, routes | **YES** | Operates sales | Admin Portal | — | SALES_OFFICER | Org-wide | Sales | Invite → grant | **NOW** |
| Driver (distribution) | Dairy | Executes delivery runs | **YES** | Operates the run | Driver App (same binary) | — | DRIVER only | Own runs | Own route/outcomes | Create profile → invite → **link** `/drivers/{id}/user` | **NOW** |
| Auditor | Dairy / external | Reviews records | **YES** | Reads the books | Admin Portal | — | AUDITOR | Org-wide read | Read-only | Invite → grant | **NOW** |
| Platform admin (Lacteva) | Lacteva | Operates the platform | **YES** (`tenant_id` NULL) | Cross-tenant machinery | Platform admin surface | — | Platform roles | Platform | Operations, relay, health | Internal | **NOW** |
| **Farmer / supplier** | — (record of the dairy) | Brings milk | **NO** | Served by an operator; gets a parchi | — | Future: Farmer App | — | — | — | **CSV import / admin-created** | Record **NOW**; app **FUTURE OPTION** |
| Customer (household) | — (record) | Receives deliveries, pays | **NO by default; OPTIONAL today** | DEMO-012: a login may *speak for* one customer record (`User.customer_id`) | Customer mobile experience | — | Customer persona (not a staff role) | Own record only (`enforce_customer_scope`) | Own deliveries/bills/receipts | Dairy creates record; login optional | **NOW** (optional) |
| Outlet / retail customer | — (record) | Buys product | **NO** | A delivery location, not a user | — | Future: Web Outlet Portal | — | — | — | CSV import (inline plans) | Record **NOW**; portal **FUTURE OPTION** |
| Procurement transporter | Dairy/3rd party | Moves raw milk inward | **NO today** | Domain not modeled | — | Future V2 persona | — | — | — | — | **V2** |
| Chilling/BMC, plant staff | Dairy | Future domains | **NO today → FUTURE** | Domains not modeled | — | V2 apps/modules | Future roles | Location-scoped | — | — | **V2 / ENTERPRISE** |
| Regional/branch manager | Dairy | Multi-branch oversight | **FUTURE** | Needs the V2 scope descriptor (`{level, id}`) | Admin Portal | — | Future scoped grant | Region/branch | Scoped | — | **V2** |
| Device / connector | — (asset) | Reports readings | **NEVER a user login** | Future *device principal* credential — revocable, per-device | — | — | — | One centre | — | Device registry | Registry **NOW**; connector **V1 gated** |

---

## SECTION 5 — The Lacteva application family

Decided strategy (Roadmap §4): "keep **one portal** (scope-driven) and **one
mobile binary** (persona-routed) as long as possible; add new *modules* before
new *apps*."

| Application | Target users | Purpose | Login | Roles | Today | Future |
|---|---|---|---|---|---|---|
| **Admin / Dairy Operations Portal** (web) | Owner, managers, finance, sales, auditor | Run the dairy | Yes | All office roles | **NOW (GREEN)** — 26 real destinations + honest `/roadmap` page | Enterprise scope on the same portal (ENTERPRISE) |
| **Platform Administration** | Lacteva staff | Operate the platform | Yes (tenant NULL) | Platform roles | **NOW** | — |
| **Collection App** (Flutter) | Operators, centre managers | Capture at the centre, offline-capable | Yes | COLLECTION_OPERATOR, CENTRE_MANAGER | **NOW (GREEN)** — proven on a real handset | Read-assist capture via connector (V1+, gated) |
| **Driver experience** (same binary, persona-routed) | Drivers | Execute delivery runs | Yes | DRIVER | **NOW (GREEN)** | — |
| **Customer mobile experience** (same binary, `Experience.customer`) | Household customers the dairy opts in | See own deliveries, balance, bills | Yes — a login *speaking for* one customer record | Customer persona | **NOW (shipped, DEMO-012)** — the C3 reconciliation | — |
| **Centre Operations** | Centre managers | Centre readiness/summary | (module of Collection App, not a separate app) | — | **NOW** (as module) | — |
| **Hardware / Centre Connector** (local agent) | The centre's devices | Read-assist from scale/analyzer | Device principal, never a user | — | **NOT BUILT — V1, DISCOVERY-GATED (P0-HW-002)** | V1 after evidence gate |
| **Farmer App** | Milk suppliers | Self-service | Would need farmer identity | — | **NOT BUILT** | **FUTURE OPTION** (commercial need) |
| **Web Outlet Portal** | Outlets/customers on the web | Self-service orders/bills | Would need portal identity | — | **NOT BUILT** | **FUTURE OPTION** |
| **Chilling/BMC · Plant apps** | Future domain staff | V2 domains | Yes (future roles) | — | **NOT BUILT** | **V2 / V2-ENTERPRISE** |
| **Enterprise Integration / API layer (SAP/ERP)** | Enterprise IT | Integrate systems | Service credentials | — | **NOT BUILT** | **ENTERPRISE** |
| **Enterprise SSO** | Enterprise IdP users | SAML/OIDC sign-in | Overlay on global identity | — | **NOT BUILT** | **ENTERPRISE** (recommended tier; TO CONFIRM) |

---

## SECTION 6 — Identity today vs enterprise identity

**Current (NOW, verified GO by the Identity/Enterprise Audit):**
one Lacteva identity per person **within an organization** → `Membership`
(unique per tenant+user; lifecycle, not multi-org) → role grants with
**scope on the grant** (`UserRole.center_id`, NULL = org-wide) → every
application authorizes against the same identity + roles + scope. RLS is
FORCED on `Organization.id`; login rebinds the session to the token's verified
tenant; a foreign resource is a 404. **There are no per-application
credentials — this is the target model, already realised.** Honest caveat from
the audit: identity is tenant-scoped today, so a person working for two
organizations has two user rows — acceptable until a real multi-org customer
exists.

**Future (ENTERPRISE — DO NOT BUILD):**
- **Global identity:** promote `User` to a global identity; `Membership`
  (already present) carries per-org roles; the token carries the *selected*
  org; "RLS stays tenant-safe because a session is always bound to one org at
  a time." Pilot impact: none.
- **Enterprise SSO** (SAML/OIDC against a customer IdP): depends on global
  identity; tier recommendation ENTERPRISE (**TO CONFIRM**). No vendor chosen.
- **Federation / parent groups:** the hybrid model — separate orgs with their
  own RLS + a light group for rollup and SSO.
- **Org-to-org:** only through explicit, consented `TradingRelationship`s and
  one-directional projections — **never widened RLS**.

**Why SSO is not required for the pilot:** the pilot is one organization with
a handful of invited staff; invitation → accept sets the credential; every
shipped app already authorizes against the one identity. The audit's own words:
"All additive. None a defect. **None required for the pilot.**" Building SSO
now would rework identity "before a real multi-org customer exists" — a named
anti-risk (Audit §32.2).

---

## SECTION 7 — Organization hierarchy: canonical examples

**A — Small dairy (the pilot shape, M1):**
`Organization (processor|collector)` → one Workspace → one Branch → **3
Collection Centres** → operators/manager scoped by `center_id`. Subscription:
3 centres. **NOW.**

**B — Large dairy (one legal entity):**
`Organization` → Workspaces as regions → Branches as facilities → **hundreds
of centres**. Needs nothing structural that does not exist; the V2 **scope
descriptor** (`{level: org|region|branch|centre, id}`) widens grant scope
beyond centre-only when the first dairy needs branch scope (**TO CONFIRM
which V1 dairy first needs it** — roadmap §17). **NOW structurally; V2 for
regional scope grants.**

**C — Enterprise group:**
Parent/federation group (light, for rollup + SSO) over **multiple legal
Organizations**, each keeping its own books, users and RLS. Cross-entity
visibility only via consented projections. A milk union that is ONE legal
entity with internal societies = one org with internal hierarchy; independent
societies under a union = separate orgs under a federation group.
**ENTERPRISE — DO NOT BUILD.**

**D — Independent collection centre:**
**The repository does not decide this — TO CONFIRM (§18).** The decision
follows business ownership: a centre *owned/operated by the dairy* is a
Collection Centre under its Branch (decided, NOW). A genuinely independent
collection business keeping its own books could be its own `collector`
Organization selling to a processor (flow M3) — but its commercial
relationship to the buying dairy (org-to-org) is an ENTERPRISE construct not
yet designed. **No assumption is made here.**

---

## SECTION 8 — Milk data ownership

**Three separable things, never conflated:** the **physical milk flow** (who
holds the milk at each hop — varies by M1–M4 and changes at each sale), **data
ownership** (whose books a record belongs to), and **Lacteva tenancy** (which
`Organization.id` the row is isolated under). The dairy may not own the milk
after dispatch and still own its own procurement records.

| Record | System of record / owner | Tenancy | Notes |
|---|---|---|---|
| Farmer master | The dairy (supplier module) | Dairy tenant | The farmer is the *subject*, the dairy the *owner*; export/delete duties per DPDPA-general-governance (not a dairy regulation) |
| Collection transaction | The dairy (milk_collection) | Dairy tenant | Immutable once completed; corrections are adjustments |
| Quality readings | The dairy, with **source attribution** (manual vs device) | Dairy tenant | Provenance is part of the record |
| Rate card | The dairy (pricing) | Dairy tenant | The chart is the dairy's own; Lacteva configures, never invents |
| Parchi / slip | The dairy issues; the farmer holds their copy | Dairy tenant | Numbered, tenant-unique, immutable |
| Settlement | The dairy (settlement) | Dairy tenant | Finalized = immutable |
| Outlet/customer records | The dairy (customer module) | Dairy tenant | The outlet's own business data is not Lacteva's concern |
| Delivery records | The dairy (delivery/logistics) | Dairy tenant | Distribution leg only |
| Billing / receivables | The dairy (billing/payment/receipt) | Dairy tenant | Money is Decimal end-to-end |
| Reports | Derived — the dairy's | Dairy tenant | Projections rebuildable from the log |
| Device records | The dairy (registry); device health is a *reported* fact | Dairy tenant | Assets, never logins |
| Audit records | The platform writes; the dairy reads its own | Dairy tenant (platform machinery cross-tenant via PlatformSessionFactory) | Append-only |

**Future org-to-org rule (decided):** each org remains SoR for *its own*
books; shared data is "a deliberate, minimal, one-directional copy/event bound
to the receiving tenant" — **never one authoritative cross-tenant row, never
widened RLS.**

---

## SECTION 9 — Future chilling / BMC / plant model (nothing built)

Decided shape (Roadmap §12, Audit §11), preserved verbatim:

- **BMC is an ASSET at a location** — a device-registry row (the pattern
  exists: `Device.center_id`, categories, health), never a location.
- **Chilling Centre is a new LOCATION TYPE** (V2): inbound reception, quality,
  batch/lot, storage, dispatch.
- **Plant (V2/ENTERPRISE):** receiving, processing, production batches,
  packaging, inventory, traceability.
- **Location ≠ asset**, always: locations extend the existing
  Workspace → Branch → Centre pattern with new types (chilling/plant/depot);
  assets attach to locations.
- **Procurement transport and distribution transport remain separate legs.**
  The current Driver/DeliveryRun model is distribution-only — "reusing the
  delivery driver model for tanker movement would corrupt both."

**How they connect to the current lifecycle without a rewrite:** collection
today ends at the centre with a completed, priced, receipted transaction. A
future chilling location *receives* what centres dispatched — a new inward
domain consuming the same completed collections (by reference), reconciling
weight/quality at each hop through the procurement-transport domain. Nothing
in the shipped collection lifecycle needs to change: the new domains sit
*after* it in the physical flow and *beside* it in the module map, exactly as
distribution already does. This is the additive path the enterprise audit
verified ("No rewrite is required").

---

## SECTION 10 — Enterprise model

The decided growth path — every step additive, none built before its phase:

**Small dairy** (one org, few centres — NOW) → **multi-centre dairy** (more
centres under branches — NOW structurally) → **regional dairy** (V2 scope
descriptor for region/branch grants; new location types) → **enterprise
dairy** (one legal entity, many regions/plants — V2/ENTERPRISE) →
**multi-organization enterprise group** (hybrid: separate tenants + light
federation group — ENTERPRISE).

Enterprise capabilities, all **ENTERPRISE / not built**: enterprise SSO
(SAML/OIDC, after global identity; no vendor chosen), SAP/ERP integration (no
module names/OData/BAPI/IDoc assumed; master-data SoR **TO CONFIRM**), global
identity (one person → many orgs; only when a real multi-org customer exists),
federation/parent groups, org-to-org trading relationships via consented
projections, enterprise integration/API layer. **RLS is never weakened by any
of these** — a session is always bound to exactly one organization.

---

## SECTION 11 — User growth model (no invented headcounts)

**Five populations, counted separately, growing on different axes:**

1. **Human identities (logins)** — grow with **centres and shifts**, not with
   farmers: per additional centre, typically its operator(s) and (optionally) a
   centre manager; drivers grow with **routes**, not centres.
2. **Centralized staff** — do NOT grow per centre: owner/admin, finance,
   sales, auditor remain a small org-wide group; V2 adds regional managers
   per *region*, not per centre.
3. **Business records** — farmers grow with the supplier base per centre;
   outlets with the delivery book. Records scale freely and cost nothing
   (never billable, never logins).
4. **Devices/assets** — roughly per centre (a blocking `scale`, optional
   analyzer/printer).
5. **Organizations/locations** — one tenant per legal entity; branches/centres
   as the physical network grows.

| Shape | Organizations | Locations | Login pattern (structure, not a promised count) | Centralized | Records |
|---|---|---|---|---|---|
| 1-centre dairy | 1 | 1 branch, 1 centre | owner + operator(s); one person may hold several roles on one identity | The owner may be most of them | That centre's farmers/outlets |
| 5-centre dairy | 1 | 1–2 branches, 5 centres | per-centre operators (+ centre managers as delegated), a few drivers | Small office: manager, finance, sales | 5 centres' worth |
| 50-centre dairy | 1 | regions (workspaces), 50 centres | per-centre staff scale linearly; **V2 regional grants** keep oversight sane | Regional managers per region; office still centralized | Large but still records |
| 500-centre enterprise | Several legal orgs under a **federation group** (ENTERPRISE) | Many regions, plants (V2), depots | Same per-centre pattern per org; global identity + SSO become worth building | Group-level rollup via federation, never widened RLS | Millions of records — still records |

**The invariant:** identities scale with *who operates the software*; records
scale with *the business*; the *billing unit stays the centre* at every size.

---

## SECTION 12 — Onboarding model

The decided lifecycle (P0-PILOT-008 §B, the Onboarding Pack §1 — preserved,
not redefined):

**Organization onboarding** (lead → signed agreement → platform admin creates
the Organization with `country_code` — currency/timezone/languages arrive from
the country registry) → **admin/owner** (invite → accept sets credential) →
**centres/branches** (workspaces → branches → centres, hours, active) →
**users** (invite → accept → grant role at scope; drivers additionally
create-profile → link `/drivers/{id}/user` → assign vehicle/route) → **roles**
(named roles, scope on the grant) → **farmers** (CSV import; duplicates named,
one bad row fails alone) → **outlets/customers** (CSV import, inline standing
orders) → **devices** (registry: `scale` per centre is a blocking readiness
check) → **configuration** (readiness, routes, vehicles, calendar) → **rate
card** (create → matrices per product → bands from the photographed chart →
human review → publish; paisa reconciliation) → **settlement rules** (free
periods) → **pilot** (Day-0 verification + dairy sign-off → 7 days) →
**production** (paid per-centre subscription on continuation).

**Three different kinds of onboarding, never conflated:**
- **LOGIN USER ONBOARDING** — invitation → accept → grant; one identity per
  person, no per-app credential, no self-signup.
- **BUSINESS RECORD IMPORT** — CSV/admin creation; farmers and outlets are
  data, not accounts.
- **DEVICE REGISTRATION** — registry rows (assets); a future connector gets a
  revocable *device principal*, never a user login.

The **pilot onboarding pack** (P0-PILOT-009 request pack + P0-PILOT-008
runbook) remains the operative instrument — this section maps it into the
ecosystem, it does not replace it.

---

## SECTION 13 — Commercial model across ecosystem scale

| Scale | Commercial shape (decided unless marked) |
|---|---|
| Pilot (any size) | `LACTEVA_TRIAL`: 30 days, free, everything on, unlimited centres |
| 1–N centre dairy | `LACTEVA_STANDARD`: **per active collection centre**, monthly; users/records/devices never billable; price **TO CONFIRM** |
| Growing dairy | Expansion = subscribing more centres — no migration, same tenant |
| V1+ options | Add-ons *anticipated, not decided* (**TO CONFIRM**): connector per connected centre, analytics tiers |
| Enterprise | Negotiated annual + minimum commitment (**TO CONFIRM**), implementation/integration fees, SSO, federation across legal entities |
| Never | Per-user pricing (rejected — "teaches login-sharing"); per-litre as primary (rejected); invented prices; a gateway that is not contracted |

---

## SECTION 14 — Application access matrix

AVAILABLE = shipped now · FUTURE = roadmap · ENTERPRISE = enterprise phase ·
N/A = not applicable to that persona.

| Persona | Organization | Login | Admin Portal | Collection App | Driver App | Customer Mobile | Farmer App | Web Outlet Portal | Enterprise/API | Typical roles | Scope |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Owner / org admin | Dairy | YES | **AVAILABLE** | AVAILABLE (if hands-on) | N/A | N/A | N/A | N/A | ENTERPRISE | ORGANIZATION_ADMIN | Org |
| Org manager | Dairy | YES | **AVAILABLE** | AVAILABLE | N/A | N/A | N/A | N/A | ENTERPRISE | Manager | Org |
| Centre manager | Dairy | YES | **AVAILABLE** | **AVAILABLE** | N/A | N/A | N/A | N/A | N/A | CENTRE_MANAGER | Centre |
| Collection operator | Dairy | YES | N/A (calm refusal) | **AVAILABLE** | N/A | N/A | N/A | N/A | N/A | COLLECTION_OPERATOR | Centre |
| Finance | Dairy | YES | **AVAILABLE** | N/A | N/A | N/A | N/A | N/A | N/A | Finance roles | Org |
| Sales officer | Dairy | YES | **AVAILABLE** | N/A | N/A | N/A | N/A | N/A | N/A | SALES_OFFICER | Org |
| Driver | Dairy | YES | N/A (refusal names the app) | N/A | **AVAILABLE** | N/A | N/A | N/A | N/A | DRIVER | Own runs |
| Auditor | Dairy/ext | YES | **AVAILABLE** (read) | N/A | N/A | N/A | N/A | N/A | N/A | AUDITOR | Org read |
| Platform admin | Lacteva | YES | **AVAILABLE** (platform) | N/A | N/A | N/A | N/A | N/A | N/A | Platform | Platform |
| Farmer / supplier | record | NO | N/A | N/A | N/A | N/A | **FUTURE** | N/A | N/A | — | — |
| Household customer | record (+optional login) | OPTIONAL | N/A | N/A | N/A | **AVAILABLE** (opt-in, DEMO-012) | N/A | FUTURE | N/A | Customer persona | Own record |
| Outlet | record | NO | N/A | N/A | N/A | N/A | N/A | **FUTURE** | N/A | — | — |
| Procurement transporter | V2 persona | NO today | N/A | N/A | N/A (distinct leg) | N/A | N/A | N/A | N/A | V2 | V2 |
| Chilling/BMC/plant staff | Dairy (V2) | FUTURE | FUTURE modules | N/A | N/A | N/A | N/A | N/A | V2/ENT | Future roles | Location |
| Enterprise group IT | Group | ENTERPRISE | ENTERPRISE scope | N/A | N/A | N/A | N/A | N/A | **ENTERPRISE** | — | Group |
| Device / connector | asset | NEVER (device principal) | N/A | N/A | N/A | N/A | N/A | N/A | V1 (gated) | — | One centre |

---

## SECTION 15 — Roadmap connection (nothing silently disappears)

| Capability | Phase (canonical) |
|---|---|
| Supplier FAT/SNF deviation flag | **NOW** (the only AI; statistics, not ML) |
| AI beyond the flag / anomaly detection | **V1** (quality/settlement/operator anomalies) |
| Forecasting (collection/demand) | **V2** |
| Advanced analytics | **V1+ → V2** |
| SAP/ERP | **ENTERPRISE** (no vendor/module names assumed) |
| GPS / route intelligence | **FUTURE** — never a pilot dependency |
| Messaging (WhatsApp/SMS send) | **V1** — vendor/DLT-BSP paperwork; email templating exists |
| Hardware connector | **V1 — DISCOVERY-GATED** (P0-HW-002 evidence gate before P0-HW-003) |
| Automated scale capture / analyzers | **V1+** (read-assist, after the gate; manual-first stands) |
| QR scanning | **V1** (rendering a QR is NOW; scanning is not) |
| PDF documents (receipt/invoice) | **V1** (clipboard placeholder today) |
| GST/FSSAI document fields | **V1** |
| Chilling centre | **V2** (a new location type) |
| BMC | **V2** (an asset at a location, via the device registry) |
| Plant/processing | **V2/ENTERPRISE** |
| Procurement transport | **V2** (separate leg, never collapsed) |
| Farmer app | **FUTURE OPTION** |
| Customer **web** outlet portal | **FUTURE OPTION** (mobile household experience is NOW) |
| Enterprise SSO | **ENTERPRISE** (tier TO CONFIRM) |
| Global identity | **ENTERPRISE** |
| Federation / org-to-org | **ENTERPRISE** (consented projections, never widened RLS) |
| Payment gateway | **TO CONFIRM** (none contracted; provider `disabled`, machinery exists) |

---

## SECTION 16 — DO NOT BUILD YET (hard boundary)

Binding on every future session, per the Master Roadmap §16 (quoted) plus this
document's reconciliations. **None of the following may be implemented, mocked,
stubbed with fake data, or presented as available unless the roadmap document
itself is revised to advance it:**

SAP/ERP integration · enterprise SSO · global identity · GPS · farmer app ·
customer/outlet **web** portal · chilling centre · BMC · plant/processing ·
procurement transport · advanced hardware automation · additional hardware
vendors · AI beyond the existing deviation flag · predictive analytics ·
WhatsApp/SMS provider integration · payment gateway · enterprise federation ·
consumer app · **the P0-HW-003 connector before the P0-HW-002 evidence gate**
· global-identity rework before a real multi-org customer.

Enforcement already in place: the executable claims guards
(P0-PRODUCT-VISIBILITY-002) fail the portal/mobile suites if UI copy claims
any of these; the roadmap's Coming-Soon policy permits labels only.

---

## SECTION 17 — Decisions already made (extracted, not recreated)

1. **Tenant = Organization** (`org_type ∈ cooperative|processor|collector|farm|other`); hierarchy Organization → Workspace → Branch → Collection Centre; a centre belongs to one branch for life.
2. **One identity per person, application-specific authorization; no per-application credentials, ever.** Invitation → accept; no self-signup.
3. **Multi-role / multi-centre on one identity** — scope lives on the grant (`UserRole.center_id`); membership unique per (tenant, user).
4. **Organization-scoped RLS, FORCED**; foreign resource = 404; cross-tenant machinery only via `PlatformSessionFactory`; **RLS never weakened for cross-org convenience** — org-to-org is consented projections.
5. **Per-centre subscription** (not per user, not per litre); 30-day non-billable trial; prices in config, absent until decided; no modules sold today; no payment gateway contracted.
6. **Farmers and customers/outlets are business records today** — never billable, never logins-by-existence; the household customer login (speaking for one customer record) is the one shipped, deliberate exception.
7. **Enterprise SSO / global identity / federation are ENTERPRISE-future**; hybrid parent/federation model recommended; build global identity only when a real multi-org customer exists.
8. **BMC is an asset** (device registry); chilling centre/plant/depot are future **location types**; location ≠ asset.
9. **The two transport legs stay distinct** — distribution driver ≠ procurement transporter; never collapse them.
10. **Manual-first hardware**; mock readings refused in production and compiled out of release builds; connector is evidence-gated.
11. **The AI roadmap is preserved** — the deviation flag ships; nothing else exists; no AI vendor.
12. **SAP/ERP is future-enterprise**; never mock module names/protocols.
13. **GPS is never a pilot dependency.**
14. **No compliance module** — government requirements are documents the dairy owns, not a build.
15. **Coming Soon = labels only, never functional-looking UI** — now test-enforced.
16. One portal (scope-driven), one mobile binary (persona-routed); new *modules* before new *apps*.

---

## SECTION 18 — Decisions still required (TO CONFIRM register)

| # | Decision | Owner |
|---|---|---|
| 1 | Pilot dairy's operating model (M1 assumed) and rate-chart shape (drives litres / FAT×SNF work) | Business + dairy |
| 2 | Subscription price per currency; payment gateway/PSP for India | Commercial |
| 3 | Exact enterprise packaging: minimum commitment, implementation fee (waived early?), dedicated environments | Commercial |
| 4 | Org-to-org commercial relationships (who pays when a union buys from collectors on Lacteva) | Commercial + Architecture |
| 5 | Independent chilling-centre / independent collection-centre commercial + tenancy model (§7 D) | Business + Architecture |
| 6 | Farmer-portal business case (FUTURE OPTION trigger) | Commercial |
| 7 | Customer/outlet web-portal business case | Commercial |
| 8 | Enterprise SSO tier (recommend ENTERPRISE) | Product |
| 9 | SAP master-data ownership (which system is SoR for what) | Enterprise engagement |
| 10 | Org-to-org settlement/data-exchange design (TradingRelationship shape) | Architecture (ENTERPRISE) |
| 11 | Module/add-on unbundling and pricing (V1+); which add-on monetises first (recommendation: connector, then analytics) | Commercial |
| 12 | Trial-duration changes (30 days is the code default) | Commercial |
| 13 | Which V1 dairy first needs branch/region scope (triggers the scope descriptor) | Product |
| 14 | Settlement cycle and pilot commercial terms for the first dairy | Business + dairy |
| 15 | Third-party chilling ownership handling in M2/M3 flows | Architecture (V2) |

---

## SECTION 19 — Executive business model

**What is Lacteva?**
Lacteva is a business platform that runs a dairy's daily milk operations end
to end. When a farmer brings milk to a collection centre, Lacteva weighs and
grades it, prices it by the dairy's own rate chart, hands the farmer a numbered
parchi, and reconciles every collection into the farmer's settlement — to the
paisa. The same system runs the selling side: outlets, standing orders,
delivery routes, drivers, invoices and receivables — with the owner watching
the whole business on one dashboard. It works in the office on a browser and at
the centre on an Android phone, including offline. The dairy pays a simple
subscription per collection centre; its farmers and customers are served
without needing apps or accounts; its data stays its own, isolated and audited.
Everything in this paragraph ships today and was proven on a real handset.

**What does Lacteva become?**
The same platform, grown along the milk's own path — none of it built yet, all
of it deliberately designed for: connectors that read the centre's scale and
analyzer instead of hands typing; messages that reach farmers on WhatsApp;
chilling centres and bulk coolers; the tanker leg from centre to plant; plant
production and traceability; analytics and forecasting on the dairy's own
history; and, at enterprise scale, groups of legal dairies under one roof with
single sign-on and ERP integration — each organization keeping its own books
and its own isolation. Lacteva grows by adding domains beside the ones that
work, never by rewriting them — and it never shows a dairy a capability it
does not yet have.

---

## SECTION 20 — Final architecture principles (permanent, binding)

1. **Never confuse a person with an organization** — identities log in; tenants keep books.
2. **Never confuse a location with an asset** — a chilling centre is a place; a BMC is a machine at one.
3. **Never make a business record a login merely because it exists** — a login is for someone who operates the software.
4. **Never create per-application credentials** — one identity, application-specific authorization.
5. **Never weaken RLS for cross-organization convenience** — org-to-org is consented, one-directional projection, always bound to the receiving tenant.
6. **Never collapse procurement transport and distribution transport** — raw milk inward and finished product outward are different domains.
7. **Never make future functionality appear available** — labels only; the claims guards enforce it.
8. **Never invent dairy data, rates, prices, vendors, or regulations** — mark the unknown TO CONFIRM.
9. **Never introduce a vendor (gateway, BSP, IdP, hardware, AI) without an approved decision.**
10. **Scope lives on the grant, not the role** — widen the scope vocabulary, never fork roles per place.
11. **The billing unit is the collection centre** — users, records and devices are never seats.
12. **Prefer additive evolution over rewrite** — new domains sit beside proven ones; new modules before new apps; one portal, one mobile binary, as long as possible.
13. **Code outranks prose; the newest approved roadmap outranks older documents on phasing** — and contradictions get named, not silently patched.
14. **Immutable stays immutable** — completed transactions, published rate cards, finalized settlements, issued parchis; corrections are new versions.
15. **Every production guarantee must be executable** — a claim without a test is an intention, not a property.

---

## Validation

Cross-referenced: Master Product Roadmap (§4, §5, §7, §12, §16, §17), Business
Operating Model (§2–§22, §A, §C), Identity/Enterprise Audit (§2–§15, §28–§34),
Commercial Model & Packaging (§A–§R), P0-PILOT-008 (§B, §E–§G, §P), Onboarding
Pack §1, Capability Visibility Audit, and code
(`organization/models.py`, `collection_center/models.py`,
`identity/models.py`, `authz/models.py`, `operational_readiness/models.py`,
`subscription/plans.py`). Contradictions found: **five, all named in §0** —
none silently fixed. Unresolved points: **fifteen, all in §18 as TO CONFIRM**.
Assumptions are labelled (M1 pilot shape). No production code, schema, API, or
UI was changed.

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Architecture | Canonical dairy ecosystem & operating model: nine-stage value chain (per-stage operator/data-owner/login/phase), twelve organization types reconciled to the code's Organization→Workspace→Branch→Centre model, commercial buyer/basis (per-centre, decided in code), canonical identity table and application family, SSO now-vs-enterprise, four hierarchy examples (independent centre left TO CONFIRM), data-ownership model separating physical flow / data ownership / tenancy, future chilling-BMC-plant shape (BMC = asset), enterprise evolution, scalable user-growth model without invented headcounts, onboarding lifecycle preserving the pilot pack, access matrix, full roadmap reconciliation (21 capabilities, nothing dropped), hard do-not-build list, 16 extracted decisions, 15-item TO CONFIRM register, executive model, 15 permanent principles — and five named contradictions (§0) between governing documents, surfaced rather than silently fixed (P0-BUSINESS-ECOSYSTEM-001). |
