---
id: REPO-AUDIT-V1
title: Repository Audit — Baseline Migration
type: reference
status: Approved
version: "1.0"
owner: Documentation Engineering
created: 2026-08-02
last-updated: 2026-08-02
related: [QR-0001, QR-0002, QR-0005]
baseline: ARCH-BASELINE-V1
---

# Repository Audit — Baseline Migration (2026-08-02)

Full-repository scan preceding migration to [ARCHITECTURE_BASELINE_V1](ARCHITECTURE_BASELINE_V1.md). Method: machine scan (`tools/validate/validate_docs.py`, `tools/xref/generate_xref.py --check`, staleness grep) + manual review of every documentation domain against prior audits ([QR-0001](docs/12-quality/QR-0001-repository-health-report.md), [QR-0002](docs/12-quality/QR-0002-gap-analysis.md), [QR-0005](docs/12-quality/QR-0005-documentation-coverage-report.md)). This audit records **findings**; actions live in the [migration plan](REPOSITORY_MIGRATION_PLAN.md).

## 1. Machine Consistency Report (task 12)

| Check | Result |
| --- | --- |
| Markdown files scanned | 112 (72 front-mattered; 60 with `PREFIX-NNNN` IDs) |
| Front matter completeness / ID-filename agreement / ID uniqueness | PASS (0 violations) |
| Status–version coherence (Draft⇔0.x, Approved⇔≥1.0) | PASS |
| Revision-history sections | PASS (all formal docs) |
| Internal links | PASS (0 broken) |
| Capability references | PASS (86/86 defined; 0 dangling) |
| XREF map freshness | Current |
| Code quality gates (platform-core) | Ruff clean; 18/18 tests passing |

## 2. Findings

### F-A1 — Duplicate concepts: 4 patterns, 0 duplicate documents

Unchanged from QR-0002 §4 (re-verified): dispute resolution (×4 capabilities), equipment care (×3), regulatory content (×2), transport (×2) are deliberate per-context capabilities sharing a pattern; each needs a single owner at domain-modeling time (CON candidates already registered). **No document duplicates another document's content**; the traceability trio (QR-0003 / ARCH-TRACE / LC-TRACE) and roadmap pair (QR-0004 / DEVELOPMENT_ROADMAP) have declared, disjoint scopes — now also arbitrated by baseline precedence rule §2.3.

### F-A2 — Conflicting architecture: 2 conflicts, both governance-order, none content

1. **Implementation precedes its records:** `services/platform-core` exists with no founding ADRs and an unapproved CAP suite beneath it. Not a content conflict (code matches the dictated stack, which the baseline now locks) but a governance-order conflict. → MR-1, MR-2.
2. **PDT-0001 composition vs reality:** PDT-0001 lists composing platform services as `PSV` placeholders while platform-core is running code with no `PSV` artifact. Architecture and implementation are connected only informally. → MR-4 (author PSV for platform-core's modules when Phase 1 opens; TODO, not a rewrite).

No two approved documents assert contradictory facts.

### F-A3 — Overlapping documents: 0 requiring merge

Reviewed all candidate pairs (indexes vs navigation vs XREF; three traceability docs; two roadmaps; PSP rules vs future POL). Each overlap is a declared division of labor with cross-links. Merging would lose roles, not remove duplication.

### F-A4 — Inconsistent naming: 0 open

Validator-enforced (filenames, IDs, prefixes). Prior findings (domain-models candidate names, `GOV` namespace) were fixed or accepted-with-rule in QR-0001. The `PRD`/`PDT` near-collision remains documented in three places as intentional.

### F-A5 — Broken references: 0

Link check and capability-reference check both clean (see §1).

### F-A6 — Obsolete content: 2 stale passages, 0 obsolete documents

1. Root `README.md` "Repository Status" still described the foundation-documentation phase — predates the capability model, product package, and code. → fixed in migration step M2.
2. `docs/03-architecture/03-application-layer/README.md` index said "None yet" while PDT-0001 exists (the parallel ARCH INDEX was updated at the time; this one was missed). → fixed in migration step M2.

**No document warrants deprecation**: point-in-time audits (QR-0001/0002/0005) are historical records, not obsolete documents; everything else is current. The migration plan establishes the deprecation ledger for the future.

## 3. Alignment Census

| Category | Count | Baseline-aligned |
| --- | --- | --- |
| Standards / governance / templates | 32 | Yes (baseline §1.1) |
| Capability model | 11 | Yes, content-locked; approval pending (MR-1) |
| EA workspace docs + PDT-0001 | 9 | Yes |
| Product package (PSP + registers) | 12 | Yes |
| Quality suite (QR + indexes + reference docs) | 11 | Yes |
| Root engineering docs (roadmap, baseline set) | 4 | Yes |
| **Documents aligned / total formal** | **72 / 72** | after migration steps M1–M3 |

## 4. Repository Health Score

Weighted: content integrity 40% (score 100), reference/naming consistency 20% (100), index freshness 10% (80 — two stale passages found), governance operation 20% (55 — approvals unstaffed, ADRs unwritten, branch protection off), tooling 10% (85 — diagram validator outstanding).

**Overall: 88/100** — up from the qualitative "content A / governance-operation D" of QR-0001; the remaining deductions are all organizational (MR-1…MR-3), not editorial.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Documentation Engineering | Baseline-migration audit: findings F-A1…F-A6, alignment census, health score. |
