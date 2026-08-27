# 12 — Quality

Repository and documentation quality artifacts (`QR` prefix): audit reports, traceability matrices, gap analyses, and the documentation roadmap. This domain exists so quality findings are **documents with IDs and history**, not chat messages that evaporate — every finding is either remediated (with the fix traceable) or accepted (with the decision recorded).

## Rules

- Naming: `QR-NNNN-<short-title>.md` per [STD-0002](../00-standards/STD-0002-naming-conventions.md); prefix registered in [STD-0003](../00-standards/STD-0003-document-numbering.md).
- QR reports state their **method** (what was checked, how) and separate **verified findings** from judgments.
- Findings reference the exact documents affected; remediations reference the QR finding in the affected document's change log.
- Living artifacts here (index, traceability matrix, roadmap) are updated whenever documents are added — checked in review per [GOV-0001](../01-governance/GOV-0001-review-workflow.md).

## Index

| ID | Title | Kind | Status | Version |
| --- | --- | --- | --- | --- |
| [QR-0001](QR-0001-repository-health-report.md) | Repository Health Report | Point-in-time audit + findings register | Approved | 1.1 |
| [QR-0002](QR-0002-gap-analysis.md) | Gap Analysis | Point-in-time audit | Approved | 1.0 |
| [QR-0003](QR-0003-traceability-matrix.md) | Traceability Matrix | Living artifact | Approved | 1.0 |
| [QR-0004](QR-0004-documentation-roadmap.md) | Documentation Roadmap & Dependency Graph | Living artifact | Approved | 1.0 |
| [QR-0005](QR-0005-documentation-coverage-report.md) | Documentation Coverage Report | Point-in-time audit | Approved | 1.0 |
| [QR-0006](QR-0006-next-work-queue.md) | Next Work Queue | Living artifact | Approved | 1.0 |

The master documentation index lives at [`docs/INDEX.md`](../INDEX.md); the business-term taxonomy at [`docs/11-glossary/TAXONOMY.md`](../11-glossary/TAXONOMY.md). The baseline-migration audit and plan (2026-08-02) live at repo root: [`REPOSITORY_AUDIT.md`](../21-milestones/REPOSITORY_AUDIT.md) · [`REPOSITORY_MIGRATION_PLAN.md`](../21-milestones/REPOSITORY_MIGRATION_PLAN.md), governed by [`ARCHITECTURE_BASELINE_V1.md`](../../ARCHITECTURE_BASELINE_V1.md).
