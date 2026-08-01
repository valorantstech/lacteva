---
id: QR-0005
title: Documentation Coverage Report
type: qr
status: Approved
version: "1.0"
owner: Documentation Engineering
created: 2026-08-02
last-updated: 2026-08-02
related: [QR-0003, QR-0004, QR-0006]
---

# QR-0005 — Documentation Coverage Report

## 1. Method

All figures below are machine-gathered (2026-08-02) by the repository tooling: `tools/validate/validate_docs.py` (consistency), `tools/xref/generate_xref.py` (reference connectivity), and a statistics scan. Coverage judgments derive strictly from the existing roadmap ([QR-0004](QR-0004-documentation-roadmap.md)) and traceability matrix ([QR-0003](QR-0003-traceability-matrix.md)) — no new scope is invented here.

## 2. Repository Statistics

| Metric | Value |
| --- | --- |
| Markdown files | 89 |
| Total words | ~52,000 |
| Formal documents (front-mattered) | 55 (44 Approved, 11 Draft) |
| Documents by type | 23 templates, 11 capability docs, 8 reference/index docs, 6 standards, 4 QR reports*, 3 governance docs |
| Registered document prefixes | 26 |
| Capabilities modeled | 86 (10 domains, ~40 subdomains) |
| Named business events (pre-inventory) | ~250 |
| Mermaid diagrams | 30 |
| Validation tooling | 2 Python tools, ~320 lines |
| Validator result | **PASS** (after 1 finding fixed: INDEX.md lacked a Change Log) |

\* Count at scan time; this report and QR-0006 bring the QR total to 6.

Consistency guarantees now machine-enforced on every run: document ID + version + status + owner + created/last-updated + revision-history section present on all formal documents; status/version coherence (Draft ⇔ 0.x, Approved ⇔ ≥ 1.0); registered prefixes; ID/filename agreement; ID uniqueness; resolving links; resolving capability references.

## 3. Coverage: Completed Artifacts

| Area | Artifacts | State |
| --- | --- | --- |
| Standards (STD-0001…0006) | 6 | Approved; 3 revised through governed version bumps |
| Governance (GOV-0001…0003) | 3 | Approved |
| Templates (TPL-0001…0023) | 23 | Approved — every registered document type with a template has one |
| Glossary + Taxonomy | 2 | Approved; zero known term gaps (all in-use abbreviations defined) |
| Quality suite (QR-0001…0006) | 6 | Approved; findings register live |
| Indexes & navigation | INDEX, NAVIGATION, XREF, 4 architecture indexes, 24 section READMEs | Complete — every folder has a purpose-stating README |
| Tooling | validator + xref generator | Working; diagram checker outstanding |

## 4. Coverage: In-Progress Artifacts

| Artifacts | Status | Blocking On |
| --- | --- | --- |
| Capability model (CAP-0001…0011) | Draft 0.1 — content complete, formally unapproved | Staffed approvers + GOV-0002 cycle (roadmap 0.2/0.3), folding in QR-0002 dispositions |

Nothing else is in progress: the repository is deliberately gated on CAP approval per the [dependency map](../03-architecture/DEPENDENCY-MAP.md).

## 5. Coverage: Missing Artifacts (all already-scoped; none newly invented)

By pipeline position, per QR-0003/QR-0004:

| Missing | Count Expected (initial) | Unblocked By |
| --- | --- | --- |
| Platform ADRs (cloud/runtime, tenancy, event backbone, API conventions, localization) | ~5 | CAP approval |
| Bounded-context domain models (DOM) — Herd & Animal, Collection, Quality, Settlement first | 4 (Phase 1) + 6 later | CAP approval |
| BRD-0001 market entry | 1 | CAP approval |
| Tactical domain artifacts (AGG/ENT/VAL/REP/POL/SPC) | per DOM | First DOMs |
| Business processes (BPR) — collection-to-settlement first | ≥ 3 candidates named | CAP approval |
| Concepts (CON) — Dispute, Custody Transfer, Regulatory Obligation, Equipment Care | 4 candidates | First two consumers each |
| PRDs, personas | per BRD | BRD-0001 |
| PSV/PDT/AGT application artifacts | per Phase 1 outputs | DOMs + ADRs |
| SRS, API, EVT, DBD, AIM | per service | Phase 2 outputs |
| OPS template + runbooks | 1 + per service | First production service |
| Diagram validator (4th checker) | 1 tool | Any time — no upstream blocker |

## 6. Duplicate-Concept Status

Re-checked against [QR-0002 §4](QR-0002-gap-analysis.md): the four shared patterns (dispute resolution, equipment care, regulatory content, transport) remain the only known conceptual duplications; no new ones introduced since. Consolidation path unchanged: each gets a single owner at domain-modeling time — the `CON` candidates listed above exist precisely for this.

## 7. Coverage Verdict

The **framework layer is 100% complete** (standards, governance, templates, indexes, tooling, navigation). The **content layer is one approval cycle away from its foundation** (CAP suite) and otherwise empty by design. There is exactly one bottleneck, and it is organizational, not editorial: staffing approvers and running the CAP approval. Everything actionable after that is ordered in [QR-0006](QR-0006-next-work-queue.md).

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial coverage report with machine-gathered statistics. |
