---
id: STD-0006
title: PlantUML Standards
type: standard
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# STD-0006 — PlantUML Standards

## 1. Purpose

PlantUML is the repository's tool for diagram types Mermaid handles poorly: **C4 architecture diagrams**, detailed component and class models, and deployment views. This standard defines how PlantUML sources are stored, structured, and reviewed.

## 2. When to Use PlantUML

Use PlantUML for:

- **C4 diagrams** (System Context, Container, Component) — the standard architecture views for the platform, using the [C4-PlantUML](https://github.com/plantuml-stdlib/C4-PlantUML) standard library.
- Class diagrams with more than trivial detail (attributes, operations, relationships with multiplicities).
- Deployment diagrams.

For everything else, default to Mermaid per [STD-0005](STD-0005-mermaid-standards.md).

## 3. Storage and Rendering

- Source files live in the owning document's `assets/` folder: `ADR-0007-container-view.puml`.
- The source file is the artifact of record. A rendered `.svg` with the **same base name** SHOULD be committed alongside it and embedded in the document:

```markdown
![Container view of the collection subsystem](assets/ADR-0007-container-view.svg)
```

- Source and rendered image MUST be updated in the same PR — a stale render is a review-blocking defect.

## 4. File Structure

Every `.puml` file follows this skeleton:

```plantuml
@startuml ADR-0007-container-view
' Doc: ADR-0007 — Event Bus Selection
' Shows: containers of the collection subsystem and their message flows
!include <C4/C4_Container>

title Collection Subsystem — Container View

' ... content ...

@enduml
```

Rules:

- `@startuml` name matches the file base name.
- A comment header states the owning document and what the diagram shows.
- Every diagram has a `title`.
- Use standard library includes (`<C4/...>`); never paste library source into the file, and never depend on network includes from arbitrary URLs.

## 5. C4 Conventions

- Levels: produce **System Context** and **Container** views for every system; **Component** views only where a container's internals are architecturally significant.
- Use `Person`, `System`, `System_Ext`, `Container`, `ContainerDb`, `Rel` from C4-PlantUML — no hand-drawn boxes.
- Every `Rel` is labeled with the interaction and protocol: `Rel(api, db, "reads/writes collection records", "SQL/TLS")`.
- External systems use `_Ext` variants; no custom coloring beyond what C4-PlantUML provides.
- One level of abstraction per diagram — do not mix context-level and component-level elements.

## 6. Layout and Style

- Prefer `LAYOUT_TOP_DOWN()` or `LAYOUT_LEFT_RIGHT()`; avoid manual positioning hints unless the auto-layout is unreadable.
- No `skinparam` color overrides; monochrome plus C4 defaults only.
- Keep diagrams under ~20 elements; split by subsystem when larger.

## 7. Review Checklist

- [ ] `.puml` source and `.svg` render both present and in sync
- [ ] File name, `@startuml` name, and owning document match
- [ ] Title and header comment present
- [ ] All relationships labeled (interaction + protocol)
- [ ] Single abstraction level; ≤ ~20 elements
- [ ] Element names match glossary and STD-0002 naming

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial approved version. |
