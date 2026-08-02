---
id: TAXONOMY
title: Taxonomy of Business Terms
type: reference
status: Approved
version: "1.1"
owner: Docs Guild
created: 2026-08-02
last-updated: 2026-08-02
related: [CAP-0001]
baseline: ARCH-BASELINE-V1
---

# Taxonomy of Business Terms

The structural companion to the [glossary](GLOSSARY.md): where the glossary defines terms alphabetically, the taxonomy organizes them by **kind** — actor, place, object, rule, event, measure — and maps each to the capability domain that governs it. Terms marked **(pending)** are used in the capability model but not yet glossary-defined; each future domain model MUST define its context's pending terms (rule from [QR-0002 §5](../12-quality/QR-0002-gap-analysis.md)).

## 1. Actors — who acts in the ecosystem

| Term | Governing Domain | Glossary |
| --- | --- | --- |
| Producer | FPR / CPR | Defined |
| Cooperative | CPR | Defined |
| Processor | PRO | Defined |
| Collector (pending) | MCL | Pending |
| Veterinarian / para-vet (pending) | FPR | Pending |
| Extension officer (pending) | CPR | Pending |
| Laboratory (pending) | QFS | Pending |
| Carrier / transporter (pending) | MCL | Pending |
| Buyer (B2B) (pending) | CMA | Pending |
| Regulator (pending) | SWC | Pending |
| Ecosystem partner (pending) | ETE | Pending |
| Tenant | ETE | Defined |

## 2. Places & Facilities — where the business happens

| Term | Governing Domain | Glossary |
| --- | --- | --- |
| Farm (pending) | FPR | Pending |
| Bulk Tank | FPR | Defined |
| Collection Center | MCL | Defined |
| Chilling Center | MCL | Defined |
| Processing plant (pending) | PRO | Pending |
| Input store (pending) | CPR | Pending |

## 3. Business Objects — the things acted upon

| Term | Governing Domain | Glossary |
| --- | --- | --- |
| Herd, Lactation | FPR | Defined |
| Animal identity (pending) | FPR | Pending |
| Milk Collection | MCL | Defined |
| Collection Transaction | MCL | Defined |
| Shift | MCL | Defined |
| Collection Session | MCL | Defined |
| Shift Reconciliation | MCL | Defined |
| Hardware Profile | MCL | Defined |
| Cold Chain | MCL | Defined |
| Sample / test result (pending) | QFS | Pending |
| Milk Quality Grade | QFS | Defined |
| Batch (context-dependent — see rule below) | MCL / PRO | Pending |
| Traceability | QFS | Defined |
| Product recipe / specification (pending) | PRO | Pending |
| Order / contract (pending) | CMA | Pending |
| Settlement, Settlement statement | PEF | Defined (Settlement) |
| Deduction / advance (pending) | PEF | Pending |
| Membership / share / Patronage | CPR | Defined (Patronage) |
| Certification / certificate (pending) | SWC | Pending |
| Consent (data) (pending) | ETE | Pending |
| Market pack (pending) | ETE | Pending |

**Context rule:** *Batch* is the canonical example of a context-dependent term (a collection batch ≠ a production batch). Per TPL-0010, each domain model defines its meaning; the glossary will carry one context-qualified entry per meaning.

## 4. Schemes & Rules — the frameworks that govern

| Term | Governing Domain | Glossary |
| --- | --- | --- |
| Milk pricing scheme (pending) | PEF | Pending |
| Quality scheme / grading scheme (pending) | QFS | Pending |
| Quality premium / penalty (pending) | PEF | Pending |
| Withdrawal Period | FPR / QFS | Defined |
| Supervisor Override | MCL | Defined |
| Regulatory obligation (pending) | SWC | Pending |
| Sharing agreement (pending) | ETE | Pending |

## 5. Events — facts the business records (selection)

The full pre-inventory (~250 named business events) lives in the capability catalogs and is traced in [QR-0003 §5](../12-quality/QR-0003-traceability-matrix.md). Representative canon:

| Event | Source Capability |
| --- | --- |
| Milk Collected | MCL.PCK.01 |
| Load Accepted / Rejected | MCL.PCK.02 |
| Quantity Graded | QFS.GRD.01 |
| Settlement Computed / Statement Issued | PEF.SET.01 |
| Payment Confirmed | PEF.SET.02 |
| Animal Registered | FPR.HRD.01 |
| Treatment Recorded / Withdrawal Period Started | FPR.HLT.04 |
| Recall Initiated | QFS.INC.02 |
| Recommendation Issued | DIA.ADV.01 |
| Outbreak Signal Detected | DIA.RSK.01 |

## 6. Measures & Indicators — how the business is quantified

| Term | Governing Domain | Glossary |
| --- | --- | --- |
| Somatic Cell Count (SCC) | QFS | Defined |
| Solids-Not-Fat (SNF) | QFS / PEF | Defined (abbr.) |
| Fat / protein content (pending) | QFS | Pending |
| Bacterial count (pending) | QFS | Pending |
| Yield (per animal/session) (pending) | FPR | Pending |
| Calving interval (pending) | FPR | Pending |
| Feed conversion efficiency (pending) | FPR | Pending |
| OTIF | CMA | Defined (abbr.) |
| Transit loss (pending) | MCL | Pending |
| kg CO₂e per liter (pending) | SWC | Pending |

## 7. Maintenance

- New glossary entries update the matching taxonomy row (Pending → Defined) in the same PR.
- New taxonomy rows require the term to appear in at least one formal document — the taxonomy indexes real usage, it does not speculate.
- Domain models are the primary engine for retiring **(pending)** markers (each defines its ubiquitous language).

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-02 | Lacteva Collect Product Team | Lacteva Collect terms added; Collection point retired in favor of defined Collection Center. |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial taxonomy: 6 kinds, ~60 terms mapped, pending-definition markers set. |
