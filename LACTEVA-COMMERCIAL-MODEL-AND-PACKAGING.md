---
id: LACTEVA-COMMERCIAL-MODEL-AND-PACKAGING
title: Commercial Model, Packaging & Unit Economics
type: reference
status: Approved
version: "1.0"
created: 2026-08-18
last-updated: 2026-08-18
owner: Product & Commercial
related: [LACTEVA-MASTER-PRODUCT-ROADMAP, LACTEVA-BUSINESS-OPERATING-MODEL, LACTEVA-IDENTITY-ENTERPRISE-ARCHITECTURE-AUDIT, LACTEVA-GO-LIVE-READINESS, LACTEVA-PILOT-ONBOARDING-PACK, LACTEVA-P0-PILOT-006-DEV-ONBOARDING-REHEARSAL]
baseline: ARCH-BASELINE-V1
---

# Lacteva Commercial Model, Packaging & Unit Economics

**Product/commercial definition only — no code, schema, billing logic, gateway,
or enforcement.** Every current-state claim is grounded in the repository. **No
price is invented as a fact**; where a number is unknown, a model + range +
rationale + decision-owner is given and tagged **TO CONFIRM**. This document
preserves — and does not silently change — the master roadmap.

**Critical grounding (already DECIDED in code, DEMO-026 `subscription/plans.py`):**
the commercial *shape* is set — a **30-day trial**, then **subscription per
collection centre** (explicitly **not per user, not per litre**); **prices are
deliberately absent from source** and read from per-currency config
(`subscription.price.LACTEVA_STANDARD.INR`) "absent until somebody decides";
and **Lacteva does not sell modules today** (a plan's empty capability set means
"everything the platform has"; the `capabilities` field exists to *enable*
future unbundling). Currency comes from the org's country. **No payment gateway
is contracted.** This document builds on those decisions, not over them.

---

## One-page executive commercial model

- **Who pays:** the **dairy business** (the tenant `Organization`) — the
  economic buyer is its owner/management. Farmers, customers/outlets, drivers-
  as-people, and devices are **not** billable users.
- **What they buy:** the Lacteva dairy operations platform — the full lifecycle
  (collection → quality → rate → settlement → parchi → orders → routes →
  delivery → billing → reporting), across **one portal + one mobile binary**,
  priced **per collection centre**.
- **Primary pricing model (DECIDED):** **per active collection centre**,
  monthly, subscription. Rationale: it tracks the value and the cost (a centre
  is where collection, devices, operators and support concentrate), it is
  predictable for a seasonal-volume dairy, it scales cleanly multi-centre, and
  the code already models it (`subscribed_centres`). **Fallback:** hybrid
  (per-centre base + light usage) for very large volumes.
- **Packages:** PILOT (free 30-day trial, everything on) → STARTER (1–2 centres)
  → PROFESSIONAL (few centres) → MULTI-CENTRE (many centres/branches) →
  ENTERPRISE (negotiated, multi-entity + integrations). **Today only TRIAL and
  STANDARD exist in code; the tiers above are packaging of the same STANDARD
  per-centre plan until unbundling is decided.**
- **Add-ons (FUTURE, not sold today):** Hardware Connector, AI/Analytics,
  SAP/ERP, Enterprise SSO, premium support — enabled later via the existing
  `capabilities` seam.
- **Services (one-time, separate from SaaS):** implementation, imports, rate-
  card/settlement configuration, training, data migration, hardware/SAP
  integration.
- **Prices:** **TO CONFIRM (Commercial).** None invented here.

---

## A. Executive summary

Lacteva's commercial architecture is already the right shape and partly in
code: a per-centre subscription with a 30-day trial and country-neutral,
config-driven pricing. This document formalises the segments, packages, the
pricing-model comparison (recommending the already-decided per-centre model
with a hybrid fallback), the pilot→paid lifecycle, the services vs recurring
split, the enterprise model, user + unit economics **frameworks** (formulas,
values TO CONFIRM), the Coming-Soon strategy, and a decision register. **Nothing
is built; no price is asserted; the roadmap is preserved.**

## B. Current commercial state (grounded)

- **Subscription module (GREEN):** `Subscription` (per-tenant), `plan_code`,
  status `trialing → active → grace`, `subscribed_centres` (**per-centre**),
  trial/started/period/grace dates, external customer/subscription/price ids
  for a future PSP, webhook ledger, grace period.
- **Plan catalog (GREEN):** `LACTEVA_TRIAL` (unlimited centres, **not
  billable**, everything on) and `LACTEVA_STANDARD` (per-centre, **billable**);
  prices as config, **absent**; **no modules sold today**.
- **No gateway contracted; no enforcement built.** The commercial *decisions
  made* are the shape (per-centre, 30-day trial, prices-as-config, country-
  neutral, no-modules-yet); the numbers and provider are open.

## C. Target customer segments

| Seg | Name | Operating complexity | Phase |
|---|---|---|---|
| A | Small / local dairy | 1–2 centres, one dairy | **NOW (pilot target)** |
| B | Growing / multi-centre dairy | several centres, one/few branches | V1 |
| C | Dairy processor / larger org | many centres, distribution, finance team | V1/V2 |
| D | Enterprise dairy org | multi-region/multi-plant, integrations, SSO | ENTERPRISE |
| E | Future ecosystem participants (chilling/BMC operators, processors, procurement orgs, logistics operators) | domain-dependent | V2/ENTERPRISE/FUTURE |

**Do not assume every ecosystem participant becomes a paying customer** — many
are represented as records (farmers, outlets) or integrate later (SAP).

## D. Buyer / persona model

| Role | Relationship |
|---|---|
| **Dairy owner / management** | **Primary customer + economic buyer** |
| Org admin/manager, finance, sales, centre manager, operator, driver, auditor | **Operate** the system (users; see §K) |
| **Farmer / supplier** | **Business record** — never a billable user (no login) |
| **Customer / outlet** | **Business record** — never a billable user (no login) |
| Device / hardware | **Asset** — never a user |
| Enterprise HQ / group | **Future buyer** (ENTERPRISE, negotiated) |
| Chilling/BMC/plant/procurement operators | **Future customers** (V2+) |

## E. Product / package architecture

Every package is the **same platform, priced per centre**; higher tiers are
*packaging + services + (future) add-ons*, not different products. Until
unbundling is decided, tiers B–E are commercial framing of the STANDARD plan.

| | **PILOT** | **STARTER** | **PROFESSIONAL** | **MULTI-CENTRE** | **ENTERPRISE** |
|---|---|---|---|---|---|
| Target | evaluating dairy | small dairy | growing dairy | multi-branch dairy | large/enterprise |
| Complexity | any, 30 days | 1–2 centres | ~3–8 centres | many centres/branches | multi-entity/region |
| Applications | Portal + Collection + Driver | same | same | same | same + integrations |
| Capabilities | **everything on** | full lifecycle | full lifecycle | full lifecycle + branch scope | + enterprise (SSO, federation, SAP) |
| Centres | unlimited (trial) | per-centre | per-centre | per-centre (volume) | negotiated |
| Users | unlimited (see §K) | unlimited | unlimited | unlimited | unlimited |
| Transaction limits | none | **none (recommended)** | none | none | none/negotiated |
| Support | best-effort | standard | standard | priority | dedicated / SLA |
| Reporting | full (12 reports) | full | full | full + (future adv.) | + enterprise reporting |
| Integration | none | none | none | none | SAP/ERP, API |
| Hardware | manual-first | manual-first | +Connector (add-on, V1) | +Connector | +Connector |
| AI | deviation flag | deviation flag | +Analytics (add-on, V1+) | +Analytics | +advanced |
| Enterprise | — | — | — | — | SSO, global identity, federation |
| Upgrade path | → any paid tier | → Professional | → Multi-Centre | → Enterprise | negotiated |
| NOT included | — | add-ons, integrations | enterprise features | enterprise SSO/SAP | (bespoke) |

**Phase tags:** PILOT/STARTER/PROFESSIONAL/MULTI-CENTRE = **NOW/V1** (packaging
of STANDARD); ENTERPRISE = **ENTERPRISE**; all add-ons = **V1+/FUTURE**.

## F. Pricing-model comparison

| Model | Predictable (customer) | Predictable (Lacteva) | Multi-centre | Seasonal volume | Enterprise | Cost alignment | Verdict |
|---|---|---|---|---|---|---|---|
| **A. Per organization** | high | low (no growth signal) | poor | fine | poor | weak | too flat |
| **B. Per centre** | **high** | **high** | **excellent** | **stable (centres, not litres)** | good (+negotiation) | **strong** (support/devices concentrate per centre) | **RECOMMENDED (DECIDED)** |
| C. Per active user | medium | medium | ok | fine | ok | weak — **penalises correct use; teaches login-sharing** | rejected (code comment) |
| D. Per transaction / litre | low (seasonal spikes) | volatile | ok | **bad for the dairy** | ok | tracks infra weakly | rejected as primary |
| E. Hybrid (centre + usage) | medium | high | good | medium | good | good | **fallback** for very high volume |
| F. Module-based | medium | high | good | fine | good | good | **future layer on B** (not today) |
| G. Enterprise negotiated | n/a | contract | n/a | n/a | **yes** | contract | **ENTERPRISE only** |

## G. Recommended pricing model

**Primary: per active collection centre, monthly (DECIDED, in code).** It is
the unit where value and cost concentrate (collection, devices, operators,
support), it is predictable for a dairy whose litres swing seasonally, it scales
linearly multi-centre, and it resists login-sharing. **Fallback: hybrid**
(per-centre base + a light usage component) for unusually high-volume centres,
introduced only if per-centre proves misaligned at scale. **Module-based
pricing (F)** layers on top in V1+ via the existing `capabilities` seam. **Actual
per-centre price: TO CONFIRM (Commercial), per currency, in config.**

## H. Pilot → paid lifecycle

```
LEAD → DEMO → PILOT (30-day trial, everything on, FREE) → ONBOARDING
     → PRODUCTION → PAID SUBSCRIPTION (per centre) → EXPANSION (more centres/add-ons) → ENTERPRISE
```
- **Pilot = the existing `LACTEVA_TRIAL`:** 30 days (DECIDED in code),
  everything available, **not billable**. (The 30 days is the code default;
  any change is **TO CONFIRM**.)
- **At completion:** convert to `LACTEVA_STANDARD`; **all data/config survives**
  (same tenant — no migration); billing starts when the paid subscription
  begins (`started_on`), after the trial/grace.
- **Expansion:** add centres (`subscribed_centres`↑) and, later, add-on
  capabilities — no re-onboarding.
- The **real dairy go-live** (business/data/legal gated) is the entry to a paid
  production relationship; **this milestone does not change that gate.**

## I. Implementation / services model (one-time, separate from SaaS)

Charge as **one-time professional services**, distinct from recurring
subscription: initial org setup; farmer import; outlet/customer import;
rate-card configuration; settlement configuration; training; data migration;
hardware integration; SAP/ERP integration; custom integration; enterprise SSO
setup; onsite implementation. **Recommendation:** a modest implementation fee
for STARTER/PROFESSIONAL (or waived to win the first pilots — **TO CONFIRM**),
scaling to a real implementation + integration fee for ENTERPRISE. **Keep
services revenue off the ARR line.**

## J. Enterprise commercial model (ENTERPRISE — do not build)

Negotiated annual contracts with a minimum annual commitment; implementation +
integration fees; enterprise support/SLA; enterprise SSO; multiple legal
entities (the **hybrid parent/federation** model from the Identity + Enterprise
audit — separate orgs keeping their own RLS + a group for rollup/SSO); data
segregation preserved (RLS never weakened); enterprise reporting; dedicated
environments **only if** a customer requires it. **All ENTERPRISE-phase; none
implemented.**

## K. User economics

Grounded in the validated identity model (**one person → one identity →
multiple application capabilities**; do not change):

- **Users are included, not separately billed** — the price is per centre.
- **Operators and drivers do not count as paid seats** — pricing per user would
  teach a dairy to share logins (the exact anti-pattern the code rejects).
- **Read-only auditors:** included.
- **Multiple roles on one identity / a user at multiple centres:** **no extra
  charge** — scope is on the grant; one identity. Charging for it would punish
  correct modeling.
- **Farmer/customer records are NOT billable users** — they have no login.

**Recommendation: do not adopt per-user pricing.** If a future enterprise
demands seat-based commercials, treat it as an ENTERPRISE-negotiated exception,
never the default.

## L. Module / add-on economics (FUTURE — not sold today)

Today plans grant "everything" (no modules). **In V1+**, via the existing
`capabilities` seam, these become sellable add-ons **on top of** the per-centre
base:

| Add-on | Phase | Commercial form |
|---|---|---|
| Hardware Connector | V1 (evidence-gated) | per connected centre |
| AI / Analytics | V1+ | module add-on |
| Advanced Analytics / Forecasting | V2 | module add-on |
| SAP / ERP Integration | ENTERPRISE | integration service + fee |
| Enterprise SSO / Identity | ENTERPRISE | enterprise-only |
| Premium support / SLA | any tier | support tier |

**Flag (roadmap change, explicit):** moving from "everything included" to
"some capabilities are paid add-ons" is a **future commercial decision**, not
today's model. It is *architecturally anticipated* (the `capabilities` field)
but **not decided** — **TO CONFIRM**.

## M. Coming Soon strategy (no fake functionality)

Only **non-interactive roadmap labels** on the existing nav registry — **no fake
screens, APIs, data, buttons, or integrations.**

| Feature | Phase | Package association | Coming Soon label | Dependency |
|---|---|---|---|---|
| AI-powered insights | V1/V2 | add-on | AI Insights — Coming Soon | real data volume |
| Hardware automation | V1 | add-on | Automated Capture — Coming Soon | hardware evidence (P0-HW-002) |
| SAP/ERP integration | ENT | enterprise | SAP/ERP — Enterprise | signed enterprise |
| Enterprise SSO | ENT | enterprise | SSO — Coming Soon | global identity |
| GPS | FUTURE | — | GPS & Tracking — Coming Soon | never a pilot dep. |
| WhatsApp/SMS | V1 | add-on/config | Messaging — Coming Soon | DLT/BSP paperwork |
| Farmer App | FUTURE OPTION | — | Farmer App — Coming Soon | commercial need |
| Customer/Outlet Portal | FUTURE OPTION | — | Customer Portal — Coming Soon | commercial need |
| Chilling / BMC / Plant | V2 | future modules | Coming Soon | V2 domains |
| Advanced Analytics | V1+/V2 | add-on | Coming Soon | data volume |

## N. Unit-economics framework (formulas; values TO CONFIRM)

No internal cost is invented (none in the repo). Model to populate when numbers
exist:

- **ARPU / month** = per-centre price × subscribed centres per customer.
- **ACV** = ARPU × 12 + annualised add-ons.
- **Gross margin** = (ARR − infra − support − messaging/AI-API − storage/backup)
  ÷ ARR.
- **CAC** = (sales + marketing + pre-sales) ÷ new customers.
- **Payback (months)** = CAC ÷ (monthly gross profit per customer).
- **Implementation recovery period** = implementation cost ÷ monthly gross
  profit (or 0 if a fee covers it).
- **Support cost / customer** = support effort × loaded rate ÷ customers.
- **Enterprise contribution** = ENTERPRISE ARR + services − dedicated cost.

**Revenue drivers:** subscription (per centre), centre expansion, add-ons,
implementation, integrations, enterprise services. **Cost drivers:** infra,
support, onboarding/implementation, integrations, hardware support, messaging
providers, AI/API consumption, storage, backups. **All actual figures: TO
CONFIRM (Commercial + Finance).**

## O. Commercial decision register

| Decision | Current state | Recommendation | Why | Owner | Status |
|---|---|---|---|---|---|
| Primary pricing unit | per centre (in code) | **per centre** | value+cost concentrate per centre; anti-sharing | Commercial | **DECIDED** |
| Per-user pricing | rejected (code) | keep rejected | punishes correct use | Commercial | **DECIDED** |
| Per-litre as primary | not used | keep as fallback only | seasonal volatility | Commercial | **DECIDED** |
| Trial | 30 days, free, everything (code) | keep 30-day free trial | evaluation without a wall | Commercial | **DECIDED** (duration change → TO CONFIRM) |
| Modules sold separately | not today (all included) | unbundle in V1+ via capabilities seam | monetise premium later | Product+Commercial | **RECOMMENDED / TO CONFIRM** |
| Actual prices (per currency) | absent (config) | set per-currency in config | country-neutral | Commercial | **TO CONFIRM** |
| Payment gateway | none contracted | select a PSP for India | to bill at all | Commercial+Eng | **TO CONFIRM** |
| Implementation fee | none | modest (or waived early) | services ≠ ARR | Commercial | **TO CONFIRM** |
| Enterprise commercials | none | negotiated annual + services | enterprise reality | Commercial | **FUTURE** |
| Hybrid fallback | not used | ready if per-centre misaligns at scale | very high volume | Commercial | **RECOMMENDED** |

## P. Do-not-build-yet (preserved)

Payment gateway; subscription enforcement; billing-engine changes; enterprise
SSO; global identity; SAP connector; GPS; WhatsApp/SMS provider integration; AI
beyond the existing MVP; farmer login/app; customer portal; chilling/BMC;
plant/processing; hardware connector before its evidence gate; any fake
enterprise/"Coming Soon" functionality. **This milestone changed no code.**

## Q. Dependencies

Paid production ← real dairy go-live (business/data/legal). Billing at all ←
PSP selection + prices in config. Add-on revenue ← the `capabilities`
unbundling decision. Hardware add-on ← P0-HW-002 evidence gate → P0-HW-003.
Enterprise commercials ← global identity + federation (ENTERPRISE). AI add-on ←
real data volume. **GPS and SAP are late and independent; neither gates the
pilot or first paid revenue.**

## R. Open questions

Per-currency prices; PSP for India; whether/when to unbundle modules; trial
duration confirmation; implementation-fee posture for early customers;
minimum enterprise commitment; whether any customer needs a dedicated
environment; which add-on is the first to monetise (recommend Hardware
Connector once its gate opens, then Analytics). **All TO CONFIRM.**

## S. Recommended next commercial milestone

**A pricing + PSP decision workshop** (Commercial + Finance + Eng) to set: the
per-currency STANDARD price in config, a PSP for India, the implementation-fee
posture, and the trial-duration confirmation — the minimum to move a converted
pilot to real billing. **This is a business decision, not an engineering
milestone; no code follows until those numbers exist.** The immediate *product*
objective remains the **real dairy go-live**.

## T. Relationship to the master product roadmap

This document **implements the commercial layer of** `LACTEVA-MASTER-PRODUCT-
ROADMAP.md §14 (commercial roadmap)` and is consistent with it and with the
Identity + Enterprise audit and P0-PILOT-006. **It changes no prior roadmap
decision.** The one item it *advances from "future" to "recommended, pending
confirmation"* is module unbundling in V1+ — flagged explicitly (§L, §O), not
silently changed. All preserved: real dairy go-live as the gate; P0-HW-003
evidence-gated; AI/SAP/GPS/messaging/chilling-BMC-plant/enterprise-SSO/global-
identity/advanced-analytics roadmaps intact; DPDPA remains general data-
governance (not a dairy regulation, not a feature) per the regulatory audit —
**no new regulatory requirement is invented here.**

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Commercial | Commercial model & packaging: segments, buyer model, package hierarchy, pricing-model comparison (per-centre recommended, matching the in-code decision), pilot→paid lifecycle, services model, enterprise model, user + unit economics frameworks, add-on economics, Coming-Soon strategy, decision register, dependencies. Definition only — no code, no invented prices; roadmap preserved (P0-PRODUCT-007). |
