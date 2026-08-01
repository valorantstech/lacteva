---
id: TPL-0011
title: Glossary Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# TPL-0011 — Glossary Template

> Template guidance: The company-wide glossary lives at [`docs/11-glossary/GLOSSARY.md`](../11-glossary/GLOSSARY.md) and uses this structure. Use this template when adding sections or terms there, or when a bounded context needs a scoped sub-glossary (rare; prefer context-qualified entries in the main glossary).

---

# Glossary — \<Scope\>

> One entry per term. Alphabetical within each section. An entry defines the term; it does not describe a feature.

## Entry Format

```markdown
### <Term>

**Definition:** <one- to three-sentence definition in plain language>
**Context:** <"Company-wide", or the bounded context (DOM-ID) where this meaning applies>
**Synonyms / Do not confuse with:** <aliases to avoid; near-terms with different meanings>
**Source:** <regulation, industry standard, or internal document that anchors the definition>
```

Rules:

- **One meaning per entry.** If a term means different things in different bounded contexts, create one entry per context with the context stated (e.g. "Batch (Collection context)", "Batch (Processing context)").
- Definitions use plain language a new hire understands; they may link other glossary terms.
- Deprecated terms stay listed, marked **Deprecated — use \<term\>**, so old documents remain interpretable.
- Adding or changing a term follows the normal review workflow; the glossary owner (docs guild) is a required reviewer.

## Sections

Organize entries under these headings:

```markdown
## Dairy Domain Terms
## Platform and Architecture Terms
## AI and Data Terms
## Business and Commercial Terms
## Abbreviations
```

The **Abbreviations** section is a two-column table:

```markdown
| Abbreviation | Expansion |
| --- | --- |
| SCC | Somatic Cell Count |
```

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
