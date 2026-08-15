---
id: DEMO-024-COMPETITIVE-REVIEW
title: DEMO-024 — Lacteva Product Capability & Competitive Review
type: reference
status: Approved
version: "1.0"
owner: Platform Engineering
created: 2026-08-15
last-updated: 2026-08-15
related: [DEMO-023-FINAL, DEMO-022-FINAL, DEMO-021-FINAL, CON-0001]
baseline: ARCH-BASELINE-V1
---

# DEMO-024 — Lacteva Product Capability & Competitive Review

**Research milestone. No code was written, no migration created, nothing
deployed.**

---

## A note on evidence

Three kinds of claim appear below and they are not interchangeable:

* **[REPO]** — verified by reading this repository. Tables, endpoints, modules
  and code comments were inspected directly, not recalled.
* **[PUBLIC]** — stated on a vendor's own website or a published specification,
  cited inline.
* **[INFERRED]** — my reasoning from business model or market structure. Not a
  fact. Marked wherever it appears.

**No claim is made about the internal software of Amul, Mother Dairy, Nandini,
Hatsun or any other dairy company.** Their systems are not public. They appear
here only as evidence of *operational shape and scale*, which is public.

---

## 1. Executive Summary

**Lacteva is an unusually well-built platform that cannot yet be sold.**

The engineering foundation is genuinely strong and, in places, better than what
the Indian market currently ships: 70 tables, 203 documented API operations,
65 tables under forced row-level security proven on real PostgreSQL, an
event outbox with idempotent consumers, `Decimal` money end to end, immutable
financial documents, point-in-time recovery proven by restore, and a
business-date model that is correct across timezones in a way most competitors
demonstrably are not. **[REPO]**

Four things block commercial launch, and none of them is architectural:

1. **Nothing is actually sent to anyone.** The notification module has one
   adapter — `LoggingNotifier` — and a code TODO for real SMS and email. **[REPO]**
   Meanwhile every Indian competitor surveyed leads with *WhatsApp bills and
   settlement slips*. **[PUBLIC]**
2. **Lacteva cannot charge a customer.** There is no plan, entitlement, trial,
   metering or subscription table anywhere. **[REPO]**
3. **The farmer money story is half-built.** Settlement deductions, bonuses,
   penalties and tax are an explicit placeholder in the code — "always 0". **[REPO]**
   Farmer advances and their recovery are a headline feature for competitors. **[PUBLIC]**
4. **There is no route.** No route, vehicle or driver table exists. **[REPO]**
   Competitors advertise route planning, truck sheets and load/unload as core. **[PUBLIC]**

The strategic risk is different from the usual one. Lacteva is not
under-engineered; it is **over-engineered relative to its commercial surface**.
The next phase should add almost no new architecture and a great deal of
market-facing capability.

**Recommended positioning: a multi-country dairy *operations* platform for the
farmer→dairy→customer chain — not a dairy ERP.** Reasoning in §16.

---

## 2. Existing Lacteva Capability Matrix

All statuses verified against the repository. Full detail, with priority and
phase, is in `DEMO-024-FEATURE-MATRIX.csv`.

### Bounded contexts present **[REPO]**

`audit`, `auth`, `authz`, `billing`, `business_calendar`, `collection_center`,
`configuration`, `customer`, `delivery`, `event_relay`, `identity`,
`milk_collection`, `notification`, `operational_readiness`, `organization`,
`payment`, `pricing`, `receipt`, `reporting`, `settlement`, `supplier`, `sync`
— 22 modules, 70 tables, 203 API operations.

### Summary by area

| Area | Status | Evidence |
|---|---|---|
| Tenancy, users, roles, RLS | **EXISTS** | 65 tables forced; proven on PostgreSQL |
| Farmer/supplier records | **EXISTS** | profile, bank accounts, documents, centre assignment |
| Milk collection + quality | **EXISTS** | fat/snf/clr; `quality_dimension` registry — dimensions are data, not code |
| Quality-based pricing | **EXISTS** | rate cards + pricing matrices + resolution/calculator |
| Settlements & farmer payments | **EXISTS** | immutable once finalized; sequential numbering |
| **Deductions/bonuses/penalties/tax** | **MISSING** | code comment: *"Placeholder until the bonus/penalty/tax engines land — always 0"* |
| **Farmer advances / loan recovery** | **MISSING** | no table, no concept |
| **Farmer ledger / passbook view** | **PARTIAL** | settlements exist; a running opening/closing ledger does not |
| Customers, subscriptions, delivery plans | **EXISTS** | weekday mask, per-day quantity overrides, pause window |
| Automatic delivery generation | **EXISTS** | per-tenant background loop on the tenant's own clock; idempotent |
| Holiday-aware scheduling | **EXISTS** | DEMO-022; one resolver |
| **Routes, vehicles, drivers** | **MISSING** | no such table exists |
| **Crates/bottles, load/unload** | **MISSING** | a real cash-control gap |
| Billing, invoices, payments, receipts, receivables | **EXISTS** | statement reconciles to `opening + billed − paid = closing` |
| Financial periods / close | **EXISTS** | closed periods refuse writes |
| **Products / inventory** | **PARTIAL/MISSING** | `product` is a free string (`RAW-COW-MILK`) |
| Reports, CSV, dashboards | **EXISTS** | 13 report endpoints; business-date correct |
| **SMS / email / WhatsApp** | **PARTIAL/MISSING** | `LoggingNotifier` only |
| Mobile field app + offline sync | **EXISTS** | Flutter; `sync_operation` queue with replay |
| Localization | **EXISTS (3 languages)** | en/hi/ar with call-site tests |
| Currency, timezone, calendar | **EXISTS** | per-organization; hierarchy documented in CON-0001 |
| Audit, backup, PITR, DR | **EXISTS** | restore into a fresh database proven |
| Device registry | **EXISTS** | `device`, health reports, categories |
| **Real hardware drivers** | **PARTIAL** | `MockScaleAdapter` / `MockAnalyzerAdapter` only |
| **AMCU / DPU integration** | **MISSING** | the dominant Indian collection pattern |
| **SaaS subscription billing** | **MISSING** | cannot charge anyone |
| **Self-service onboarding/trial** | **PARTIAL** | org creation exists; no guided signup |
| AI | **FUTURE** | nothing, correctly |

### Foundation versus production-ready

This distinction matters more than the status column.

**Production-ready** (executed and proven, not merely present): tenancy and
RLS, collection, pricing, settlement, payment, receipt, billing, delivery
generation, business dates, backup/restore, deployment. These have been driven
end to end against real PostgreSQL and against production.

**Foundation only** (present, shaped correctly, not yet load-bearing):
notification delivery, hardware adapters, device→collection linkage, the
customer-facing mobile surface, and the public-API story (documented, but no
keys, webhooks or partner access).

---

## 3. Dairy Industry Workflow

The lifecycle, with Lacteva's coverage marked. **[REPO]** for coverage;
workflow shape is standard industry practice **[PUBLIC/INFERRED]**.

```
FARMER                          ✅ supplier + profile
  ↓
FARMER ONBOARDING               ✅ registration, documents, bank, centre
  ↓
COLLECTION CENTRE               ✅ centres, operating hours, readiness
  ↓
MILK COLLECTION                 ✅ sessions, guided capture, offline
  ↓
QUALITY TEST                    ✅ fat / snf / clr, dimension registry
  ↓                             ⚠️  manual entry; no analyzer driver
FAT/SNF PARAMETERS              ✅ stored, priced from
  ↓
PROCUREMENT PRICE               ✅ rate cards + matrices (strong)
  ↓
FARMER LEDGER                   ⚠️  settlements yes; running passbook no
  ↓                             ❌ advances, deductions, bonuses
PAYMENT                         ✅ full lifecycle + receipts
  ↓
CHILLING CENTRE / BMC           ❌ not modelled
  ↓
PROCESSING                      ❌ not modelled (deliberately)
  ↓
INVENTORY                       ❌ not modelled
  ↓
DISTRIBUTION                    ⚠️  deliveries yes; routes no
  ↓
CUSTOMER / RETAILER             ✅ customers, plans, subscriptions
  ↓
DELIVERY                        ✅ generation + recording + report
  ↓
BILLING                         ✅ period invoices
  ↓
PAYMENT                         ✅ + allocation to invoices
  ↓                             ❌ no UPI / gateway
SETTLEMENT                      ✅ supplier side
  ↓
REPORTING                       ✅ 13 endpoints + CSV
```

**Lacteva covers the two ends and not the middle.** It is strong from farmer to
farmer-payment, and strong from customer to customer-payment. It does not model
what happens *between* collection and delivery — chilling, processing,
inventory, routing. For a milk *trading and distribution* business that middle
is thin and Lacteva already fits. For a *processing* dairy it is a real gap,
and one I recommend against closing (§15).

### Workflow coverage by role

| Role | Covered | Missing |
|---|---|---|
| Farmer | receipts, payment history via portal | passbook, advances, WhatsApp slip |
| Centre operator | collection wizard, offline, readiness | analyzer/AMCU capture, shift close |
| Dairy manager | dashboards, generation, reports | routes, stock, margin |
| Procurement manager | rate cards, matrices, supplier reports | advances, deductions, comparatives |
| Sales team | customers, plans, deliveries | leads, churn, self-service ordering |
| Distributor | — | **entirely absent**; no distributor tier exists |
| Delivery agent | mobile round, record delivery | route sheet, load/unload, cash collection |
| Finance team | invoices, payments, receipts, receivables, period close | tax, Tally export, UPI reconciliation |
| Administrator | users, roles, audit, config, calendar | usage/billing of their own subscription |
| Enterprise management | audit, DR, RLS, health | multi-entity consolidation |

---

## 4. Customer Segment Analysis

Segment economics are **[INFERRED]** unless a price is cited.

| # | Segment | Biggest problem | Minimum features | Will pay for | Doesn't need | Lacteva fit |
|---|---|---|---|---|---|---|
| 1 | **Small/local dairy** (<200 farmers) | Notebooks; disputes over fat and money | Collection, fat/SNF, rate chart, farmer payment, **WhatsApp slip** | Accuracy, no arguments | Periods, RLS, DR, audit | ⚠️ Over-served technically, under-served commercially |
| 2 | **Medium dairy** (200–2,000) | Reconciliation across centres | Above + multi-centre, advances, reports | Time saved, leak prevention | Processing, e-invoicing | ✅ **Strong fit** |
| 3 | **Regional dairy** | Coordinating centres, routes, distributors | Above + routes, inventory, distributor tier | Control and visibility | AI | ⚠️ Good, blocked on routes |
| 4 | **Large dairy enterprise** | Integration and compliance | ERP integration, tax, consolidation | Compliance, audit | Simplicity | ❌ Not yet — no tax, no ERP integration |
| 5 | **Dairy cooperative** | Member transparency; societies | Member ledger, **AMCU/DPU**, payment cycles | Trust and fairness | Retail subscription | ⚠️ Blocked on AMCU + ledger |
| 6 | **Milk collection organization** | Quality-linked pricing at scale | Collection, quality, pricing, settlement | Exactly Lacteva's core | Customer billing | ✅ **Strongest technical fit today** |
| 7 | **Farmer group / FPO** | Cheap, simple, vernacular | Collection + payment, low price | Very little — price-sensitive | Almost everything | ❌ Uneconomic to serve directly |
| 8 | **Subscription milk delivery** | Daily rounds, pauses, dues | Subscriptions, generation, billing, **routes**, UPI | Route + collection efficiency | Procurement half | ✅ **Best commercial fit** — blocked on routes and UPI |
| 9 | **Distributor** | Load, returns, crates, credit | Load/unload, crates, credit control | Cash-leak prevention | Procurement | ❌ Tier not modelled |
| 10 | **Multi-location enterprise** | Consolidation and isolation | Multi-org, RLS, audit, DR | Governance | — | ✅ Architecture already there; no consolidated reporting |

**The two segments Lacteva can win soonest are #6 (milk collection
organizations) and #8 (subscription milk delivery).** They sit at opposite ends
of the chain, and Lacteva is the rare platform with a credible claim on both.

---

## 5. Competitor Landscape

### 5.1 Indian SMB dairy software — the crowded, cheap end **[PUBLIC]**

| Vendor | Advertised capability | Price |
|---|---|---|
| [Hamari Dairy](https://hamaridairy.com/) | FAT/SNF/CLR testing, billing with **advance payments**, **route + driver + truck sheet**, **feed/medicine stock**, analyzer integration, offline, role-based access, 10+ Indian languages | **from ₹139/month**, 15-day trial |
| [Simple Dairy](https://simpledairy.com/) | **WhatsApp invoicing with UPI links**, per-customer rates, vacation management, delivery-boy routing, farmer ledger, **daily WhatsApp settlement slips**, counter-sales POS, online store with subscriptions, crate/bottle deposits, load per route | **₹1.09 per customer/month** (₹109 for 100), 30-day trial |
| [DairyKhata](https://dairykhata.in/) | Collection tracking, cattle management, automated payments | not stated |

**What this tells us.** The commodity end is crowded, cheap and
feature-complete in exactly the places Lacteva is weakest: WhatsApp, UPI,
routes, advances, stock, vernacular languages. Competing here on price is
unwinnable and competing here on architecture is invisible to the buyer.

### 5.2 Collection hardware and the AMCU pattern **[PUBLIC]**

Village-level collection in India runs largely through **Automatic Milk
Collection Units**: a weighing scale and milk analyzer wired to a Data
Processing Unit that holds the rate chart, computes the amount, prints a slip
and transfers data to a central server. The NDDB publishes a
[technical specification for AMCUs](https://www.nddb.coop/sites/default/files/pdfs/AMCU_Technical%20Specification_.pdf),
and vendors including [Prompt](https://promptamcs.com/) build to it.

**This is the single most important integration fact in the report.** A
cooperative or collection organization does not want an app to type fat into —
it wants the number to arrive from the machine. Lacteva has the ports
(`ScaleReading`, `AnalyzerReading`) and only mock adapters. **[REPO]**

### 5.3 Subscription delivery **[PUBLIC]**

[Country Delight](https://countrydelight.in/) (25 cities, 11 states) and
Milkbasket are *operators*, not software vendors — but they define what
customers now expect: app ordering, subscription pause/resume, live tracking,
digital proof of delivery. Several vendors sell "build a Country Delight clone"
platforms. Lacteva has the subscription engine and lacks the customer-facing
surface and the route.

### 5.4 East Africa **[PUBLIC]**

Kenyan dairy digitisation runs through cooperative-focused platforms and
mobile-money rails — SNV and 2SCALE document cooperative digitisation
programmes, Safaricom's DigiFarm has a dairy management solution, and reporting
describes farmers receiving **SMS with delivered volume and accrued amount**.
Mobile money (M-Pesa) is the payment rail rather than UPI.

**This validates Lacteva's multi-country architecture** — the same product with
a different payment port and message channel, which is precisely how Lacteva is
already built.

### 5.5 Large Indian dairies **[INFERRED — no claim about their software]**

Amul/GCMMF, Mother Dairy, Nandini/KMF, Hatsun, Heritage, Dodla, Milma, Aavin
and the rest are evidence of the *operational shape* Lacteva must eventually
respect: tens of thousands of village societies, twice-daily collection,
quality-linked payment cycles, chilling and processing tiers, and distributor
networks. **Nothing is asserted about what software they run.** They are not
addressable customers for Lacteva today and should not drive the roadmap.

---

## 6. Competitive Gap Matrix

| Capability | Lacteva | Competitor category | Importance | Gap | Recommended action |
|---|---|---|---|---|---|
| WhatsApp bills / slips | ❌ none | Indian SMB software | **P0** | Total | Build a message-channel port; WhatsApp + SMS adapters |
| SMS/email delivery | ⚠️ logging stub | All | **P0** | Total in practice | Real adapters behind the existing `Notifier` port |
| SaaS subscription billing | ❌ none | All SaaS | **P0** | Total | Plans, trial, entitlement, metering |
| UPI / payment collection | ❌ none | Indian SMB | **P0** | Total | Payment-rail port; UPI in India, M-Pesa in Kenya |
| Farmer advances + deductions | ❌ placeholder | Indian SMB + cooperative | **P0** | Total | Deduction engine on the existing settlement line |
| Routes / delivery agents | ❌ none | SMB + subscription | **P0** | Total | Route, agent assignment, round sheet |
| Farmer ledger / passbook | ⚠️ partial | All | **P1** | Presentation | Ledger view over existing data |
| Analyzer / scale drivers | ⚠️ mocks | Hardware vendors | **P1** | Driver layer | One real adapter, one real deployment |
| AMCU / DPU ingestion | ❌ none | Cooperative market | **P1** | Total | File/API ingestion to NDDB-style spec |
| Products / stock | ⚠️ string | SMB software | **P1** | Substantial | Catalog first, stock second |
| Crates / deposits | ❌ none | Distribution | **P1** | Total | With routes |
| Tax / GST | ❌ none | All Indian finance | **P1** | Total | Per-country tax port |
| Accounting export (Tally) | ❌ none | Indian finance | **P1** | Total | Export before integration |
| More Indian languages | ⚠️ 3 | SMB (10+) | **P1** | Incremental | Catalogs only; machinery exists |
| Customer self-service app | ⚠️ partial | Subscription | **P1** | Substantial | After routes |
| Public API keys / webhooks | ⚠️ partial | Enterprise | **P2** | Moderate | Outbox already exists |
| Counter POS | ❌ none | SMB | **P2** | Total | Different business; defer |
| Chilling / processing / yield | ❌ none | Dairy ERP | **P3** | Total | **Do not build** (§15) |
| AI anything | ❌ none | Marketing claims | **P3** | Total | Defer; no data yet |
| RLS / DR / audit / period close | ✅ strong | Most SMB lack | — | **Lacteva ahead** | Sell it to cooperatives and enterprises |
| Business-date/timezone correctness | ✅ strong | Rarely correct | — | **Lacteva ahead** | The multi-country wedge |

---

## 7. Lacteva Differentiation

Sorting the candidate positions honestly. **Most are table stakes.**

### Genuinely differentiating

1. **Multi-country by construction.** Country → currency → timezone → language
   → calendar, resolved from a registry with no country branching anywhere in
   the code. Verified: a search for country conditionals in business logic
   finds none. **[REPO]** Almost every competitor surveyed is single-country.
   This is Lacteva's most defensible asset and its hardest to copy.

2. **Financial correctness as a product property.** Immutable documents,
   `Decimal` end to end, statements that reconcile by identity, period close
   that refuses writes, sequential document numbers on the dairy's own year.
   **[REPO]** For cooperatives — where a payment dispute is a governance
   incident — this is a *sales argument*, not an implementation detail.

3. **The complete chain, one platform.** Farmer→dairy→customer in one tenant,
   with both money directions reconciled. Competitors tend to be strong on
   procurement *or* on delivery. **[PUBLIC]** Lacteva is credible on both.

4. **Tenant isolation provable to an auditor.** 65 tables with forced RLS,
   proven on real PostgreSQL, plus PITR and restore verification. **[REPO]**
   Only matters to cooperative and enterprise buyers — but to them it matters a
   great deal.

### Table stakes (build, but do not claim as differentiation)

Affordable SaaS · mobile-first · offline field operations · subscription
delivery · automated recurring delivery · real-time dashboards · easy
onboarding · multi-language · multi-currency.

Every one of these is advertised by ₹139/month competitors. **[PUBLIC]**
Offline in particular: Lacteva's implementation is better than most, and the
buyer cannot tell.

### Not differentiating yet, and possibly never

**AI-assisted operations** — no competitor is winning on it and Lacteva has no
data to train on. **Route optimization** — cannot differentiate on a capability
you do not have; get routes working first. **Hardware integration** — necessary
to *enter* the cooperative market, not to stand out in it. **Modular pricing** —
a packaging decision, not a product one.

### The one-sentence position

> **The only dairy operations platform that runs a dairy's whole chain —
> farmer to household — correctly in any country, on any clock, in any
> currency, with books that reconcile.**

---

## 8. Onboarding Strategy

The proposed journey is right, with one correction: **modules must come before
business configuration**, because what a dairy is asked to configure depends on
which half of the chain it runs.

```
Country → Currency · Timezone · Language   (registry-resolved, editable)
   ↓
Organization type                          (decides everything after)
   ↓
Organization details → Admin account
   ↓
Modules  (procurement · distribution · both)
   ↓
Business configuration (module-dependent)
   ↓
Trial (30 days) → Sample data (optional, discardable) → Go live
```

### Mandatory data by organization type

| | Dairy firm | Cooperative | Farmer/FPO | Collection centre | Enterprise | Subscription delivery |
|---|---|---|---|---|---|---|
| Country/currency/timezone | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Legal name + admin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| At least one centre | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |
| Rate card / matrix | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |
| Suppliers | ✅ | ✅ | ✅ | ✅ | ✅ | ➖ |
| Members/shares | ➖ | ✅ | ➖ | ➖ | ➖ | ➖ |
| Customers + plans | ✅ | ➖ | ➖ | ➖ | ✅ | ✅ |
| Products/pack sizes | ➖ | ➖ | ➖ | ➖ | ✅ | ✅ |
| Routes/agents | ➖ | ➖ | ➖ | ➖ | ✅ | ✅ |
| Tax registration | ➖ | ➖ | ➖ | ➖ | ✅ | ⚠️ |
| Workspaces/branches | ➖ | ⚠️ | ➖ | ➖ | ✅ | ➖ |

**Design rule:** never ask for anything the platform can derive. Country
already implies currency, timezone, language and date format — and it already
does. **[REPO]** Sample data must be *discardable*, or nobody will trust the
first real month.

---

## 9. Pricing Strategy

### Market anchors **[PUBLIC]**

- Hamari Dairy: **from ₹139/month**
- Simple Dairy: **₹1.09 per customer/month** (₹109 at 100 customers)
- SalesPort: **₹1.5 lakh one-time + ₹5,000/month AMC**; and it describes
  enterprise dairy ERP engagements at ₹3–5 lakh/month with ₹50 lakh+
  implementations

The market is barbell-shaped: near-free SMB tools, or six-figure enterprise
projects. **The middle is thin, and that is where Lacteva belongs.**

### Recommendation: price on the thing the customer already counts

| | Starter | Growth | Professional | Enterprise |
|---|---|---|---|---|
| Basis | ≤2 centres, ≤200 suppliers **or** ≤300 customers | ≤5 / ≤1,000 / ≤2,000 | ≤15 / ≤5,000 / ≤10,000 | Unlimited |
| Core operations | ✅ | ✅ | ✅ | ✅ |
| WhatsApp/SMS | metered bundle | included | included | included |
| Routes & agents | — | ✅ | ✅ | ✅ |
| Advances & deductions | — | ✅ | ✅ | ✅ |
| Period close & audit | — | — | ✅ | ✅ |
| Hardware/AMCU | — | — | add-on | ✅ |
| API/webhooks | — | — | add-on | ✅ |
| DR/PITR assurances | — | — | — | ✅ |

**Basis: a single headline number per tier — collection centres — with
supplier and customer counts as generous guardrails rather than meters.** Why:

- **Per-user fails.** Dairies have many low-value operator logins; charging per
  user teaches them to share credentials, which destroys the audit trail Lacteva
  is otherwise good at.
- **Per-litre fails.** It is the number a dairy negotiates hardest and its
  seasonality would make the bill unpredictable.
- **Per-farmer/per-customer alone is fragile** — it is exactly Simple Dairy's
  ₹1.09 and invites a race to the bottom.
- **Per-centre is stable, countable, honest, and correlates with real value.**

**Add-ons, not tiers:** message volume beyond the bundle, hardware/AMCU
integration, accounting export, API access, extra languages.

**Trial: 30 days, all features, no card** — matching the more generous
competitor and removing every reason to hesitate.

---

## 10. AI Opportunities

| Opportunity | Value | Verdict |
|---|---|---|
| Quality anomaly / adulteration detection | High — a real, costly dairy problem | **NEXT** — and try statistics before ML |
| Collection forecasting | Medium — chilling and route planning | **NEXT**, after ~12 months of history |
| Route optimization | High once routes exist | **LATER** — meaningless before Phase 3 |
| Demand forecasting | Medium | **LATER** |
| Payment/churn prediction | Low — small dairies know their defaulters | **LATER** |
| Price recommendation | Low — and dangerous; pricing is a governance act | **LATER** |
| Operational assistant / chat | Low | **Do not build** |

**Nothing is NOW.** Lacteva has no multi-year, multi-tenant history to learn
from, and every AI feature listed is a differentiator only if the underlying
operational feature already works.

---

## 11. Hardware Opportunities

| Opportunity | Verdict | Reasoning |
|---|---|---|
| **Milk analyzer + weighing scale** | **NEXT (highest-value hardware work)** | Ports and a device registry already exist with mock adapters. **[REPO]** One real driver converts a demo into a deployable collection centre |
| **AMCU / DPU ingestion** | **NEXT** | The dominant Indian collection pattern; NDDB publishes a specification. **[PUBLIC]** This is the price of entry to the cooperative market |
| GPS / vehicle tracking | LATER | After routes |
| RFID/smart card farmer identification | LATER | Common at AMCUs; only alongside AMCU work |
| Biometric attendance | Do not build | Not a dairy operations concern |

**Recommended shape:** ingest, don't drive. Reading a file or an HTTP callback
from an existing AMCU is a fraction of the work of certifying against dozens of
devices, and it fits the platform Lacteva already is.

---

## 12. Compliance Opportunities

| Opportunity | Verdict | Reasoning |
|---|---|---|
| **Tax/GST on invoices** | **NEXT** | Blocks any Indian business above the threshold. Must be a per-country tax port — never `if country == "IN"` |
| **Accounting export (Tally/Zoho)** | **NEXT** | Near-universal in Indian SMB finance **[INFERRED]**; an export file is cheap and removes a real objection |
| Audit trail | **NOW — already done** | `audit_record` + endpoints **[REPO]**. Sell it |
| E-invoicing / e-way bill | LATER | Threshold-dependent; large enterprises only |
| FSSAI / food safety records | LATER | Belongs to processing, which Lacteva does not do |
| Data protection (DPDP, GDPR) | **NEXT (light)** | Export and erasure endpoints; tenant offboarding partially exists **[REPO]** |

---

## 13. P0 / P1 / P2 / P3 Feature Priorities

**P0 — mandatory for commercial launch**

1. Real message delivery (SMS + **WhatsApp**) behind the existing port
2. SaaS subscription: plans, trial, entitlement, metering
3. Self-service onboarding with discardable sample data
4. Farmer advances + settlement deductions (finish the placeholder)
5. Routes, delivery agents, round sheets
6. Payment collection rail (UPI in India, M-Pesa in Kenya) behind one port

**P1 — important competitive capability**

Farmer ledger/passbook · analyzer + AMCU ingestion · product catalogue and
basic stock · crates and deposits · tax port · accounting export · additional
Indian languages · customer self-service ordering · analytics depth

**P2 — differentiators**

Public API keys and webhooks · multi-entity consolidation · cooperative member
management · counter POS · quality anomaly detection

**P3 — future**

Processing/yield · chilling tier · e-invoicing · fleet telematics · demand
forecasting · route optimization · AI assistant

---

## 14. Recommended Development Roadmap

Ten phases. **Phase 1 is the only one that unblocks revenue**, and I would not
begin Phase 2 before it is done.

### PHASE 1 — Commercial Foundation *(the launch blocker)*
| Milestone | Problem | User | Complexity | Affects |
|---|---|---|---|---|
| **1. Message delivery** | Nothing reaches anyone; WhatsApp slips are the market's baseline | Farmer, customer | Medium | Backend, portal |
| **2. SaaS subscription & trial** | Lacteva cannot charge | Lacteva | Medium | Backend, portal |
| **3. Self-service onboarding + sample data** | No path from interest to trial | New customer | Medium | Backend, portal |

### PHASE 2 — Procurement & Farmer Operations
| Milestone | Problem | User | Complexity | Affects |
|---|---|---|---|---|
| **4. Advances, deductions, bonuses** | The settlement placeholder; farmer credit is universal | Procurement, farmer | Medium | Backend, portal, mobile |
| **5. Farmer ledger/passbook + shift close** | Farmers cannot see their own running position | Farmer | Low | Backend, portal, mobile |

### PHASE 3 — Distribution & Logistics
| Milestone | Problem | User | Complexity | Affects |
|---|---|---|---|---|
| **6. Routes & delivery agents** | Deliveries exist with no round to walk | Delivery agent | Medium-high | All three |
| **7. Load/unload, crates, cash collection** | Real cash and asset leakage | Delivery agent | Medium | Backend, mobile |
| **8. Product catalogue + basic stock** | `product` is a string | Dairy manager | Medium | Backend, portal |

### PHASE 4 — Customer & Subscription Growth
| **9. Customer self-service ordering** | Subscribers expect an app | Customer | Medium-high | Backend, mobile |

### PHASE 5 — Finance
| **10. Tax port + accounting export** | Blocks Indian businesses above threshold | Finance | Medium | Backend, portal |

### PHASE 6 — Analytics
| **11. Operational & financial analytics depth** | Data is captured, insight is thin | Manager | Medium | Backend, portal |

### PHASE 7 — Integrations & Hardware
| **12. Analyzer/scale drivers + AMCU ingestion** | Cooperative market entry | Centre operator | High | Backend, mobile |
| **13. Public API keys + webhooks** | Enterprise integration | Enterprise | Low-medium | Backend, portal |

### PHASE 8 — AI
| **14. Quality anomaly detection** | Adulteration is costly and detectable | Procurement | Medium | Backend, portal |

### PHASE 9 — Enterprise
| **15. Multi-entity consolidation + cooperative members** | Groups cannot see across entities | Enterprise, cooperative | Medium-high | Backend, portal |

### PHASE 10 — Globalization
| **16. Language expansion + additional country packs** | 3 languages vs 10+ | Farmer, operator | Low each | All three |

---

## 15. What NOT to Build

**Processing, yield and plant operations.** It is a different product with a
different buyer, and it would turn Lacteva into a dairy ERP competing with
₹50-lakh implementations. Lacteva's advantage is the *chain*, not the plant.

**A full inventory/WMS.** Catalogue and simple stock, yes. Batches, expiry,
multi-warehouse transfers and reservations: no. It would swallow a phase and
serve customers Lacteva is not otherwise ready for.

**Any AI, now.** No history to learn from, no competitor winning on it, and
every AI feature is worthless until the operational feature beneath it works.

**Real hardware drivers before ingestion.** Certifying against many devices is
a hardware business. Ingesting from an AMCU is a software one.

**Counter POS.** A retail outlet is a different operation. Simple Dairy sells
it; that does not mean Lacteva should.

**Country-specific branches.** The single most valuable architectural property
Lacteva has is that no business logic asks which country it is in. Tax, payment
rails and messaging must be **ports with per-country adapters**, always.

**Microservices.** The modular monolith is working, the seams are already
drawn, and nothing in this review is blocked by deployment topology.

**Per-user pricing.** It would push dairies to share logins and destroy the
audit trail.

**Attendance, payroll, HR.** Adjacent, endless, and not why anyone buys dairy
software.

**A rewrite of anything.** Nothing in this survey justifies it.

---

## 16. Recommended Product Positioning

Evaluated against the evidence:

| Candidate | Verdict |
|---|---|
| A dairy ERP | ❌ Competes with ₹50-lakh implementations Lacteva cannot service, and demands processing/inventory it should not build |
| A milk procurement platform | ❌ Discards the delivery half, which is already built and is the better commercial fit |
| A dairy operations platform | ✅ **Recommended** |
| A complete dairy business operating system | ❌ True eventually; unprovable today and it implies the ERP scope |
| A SaaS platform for dairies of all sizes | ❌ "All sizes" means the ₹139 segment, which is unwinnable |

### **Lacteva is a multi-country dairy operations platform for the farmer→dairy→customer chain.**

**LACTEVA CORE** — milk collection with quality; quality-based procurement
pricing; farmer settlement and payment; customers, subscriptions and automatic
delivery generation; billing, payments, receipts and receivables; business-date,
currency and calendar correctness in any country; mobile field operations with
offline capture; multi-tenant isolation with provable audit and recovery.

**LACTEVA DIFFERENTIATORS** — multi-country with no country branching;
financial correctness as a product property; the complete chain in one tenant;
tenant isolation provable to an auditor.

**LACTEVA FUTURE** — AMCU and analyzer ingestion; tax and accounting
integration; cooperative member management; consolidation; quality anomaly
detection; language expansion.

**LACTEVA SHOULD NOT BUILD YET** — processing and yield; full WMS; AI; hardware
drivers; counter POS; e-invoicing; attendance and payroll; microservices; any
country-specific branch in business logic.

---

## 17. Proposed DEMO-025

**DEMO-025 — Commercial Foundation I: Message Delivery**

The narrowest thing that changes Lacteva from a platform into a product.

**Why this and not subscription billing first.** Both are Phase 1. Messaging is
the better first step because it is *visible to the customer* — a farmer
receiving a WhatsApp settlement slip is the demo that sells the platform — and
because it is entirely additive: a `Notifier` port already exists with a
logging adapter and a code TODO naming exactly this work. **[REPO]** Nothing
architectural needs deciding.

**Scope.** Real adapters behind the existing port: SMS and WhatsApp for India,
SMS for Kenya, email everywhere. Per-country channel selection resolved from
the existing registry — never a country branch. Template rendering in the
existing three languages. Delivery status and retry recorded on the existing
`notification` tables. Two journeys end to end: **a farmer's settlement slip**
and **a customer's invoice**.

**Explicitly out of scope.** Subscription billing (DEMO-026), UPI links
(needs the payment-rail port), marketing consent flows, and any new UI beyond
what is required to see that a message was sent.

**Definition of done.** A real message delivered to a real handset from the
deployed platform, with the provider credential held as a secret, delivery
failures visible in the existing notification records, no country branching in
business logic, and the full regression suite and PostgreSQL proof green.

---

## Sources

- [Hamari Dairy](https://hamaridairy.com/) — features and pricing
- [Simple Dairy](https://simpledairy.com/) — modules and per-customer pricing
- [DairyKhata](https://dairykhata.in/) — SMB dairy SaaS
- [SalesPort dairy management software](https://sortstring.com/dairy-management-software) — deployment and enterprise pricing anchors
- [NDDB AMCU technical specification](https://www.nddb.coop/sites/default/files/pdfs/AMCU_Technical%20Specification_.pdf) — the collection-unit standard
- [Prompt AMCS](https://promptamcs.com/) — automatic milk collection systems
- [Country Delight](https://countrydelight.in/) and [Wikipedia](https://en.wikipedia.org/wiki/Country_Delight) — subscription delivery scale
- [SNV: digitisation and dairy cooperatives in Kenya](https://www.snv.org/update/digitization-a-game-changer-for-dairy-cooperatives-in-kenya)
- [2SCALE: digitizing milk procurement in Kenya](https://www.2scale.org/en/updates/digitizing-milk-procurement-in-kenya-en)
- [SoftwareSuggest dairy software category](https://www.softwaresuggest.com/dairy-industry-software) and [Techjockey](https://www.techjockey.com/category/dairy-management-software) — market breadth

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-15 | Platform Engineering | DEMO-024: repository capability survey, competitive research, segment and gap analysis, positioning, pricing and a ten-phase roadmap. Research only — no code, no deployment. |
