---
id: STD-0001
title: Markdown Writing Standards
type: standard
status: Approved
version: "1.3"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
baseline: ARCH-BASELINE-V1
---

# STD-0001 — Markdown Writing Standards

## 1. Purpose

Defines how Markdown documents in this repository are structured and written, so that any document is instantly familiar to any reader and machine-processable by tooling.

## 2. Front Matter

Every document (except folder `README.md` files) begins with YAML front matter:

```yaml
---
id: <DOC-ID per STD-0003>
title: <Title Case title>
type: <adr | brd | prd | srs | api | dbd | aim | evt | cap | dom | std | gov | tpl | ops>
status: <Draft | In Review | Approved | Deprecated | Superseded>
version: "<MAJOR.MINOR per STD-0004>"
owner: <team or role, not an individual's personal email>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
---
```

Optional keys when applicable: `supersedes`, `superseded-by`, `reviewers`, `approvers`, `related` (list of document IDs), `layer` (concept | business | domain | application | technology — required for Enterprise Architecture artifacts), `context` (owning `DOM` ID — required for domain-layer tactical artifacts), `baseline` (the governing architecture baseline ID — REQUIRED on all formal documents; currently `ARCH-BASELINE-V1`, see `ARCHITECTURE_BASELINE_V1.md` at repo root).

## 3. Document Structure

- Exactly one H1 (`#`), matching the pattern `<DOC-ID> — <Title>`.
- Headings are numbered at H2 level (`## 1. Purpose`) in formal documents; templates define the numbering.
- Never skip heading levels (H2 → H4 is forbidden).
- Every formal document ends with a `## Change Log` section (a table of version, date, author, change summary).
- Maximum heading depth is H4. If you need H5, restructure the document.

## 4. Prose Style

- **Voice:** direct, active, present tense. "The service validates the token", not "the token will be validated by the service".
- **Requirement language:** use RFC 2119 keywords — MUST, MUST NOT, SHOULD, SHOULD NOT, MAY — capitalized, only in their normative sense.
- **Sentences:** one idea per sentence. Prefer 25 words or fewer.
- **Paragraphs:** 3–5 sentences. Longer explanations become subsections or lists.
- **No filler:** delete "in order to", "it should be noted that", "basically", "very".
- **Acronyms:** expand on first use per document, e.g. "Software Requirements Specification (SRS)".
- **Terminology:** use glossary terms exactly as defined in [`docs/11-glossary/GLOSSARY.md`](../11-glossary/GLOSSARY.md). If a term is missing, add it in the same PR.

## 5. Formatting Rules

- Line length: no hard wrap; one sentence per line is permitted and encouraged for reviewability (smaller diffs).
- **Bold** for UI elements and key terms on first definition; *italics* sparingly for emphasis; `code font` for identifiers, file paths, commands, and literal values.
- Lists: `-` for unordered lists, `1.` for ordered lists. Nest at most two levels.
- Tables: use for enumerable, comparable facts only. Every table has a header row. Do not put multi-sentence prose in cells.
- Code blocks: always fenced with a language tag (```` ```json ````, ```` ```sql ````, ```` ```mermaid ````).
- Blank line before and after every heading, list, table, and code block.

## 6. Links

- Use **relative links** within the repository, never absolute URLs to the hosting platform.
- Link to a document the first time it is mentioned; plain text thereafter.
- Link document IDs using relative paths — pattern: `[<DOC-ID>](<relative-path-to-file>.md)`.
- Illustrative links in examples MUST be written in code font (backticks), so link checkers do not treat them as real targets.
- External links MUST be to stable, canonical sources (specifications, official docs).

## 7. Images and Diagrams

- Prefer **Mermaid** (rendered from source, diffable) per [STD-0005](STD-0005-mermaid-standards.md); use **PlantUML** for diagram types Mermaid handles poorly per [STD-0006](STD-0006-plantuml-standards.md).
- Binary images are a last resort; when used, store them in an `assets/` subfolder next to the document and always provide alt text.

## 8. Dates, Numbers, Units

- Dates: ISO 8601 (`2026-08-02`). Times: UTC with offset (`14:30Z`).
- Numbers: thousands separators for ≥ 10,000 (`250,000`); SI units; currency with ISO code (`EUR 1,200`).

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.3 | 2026-08-02 | Documentation Engineering | Registered `baseline` front-matter key (baseline migration M3). |
| 1.2 | 2026-08-02 | Architecture Board | Added optional front-matter keys `layer` and `context` for Enterprise Architecture artifacts. |
| 1.1 | 2026-08-02 | Documentation Engineering | Editorial: illustrative links must use code font (QR-0001 finding); fixed a broken example link. |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial approved version. |
