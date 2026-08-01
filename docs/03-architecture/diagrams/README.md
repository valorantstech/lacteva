# Cross-Cutting Diagrams

System-level diagrams **not owned by a single document**: the platform context view, the context map across bounded contexts, deployment topology overviews.

## Rules

- A diagram that illustrates one document belongs in that document (inline Mermaid) or its `assets/` folder — not here. This folder is only for views that span the platform.
- Sources are mandatory: `.mmd` (Mermaid) or `.puml` (PlantUML) per [STD-0005](../../00-standards/STD-0005-mermaid-standards.md) / [STD-0006](../../00-standards/STD-0006-plantuml-standards.md); PlantUML sources are committed with an in-sync `.svg` render.
- Naming: `<scope>-<view>.<ext>`, e.g. `platform-context-view.puml`, `bounded-context-map.mmd`.
- Every diagram here is referenced from at least one document or README; orphaned diagrams are deleted.

## Index

| File | Shows | Referenced By |
| --- | --- | --- |
| — | *No cross-cutting diagrams yet; the platform context view and bounded-context map are created when architecture work begins.* | |
