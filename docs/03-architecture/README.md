# 03 — Architecture

Approved architecture documentation for the Lacteva platform: **decisions** (ADRs), **domain models** (bounded contexts), and **system diagrams**.

## Structure

| Folder | Contents | Prefix |
| --- | --- | --- |
| [`adr/`](adr/README.md) | Architecture Decision Records — why the platform is built the way it is | `ADR` |
| [`domain-models/`](domain-models/README.md) | Bounded-context domain models in ubiquitous language | `DOM` |
| [`diagrams/`](diagrams/README.md) | Cross-cutting system diagrams not owned by a single document | — |

## Principles for This Domain

- **Decisions are recorded when made, not reconstructed later.** If a significant choice was made without an ADR, writing the ADR retroactively is the fix — with honest context.
- **ADRs are immutable once approved** ([STD-0004 §3](../00-standards/STD-0004-versioning-strategy.md)); course changes are new, superseding ADRs.
- **Domain models precede schemas and APIs.** DBDs and API specs realize a DOM; unexplained divergence between them is a defect.
- Architecture views follow the **C4 model** rendered per [STD-0006](../00-standards/STD-0006-plantuml-standards.md) (PlantUML) or, for simple views, [STD-0005](../00-standards/STD-0005-mermaid-standards.md) (Mermaid).

## What Counts as "Architecturally Significant"

Write an ADR when a decision is expensive to reverse, constrains multiple teams, selects a platform technology, defines a contract pattern, or trades off quality attributes (e.g. consistency vs availability). When in doubt, write the ADR — a short one costs an hour; an undocumented decision costs an archaeology project.
