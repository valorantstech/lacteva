---
id: LACTEVA-FIRST-DAIRY-SALES-AND-PILOT-PACKAGE
title: First Dairy Sales & Pilot Package
type: reference
status: Approved
version: "1.0"
owner: Product & Commercial
created: 2026-08-18
last-updated: 2026-08-18
related: [LACTEVA-MASTER-PRODUCT-ROADMAP, LACTEVA-COMMERCIAL-MODEL-AND-PACKAGING, LACTEVA-P0-PILOT-008-REAL-DAIRY-ONBOARDING-READINESS, LACTEVA-DAIRY-ONBOARDING-INFORMATION-REQUEST-PACK, LACTEVA-BUSINESS-OPERATING-MODEL, LACTEVA-IDENTITY-ENTERPRISE-ARCHITECTURE-AUDIT, LACTEVA-REGULATORY-APPLICABILITY-AUDIT, LACTEVA-HARDWARE-CONNECTOR-DISCOVERY]
baseline: ARCH-BASELINE-V1
---

# Lacteva — First Dairy Sales & Pilot Package

**Commercial preparation only — no code, schema, API, UI, integration, or
invented fact.** Everything a salesperson needs to approach, demo, qualify,
onboard, and run the first real Indian dairy pilot — grounded in the committed
repository. **Discipline tags used throughout:** **FACT** (proven in repo) ·
**CONFIG** (available, depends on dairy data) · **PILOT** (available for the
controlled pilot) · **COMING SOON** (future) · **ENTERPRISE** (future
enterprise) · **TO CONFIRM** (business decision not yet made) · **UNKNOWN**.
**No price, customer, regulation, statistic, integration, or protocol is
invented.**

---

## A. Executive one-page overview

**What Lacteva is (today):** a deployed, working platform that runs a dairy's
milk operations end to end — from a farmer's milk arriving at a collection
centre, through weighing, quality, the dairy's own rate, the printed/shared
**parchi**, and settlement, to customers/outlets, standing orders, delivery,
billing and reporting. **FACT** — proven live and on a real Android handset
(P0-PILOT-004).

**Who we sell to first:** a small-to-medium **private dairy / milk-collection
business** where the owner or manager can approve a controlled pilot. The
architecture stays enterprise-capable; we simply start focused.

**The offer:** a **controlled pilot on a 30-day free trial** (the trial exists
in the product today), configured with the dairy's **own real rate chart,
farmers, outlets and settlement rules**, with the headline proof being **a real
collection reconciled to the dairy's own arithmetic — to the paisa** before
anything goes into production.

**What we need from the dairy:** the items in the committed
**Dairy Onboarding Information Request Pack** — organization details, centres,
staff, farmer list, outlet list, the **actual rate chart**, settlement rules,
FSSAI + Legal Metrology copies, and a signed pilot agreement.

**Commercial:** subscription is **per collection centre** (not per user, not
per litre — decided in code), users included; **prices and payment method are
TO CONFIRM.** No modules are sold separately today.

**Verdict:** **Lacteva is ready to approach the first dairy.** The gate is
business/data/legal, not engineering.

## B. Value proposition

Lacteva is **not "milk collection software."** It is the **operational spine of
a dairy business**: one system that turns fragmented paper/Excel steps —
weighing slips, a rate register, a settlement notebook, a delivery diary, a
receivables ledger — into **one connected, auditable digital chain**, on a
computer for the office and a phone for the field, working **offline** where
there is no signal, and **honest** about where every number came from.

Concrete, existing value (all **FACT / CONFIG**):
- Faster, error-free **collection capture** with the dairy's **own rate** applied automatically.
- A **numbered parchi** the farmer can be handed on paper or by shared text.
- **Settlement** on the dairy's own cycle, reconciled line-by-line to collections.
- **Customers/outlets, standing orders, routes, delivery, billing and receivables** — the sales side, not just procurement.
- **Reporting** and a live dashboard — the owner sees the whole dairy at a glance.
- **Role-based access** and **multi-centre** operation, with a full **audit trail**.
- **One login per person** across the apps they need.

## C. Current product capabilities (what we can honestly sell TODAY)

| Capability | Status |
|---|---|
| Farmer/supplier management + CSV import | **FACT / CONFIG** |
| Collection centres, operators, sessions/shifts, readiness checks | **FACT** |
| Cow & buffalo, priced as separate products | **FACT** |
| Quantity (kg), FAT/SNF/CLR quality capture with source attribution | **FACT** (**kg today; litres = TO CONFIRM/engineering if chart needs it**) |
| Rate cards (FAT-banded per product, effective dates, per-centre) | **FACT / CONFIG** (the chart is the dairy's) |
| Collection lifecycle → **parchi** (numbered, print/share, bilingual EN/HI) | **FACT** |
| Settlement (free cycles), billing, payments, receivables | **FACT / CONFIG** |
| Customers/outlets, standing orders, routes, vehicles, drivers, delivery | **FACT** |
| Offline capture + sync (operator + driver) | **FACT** (proven on a real handset) |
| Reporting (12 report views + dashboard), audit trail | **FACT** |
| RBAC roles + PostgreSQL row-level tenant isolation | **FACT** |
| Backup + off-site replication + restore | **FACT** |
| Supplier FAT/SNF **deviation flag** (statistics, non-blocking) | **FACT** (the only AI today) |
| **Not supported today:** litres pricing / FAT×SNF grid pricing (unless the chart needs it → engineering), advances/loans at collection time | **COMING SOON / V1** |

Boundaries by category, for honesty in the room: **A. Available NOW** = the
lifecycle above. **B. Configuration-dependent** = rate chart, farmer/outlet
lists, settlement cycle, centres/users. **C. Pilot-dependent** = a real dairy's
data + sign-off. **D. Coming Soon** = §T. **E. Future/Enterprise** = §U. **F.
Not currently supported** = anything in §T/§U — **never presented as available.**

## D. Target customer profile

Numeric thresholds are **not** defined in the repository — they are
**TO CONFIRM — SALES QUALIFICATION PARAMETER**, not guessed here.

- **1 · Ideal first customer:** a private dairy / milk-collection business with
  a **small number of collection centres**, running **cow and/or buffalo**
  collection on a **FAT-banded (kg) rate chart**, today on **paper/Excel**, with
  an **owner/manager who can approve a pilot** and staff willing to use an
  Android phone. Settlement on a simple cycle. *(Centre/farmer/volume numbers:
  TO CONFIRM.)*
- **2 · Good customer:** the above with a slightly more complex chart or a few
  centres; distribution to outlets as well as procurement.
- **3 · Possible customer:** larger multi-centre dairy, or a chart that needs
  **litres or FAT×SNF grid** (a bounded engineering increment first — flag it,
  don't hide it).
- **4 · Poor first-pilot customer:** anyone needing, on day one, a capability
  that is **Coming Soon/Enterprise** (SAP, GPS, automated hardware, farmer app,
  multi-legal-entity federation) — good future customers, wrong *first* pilot.
- **5 · Enterprise (future expansion):** multi-region/multi-plant organizations,
  cooperatives/unions — **ENTERPRISE roadmap**, not the first pilot.

## E. Dairy pain points (the ones Lacteva addresses today)

Manual weighing slips and re-entry; a rate register applied by hand (error-
prone at settlement); a settlement notebook nobody can audit; farmers waiting
on and disputing payments; no single view across centres; deliveries and
receivables tracked separately from collection; and no honest record of *how*
each reading was taken. **Every one of these maps to an existing capability
(§C)** — no future feature is needed to relieve them.

## F. Lacteva solution (existing capabilities only)

Collection captured once, priced by the dairy's own chart, receipted as a
parchi; settlement reconciled to those collections; the sales side (outlets →
orders → routes → delivery → billing → receivables) on the same system; the
owner's dashboard over all of it; role-scoped access and an audit trail; and it
keeps working offline in a dead-zone centre. **This is the pilot.**

## G. End-to-end milk lifecycle (as it runs today)

```
Procurement:  Farmer → Collection Centre → Operator → Weight (kg) → FAT/SNF/CLR
              → Rate (dairy's chart) → Accept → Complete → PARCHI → Settlement
Distribution: Customer/Outlet → Standing Order → Route → Driver → Delivery
              → Billing → Receivable
Across both:  Reporting · Audit · Role-based access · Multi-centre · Offline
```
All **FACT**. *(Procurement transport — centre→chilling→plant — is a separate
future domain, not this; §U.)*

## H. Application ecosystem (today)

| Application | Who | Status |
|---|---|---|
| **Lacteva Management Portal** (browser) | owner, managers, finance, sales, auditor | **FACT** |
| **Lacteva Collection App** (Android) | collection operators, centre managers | **FACT** |
| **Lacteva Driver App** (Android; same binary, persona-routed) | drivers | **FACT** |
| Farmer App / Customer Portal / Hardware Connector / SAP layer | — | **COMING SOON / FUTURE** (§T) |

## I. User / login model

**One person → one Lacteva identity → multiple roles → multiple centres/scopes →
multiple applications.** **FACT** (proven in P0-PILOT-006). The same login works
across every app that person needs — **no separate password per app.** Roles:
Owner/Admin/Manager, Centre Manager, Collection Operator, Finance Manager/
Officer, Sales Officer, Driver, Auditor.

- **Login users:** the staff above.
- **Business records (NOT logins):** farmers, customers/outlets.
- **Assets (NOT logins):** devices (scale, analyzer, printer).

**Farmers and customers do not get logins for the pilot.** A farmer app and a
customer portal are **FUTURE OPTIONS** (§T), not part of the pilot.

## J. Demo script (10–15 minutes; demonstrate only what exists)

Run against a demo/synthetic org. **Say only what is on screen.** *(Do not
claim hardware, GPS, SAP, AI beyond the deviation flag, or any future app.)*

1. **The dairy, set up** — show the organization + its collection centres. *(30s)*
2. **Operator logs in** — one login; the phone opens the **Collection App**
   (not the office portal) — "the same person's one login knows they're an
   operator." *(1m)*
3. **Pick the farmer** — search by code/name; "farmers are records, no app
   needed." *(1m)*
4. **Milk** — choose **cow/buffalo**; container. *(30s)*
5. **Weight** — enter gross/tare; net computed. *(If asked about a machine:
   "manual today; the connector is a planned option — not in this pilot.")* *(1m)*
6. **Quality** — enter **FAT / SNF / CLR**. *(1m)*
7. **Rate** — the **dairy's own chart** prices it automatically; "we configure
   your chart; we never invent a rate." *(1m)*
8. **Complete** — accept → COMPLETED. *(30s)*
9. **Parchi** — show the numbered receipt; print/share; "the farmer's copy —
   paper or a shared message, no app." *(1m)*
10. **Settlement** — show a settlement for a period, lines tracing to
    collections. *(1–2m)*
11. **Owner view** — the **dashboard**: collections, value, average FAT,
    receivables. *(1–2m)*
12. **Sales side (if relevant)** — an outlet's standing order → a delivery run
    on the **Driver App** → outcome → invoice. *(1–2m)*
13. **Reports** — daily collection, by-supplier, receivables. *(1m)*
14. **Offline** *(optional, powerful)* — airplane mode, capture, sync-once. *(1m)*
15. **What's next** — "we configure *your* chart and lists, then reconcile one
    of *your* real collections to the paisa before go-live." *(30s)*

**Never in the demo:** fake screenshots, a fake device reading, a fake SAP/GPS/
WhatsApp/AI result, or any "coming soon" screen presented as working.

## K. Pilot proposal (from the existing commercial model)

- **Purpose:** prove Lacteva runs the dairy's real operations correctly, on the
  dairy's own data, before any commitment.
- **Duration:** a **30-day trial exists in the product** (the plan default).
  Whether the pilot equals exactly 30 days is **TO CONFIRM**.
- **Price:** the trial is **free**; the paid plan is **per centre**, **price
  TO CONFIRM.** No modules sold separately.
- **Lacteva provides:** configuration, imports, rate-card build, settlement
  setup, Day-0 verification + reconciliation, support during the pilot, backup.
- **The dairy provides:** the onboarding pack (§N), staff availability, and
  sign-off.
- **Scope:** §L. **Success:** §M. **Exit/continuation:** at pilot end, convert
  to the paid per-centre plan (**all data/config survives — same account**) or
  stop; **billing starts only when the paid subscription begins.**

## L. Pilot scope (recommended, bounded)

Prefer a **bounded first deployment** over digitizing the whole dairy at once:
**one organization · one branch · one or a few collection centres · the
operators at those centres · that centre's farmers · the dairy's real rate
chart · real collections · one real settlement reconciliation.** Add the sales
side (outlets/routes/delivery) **only if the dairy wants it in the pilot.**
**Recommended starting scope — TO CONFIRM with the dairy.** *(No centre/farmer
counts are hard-coded; the repository does not define them.)*

## M. Pilot success criteria (from existing functionality)

- [ ] Staff authenticate; correct role/access; correct centre visibility.
- [ ] Farmer records loaded correctly (counts match the file).
- [ ] Collection captured; quantity + quality recorded.
- [ ] **Rate calculated according to the dairy's actual chart.**
- [ ] Parchi generated.
- [ ] Settlement reconciled.
- [ ] Customer/outlet + delivery workflow works (if in scope).
- [ ] Reports available; audit trail preserved; backup verified.
- [ ] **No material financial discrepancy.**
- [ ] **Owner/manager signs off.**

**The headline criterion:** a **real collection reconciles to the dairy's own
arithmetic — to the paisa.** *(No invented percentages or SLA numbers.)*

## N. Dairy onboarding requirements

**Authoritative source: `LACTEVA-DAIRY-ONBOARDING-INFORMATION-REQUEST-PACK.md`**
(do not create a conflicting second model). In summary, the dairy provides:
organization details; collection centres; staff/users; farmer list;
customer/outlet list (if delivering); the **actual rate chart**; settlement
rules; **FSSAI** licence copy; **Legal Metrology** scale certificate (where
applicable); **signed pilot agreement**; privacy/consent wording. **The dairy
remains the source of truth** for all of it.

## O. Responsibilities — Lacteva vs Dairy

| | Lacteva | Dairy |
|---|---|---|
| Rate chart, farmer/outlet lists, settlement rules | configures | **provides (source of truth)** |
| FSSAI / Legal Metrology copies | files, verifies presence | **holds/provides** |
| Org/centre/user setup, imports, rate-card build | **executes** | approves |
| Day-0 reconciliation | runs verification | **signs off** |
| Backup/restore, production config, security | **owns** | — |
| Scale stamping, hygiene, floor-price compliance | records/evidences | **owns (regulated entity)** |
| Subscription | invoices (when billing exists) | **buyer** |

## P. Commercial model reference

Per `LACTEVA-COMMERCIAL-MODEL-AND-PACKAGING.md` (grounded in code, DEMO-026):
**per-collection-centre** subscription; **not per user, not per litre**; **30-
day trial** (`LACTEVA_TRIAL`) → **STANDARD** (per-centre, billable); **prices
absent — set per currency when decided (TO CONFIRM)**; **no payment gateway
contracted (TO CONFIRM)**; **no modules sold separately today.** Users are
included; multi-role/multi-centre on one identity **costs nothing extra.**

## Q. FAQ (answered only from repository evidence)

- **What is Lacteva?** A platform that runs a dairy's milk operations end to end
  — collection, quality, rate, parchi, settlement, outlets, delivery, billing,
  reporting. **FACT.**
- **Who is it for?** Dairies / milk-collection businesses; the first pilot suits
  a small-to-medium private dairy.
- **Do farmers need smartphones?** **No.** **Do farmers need a login?** **No** —
  they are records; they receive a parchi.
- **Do operators need a login?** **Yes** — one login, on the Collection App.
- **Can one person work at multiple centres?** **Yes** (scoped role grants).
  **Use multiple apps?** **Yes — with one login.** **FACT.**
- **Can we keep our existing rate chart?** **Yes** — we configure *your* chart.
  **Does Lacteva invent/change our rate?** **No** — never.
- **Can we use our existing farmer list / Excel / CSV?** **Yes** — CSV import
  with preview and duplicate detection. **FACT.**
- **What if internet is unavailable?** Capture works **offline** and syncs later,
  once each. **FACT** (proven on a handset).
- **How is data protected?** Role-based access + database-level tenant isolation
  + audit trail + verified backups. **FACT.** **Who owns the data?** The dairy.
- **Hardware later?** The **software seam exists**; a connector is a **planned
  option**, gated on a device-discovery visit — **not** in this pilot. **COMING SOON.**
- **SAP/ERP later?** **Enterprise roadmap.** Not implemented. **ENTERPRISE.**
- **Is GPS/WhatsApp/AI mandatory?** **No.** GPS and messaging are **future**;
  the only AI today is a non-blocking FAT/SNF deviation flag.
- **Can we start small / expand to more centres / support enterprise later?**
  **Yes / yes / yes** — bounded pilot, per-centre expansion, enterprise-capable
  architecture. **FACT / ENTERPRISE.**
- **What does it cost?** **TO CONFIRM** — the trial is free; the paid plan is
  per centre.

## R. Objection handling (never promise a non-existent feature)

- **"We already use Excel."** Keep your data — import it as CSV; Lacteva adds
  the rate calculation, parchi, reconciled settlement, and one view Excel can't.
- **"We already have a collection machine."** Keep it — enter its readings
  manually today; a connector to read it automatically is a planned option
  (after a device-discovery visit), not required for the pilot.
- **"We don't want to change our rate chart."** You don't — we configure *your*
  chart and reconcile a real collection to your own arithmetic to the paisa.
- **"Our operators aren't technical."** The Collection App is a guided step-by-
  step flow on a normal Android phone; proven on a real handset.
- **"We don't want farmers to install an app."** They don't — farmers are
  records and get a parchi; no app, no login.
- **"We already have an ERP / need SAP."** Lacteva runs dairy operations today;
  SAP/ERP integration is on the enterprise roadmap — we won't pretend it's
  ready.
- **"We need WhatsApp / automatic weighing."** Both are future/planned — the
  parchi shares as text today, and weighing is manual-first; neither blocks a
  pilot.
- **"We're worried about data."** Role-scoped access, database-level isolation,
  audit trail, verified off-site backups; your data stays yours.
- **"We want to start with one centre / test before paying."** Exactly the plan
  — a bounded pilot on a free 30-day trial; you pay only if you continue.

## S. Competitive / category positioning (no competitor names, no market claims)

| | Paper/manual | Excel/manual | Collection-only software | ERP-heavy | **Lacteva** |
|---|---|---|---|---|---|
| Collection + rate + parchi | manual | manual | ✓ | partial | **✓** |
| Settlement reconciled to collections | manual | manual | partial | ✓ | **✓** |
| Distribution (outlets/orders/routes/delivery/billing) | separate | separate | usually no | ✓ | **✓** |
| One app, offline, field + office | — | — | varies | heavy | **✓ (offline, one login)** |
| Multi-centre + role access + audit | — | — | varies | ✓ | **✓** |
| Fit for a small dairy to start | — | ✓ (but manual) | ✓ | **too heavy/costly** | **✓ (bounded pilot)** |
| Honest data provenance (how each reading was taken) | — | — | rare | rare | **✓** |

*Category-level only; based on capabilities Lacteva actually supports.*

## T. Coming Soon roadmap (preserved — never shown as available)

**COMING SOON / PLANNED:** hardware connector + automated scale/analyzer
capture + printer integration (evidence-gated, after a device-discovery visit);
messaging (WhatsApp/SMS/email — email config-only; SMS/WhatsApp need vendor
paperwork); supplier trend analytics; advances/loans at settlement; FSSAI/GST
fields on documents.
**FUTURE:** AI beyond the MVP flag (anomaly detection, forecasting); advanced
analytics; GPS/tracking; chilling centre; BMC; procurement transport;
plant/processing; farmer app; customer/outlet portal.
**ENTERPRISE:** SAP/ERP integration; enterprise integration/API layer;
enterprise SSO; global identity; parent/federation model; organization-to-
organization relationships; enterprise reporting; multi-region/multi-plant.

**None is operational. None has a fake screen, button, API, or demo. May be
labelled "Coming Soon / Planned / Enterprise Roadmap / Future" — never
"available."**

## U. Enterprise future (the long story, preserved)

Lacteva is **not** designed only for a small dairy. The architecture evolves —
additively, without a rewrite (Identity + Enterprise audit: **GO**) — along:
**Dairy → Collection Centres → Chilling/BMC → Procurement Transport →
Plant/Processing → Enterprise → SAP/ERP → Advanced Analytics/AI.** The first
pilot starts focused; the platform stays enterprise-capable. **ENTERPRISE /
FUTURE.**

## V. AI / SAP / GPS / hardware positioning (honesty rules)

- **AI:** only the **supplier FAT/SNF deviation flag** exists today (statistics,
  non-blocking). Everything else is **future** — never presented as implemented.
- **SAP/ERP:** **not implemented** — enterprise roadmap; never mocked or claimed.
- **GPS:** **not implemented**, **never a pilot dependency**.
- **Hardware automation:** **manual-first today**; the connector is **evidence-
  gated future** — never presented as working.
- **Farmer/customer apps, enterprise SSO/federation:** **future options** — not
  available.

## W. Sales qualification checklist

- [ ] Dairy / milk-collection business with collection centre(s). **FACT-fit.**
- [ ] Owner/manager who can **approve a pilot**. **(decision-maker access)**
- [ ] Cow and/or buffalo on a **FAT-banded (kg) chart** *(else flag litres/grid
      as an engineering pre-step)*.
- [ ] Currently on **paper/Excel** (clear before/after value).
- [ ] Staff willing to use an **Android phone** at the centre.
- [ ] A simple **settlement cycle** they can describe.
- [ ] Willing to run a **bounded controlled pilot** and provide the onboarding
      pack.
- [ ] No **day-one dependency** on a Coming Soon/Enterprise item (§T).
- [ ] *(Centre/farmer/volume thresholds: **TO CONFIRM — SALES QUALIFICATION
      PARAMETER**.)*

## X. Pilot readiness checklist (before go-live)

Mirrors `LACTEVA-P0-PILOT-008` §S: signed agreement · FSSAI + Legal Metrology
copies · four artifacts (rate chart, farmer list, outlet list, settlement
rules) · org/centres/users created + access-checked · farmers/outlets imported
(counts verified) · rate card published + human-reviewed + **paisa-reconciled**
· settlement configured + dry-run reconciles · production backup retention set
to 30 days + verified/off-site · Day-0 technical green + **dairy sign-off** ·
conditional engineering (litres/FAT×SNF) **only if the chart required it.**

## Y. Sales conversation script (short)

**Open:** "You run milk collection on paper/Excel today. Lacteva puts your whole
milk operation — collection, your own rate, the farmer's parchi, settlement,
and your deliveries and accounts — into one system that also works offline at
the centre." **Prove:** run the §J demo. **De-risk:** "We start with a bounded
pilot on a free 30-day trial, configured with *your* rate chart and *your*
farmers — and before anything goes live, we recompute one of *your* real
collections to the paisa." **Ask:** "Can we set up 30 minutes for me to show
this, and would you share your current rate chart and a sample parchi so we can
prepare?" **Never claim** a Coming Soon feature is available.

## Z. Next steps

1. Send the **Dairy Onboarding Information Request Pack** (committed;
   shareable). 2. Book the **demo** (§J). 3. **Qualify** (§W). 4. Get the
   **agreement signed** and the **four artifacts** in. 5. Execute the
   **P0-PILOT-008 runbook** + Day-0 reconciliation. 6. On sign-off, start the
   pilot; convert to the **per-centre** paid plan on continuation.

---

## Appendix — ready-to-use materials (consistent with the above)

*Fill the [brackets]; never insert an invented price, statistic, or claim.*

### 1. One-page handout (copy)

> **Lacteva — run your whole milk operation in one place.**
> Collection · Quality · Your own rate · Parchi · Settlement · Outlets ·
> Delivery · Billing · Reports — on a computer for the office and a phone for
> the centre, working **offline** when there's no signal.
> • Keep **your** rate chart — we configure it; we never change your rate.
> • Farmers need **no app and no login** — they get a parchi.
> • **One login per person**, across every app they use.
> • Start with a **bounded pilot on a free 30-day trial**; we reconcile a real
> collection **to the paisa** before go-live.
> *Contact: [name] · [mobile] · [email].*

### 2. Dairy-owner presentation outline

1. Your operation today (paper/Excel pain). 2. What Lacteva does end to end
(the lifecycle, §G). 3. Live demo (§J). 4. Your data stays yours; works offline;
role-based access. 5. The bounded pilot + free trial + paisa reconciliation.
6. What we need from you (the request pack). 7. What's on the roadmap
(clearly-labelled Coming Soon — not today). 8. Next steps.

### 3. WhatsApp introduction (copy)

> Namaste [name], this is [your name] from Lacteva. We help dairies run milk
> collection, quality, your own rate, the farmer parchi, settlement, and
> deliveries in one simple system — on a phone at the centre and a computer in
> the office, and it works even without internet. Could I show you a 15-minute
> demo this week? You can keep your existing rate chart and farmer list.

### 4. Email introduction (copy)

> **Subject:** A simpler way to run your dairy's milk operations
>
> Dear [name],
> Lacteva is a platform that runs a dairy's milk operations end to end —
> collection, quality, your own rate, the farmer's parchi, settlement, and your
> outlets/deliveries/billing — on a computer for the office and an Android phone
> for the centre, working offline where there's no signal.
> A few things dairies like: you keep your own rate chart (we configure it, we
> never change your rate), farmers need no app or login, and each person has a
> single login across the apps they use.
> We'd start with a bounded pilot on a free 30-day trial, set up with your real
> data — and before anything goes live, we recompute one of your own recent
> collections to the paisa so you can see it matches your books exactly.
> Could we set up a short demo? If you can share your current rate chart and a
> sample parchi, we'll prepare with your numbers.
> Best regards, [name] · [mobile] · [email]

### 5. Pilot proposal template

> **Lacteva Controlled Pilot — [Dairy name]**
> **Purpose:** validate Lacteva on [Dairy]'s real operations before commitment.
> **Scope (recommended — to confirm):** 1 organization · [branch] · [1–N]
> collection centre(s) · operators at those centres · their farmers · [outlets/
> delivery: in/out of scope] · real rate chart · one real settlement.
> **Duration:** free 30-day trial *(pilot length to confirm)*.
> **Lacteva provides:** configuration, imports, rate-card build, settlement
> setup, Day-0 verification + paisa reconciliation, support, backup.
> **[Dairy] provides:** the onboarding pack, staff availability, sign-off.
> **Success:** §M — headline: a real collection reconciles to [Dairy]'s own
> arithmetic to the paisa; owner signs off.
> **Continuation:** convert to the per-centre paid plan (price to confirm); all
> data/config survives; billing starts only on continuation. **Exit:** stop at
> pilot end with no obligation.
> **Signatures:** [Dairy] ________ · Lacteva ________ · Date ______

### 6. Sales qualification form

> Dairy: ______  Contact/role: ______  Mobile/email: ______
> Business type (private dairy / collection business / other): ______
> Collection centres (count): ______ *(TO CONFIRM parameter)*
> Milk types (cow/buffalo/both): ______  Rate basis (FAT / FAT+SNF / formula;
> kg/litre): ______
> Current process (paper / Excel / software): ______
> Settlement cycle: ______  Distributes to outlets? (Y/N): ______
> Decision-maker can approve a pilot? (Y/N): ______
> Any day-one need that is Coming Soon/Enterprise (SAP/GPS/auto-hardware/farmer
> app)? (list): ______
> Qualification: **Ideal / Good / Possible / Poor-first-pilot / Enterprise-
> future** (circle).  Notes: ______

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-18 | Product & Commercial | First dairy sales & pilot package: value proposition, today's capabilities (FACT/CONFIG tagged), target profiles, demo script, pilot proposal/scope/success, onboarding summary (referencing the request pack), responsibilities, commercial reference (per-centre, prices TO CONFIRM), FAQ, objection handling, category positioning, preserved Coming-Soon/Enterprise roadmap, AI/SAP/GPS/hardware honesty rules, qualification + readiness checklists, conversation script, and ready-to-use materials (handout, WhatsApp, email, proposal template, qualification form). No code; no invented price/customer/regulation/statistic/integration; roadmap fully preserved (P0-COMM-001). |
