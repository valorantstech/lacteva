---
id: PDT-0001
title: Lacteva Collect
type: pdt
layer: application
status: Draft
version: "0.1"
owner: Lacteva Collect Product Team
created: 2026-08-02
last-updated: 2026-08-02
related: [PSP-0001, PSP-0002, PSP-0003, CAP-0003, CAP-0004]
baseline: ARCH-BASELINE-V1
---

# PDT-0001 — Lacteva Collect

## 1. Proposition

For dairy organizations running collection centers — cooperatives, collectors, processors — Lacteva Collect makes every liter's journey from member to bulk **measured, tested, attributed, and reconciled**, replacing paper registers with shift-controlled records that members trust and settlement can pay against.

## 2. Audience

| Segment / Persona | Primary Jobs Served |
| --- | --- |
| Center Operator | Run collections fast and defensibly; open/close accountable shifts |
| Center Supervisor | Reconcile shifts; catch variance and equipment drift early |
| Producer (Member) | See own deliveries, tests, and receipts; trust the measurement |
| Cooperative / collector management | Center performance, loss control, settlement-ready records |

## 3. Capability Surface

| Capability Domain / IDs | Surfaced As |
| --- | --- |
| MCL.PCK.01, MCL.PCK.03 | Verified collection transactions; dispute-ready records |
| MCL.CCH.01, MCL.CCH.02 | Shift-controlled center operations; cold-chain discipline |
| QFS.TST.03, QFS.TST.01 | Acceptance testing at the point of delivery; sampling |
| CPR.MEM.01 | Member identity and eligibility at check-in |
| FPR.HLT.04 | Withdrawal exclusions honored at the gate |
| PEF.SET.01 *(consumer)* | Settlement-ready quantity/quality records |

## 4. Composition

| Component | Kind | Contribution to the Product |
| --- | --- | --- |
| Collection platform service | Platform service | *(placeholder — PSV to be defined in Phase 1 per the dependency map; will own shift and transaction records)* |
| Quality/testing integration | Platform service | *(placeholder — PSV, QFS context)* |
| Advisory/anomaly agent | AI agent | *(placeholder — AGT candidate per MCL.PCK.01/DIA anomaly-detection opportunities)* |

## 5. Markets

- **Launch archetypes:** smallholder producer-delivery centers (Basic/Standard hardware profiles) and cooled chilling centers (Standard/Advanced) — both covered by one product per [PSP-0007](../../13-products/lacteva-collect/PSP-0007-hardware-profile.md).
- **Localization-sensitive:** variance tolerance, refusal reason lists, suspension thresholds, offline-age limits (all *(market)* parameters in [PSP-0009](../../13-products/lacteva-collect/PSP-0009-business-rules.md)); languages and receipt formats (ETE.LOC.01).

## 6. Boundaries

- **This product is not:** settlement computation (PEF.SET realization), farm-gate tanker pickup on routes (a future product/extension — see REVIEW-NOTES Q1), laboratory management (QFS.TST.02), or member self-service beyond delivery visibility.
- **Relationship to sibling products:** none exist yet; the first sibling boundary will be the route-collection flow if approved.

## 7. Product Success Measures

| Measure | Definition | Direction |
| --- | --- | --- |
| Shift reconciliation rate | Shifts Reconciled without investigation ÷ shifts Closed | Up |
| Mean absolute shift variance | Per [PSP-0008 §3](../../13-products/lacteva-collect/PSP-0008-operational-metrics.md) | Down |
| Measurement dispute rate | Disputes per 1,000 collections (MCL.PCK.03 KPI) | Down |
| Digital receipt coverage | Accepted deliveries with receipts issued ÷ all | Up |

## 8. Requirements Trace

| PRD | Scope | Status |
| --- | --- | --- |
| *(none yet — BRD-0001 precedes; chapter specs in the [product package](../../13-products/lacteva-collect/README.md) serve as pre-PRD source)* | | |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | 2026-08-02 | Lacteva Collect Product Team | Initial draft from approved chapters 1–3 (TPL-0016). |
