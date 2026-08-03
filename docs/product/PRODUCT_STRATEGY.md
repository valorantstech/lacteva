---
id: PRODUCT-STRATEGY
title: Lacteva Product Strategy
type: reference
status: Approved
version: "1.0"
owner: Product
created: 2026-08-04
last-updated: 2026-08-04
related: [CAP-0001, PDT-0001]
baseline: ARCH-BASELINE-V1
---

# Lacteva Product Strategy

The commercial strategy for the Lacteva Dairy Operating System. Grounded in the [Business Capability Model](../05-capabilities/CAP-0001-business-capability-master-map.md) (what dairy businesses do), the [five-year architecture plan](../ai/CLAUDE_CONTEXT.md) (what we build, in what order), and the shipped Procurement Platform (what already works). On conflict about *what the product is technically*, the architecture baseline wins; this document owns *who it is for and how it is sold*.

---

## 1. Who is Lacteva for?

Lacteva is for **organizations that buy milk from many small producers and turn it into money that must be trusted on both sides of the scale**. The core buyer is the dairy organization — cooperative, aggregator, or processor. The daily users are its operators, lab staff, accountants, and managers. Farmers and suppliers are first-class *beneficiaries* of the system (fair, explainable, fast payment) before they become direct users of it (Farmer App).

Lacteva is *not* for hobby farms, single-farm direct-to-consumer sellers, or retailers — segments whose problems are not "collect quality-priced milk from thousands of suppliers and settle it honestly."

## 2. Customer segments

| Segment | Shape | Daily volume | Today's tooling |
| --- | --- | --- | --- |
| **S1 — Village societies & BMC operators** | 1 collection point, 50–500 farmers | 500–5,000 L | Paper registers, a DPU/AMCS box, memory |
| **S2 — Dairy cooperatives & producer companies** | 1–10 centers, 500–5,000 farmers | 2,000–20,000 L | Spreadsheets + disconnected DPU software |
| **S3 — Chilling-center networks & private aggregators** | 10–100 centers, route logistics | 20,000–200,000 L | Fragmented vendor software per center, no consolidation |
| **S4 — Private dairies & processors** | Procurement + processing + sales | 50,000–500,000 L | Legacy dairy ERP or generic ERP mis-fitted to milk |
| **S5 — Enterprise dairies, unions & federations** | 100+ centers, multi-entity, regulated | 200,000–2,000,000+ L | Custom-built systems, decade-old, integration-hostile |
| **S6 — Ecosystem partners** (later) | Banks, insurers, input sellers, logistics | — | No programmatic access to dairy data flows |

## 3. Problems per segment

- **S1/S2:** measurement disputes and trust erosion; manual FAT-based price arithmetic (error-prone, opaque); settlement takes weeks; no records when a dispute or audit arrives; operator dependence ("the register lives in one person's head").
- **S3:** zero consolidated visibility across centers; per-center data silos; leakage/fraud between center and hub; cannot answer "how much milk, at what quality, owed to whom, today?"
- **S4:** procurement, processing, and sales systems don't share a data spine; batch traceability is manual; pricing policy changes take weeks to roll out; compliance reporting is a fire drill.
- **S5:** vendor lock-in on aging systems; every integration is a custom project; multi-entity/multi-market operations forced through single-tenant software; no audit-grade lineage from farmer to ledger.
- **All segments:** the milk itself is perishable — any software that blocks the collection line is worse than paper. (This is why Lacteva's collection flow never blocks on pricing, connectivity, or downstream systems.)

## 4. Editions

Three commercial editions, mapped onto platform layers — plus the ecosystem tier:

1. **Lacteva Collect** — the procurement core: centers, suppliers, sessions, milk collection, pricing, settlement, payments, receipts, reports, operator app, admin portal. *For S1–S3.*
2. **Lacteva Operations** — Collect + Processing + Inventory (reception, tanks, quality lab, batches, production, packaging, warehouse, expiry) + Sales basics (orders, dispatch, invoices). *For S3–S4.*
3. **Lacteva Enterprise** — Operations + Finance (ledger, tax/GST, reconciliation) + AI Platform + Enterprise services (API gateway, SSO, webhooks, warehouse/analytics, SLAs, on-prem/hybrid deployment, multi-entity). *For S4–S5.*
4. **Lacteva Marketplace** *(ecosystem, not an edition)* — certified integrations, plugins, and partner apps on top of any edition. *For S6 and existing customers.*

## 5. Feature matrix by edition

| Capability | Collect | Operations | Enterprise |
| --- | :-: | :-: | :-: |
| Collection centers, sessions, readiness | ✅ | ✅ | ✅ |
| Suppliers, QR identity, documents | ✅ | ✅ | ✅ |
| Milk collection engine (immutable transactions) | ✅ | ✅ | ✅ |
| Quality-based pricing (rate cards, matrices, resolution, calculator) | ✅ | ✅ | ✅ |
| Settlements, payments, receipts | ✅ | ✅ | ✅ |
| Operational reports & dashboards | ✅ | ✅ | ✅ |
| Operator mobile app (offline-capable) | ✅ | ✅ | ✅ |
| Notifications (SMS/app) to suppliers | ✅ | ✅ | ✅ |
| Farmer App | add-on | ✅ | ✅ |
| Processing (reception, tanks, lab, batches, production) | — | ✅ | ✅ |
| Inventory (warehouse, transfers, expiry, audit) | — | ✅ | ✅ |
| Sales (customers, orders, invoices, dispatch) | — | ✅ | ✅ |
| Finance (ledger, GST/tax, reconciliation) | — | add-on | ✅ |
| AI (predictions, anomaly & fraud detection, assistant) | — | add-on | ✅ |
| API gateway, SDK, webhooks, integrations | read-only API | standard API | full + gateway |
| SSO, advanced RBAC, audit exports | — | — | ✅ |
| On-premise / hybrid deployment | — | — | ✅ |
| Multi-entity / federation management | — | — | ✅ |
| SLA & dedicated support | community/standard | standard | enterprise |

Every edition shares one codebase and one data model; editions are **entitlement configuration, never forks** (the platform's configuration-before-customization principle applied to packaging).

## 6. Pricing philosophy

- **Priced on value handled, not seats.** Dairy value scales with litres, not logins. Base subscription per edition + volume bands (litres/month collected). Adding an operator, a viewer, or a lab technician must never cost extra — per-seat pricing punishes exactly the digitization we want.
- **Farmers never pay.** No per-farmer, per-supplier, or Farmer-App fees, ever. Supplier trust is the product's engine; taxing it would be strategic self-harm.
- **Transparent and local.** Public price bands, local currency, local payment methods. A cooperative treasurer must be able to explain the Lacteva bill to their board in one sentence.
- **Start cheap where trust starts.** Collect entry pricing must undercut the true cost of the status quo (disputes + leakage + clerical time), not compete with "free paper."
- **Consumption pricing only where costs are consumption-shaped:** AI inference, SMS volume, archival storage. Never for core record-keeping.
- **Enterprise = commercial flexibility** (license + support for on-prem, committed-volume discounts), same software.

## 7. Deployment models

- **SaaS (default).** Multi-tenant cloud — the architecture's native shape (`Organization` = tenant). Fastest onboarding, continuous delivery, pooled operations. Target for S1–S4.
- **On-premise (Enterprise).** The same modular monolith + compose/K8s footprint, deployed in the customer's datacenter for regulatory or sovereignty needs. Constraint we accept: versioned releases and a support matrix instead of continuous deploy. No forked features — on-prem lags, never diverges.
- **Hybrid (the dairy reality).** Cloud control plane + **edge-resilient collection**: the operator app (and later an edge gateway at large centers) works offline and syncs when connectivity returns. Hybrid is not an enterprise luxury here — rural connectivity makes offline-first table stakes for every edition, which is why it sits inside the MVP, not the enterprise tier.

## 8. Multi-country strategy

- **Market packs are configuration, not code** (locked platform principle): language packs, units, currency, quality-dimension defaults, regulatory parameters (e.g., GST/e-invoicing in India, KRA requirements in Kenya), payment rails (UPI, M-Pesa, bank transfer), receipt formats. A new country is a pack + a partner, not a branch.
- **Entry sequence:** launch markets where the pain and the mobile-money rails are strongest and where our i18n groundwork already points — **East Africa (Kenya first) and South Asia (India first)**; then Southeast Asia, East/West Africa expansion, LATAM.
- **Go-to-market per country through dairy-adjacent partners** (co-op unions, DPU hardware resellers reframed as integration partners, agri-fintechs) rather than direct-only sales.
- **Data residency** follows deployment model: regional SaaS clusters as demand justifies; on-prem where law requires.

## 9. AI strategy

- **Data before models.** The differentiating asset is already being built: immutable transactions, explainable pricing traces, complete event streams, audit trails. Every AI feature is trained and evaluated on records the customer can inspect.
- **Ship the ladder in order:** descriptive (reports — shipped) → anomaly detection (quality/fraud outliers vs supplier baselines) → prediction (daily milk volume, supplier churn, demand) → optimization (routes, dynamic pricing simulation) → **LLM assistant** ("why was Amina paid 5,647.50 yesterday?" answered from the trace, in the operator's language).
- **AI advises; rules decide.** AI never silently sets a price or blocks a farmer. Suggestions surface with explanations; the BR register + rules engine remain the deciders. Explainability is a product feature, not a compliance chore — it is *the* trust story.
- **Tenant data is never pooled without consent.** Cross-tenant benchmarks ("your FAT average vs region") only as an explicit opt-in product, anonymized and aggregated.
- **Sell AI as an Enterprise capability / add-on**, priced on consumption, because its costs are consumption-shaped and its value is easiest to prove after the customer's own data has accumulated.

## 10. Marketplace strategy

- **Phase 1 (platform):** public API + SDK + webhooks (cheap once the consumer framework lands) — existing customers integrate their accountants, banks, and logistics.
- **Phase 2 (certified integrations):** payment providers, SMS gateways, analyzer/scale hardware vendors (device certification instead of hardware lock-in — inverting the traditional DPU model), accounting systems (Tally, QuickBooks, ERPNext).
- **Phase 3 (marketplace):** third-party plugins on documented extension points with revenue share; partner apps for S6 (credit scoring on collection history — *with the farmer's consent*, insurance, input financing).
- **The rule that keeps the marketplace honest:** partners get APIs and events, never raw database access; farmer-level data flows only under explicit, revocable consent.

## 11. Five-year product roadmap (commercial view)

| Horizon | Ships | Sells |
| --- | --- | --- |
| **Year 1** | Procurement completion (payments, receipts, offline, notifications), production hardening, first market pack | **Lacteva Collect** in 1–2 launch markets |
| **Year 2** | Farmer App, Collection Manager, Regional Dashboard; Processing platform (reception→packaging); consumer/webhook platform | Collect at scale; **Operations** early adopters |
| **Year 3** | Inventory + Sales platforms; Finance foundation (ledger, GST); first AI (anomaly, milk prediction) | **Operations** as lead SKU; 3–5 markets |
| **Year 4** | Finance completion, AI expansion (forecasting, dynamic-pricing simulation, routes), API gateway + SDK + integrations | **Enterprise** edition; on-prem/hybrid deals |
| **Year 5** | LLM assistant, analytics warehouse, marketplace + plugins, federation-scale multi-entity | Enterprise + **Marketplace** ecosystem revenue |

(The engineering decomposition of this table is the five-year architecture plan; work orders remain the sequencing authority.)

## 12. Product principles

1. **Never block the milk.** Perishable-first design: collection proceeds through connectivity loss, pricing gaps, and downstream failures — always. (Already law in the codebase.)
2. **Every number is explainable.** Prices, settlements, and reports carry traces back to their inputs. If we can't show the "why," we don't show the number.
3. **Farmer trust is the moat.** Features are judged by whether they increase supplier trust in the organization using Lacteva.
4. **Capabilities over CRUD; configuration over customization; platform before product** — the locked engineering principles are also the product principles.
5. **One codebase, many editions.** Packaging is entitlements; there are no forks, ever.
6. **Meet users where they are:** mobile-first operators, low-end Android, local language, intermittent networks.
7. **Boringly reliable beats impressively fragile.** A cooperative's payroll depends on us; we optimize for auditability and recovery before novelty.

## 13. Features explicitly NOT planned

- **Selling or brokering farmer/supplier data.** Not at any price, to anyone. (Consent-based partner integrations are the farmer's choice, not our revenue line.)
- **Per-seat or per-farmer pricing mechanics.**
- **Manufacturing or bundling proprietary hardware.** We certify and integrate scales/analyzers; we do not build or lock them.
- **A generic ERP** (HR, payroll, CRM-for-anything, project management). Adjacent needs integrate via the marketplace.
- **Full accounting-software replacement in early editions** — Finance platform arrives Year 3–4; until then we integrate with incumbents rather than pretend.
- **Blockchain/crypto anything.** The trust problem is solved by immutable records, traces, and audits — not by tokens.
- **Consumer-facing milk retail/delivery apps.** Downstream of our customer's customer.
- **Custom one-off forks for large deals.** Enterprise flexibility lives in configuration, packs, and plugins.

## 14. Why Lacteva over traditional dairy software?

Traditional dairy procurement software is a **hardware-tethered, single-PC, single-site register**: DPU/AMCS vendors bundle opaque desktop software with their scales; data lives on one machine at one center; pricing math is a black box; there is no consolidated view, no API, no audit trail, no farmer-facing transparency — and switching costs are engineered in via the hardware.

Lacteva's counter-position, feature by shipped feature: **explainable pricing** (every payable amount carries a resolution + calculation trace to the exact rate card band); **immutable, audit-grade records** (transactions snapshot at completion; every mutation audited; events durable); **consolidated multi-center, multi-entity visibility** in real time; **hardware freedom** (certified integrations, not bundles); **modern access** (cloud + offline mobile + APIs) versus one dusty PC; **configurable rules** (a pricing policy change is a rate-card version, live in minutes, not a vendor site visit); and **a platform trajectory** — the same system grows from one village society to a federation, so the software is never the reason to re-migrate. The one-line pitch: *traditional software records what the machine said; Lacteva proves what everyone is owed and why.*

---

## Ideal Customer Profiles

### ICP-1 — Small Dairy (Lacteva Collect)

Cooperative society or producer company. **300–3,000 farmers, 1–5 collection centers, 2,000–20,000 L/day**, 5–25 staff. Buying trigger: settlement disputes, a suspected leakage incident, or a modernization grant/NGO program. Decision-maker: society secretary/chair + treasurer; must be sellable in one demo on a phone. Success in 90 days: disputes at the scale near zero, settlement cycle from weeks to days, first season of clean records. Willingness to pay: low but real — priced against clerical cost + leakage, paid monthly, local rails. Risks: change resistance from clerks, connectivity — countered by offline-first and receipts that make farmers *demand* the system.

### ICP-2 — Regional Dairy (Lacteva Collect → Operations)

Chilling-center network, union, or mid-size private dairy. **5,000–50,000 farmers, 10–100 centers, 20,000–200,000 L/day**, professional management, possibly light processing. Buying trigger: zero cross-center visibility, fraud between center and hub, or a processor contract demanding traceability. Decision-makers: GM/CEO + procurement head + finance head; a 60–90 day paid pilot on 5–10 centers is the sales motion. Success: consolidated daily procurement dashboard, uniform pricing policy rollout in a day, per-center variance flags, one settlement run for the whole network. Expansion path: Operations edition when processing comes in-house; the Regional Dashboard app is built for exactly this buyer.

### ICP-3 — Enterprise Dairy (Lacteva Enterprise)

Federation, mega-dairy, or multi-entity processor. **50,000–500,000+ farmers, 100–1,000+ centers, 200,000–2,000,000+ L/day**, in-house IT, regulatory exposure, existing (aging) systems. Buying trigger: end-of-life legacy platform, audit/compliance failure, or board-level digital mandate. Decision: CIO + CFO + procurement director; 6–18 month cycle with RFP, security review, integration proof (API/SSO/data migration), on-prem or hybrid negotiation, SLAs. Success: phased center migration without collection downtime, ledger-reconcilable procurement, API integration into incumbent ERP/finance, measurable leakage reduction at federation scale. This ICP funds the Enterprise platform tier; we do not chase it before Year 3 except as design partners.

---

## What should Lacteva Version 1.0 contain to sell commercially within 12 months?

**Sell exactly one thing: Lacteva Collect, complete and production-hard, in one launch market.** The engineering is ~70% done; the remaining 30% is precisely the unglamorous part that makes it sellable:

**In V1.0 (must ship):**
1. **The four MVP completers** — Payments (SET-002, bank/mobile-money rails), Receipts (printed + SMS/app — the farmer-trust artifact), Offline collection (the field prerequisite), Notifications (consumer framework + SMS gateway).
2. **Production hardening (the M1 list):** Postgres RLS, RS256 keys, rate limiting, bootstrap-admin flow, real backups/restore drills, monitoring + alerting on the metrics already exported.
3. **Cloud deployment (M3):** one region, IaC, staging→prod promotion, the migration job — SaaS onboarding that doesn't require an engineer.
4. **Commercial plumbing:** self-serve tenant signup + edition entitlements, volume metering (litres/month — the pricing unit), billing integration, in-product usage visibility.
5. **Market pack #1** (Kenya *or* India — pick one): language completion, currency/payment rails, receipt format, regulatory parameters, localized onboarding content.
6. **Operability for customers:** data export (their data is theirs), import tooling for supplier registers, role templates, an admin runbook, and support workflows.

**Explicitly deferred from V1.0:** Processing, Inventory, Sales, Finance, AI (beyond the shipped reports), marketplace, Farmer App (fast-follow V1.1 — receipts via SMS carry the trust story until then), second market.

**Why this wins in 12 months:** every item above builds on modules already tested end-to-end; nothing requires new architecture. The pitch to ICP-1/ICP-2 is concrete and demoable today — *collect milk offline, price it explainably, settle it in one click, pay it, prove it* — and each deferral has a credible "it's on the platform roadmap" answer backed by the five-year plan rather than vaporware.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-04 | Product (strategy work order) | Initial product strategy: segments, editions, feature matrix, pricing philosophy, deployment, multi-country, AI, marketplace, roadmap, principles, exclusions, positioning, ICPs, V1.0 definition. |
