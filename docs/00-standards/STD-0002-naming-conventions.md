---
id: STD-0002
title: Naming Conventions
type: standard
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# STD-0002 — Naming Conventions

## 1. Purpose

Defines naming rules for files, folders, branches, and identifiers so that names are predictable, sortable, and unambiguous across the entire repository.

## 2. General Principles

- Names are **lowercase kebab-case** unless a rule below says otherwise.
- Names describe **content, not history** (`event-bus-selection`, not `new-proposal-v2-final`).
- ASCII only. No spaces, underscores (except where a tool requires them), or special characters.
- Abbreviations only if they appear in the [glossary](../11-glossary/GLOSSARY.md).

## 3. Folders

- Lowercase kebab-case: `domain-models/`, not `DomainModels/`.
- Documentation domains are numbered for ordering: `00-standards/`, `03-architecture/`.
- Every folder MUST contain a `README.md` explaining its purpose and indexing its contents.

## 4. Document Files

Pattern:

```
<PREFIX>-<NNNN>-<short-kebab-title>.md
```

- `PREFIX` — document type prefix per [STD-0003](STD-0003-document-numbering.md) (e.g. `ADR`, `BRD`, `API`). Uppercase.
- `NNNN` — zero-padded four-digit sequence number.
- `short-kebab-title` — 2–6 words, matching the document title.

Examples:

- `ADR-0007-event-bus-selection.md`
- `SRS-0012-milk-collection-service.md`
- `AIM-0003-yield-forecasting-model.md`

Special files, always uppercase, only at the levels defined here: `README.md` (every folder), `CONTRIBUTING.md`, `CHANGELOG.md`, `GLOSSARY.md`, `CODEOWNERS`.

## 5. Branches

```
<type>/<ticket-or-doc-id>-<short-description>
```

- Types: `docs`, `feat`, `fix`, `chore`, `refactor`, `test`, `ci`, `hotfix`.
- Examples: `docs/adr-0007-event-bus-selection`, `feat/LAC-142-tenant-provisioning`.

## 6. Code and Platform Identifiers

These apply as code enters the repository; language style guides may refine but not contradict them.

| Artifact | Convention | Example |
| --- | --- | --- |
| Service names | kebab-case, noun-based | `milk-collection-service` |
| Library names | kebab-case, `lacteva-` prefix for published packages | `lacteva-tenant-context` |
| REST resource paths | plural nouns, kebab-case | `/v1/milk-collections` |
| JSON fields | `camelCase` | `fatContentPercent` |
| Database schemas/tables | `snake_case`, singular table names | `milk_collection` |
| Database columns | `snake_case` | `collected_at` |
| Event names | past tense, dot-namespaced per STD/EVT rules | `collection.milk-collected.v1` |
| Environment variables | `SCREAMING_SNAKE_CASE`, `LACTEVA_` prefix | `LACTEVA_DB_URL` |
| Kubernetes / cloud resources | kebab-case with environment suffix | `milk-collection-svc-prod` |

## 7. Diagram and Asset Files

- Mermaid lives inline in documents (preferred). Standalone diagram sources: `<doc-id>-<diagram-name>.mmd` / `.puml` in the document's `assets/` folder.
- Exported images mirror the source name: `ADR-0007-context-view.svg`.

## 8. Prohibited Names

- `misc`, `stuff`, `temp`, `new`, `old`, `final`, `copy`, dates in folder names, personal names.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial approved version. |
