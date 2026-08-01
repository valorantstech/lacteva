---
id: TPL-0018
title: Entity Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# TPL-0018 — Entity (ENT) Template

> Template guidance: Copy below the rule into `docs/03-architecture/02-domain-layer/<context-folder>/ENT-NNNN-<entity-name>.md`. Standalone entity documents are for entities **referenced across aggregates or carrying non-trivial rules** — trivial members are documented inline in their AGG (granularity rule in the layer README). An entity has identity and lifecycle; if two instances with identical attributes are interchangeable, it is a value object (TPL-0019).

---

```yaml
---
id: ENT-NNNN
title: <Entity name>
type: ent
layer: domain
context: <DOM-NNNN>
status: Draft
version: "0.1"
owner: <context owner team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<AGG-ID it belongs to>, <VAL-IDs>]
---
```

# ENT-NNNN — \<Entity Name\>

## 1. Definition

\<what one instance represents in the business, one paragraph\>

- **Belongs to aggregate:** \<AGG-ID\> (root? yes/no)

## 2. Identity

- **Identified by:** \<the identity in business terms\>
- **Identity is assigned:** \<when/by whom — e.g. at registration, by the national scheme\>
- **Identity never changes because:** \<why stability matters here\>

## 3. Attributes

| Attribute | Type (business) | Meaning | Rules |
| --- | --- | --- | --- |
| \<name\> | \<VAL-ID or plain kind\> | \<glossary-term meaning\> | \<validity/mutability rules\> |

## 4. Lifecycle

\<states and transitions if non-trivial (Mermaid stateDiagram-v2 per STD-0005), or "Follows the aggregate's lifecycle (AGG-NNNN §5)"\>

## 5. Behavior Rules

> Template guidance: rules local to this entity; rules spanning aggregate members belong in the AGG's invariants — do not duplicate them here.

| # | Rule |
| --- | --- |
| R1 | \<rule\> |

## 6. Referenced By

| Artifact | As |
| --- | --- |
| \<AGG/PSV/BPR IDs\> | \<role in that artifact\> |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
