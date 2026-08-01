---
id: QR-0002
title: Gap Analysis
type: qr
status: Approved
version: "1.0"
owner: Documentation Engineering
created: 2026-08-02
last-updated: 2026-08-02
related: [QR-0001, QR-0003, QR-0004, CAP-0001]
---

# QR-0002 — Gap Analysis

## 1. Purpose

Identifies what the repository **should contain but does not**: missing business domains and capabilities in the model, missing document types, and conceptual overlaps needing a single owner. Each gap carries a disposition: *model gap* (extend the capability model), *scoping decision needed* (record in/out explicitly), or *sequenced* (already planned; see [QR-0004](QR-0004-documentation-roadmap.md)).

## 2. Business Model Gaps (missing domains / capabilities)

Reviewed against the full dairy value chain and the 1M-business/50-country ambition:

### G-01 — Byproduct & Co-Product Valorization (disposition: model gap — recommend adding)

Whey is ~90% of milk volume in cheesemaking and a defining economic/environmental factor for processors; buttermilk, skim streams, and manure-as-energy are similar. The model has no capability for byproduct planning, valorization, or disposal. **Recommendation:** add a subdomain under PRO (e.g. `PRO.BYP`) in the next CAP-0005 revision — a genuine business ability, not a feature.

### G-02 — Consumer & Retail Engagement (disposition: scoping decision needed)

CMA covers B2B commerce thoroughly but direct-to-consumer sales, consumer marketing, and retail shelf execution only implicitly (CMA.DST.01 stops at the buyer). Many cooperatives and processors run consumer brands. **Recommendation:** an explicit scoping decision — either a future CMA subdomain or a recorded exclusion ("Lacteva serves supply-side commerce; consumer marketing is out of scope"). Do not let scope be decided by omission.

### G-03 — Livestock Trading (disposition: model gap — recommend adding)

Animals are bought and sold constantly (heifers, culls, breeding stock); FPR.HRD.03 tracks movements/custody but no capability covers the **commerce** of animals — valuation, matching, sale. In smallholder markets, livestock marketplaces are a major adjacent value pool. **Recommendation:** evaluate a `CMA.MKT.03 Livestock Trading` capability (or explicit exclusion) at next model revision.

### G-04 — Farm Workforce & Labor (disposition: scoping decision needed)

Milking labor, herd staff, and seasonal workforce are major farm cost/constraint factors; the model is silent. Probably out of platform scope (general workforce management is not dairy-specific) — but that should be a **recorded** exclusion in CAP-0001, not silence.

### G-05 — Lacteva's Own Business Operations (disposition: scoping decision — record as intentionally excluded)

The model deliberately describes the **industry**, not Lacteva's own company (tenant subscription, billing, support, sales). Correct — but CAP-0001 should say so explicitly so no one "finds" the gap repeatedly. **Recommendation:** add a one-paragraph scope exclusion to CAP-0001 §2 at its next revision; Lacteva-company capabilities can get their own model when needed.

### G-06 — Genetics/Recording Institutional Ecosystem (disposition: adequately covered — no action)

Milk recording organizations, breed associations, and genetic evaluation institutions are touched by FPR.BRE.02, FPR.MLK.02, and ETE.DGV.02. Reviewed and judged sufficient at capability granularity; institutional detail belongs in future domain models.

## 3. Documentation-Type Gaps

| Gap | Impact | Disposition |
| --- | --- | --- |
| No `OPS` runbook template | Acceptable now; blocking at first production service | Sequenced — Phase 4, QR-0004 |
| No persona/user-research document home | PRDs will need shared personas ("reference shared persona definitions once they exist" — TPL-0003) | Decide home (likely `04-requirements/product/` sub-index) when first PRD starts — Phase 2 |
| No security/threat-model document home | Needed before first service design | Decide at platform-ADR time (Phase 1); candidate: `03-architecture/security/` |
| No decision log for **business** (non-architecture) decisions | Scheme scoping decisions (this report's G-02/G-04/G-05) have no formal home; ADRs are architecture-scoped | Small process decision: either widen ADR scope or add a lightweight `BDR` type — recommend deciding in Phase 0 |
| Traceability matrix, master index | Required by governance ambition, absent until now | Delivered: [QR-0003](QR-0003-traceability-matrix.md), [`docs/INDEX.md`](../INDEX.md) |

## 4. Conceptual Overlaps and Duplications (F-08 detail)

Recurring concepts appearing in multiple capabilities — each reviewed for whether duplication is justified:

| Concept | Occurrences | Judgment |
| --- | --- | --- |
| **Dispute resolution** | MCL.PCK.03 (collection), QFS.GRD.01 (grades), PEF.SET.03 (deductions), CMA.MKT.02 (marketplace conduct) | Justified as distinct capabilities (different actors, stakes, arbiters) — but the *pattern* (raise → evidence → resolve → adjust) must be modeled once in domain modeling as a shared concept, or four divergent dispute mechanisms will be built |
| **Equipment care & maintenance** | MCL.LGX.02, CPR.INP.02, FPR.MLK.01 (equipment readiness) | Justified per context; flag as a shared pattern for domain modeling |
| **Onboarding** | ETE.ONB.01 (ecosystem identity) and CPR.MEM.02 (cooperative membership) | Correctly layered — CPR.MEM.02 explicitly builds on ETE.ONB.01; no change |
| **Regulatory knowledge** | SWC.REG.01 (obligations) and ETE.LOC.01 (market packs) | Overlap acknowledged in both documents as "co-produced" — acceptable at capability level, but the **boundary must be settled in domain modeling** (single source for regulatory content, two consumers) |
| **Transport** | MCL.LGX.01 (collection) and CMA.DST.01 (distribution) | CMA.DST.01 already declares it shares the transport capability; no duplication |
| **Audit/inspection** | SWC.REG.02 serves both regulatory and certification audits (SWC.CRT.01) | Deliberate single capability; no change |

**Net finding:** no capability needs merging or deleting; four shared patterns (disputes, equipment care, regulatory content, transport) must each get a **single owner** in the domain-model phase.

## 5. Glossary and Taxonomy Gaps

- Abbreviation and term gaps found by audit were remediated in GLOSSARY v1.2 (QR-0001 F-02).
- The glossary lacked a structural view of how terms relate — remediated by the new taxonomy: [`docs/11-glossary/TAXONOMY.md`](../11-glossary/TAXONOMY.md).
- Remaining debt (acceptable): capability documents use many domain terms (e.g. *lactation curve*, *colostrum*, *heat detection*, *silage*) not yet in the glossary. Rule going forward: each future domain model adds its ubiquitous-language terms; the taxonomy marks which terms are pending definition.

## 6. Summary of Recommended Actions

| # | Action | Where | When (QR-0004 phase) |
| --- | --- | --- | --- |
| 1 | Add byproduct valorization subdomain | CAP-0005 revision | Phase 1 (with CAP approval cycle) |
| 2 | Record scope decisions: consumer engagement, livestock trading, workforce, Lacteva-company ops | CAP-0001 §2 revision | Phase 0/1 |
| 3 | Settle single ownership of 4 shared patterns | First domain models | Phase 1 |
| 4 | Decide business-decision-record mechanism | Governance | Phase 0 |
| 5 | Add security documentation home | `03-architecture/` | Phase 1 |
| 6 | OPS template | `02-templates/` | Phase 4 |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial gap analysis: 6 model gaps, 5 documentation-type gaps, 6 overlap judgments. |
