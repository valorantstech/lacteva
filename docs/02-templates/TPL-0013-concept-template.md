---
id: TPL-0013
title: Concept Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
baseline: ARCH-BASELINE-V1
---

# TPL-0013 — Concept (CON) Template

> Template guidance: Copy below the rule into `docs/03-architecture/00-concepts/CON-NNNN-<concept-name>.md`. A concept document defines a cross-cutting idea **once**, for every layer and context that uses it. Create one only when ≥ 2 consumers would otherwise define the idea themselves (threshold per the layer README). Register the concept in the glossary (pointing here) and in the Concept Trace Register (TRACEABILITY.md).

---

```yaml
---
id: CON-NNNN
title: <Concept name — a noun phrase>
type: con
layer: concept
status: Draft
version: "0.1"
owner: <steward team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<IDs of consuming artifacts>]
---
```

# CON-NNNN — \<Concept Name\>

## 1. Definition

\<the authoritative definition, 1–2 paragraphs; plain language; glossary-linked terms\>

## 2. Why This Concept Exists

\<the confusion or duplication it prevents; the ≥ 2 consumers that triggered its creation\>

## 3. Distinctions

> Template guidance: what this concept is NOT — its nearest neighbors and the exact line between them. This section does the concept's real work.

| Not To Be Confused With | The Difference |
| --- | --- |
| \<neighbor term/concept\> | \<the precise distinction\> |

## 4. Manifestations Across Layers

| Layer / Context | How the Concept Appears |
| --- | --- |
| Business (CAP/BPR) | \<e.g. which capabilities exercise it\> |
| Domain (DOM/…) | \<e.g. which contexts model it, and as what\> |
| Application (PSV/AGT) | \<how services/agents surface it\> |

## 5. Invariant Properties

\<numbered properties that hold wherever the concept appears — the portable core; anything context-specific belongs to that context's artifacts, not here\>

## 6. Consumers

| Artifact | Uses the Concept For |
| --- | --- |
| \<ID\> | \<usage\> |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
