---
id: LC-REVIEW
title: Lacteva Collect — Review Notes (Assumptions, Ambiguities, Questions)
type: reference
status: Draft
version: "0.1"
owner: Lacteva Collect Product Team
created: 2026-08-02
last-updated: 2026-08-02
related: [PDT-0001, PSP-0001, PSP-0009]
---

# Lacteva Collect — Review Notes

The confirmation register for this package. **Nothing here changes the approved architecture** — it records what the implementation had to assume, what was ambiguous, and what needs an owner's answer. Each item carries a stable ID; resolutions update the item (never delete it) and propagate to the affected PSP in the same PR.

## 1. Provenance Statement (read first)

**P1 — Source material.** The three approved chapters (Actors & Operational Roles, Collection Center Architecture, Shift Management Engine) were commissioned as externally decided, but **their source text is not present in this repository**. This package was therefore derived from the approved capability model (CAP-0003, CAP-0004, CAP-0008, CAP-0007) and standard collection-center operating practice. Every detail below the capability level is a **derivation, not a transcription**, and requires architecture-owner confirmation before the package's approval cycle. If the source chapters exist elsewhere, adding them (or diffing against them) is the single highest-value review action.

## 2. Assumptions (A-series)

| ID | Assumption | Where Applied | Risk if Wrong |
| --- | --- | --- | --- |
| A1 | Lacteva Collect covers **producer delivery to centers** only; farm-gate tanker/route pickup is out of scope for these chapters | PDT-0001 §6, PSP-0002 | Package scoped too narrow; route flows need their own chapter |
| A2 | The actor set is the seven roles in PSP-0001; no separate cashier/tester roles at launch | PSP-0001 | Role model too coarse for large centers |
| A3 | One person may hold Operator + Supervisor roles, but never both for the same shift's override decisions | PSP-0001 §3 | Small single-person centers may need a market-parameterized relaxation |
| A4 | Shift states are the 8 in PSP-0004; no separate "audit hold" state | PSP-0004 | State machine revision cascades to events and rules |
| A5 | One shift wraps one collection session by default; multi-session shifts are configuration | PSP-0003 §1 | Session/shift arithmetic in metrics changes |
| A6 | Variance formula: (opening + intake) − (dispatched + closing), tolerance as % of recorded intake | PSP-0006, R05 | Reconciliation semantics change; metric history breaks |
| A7 | One operator device per shift (single-writer offline model) | PSP-0004 §4 | Multi-device centers need conflict rules the package doesn't define |
| A8 | Hardware profiles are exactly three classes (Basic/Standard/Advanced) | PSP-0007 | Check lists and provenance rules re-partition |
| A9 | Payment/cash handling at the center (advances, cash payout) is **not** in these chapters — settlement is downstream (PEF.SET) | Whole package | If Collect handles cash, a chapter (rules, reconciliation) is missing |
| A10 | Member self-service (viewing own records) is product scope but not specified in these three chapters | PDT-0001 §2 | Audience table overstates near-term surface |

## 3. Ambiguities Found in the Repository (AMB-series)

| ID | Ambiguity | Current Handling |
| --- | --- | --- |
| AMB1 | *Collection center* vs *chilling center*: the glossary defines Chilling Center; the capability model (MCL.CCH.01) centers on chilling centers, but many delivery points have no cooling | PSP-0002 defines collection center as the superset; chilling center = cooled profile. Glossary updated accordingly — needs owner confirmation |
| AMB2 | MCL.PCK.01 is named "Farm Pickup & Quantity Recording" yet covers both pickup and center delivery archetypes | Package cites MCL.PCK.01 for center delivery per CAP-0003 §1's dual-archetype note; no rename proposed (rule: never rename approved concepts) |
| AMB3 | Where operator identity/authentication lives (ETE.ONB.01 covers *businesses*, not staff persons) | Treated as future platform identity concern (PSP-0001 §5); flagged as a capability-model gap candidate for ETE |
| AMB4 | Sampling (QFS.TST.01) at centers: mandatory or scheme-dependent? | Modeled as scheme-dependent step ("where scheme requires") |

## 4. Questions for Architecture Owners (Q-series)

| ID | Question | Blocks |
| --- | --- | --- |
| Q1 | Is route/tanker collection a future Lacteva Collect chapter or a separate product? | PDT-0001 boundary |
| Q2 | Does Collect handle any money at the center (advances, input-store sales at check-in)? | Possible missing chapter (see A9) |
| Q3 | What are the launch values (or ranges) for the *(market)* parameters: variance tolerance (R05), suspension threshold (R07), offline age (R09), refusal reasons (R12)? | Market pack content (ETE.LOC.01) |
| Q4 | Is supervisor reconciliation mandatory for every shift, or sampling-based above a trust threshold? | PSP-0004/0006 final semantics |
| Q5 | Are member-facing digital receipts (beyond print) in chapter scope? | PSP-0001/0002 receipts handling |
| Q6 | When a shift cannot open (blocking failure, no override), is manual paper fallback formally recognized and later back-entered, or is the session lost to records? | PSP-0005 §5 failure semantics |
| Q7 | Shift identity format: platform-global or center-scoped sequence? (Stable-identifier policy needs one answer before DBD work) | Future DBD/API |
| Q8 | Do auditors get live access or record exports only? | PSP-0001 auditor role realization |

## 5. Governance Notes (G-series)

| ID | Note |
| --- | --- |
| G1 | This package was drafted **ahead of** the content pipeline order (QR-0006 Track B: CAP approval → BRD → DOM precede product work). Legal under the draft-parallelism rule ([DEPENDENCY-MAP §2](../../03-architecture/DEPENDENCY-MAP.md)) — but the package cannot enter GOV-0002 approval until CAP approval (B2) completes, and PDT-0001 additionally needs BRD-0001 (B3). |
| G2 | Rules R01–R12, the event register, and the shift/center object definitions are **pre-formalizations** of Phase 1 artifacts (POL/EVT/AGG/BPR). On authoring, those become authoritative and the PSPs must be updated to reference them (13-products README rule) — tracked in [TRACEABILITY.md §2](TRACEABILITY.md). |
| G3 | New glossary terms from this package were added to the central glossary (v1.3) rather than a product glossary, per the prefer-references rule. |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | 2026-08-02 | Lacteva Collect Product Team | Initial register: P1, A1–A10, AMB1–AMB4, Q1–Q8, G1–G3. |
