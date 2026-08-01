---
id: TPL-0016
title: Product Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# TPL-0016 — Product (PDT) Template

> Template guidance: Copy below the rule into `docs/03-architecture/03-application-layer/PDT-NNNN-<product-name>.md`. A PDT is the **stable architecture object** for a market-facing product — what it is and how it composes platform services, valid for years. Release-scoped requirements live in PRDs that cite this document. Do not confuse the prefixes (PDT ≠ PRD).

---

```yaml
---
id: PDT-NNNN
title: <Product name>
type: pdt
layer: application
status: Draft
version: "0.1"
owner: <product team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<BRD-IDs>, <PSV-IDs>, <AGT-IDs>]
---
```

# PDT-NNNN — \<Product Name\>

## 1. Proposition

\<one paragraph: for whom, what job it does, why it wins — timeless, not a release pitch\>

## 2. Audience

| Segment / Persona | Primary Jobs Served |
| --- | --- |
| \<segment\> | \<jobs\> |

## 3. Capability Surface

> Template guidance: the capabilities this product makes usable, at product level — coarser than PSV realization lists.

| Capability Domain / IDs | Surfaced As |
| --- | --- |
| \<e.g. MCL.PCK, PEF.SET\> | \<the product-level ability, e.g. "verified collection & payment record"\> |

## 4. Composition

| Component | Kind | Contribution to the Product |
| --- | --- | --- |
| \<PSV-ID\> | Platform service | \<what it powers\> |
| \<AGT-ID\> | AI agent | \<what it powers\> |

## 5. Markets

- **Launch markets / archetypes:** \<where, per CAP-0001 §7 variability axes\>
- **Localization-sensitive aspects:** \<what varies per market; ties to ETE.LOC.01\>

## 6. Boundaries

- **This product is not:** \<adjacent propositions deliberately excluded\>
- **Relationship to sibling products:** \<overlaps/handoffs with other PDTs\>

## 7. Product Success Measures

| Measure | Definition | Direction |
| --- | --- | --- |
| \<north-star + guardrail metrics\> | \<definition\> | \<up/down\> |

## 8. Requirements Trace

| PRD | Scope | Status |
| --- | --- | --- |
| \<PRD-ID or "None yet"\> | \<release scope\> | |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
