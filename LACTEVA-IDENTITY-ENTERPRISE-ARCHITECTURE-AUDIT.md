---
id: LACTEVA-IDENTITY-ENTERPRISE-ARCHITECTURE-AUDIT
title: Identity & Enterprise Organization Architecture Audit + Master Roadmap
type: reference
status: Approved
version: "1.0"
owner: Product & Platform Engineering
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-BUSINESS-OPERATING-MODEL, LACTEVA-PILOT-MASTER-ROADMAP, LACTEVA-PRODUCT-GAP-REVIEW, LACTEVA-GO-LIVE-READINESS, LACTEVA-REGULATORY-APPLICABILITY-AUDIT, ARCHITECTURE_BASELINE_V1]
baseline: ARCH-BASELINE-V1
---

# Identity & Enterprise Organization Architecture Audit + Master Roadmap

**Audit + definition only — no code, schema, migration, or production change.**
Every claim below is grounded in the repository; the Business Operating Model
is the target. Unknowns are tagged. Tag taxonomy: **GREEN** (exists/proven) ·
**CONFIG** (dairy-specific configuration) · **NEXT** (immediate engineering) ·
**V1 · V2 · ENTERPRISE · FUTURE OPTION · COMING SOON · NOT REQUIRED ·
UNKNOWN/TO CONFIRM**.

---

## 1. Executive verdict

**GO.** The existing identity, organization, membership, role, scope, and
tenant-isolation architecture is sound, and it **can evolve into the enterprise
target without a rewrite.** The core is already the target's centre:
multi-role / multi-location *within one organization* is already supported
(scoped role grants); RBAC is registry-driven; RLS is FORCED on the tenant.
The three enterprise gaps are **bounded, additive increments, not defects**:
(1) *global identity* (one person → many orgs — today identity is
tenant-scoped by deliberate baseline decision); (2) a *generalised
organizational scope* (region/branch, today centre-only); (3) an
*organization-to-organization relationship* domain (today none — correctly).
**No GENUINE CURRENT DEFECT was found.** No previous roadmap item is lost;
all — AI, SAP, GPS, messaging, hardware, chilling, plant, procurement
transport, farmer/customer portals, enterprise SSO — remain explicitly tracked
in the master roadmap (§23).

## 2. Existing identity architecture — GREEN (tenant-scoped)

- `User` (identity module): `tenant_id` (nullable for platform-level), email,
  password hash, name, locale, timezone, active flag, optional `customer_id`.
- **Identity is tenant-scoped**: one `User` row per tenant (ARCH baseline
  §1.5). A person who works for two organizations today has **two user rows**.
- Auth: login rebinds RLS to the token's verified tenant; membership must be
  active; the token carries `tenant_id` + roles. Password reset + invitation
  flows exist; the raw invite token is delivered only via the notification
  channel (SEC-003) — never returned by the API.
- **Assessment:** correct and safe for a single-dairy pilot and for RLS. The
  "one person = one identity across orgs" target (§6) is a future increment,
  not a defect.

## 3. Existing organization architecture — GREEN

- `Organization` (tenant): `org_type` (cooperative | processor | collector |
  farm | other), country, currency, timezone, locales, status, offboarded_at.
- Location hierarchy: `Workspace` → `Branch` → `CollectionCenter` (centre under
  branch). RLS binds all to `Organization.id`.
- **Assessment:** the tenant already distinguishes dairy *types*, and the
  three-level location hierarchy gives headroom for enterprise structure (§12)
  without new top-level concepts today.

## 4. Existing membership model — GREEN (lifecycle, single-org)

- `Membership` unique per `(tenant_id, user_id)`: status (active|suspended),
  joined_at, invited_by. It models **lifecycle and provenance inside one org**,
  explicitly *not* multi-org (baseline §1.5).
- **Assessment:** exactly right for today; it is the natural carrier for the
  future multi-org increment (a global identity gains one membership per org).

## 5. Existing RBAC / RLS — GREEN

- **RBAC**: permission registry (`<module>.<entity>.<action>`), 10 named roles
  (ORGANIZATION_ADMIN, ORGANIZATION_MANAGER, CENTRE_MANAGER,
  COLLECTION_OPERATOR, FINANCE_MANAGER, FINANCE_OFFICER, SALES_OFFICER, DRIVER,
  AUDITOR, PLATFORM_SUPER_ADMIN), `require_permission()` at the composition
  root, registry-first discipline.
- **Scope on the grant**: `UserRole` carries an optional `center_id` — NULL =
  org-wide, non-null = narrowed to one centre. **Scope lives on the grant, not
  the role**, so the same role is grantable at different centres. `center_scope`
  computes the reachable centre set; org-wide (NULL) short-circuits.
- **RLS**: PostgreSQL row-level security FORCED on `Organization.id`; a foreign
  resource is a 404 (verified live). Application filters are defence-in-depth.
- **Assessment:** the scope-on-grant design is the correct foundation; it is
  **centre-only today** and generalises to region/branch when those exist (§9).

## 6. Existing application-access model — GREEN (one identity, app-specific authz)

Portal (Next.js), Collection App and Driver App (one Flutter binary,
persona-routed), and Platform Admin **all authorise against the same identity +
roles + scope**. The portal shell's `entryFor`/`visibleTo` gate and the
mobile `experienceFor` both read the user's permissions from the same token —
a driver is refused the office portal and routed to the run app; an operator
gets the capture wizard. **There are no per-application credentials.** This is
the target model, already realised.

## 7. Multi-organization user analysis — GAP (ENTERPRISE increment, not a defect)

- **Today:** not supported — identity is tenant-scoped; one person in orgs A
  and B = two user rows, two logins.
- **Target:** ONE PERSON = ONE LACTEVA IDENTITY → memberships in A, B, C
  (auditor, consultant, enterprise employee, transporter manager).
- **Recommended increment (ENTERPRISE, do not build):** promote `User` to a
  **global identity** (drop the hard `tenant_id` binding to identity; keep it as
  "home/primary" at most) and let `Membership` (which already exists, one per
  org) carry the per-org roles and the active org context. The token then
  carries the *selected* org; RLS binds to that org exactly as today. **RLS
  stays tenant-safe** because a session is always bound to one org at a time —
  never a cross-tenant query. This is bounded: Membership and per-tenant roles
  already exist; the change is identity-global + an org-switch at auth.
- **Pilot impact:** none — a single dairy needs only single-org identities.

## 8. Multi-role / multi-location user analysis — GREEN within one org

- **Today:** a person can hold **multiple role grants** in one org, each with
  its own `center_id` scope — e.g. Manager at Centre A *and* Centre B, or
  Manager + a second role. Already supported and proven by the scope design.
- **Gap:** scope is **centre-only**. Region/branch scope arrives with those
  levels (§9). No change needed for the pilot.

## 9. Multi-location scope model — recommendation (V2)

The simplest model that scales: **keep scope on the grant; widen its vocabulary
from `center_id` to a small scope descriptor** — `{level: org|region|branch|
centre, id}` — so one grant can mean "all centres in Branch X" or "Region Y".
A person over several branches gets one grant per branch (or one region grant),
exactly as multiple centre grants work today. **Do NOT** invent a general
condition language. **V2**, gated on region/branch actually existing as
operational levels. **ASSUMPTION:** a scope descriptor beats both a single
`center_id` and a full policy engine.

## 10. Organization-to-organization relationship analysis — FUTURE domain (do not build)

The mandatory new check. Today: **no org-to-org relationship is modeled**, and
that is correct — the pilot is one dairy.

Answers to the ten questions, as an *architecture recommendation only*:

1. **Can two independent orgs interact safely?** Only through an *explicit,
   consented relationship* — never by widening RLS. Each org's records stay in
   its own tenant.
2. **Supplier/buyer representation:** a future `TradingRelationship` entity
   (org A ↔ org B, type: supplies-to | sells-to | transports-for), living as a
   controlled, bilaterally-acknowledged link — not a shared table.
3. **Milk ownership at each hop:** a transfer/movement carries an *owner org*
   and a *counterparty org*; ownership changes at the agreed hop (e.g. society
   → union at reception). This is the reconciliation boundary (§ procurement
   transport).
4. **Who operates the location:** the operating org (has the users/devices).
5. **Who owns the location:** an attribute of the location, possibly a
   different org (a union-owned chilling centre operated by a society).
6. **System of record:** each org is SoR for *its own* books; a shared movement
   is recorded on *both* sides and reconciled — never one authoritative
   cross-tenant row.
7. **Cross-boundary permissions:** a relationship grants a *narrow, explicit*
   view (e.g. "Union B may see the dispatch manifests Society A sent it"),
   implemented as a consented projection/event, not a cross-tenant query.
8. **Can a user see only authorised relationship data?** Yes — the projection
   is scoped to the relationship and the user's role in *their* org.
9. **Can RLS stay tenant-safe?** Yes — because nothing widens RLS; shared data
   is a deliberate, minimal, one-directional copy/event bound to the receiving
   tenant.
10. **Minimal future domain:** `TradingRelationship` + a **milk-movement /
    dispatch-manifest exchange** over the existing event bus, with per-
    relationship consent. **ENTERPRISE/FUTURE. DO NOT BUILD.**

## 11. Location vs asset analysis — GREEN foundation, correct distinction

- **A Chilling Centre is a LOCATION; a BMC is an ASSET at that location.** Do
  not model BMC as a location.
- **Today:** the device registry (`Device`: scale | milk_analyzer | printer |
  qr_scanner | rfid_reader | camera, with `center_id`, status, health) already
  models **assets at a location** with provenance and the production-refused
  mock seam. A BMC, analyzer, scale, printer, temperature sensor at a chilling
  centre would be **device rows under that location** — the pattern exists.
- **Assessment:** when the chilling-centre *location type* arrives (V2), assets
  attach via the existing registry. No premature modeling. GREEN foundation.

## 12. Enterprise hierarchy analysis — additive

Current: Platform → Organization → Workspace → Branch → Centre. Target adds
*location types* (chilling, BMC-as-asset, plant, depot) under the same
pattern, and — for genuine multi-legal-entity groups — the parent/federation
question (§ below). **No new top-level concept is required for a single dairy.**

### Parent organization vs tenant (mandatory §5 check)

Three models compared:

| Model | Security/RLS | Billing | Identity | Data ownership | Reporting | SSO |
|---|---|---|---|---|---|---|
| **A. One org, internal hierarchy** | one tenant, simple RLS | one subscription | single-org identities | one SoR | trivial rollup | one IdP |
| **B. Many orgs + relationships** | tenant-safe, isolated | per-org | needs global identity (§7) | per-org SoR | cross-org rollup needs projection | federated |
| **C. Hybrid** | isolated tenants + a light parent group | per-org, group invoice option | global identity + memberships | per-org SoR, group reads via projection | group dashboard over consented projections | group SSO over member orgs |

**Recommendation: C (hybrid).** One `Organization` per *legally/operationally
distinct entity that keeps its own books, users and RLS*; a lightweight
**parent/federation grouping** for enterprise reporting rollup and SSO; and
**internal hierarchy (region/branch) within a single legal entity's own org**.
So: a milk union that is one legal entity with internal societies = **one org
with internal hierarchy**; independent societies each keeping their own books
under a union = **separate orgs under a federation group** (model B mechanics),
reconciled via §10. **ENTERPRISE/FUTURE. DO NOT BUILD.**

## 13. Onboarding analysis — GREEN mechanics

Enterprise, employee, driver onboarding flows all exist and are proven
(P0-PILOT-004: driver end-to-end; imports live). Farmers and customers/outlets
are **imported/created by the dairy, no login today**; self-service portals are
FUTURE OPTIONs. Full flows are in LACTEVA-PILOT-ONBOARDING-PACK and the
Business Operating Model §17–21. The gate is the dairy's data + signatures, not
software.

## 14. SSO analysis — ENTERPRISE target-state (do not build)

Identity is already centralised in one module behind `deps.py`. Target: one
Lacteva identity + centralized auth + app-specific authz (already true), plus
**enterprise customers using their own IdP** (SAML/OIDC) so their staff sign in
via corporate SSO. Depends on the global-identity increment (§7). **Decision
required (§31):** V1 or ENTERPRISE? (Recommend ENTERPRISE.) **DO NOT BUILD.**

## 15. Security / RLS implications

- Every enterprise increment **preserves RLS**: a session is always bound to
  exactly one org; global identity changes *who* can hold a session, never
  *widens* a session's reach. Org-to-org sharing is explicit consented
  projection, never a cross-tenant read.
- Scope generalisation (§9) is defence-in-depth on top of RLS, not a
  replacement.
- **No security regression is implied by any recommended increment.**

## 16. Current architecture vs target

| Target | Existing | Gap |
|---|---|---|
| One identity, app-specific authz (within org) | GREEN | — |
| Multi-role / multi-location in one org | GREEN (scoped grants) | scope vocabulary (V2) |
| Global identity (one person, many orgs) | tenant-scoped identity | **ENTERPRISE increment (§7)** |
| Org hierarchy (region/branch/centre) | Workspace/Branch/Centre | region rename + scope (V2) |
| Location types (chilling/plant/BMC/depot) | centre only | **V2 domains** |
| Assets at a location | device registry | none (attach on new location types) |
| Org-to-org relationships | none | **ENTERPRISE domain (§10)** |
| Parent/federation | flat tenant | **ENTERPRISE (hybrid, §12)** |
| Enterprise SSO | centralized identity | **ENTERPRISE (§14)** |
| RBAC / RLS | GREEN | scope generalisation only |

## 17. Required architectural gaps (summary)

1. Global identity + org switch (ENTERPRISE) — §7.
2. Scope descriptor generalisation (V2) — §9.
3. New location types + assets (V2) — §11, §12.
4. Org-to-org relationship domain (ENTERPRISE) — §10.
5. Parent/federation grouping (ENTERPRISE, hybrid) — §12.
6. Enterprise SSO (ENTERPRISE) — §14.

**All additive. None a defect. None required for the pilot.**

## 18. What must change NOW
**Nothing architectural.** The pilot runs on the current identity/org model.
The only NOW items are the dairy's data + signatures + the production
backup-retention config (go-live readiness). **No code.**

## 19. What can wait until V1
Scope descriptor groundwork *if* a V1 dairy needs branch-level managers;
otherwise V1 is the commercial set (advances/loans, FSSAI/GST document fields,
SMTP, first messaging vendor, supplier-trend analytics, host hardening) — none
identity-architectural.

## 20. What belongs to V2
Scope generalisation; chilling-centre + BMC (location + assets); plant/
processing domain; procurement-transport domain (distinct from distribution);
advanced analytics.

## 21. What belongs to ENTERPRISE
Global identity (§7); org-to-org relationships (§10); parent/federation (§12);
enterprise SSO (§14); multi-region/multi-plant hierarchy; SAP/ERP; enterprise
API layer; enterprise dashboards/audit; advanced AI.

## 22. What must NOT be built (see §32 for the canonical list)
Enterprise SSO; SAP/ERP; GPS; WhatsApp/SMS providers; farmer app; customer/
outlet portal; chilling/BMC; plant/processing; procurement transport;
enterprise multi-region hierarchy; advanced AI beyond the existing MVP;
compliance module; hardware connector before the discovery gate; global-identity
rework before a multi-org customer exists.

## 23. Master Lacteva roadmap (nothing lost)

**NOW / CURRENT (GREEN + CONFIG):** procurement; collection centres;
farmers/suppliers; quality; rate cards; parchi; settlement; customers; orders;
routes; vehicles; drivers; delivery; billing; reporting; audit; RBAC/RLS;
offline collection; mobile apps (both personas, on glass); admin portal;
subscription/SaaS foundation; device registry; backup/restore; supplier FAT/SNF
deviation AI flag. Config: rate chart, farmer/outlet lists, settlement cycle.

**NEXT / V1:** hardware connector MVP (P0-HW-002, after discovery gate);
production hardening; SMTP; advances/loans; supplier trend analytics; quality
anomaly detection; settlement anomaly detection; operator anomaly detection;
FSSAI/GST document fields; first messaging provider; outlet-model refinement;
commercial hardening.

**V2:** chilling centre; BMC operations; milk reception; temperature; milk
movement; **procurement transport**; tanker operations; weight/quality
reconciliation; procurement transporter persona; advanced analytics; scope
generalisation.

**V2 / ENTERPRISE:** dairy plant; processing; production batches; raw/finished
inventory; plant quality; batch traceability; finished goods.

**ENTERPRISE:** multi-region; multi-business-unit; multi-plant; advanced org
scopes; **organization-to-organization relationships**; **global identity**;
**parent/federation**; enterprise dashboards; enterprise audit; **enterprise
SSO**; SAP/ERP integration; enterprise API/integration layer; advanced AI;
GPS/tracking; enterprise messaging.

**FUTURE OPTIONAL:** farmer app; customer portal; outlet portal; demand
forecasting; procurement forecasting; route optimization; enterprise decision
support.

## 24. Product "Coming Soon" strategy — recommendation (do not build now)

Navigation should aid discovery without faking function. Recommended pattern
(a **future** feature-flag / module-availability capability — the nav registry
that already drives the portal shell's access gate is the natural home):

- **Live modules:** Collection · Procurement · Distribution · Finance ·
  Reporting.
- **Coming Soon (non-interactive labels only, no fake screens/APIs/buttons):**
  Chilling — Coming Soon · Plant — Coming Soon · Procurement Transport —
  Coming Soon · AI Insights — Coming Soon · GPS & Tracking — Coming Soon ·
  SAP/ERP — Enterprise · Farmer App — Coming Soon · Customer Portal —
  Coming Soon · Enterprise SSO — Coming Soon.

**Rules:** never a functional-looking screen, never a fake API, never a button
that appears to work, never "implemented." Show a future module only where it
improves discovery and does not confuse pilot users. **Implement later as a
module-availability flag on the existing nav registry.** COMING SOON.

## 25. AI roadmap
**Current (GREEN):** supplier FAT/SNF deviation flag. **V1 (existing data, no
vendor):** supplier trend analysis; collection quality alerts; settlement
anomaly; operator anomaly. **V2:** demand/procurement forecasting; route
optimization (needs GPS). **ENTERPRISE:** plant/inventory intelligence;
enterprise decision support. Do not build; do not invent vendors.

## 26. SAP / ERP roadmap
**ENTERPRISE.** Boundaries only: finance, accounting, inventory, procurement,
sales, customer master, supplier master, settlement, billing; direction and
middleware per-customer; master-data system-of-record is a business decision.
Do not build, do not mock, do not invent OData/BAPI/IDoc for a specific
customer.

## 27. GPS / messaging roadmap
**GPS (FUTURE):** driver location, vehicle tracking, route adherence, ETA,
geofencing, and *both* transport legs — **never a pilot blocker.** **Messaging
(V1, paperwork-led):** WhatsApp (BSP), SMS (DLT), email (SMTP — config-only,
adapter exists). Vendor-less adapters already exist; do not implement providers
now.

## 28. User / persona roadmap
**GREEN today:** Organization Admin/Manager, Centre Manager, Collection
Operator, Finance Manager/Officer, Sales/Distribution Officer, Driver, Auditor,
Platform Admin. **FUTURE personas:** Enterprise Owner, Regional Manager,
Procurement Manager, Quality Manager, Chilling-Centre Manager, Plant Manager,
Plant Operator, Procurement Transporter, Enterprise Integration Admin,
Enterprise SSO Admin. **FUTURE OPTION (no login until commercially justified):**
Farmer, Customer, Outlet. **Rule: no login merely because an entity exists.**

## 29. Application roadmap
**GREEN:** Enterprise/Admin Portal; Collection App; Driver App; Platform Admin
— all one-identity, authz-driven. **NEXT:** Hardware Connector (gated).
**V2/ENTERPRISE/FUTURE:** Chilling-Centre app; Procurement-Transport app; Plant
Operations; Farmer App; Customer/Outlet Portal; Enterprise Integration/API
layer. All authorise from identity + org + role + scope — **no per-app
credentials, ever.**

## 30. Commercial roadmap (no prices invented)
**Foundation exists** (subscription module: plan_code, trial, per-centre
payment, webhook ledger, grace). **Pilot:** simple/subsidised. **V1:**
per-location + module-based + optional per-user. **ENTERPRISE:** multi-site +
integrations + analytics + AI + SAP + enterprise support. **Levers:** org
subscription, location, user seats, modules, transaction volume, hardware
connector, AI/analytics, SAP, implementation, support/AMC.

## 31. Open business decisions
Pilot commercial terms; SSO tier (V1 vs ENTERPRISE — recommend ENTERPRISE);
pricing-model mix; master-data system-of-record for the SAP era; whether the
pilot dairy runs model M1 (assumed); the farmer-app commercial trigger; when a
V1 dairy first needs branch-level scope; whether multi-org grouping is federation
(separate orgs) or internal hierarchy for the first enterprise customer.

## 32. Architectural risks
1. **Merging procurement transport into the distribution driver** — keep
   separate domains (Business Model §11).
2. **Reworking identity to global too early** — do it only when a real
   multi-org customer exists; premature change adds risk with no pilot payoff.
3. **Per-app credential creep** — resist; one identity, app-specific authz.
4. **Modeling BMC as a location** — it is an asset; attach via the device
   registry.
5. **Widening RLS for org-to-org** — never; use consented projections/events.
6. **Compliance-module temptation** — the dairy is the regulated entity.
7. **Fake "Coming Soon" screens** — labels only, never functional-looking UI.

## 33. Recommended next milestone
**None is engineering.** The immediate business objective remains the **real
dairy go-live** (gated on the dairy's four artifacts + signatures, per
LACTEVA-GO-LIVE-READINESS). The next *engineering* milestone remains **P0-HW-002
Connector MVP**, gated on the hardware discovery visit. The identity/enterprise
increments in this audit are **ENTERPRISE/V2** and are triggered by a real
multi-org or multi-location customer — not now.

## 34. Final go / no-go verdict
**GO.** The existing Lacteva identity + enterprise organization architecture is
correct, secure (RLS FORCED, tenant-safe), and **evolvable into the full
enterprise target without a rewrite**. No genuine current defect. Every future
capability — AI, SAP, GPS, messaging, hardware, chilling, plant, procurement
transport, farmer/customer portals, enterprise SSO, global identity,
org-to-org, parent/federation — is explicitly tracked and bounded. **Nothing to
build in this milestone.**

---

## A. Decisions we have already made
Tenant = Organization (org_type); Workspace/Branch/Centre hierarchy; RLS on
Organization.id; registry-first RBAC; **scope on the grant** (multi-role /
multi-location within an org); **one identity per person, app-specific
authorization** (within an org today); device registry models assets at a
location; distribution driver ≠ procurement transporter; hybrid parent/tenant
model recommended for enterprise; global identity + org-to-org are bounded
ENTERPRISE increments; no compliance module; no fake "Coming Soon" screens.

## B. Decisions still required from us
SSO tier; pricing mix; master-data SoR for SAP; federation-vs-internal-hierarchy
for the first enterprise group; the farmer/customer-portal commercial triggers;
when branch-level scope is first needed.

## C. Architectural risks
See §32 — headline: keep the two transport domains separate, don't globalise
identity early, don't widen RLS for org-to-org, don't fake future UI.

## D. Recommended next milestone
The dairy go-live (business-gated) and, for engineering, P0-HW-002 (discovery-
gated). No identity/enterprise code in the near term.

## E. Can the existing architecture evolve into the target?
**Yes, without a rewrite.** Multi-role/multi-location is already there; global
identity, scope generalisation, new location types, org-to-org relationships,
parent/federation, and SSO are additive increments bounded by the existing
modular-monolith seams and the Membership/UserRole/scope model already in code.

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Platform Engineering | Identity + enterprise org architecture audit (grounded in code: tenant-scoped identity, scoped role grants, RLS) + master roadmap preserving every future item; recommendations for global identity, scope generalisation, org-to-org relationships, hybrid parent/federation, SSO — all ENTERPRISE/V2, no code. No genuine defect found; GO verdict. |
