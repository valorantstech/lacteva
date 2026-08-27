---
id: REPO-MIGRATION-V1
title: Repository Migration Plan — Baseline V1
type: reference
status: Superseded
version: "1.0"
owner: Documentation Engineering
created: 2026-08-02
last-updated: 2026-08-02
related: [ARCH-BASELINE-V1, REPO-AUDIT-V1]
baseline: ARCH-BASELINE-V1
---

# Repository Migration Plan — Baseline V1

Migrates the repository to [ARCHITECTURE_BASELINE_V1](../../ARCHITECTURE_BASELINE_V1.md) per the [audit](REPOSITORY_AUDIT.md), under the locked rules: **no deletions, no renames of approved concepts, no architecture changes; deprecation over deletion; git history preserved** (all changes are ordinary commits — no history rewriting, no file moves).

## 1. Executed Migration Steps (M-series — done in this migration)

| # | Step | Mechanics |
| --- | --- | --- |
| M1 | Publish baseline + audit + this plan at repo root; index them | New files; INDEX/NAVIGATION/12-quality README rows |
| M2 | Fix the two stale passages (audit F-A6): root README status; application-layer index | In-place edits with change history in git |
| M3 | **Baseline referencing:** add `baseline: ARCH-BASELINE-V1` front matter to all 72 formal documents (script-applied, uniform); add a governance line to the root and docs READMEs; register the `baseline` key in STD-0001 (v1.3) | Mechanical, content-untouched; `docs/XREF.md` exempt (generator-owned, regenerated) |
| M4 | Deprecation ledger established (below) — currently empty by audit finding F-A6 | This document §3 |
| M5 | Template front-matter blocks gain the `baseline:` line so future documents inherit the requirement | TPL front-matter examples updated in a follow-up pass if not this commit — see MR-6 |
| M6 | Re-run validator + XREF; commit with full history | CI-verified |

## 2. Manual Architectural Review Items (MR-series — TODOs, task 14)

These require humans with authority; the migration deliberately does **not** resolve them:

| ID | Item | Why Manual | Feeds |
| --- | --- | --- | --- |
| MR-1 | Staff Architecture Board + domain owners; run CAP-0001…0011 through GOV-0002 (fold in QR-0002 dispositions) | Approval authority | Baseline §1.2 caveat |
| MR-2 | Backfill founding platform ADRs (stack, tenancy, event backbone, API conventions, localization) citing the baseline | Decisions need accountable owners on record | Baseline §1.5 caveat; queue B4 |
| MR-3 | **Ratify Baseline V1** (Architecture Board sign-off per GOV-0002) | The baseline locks others' work; it must itself be ratified | Everything |
| MR-4 | Author `PSV` artifact(s) for platform-core's modules; update PDT-0001 composition from placeholders | Service-boundary judgment (one PSV or several) | Audit F-A2.2 |
| MR-5 | Assign single owners for the 4 shared concept patterns at first domain-model authoring | Domain-modeling judgment | Audit F-A1 |
| MR-6 | Decide whether template front-matter examples are updated in bulk (23 template edits) or on next-touch | Churn-vs-consistency tradeoff | M5 |
| MR-7 | Answer the Collect register: A1–A10 assumptions, Q1–Q8 questions, source-chapter provenance P1 | Product architecture ownership | PSP package approval |
| MR-8 | Repository ops: branch protection + CODEOWNERS teams (aware this constrains the current direct-commit workflow) | Org/tooling decision | QR-0006 A1/A3 |

## 3. Deprecation Ledger

Rule: a deprecated document keeps its file and history; front matter gains `status: Deprecated` + `superseded-by:`, its index row is annotated, and inbound references are re-pointed in the same PR (grep-verified).

| Document | Deprecated | Superseded By | Reason |
| --- | --- | --- | --- |
| *(none — audit found no obsolete documents)* | | | |

## 4. Ongoing Migration Rules

1. New formal documents MUST carry `baseline: ARCH-BASELINE-V1` (validator enforcement is a candidate `tools/` enhancement — add when convenient, not blocking).
2. Any document found conflicting with the baseline gets a defect entry in `docs/12-quality/` and is corrected *toward the baseline* — never the reverse without a V2.
3. Point-in-time reports (QR audits, this audit) are never edited to match later reality; later reports supersede them narratively.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial migration plan: M1–M6 executed steps, MR-1…MR-8 manual review queue, empty deprecation ledger. |
| 1.1 | 2026-08-27 | Documentation Engineering | Superseded by LACTEVA-ARCH-002: M1–M6 are executed and the root consolidation this plan did not cover has now happened. Kept as the record of how the governed `docs/` tree came to exist. Moved to `docs/21-milestones/`; content otherwise unchanged. |
