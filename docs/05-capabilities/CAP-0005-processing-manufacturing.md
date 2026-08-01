---
id: CAP-0005
title: Processing & Manufacturing Domain
type: cap
status: Draft
version: "0.1"
owner: Enterprise Architecture
created: 2026-08-02
last-updated: 2026-08-02
related: [CAP-0001, CAP-0003, CAP-0004, CAP-0006]
---

# CAP-0005 — Processing & Manufacturing Domain (PRO)

## 1. Domain Definition

Transforming accepted raw milk into dairy products — deciding what to make from the day's intake, making it, packaging it, and holding it until sale. The domain's defining constraint is that its main input is **perishable, arrives daily in variable quantity and quality, and cannot be stopped**: cows do not pause production when demand dips.

**Global note:** spans a village dairy making paneer or yogurt in open vats to a multi-line plant producing UHT, powder, and cheese. Product portfolios differ radically by market; the abilities do not.

## 2. Subdomain Overview

| Code | Subdomain | Ability |
| --- | --- | --- |
| `PLN` | Production Planning | Allocating perishable intake to products profitably |
| `MFG` | Manufacturing | Executing transformation with controlled recipes and yields |
| `PKG` | Packaging | Getting product into compliant, sellable units |
| `INV` | Inventory | Holding raw, in-process, maturing, and finished goods |

```mermaid
flowchart LR
    IN(Accepted intake<br>from MCL) --> PLN[PLN Planning]
    PLN --> MFG[MFG Manufacturing] --> PKG[PKG Packaging] --> INV[INV Inventory]
    INV --> OUT(To CMA commerce)
```

## 3. PLN — Production Planning

### PRO.PLN.01 — Milk Intake Allocation & Production Planning

**Purpose:** Decide, for each day's actual intake (volume and composition), which products to make in which quantities on which lines.

| Attribute | Detail |
| --- | --- |
| Actors | Production planner; plant manager; sales/demand planner |
| Business value | The daily allocation decision is the processor's core profit lever: the same milk can become high-margin cheese or break-even powder |
| Dependencies | MCL.PCK.02 (accepted intake); QFS.GRD.01 (composition/quality determines fitness for products); CMA.SLS.01 (demand); PRO.MFG.02 (recipes) |
| Business events | Production Plan Issued; Plan Revised for Intake Variance; Line Scheduled |
| AI opportunities | Profit-optimal allocation of variable intake across products; intake-composition prediction from collection data |
| Reports | Daily production plan vs actual; contribution margin by allocation; intake utilization |
| KPIs | Contribution margin per liter of intake; plan adherence %; unallocated intake % |

### PRO.PLN.02 — Demand–Supply Balancing

**Purpose:** Reconcile the inflexible milk supply with fluctuating product demand over weeks and seasons — buffer products, inventory strategy, supply commitments.

| Attribute | Detail |
| --- | --- |
| Actors | Supply planner; sales leadership; procurement (supplementary purchases); collection planning |
| Business value | Prevents the two chronic failures of dairy processing: dumping surplus milk at distress prices and failing contracted deliveries in deficit |
| Dependencies | DIA.FOR.01 (supply forecast); DIA.FOR.02 (demand forecast); MCL.RTE.02 (collection capacity); CMA.PRI.01 (commitments) |
| Business events | Supply–Demand Position Updated; Surplus Projected; Deficit Projected; Balancing Action Decided |
| AI opportunities | Integrated supply–demand simulation; buffer-product mix optimization (what to make for storability) |
| Reports | Rolling balance position; balancing action log; seasonal planning pack |
| KPIs | Forecast balance accuracy; distress-sale volume %; contracted delivery fulfillment % |

## 4. MFG — Manufacturing

### PRO.MFG.01 — Production Execution & Yield Management

**Purpose:** Execute production runs — batch by batch — recording inputs, process parameters, outputs, and losses against expected yields.

| Attribute | Detail |
| --- | --- |
| Actors | Production operators; shift supervisors; quality control |
| Business value | Yield percentage points are margin: knowing where milk solids are lost (and stopping it) is continuous money |
| Dependencies | PRO.PLN.01 (what to run); PRO.MFG.02 (how to run it); QFS.TRC.01 (batch records feed traceability) |
| Business events | Batch Started; Batch Completed; Yield Variance Recorded; Batch Held for Quality |
| AI opportunities | Yield prediction and deviation root-cause analysis; process-parameter optimization per product |
| Reports | Batch records; yield analysis by product/line/shift; loss accounting |
| KPIs | Yield vs standard %; batch right-first-time %; solids loss % |

### PRO.MFG.02 — Product Recipe & Specification Management

**Purpose:** Define and govern what each product **is** — composition, process parameters, quality specifications — and manage changes to it.

| Attribute | Detail |
| --- | --- |
| Actors | Product development; quality assurance; regulatory affairs; production |
| Business value | Consistent product identity across batches, plants, and markets; controlled change instead of recipe drift |
| Dependencies | SWC.REG.01 (compositional standards per market); QFS.GRD.02 (input quality requirements); CMA.EXP.01 (destination-market specs) |
| Business events | Specification Approved; Specification Revised; Specification Retired |
| AI opportunities | Reformulation suggestion under input-cost or regulatory changes |
| Reports | Specification register; change history; specification compliance by batch |
| KPIs | Batches within specification %; specification change lead time |

## 5. PKG — Packaging

### PRO.PKG.01 — Packaging & Labeling Management

**Purpose:** Package products into sellable units with compliant labels — declarations, dates, batch codes, market-specific language and marks.

| Attribute | Detail |
| --- | --- |
| Actors | Packaging operators; label/regulatory compliance; marketing; certification bodies (marks) |
| Business value | Labeling errors are a top cause of avoidable recalls and border rejections; packaging is also the product's face to the buyer |
| Dependencies | PRO.MFG.01 (what is packaged, batch identity); SWC.REG.01 + ETE.LOC.01 (labeling law per market); SWC.CRT.01 (certification marks) |
| Business events | Packaging Run Completed; Label Version Approved; Labeling Error Detected |
| AI opportunities | Automated label compliance checking per destination market; packaging line defect detection |
| Reports | Packaging output; label version register; packaging loss analysis |
| KPIs | Labeling error incidents (target: zero); packaging material loss %; line efficiency |

## 6. INV — Inventory

### PRO.INV.01 — Raw & Finished Goods Inventory

**Purpose:** Know and manage what is on hand — raw milk in silos, ingredients, packaging materials, finished goods — across locations.

| Attribute | Detail |
| --- | --- |
| Actors | Warehouse/stores staff; production planner; sales (available to promise) |
| Business value | For perishables, inventory accuracy is not bookkeeping: it is what prevents both stock-outs and write-offs |
| Dependencies | PRO.MFG.01 (production in/out); CMA.SLS.01 (reservations); QFS.TRC.01 (batch-level identity in stock) |
| Business events | Stock Received; Stock Issued; Stock Adjusted; Stock Reserved |
| AI opportunities | Perishable-aware stock optimization; shrinkage anomaly detection |
| Reports | Stock position by location/batch/age; movement history; shrinkage analysis |
| KPIs | Inventory accuracy %; stock-out incidents; write-off % of production value |

### PRO.INV.02 — Maturation & Shelf-Life Management

**Purpose:** Manage time-dependent inventory — cheese maturation, product aging, and the shelf-life clock on everything — so product is sold at peak value, not written off.

| Attribute | Detail |
| --- | --- |
| Actors | Maturation/warehouse specialists; quality assurance; sales |
| Business value | Maturation converts time into value (cheese); shelf-life converts time into loss (fresh products) — both need active clock management |
| Dependencies | PRO.INV.01; QFS.TST.02 (maturation grading); CMA.SLS.01 (sell-by-driven prioritization) |
| Business events | Maturation Lot Registered; Maturation Assessment Recorded; Shelf-Life Warning Raised; Product Expired |
| AI opportunities | Maturation outcome prediction (grade at target age); markdown/redistribution optimization before expiry |
| Reports | Maturation stock ledger; expiry risk report; age-value analysis |
| KPIs | Expiry write-off %; % lots reaching target maturation grade; average remaining shelf-life at dispatch |

## 7. Cross-Domain Dependencies

| This Domain Needs | From | For |
| --- | --- | --- |
| Accepted intake with quality data | MCL, QFS | Planning and allocation |
| Demand signals, orders, commitments | CMA | What to produce |
| Supply and demand forecasts | DIA | Balancing |
| Compositional/labeling regulation per market | SWC, ETE | Recipes and packaging |
| Its batch records consumed by | QFS | Traceability and recall |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | 2026-08-02 | Enterprise Architecture | Initial draft: 4 subdomains, 7 capabilities. |
