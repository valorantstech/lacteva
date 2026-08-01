---
id: QR-0006
title: Next Work Queue
type: qr
status: Approved
version: "1.1"
owner: Documentation Engineering
created: 2026-08-02
last-updated: 2026-08-02
related: [QR-0004, QR-0005, CAP-0001]
---

# QR-0006 — Next Work Queue

## 1. Purpose and Rules

The ordered, actionable work queue derived **only from existing architecture**: every item below is already named in the roadmap ([QR-0004](QR-0004-documentation-roadmap.md)), the dependency map ([DEPENDENCY-MAP](../03-architecture/DEPENDENCY-MAP.md)), the gap analysis ([QR-0002](QR-0002-gap-analysis.md)), or the capability model — nothing here is new scope. Items are picked strictly top-down within their track; an item is *ready* when its "Needs" column is satisfied.

**Maintenance:** completed items move to the log (§4) with their resulting document IDs; the queue is re-derived whenever the roadmap changes.

## 2. Queue — Track A: Repository Operations (no upstream blockers; start any time)

| # | Item | Needs | Done When |
| --- | --- | --- | --- |
| A1 | Protect `main` on GitHub (require PRs + CODEOWNERS review) | Repo admin access | Direct pushes rejected |
| A2 | Wire `tools/validate/validate_docs.py` + `tools/xref/generate_xref.py --check` into CI (GitHub Actions) | A1 useful first | Both gate every PR |
| A3 | Replace CODEOWNERS placeholder teams with real GitHub teams | Org/team setup | CODEOWNERS resolves |
| A4 | Build the diagram validator (4th checker per `tools/README.md`) | — | Mermaid parse + `.puml`/`.svg` sync checked in CI |
| A5 | Decide the business-decision-record mechanism (QR-0002 §3) | Governance discussion | Decision recorded; GOV/STD updated if needed |

## 3. Queue — Track B: Content Pipeline (strictly ordered)

| # | Item | Needs | Done When |
| --- | --- | --- | --- |
| B1 | Staff approver roles: Architecture Board (≥ 2), domain owners | Organizational decision | Names against GOV-0002 roles |
| B2 | CAP approval cycle: CAP-0001…0011 through GOV-0002, folding in QR-0002 dispositions (byproduct subdomain; scope-exclusion statements for consumer engagement, livestock trading, workforce, Lacteva-company ops) | B1 | CAP suite `Approved 1.0` |
| B3 | BRD-0001 — initial market entry (TPL-0002) | B2 | Approved; selects capability scope for Phase 2 |
| B4 | Founding platform ADRs: cloud/runtime baseline; tenancy & isolation; event backbone; API conventions; localization architecture (TPL-0001; ~5 ADRs) | B2 | Each Approved; technology layer unblocked |
| B5 | DOM domain models, first four: Herd & Animal (FPR), Collection (MCL), Quality (QFS), Settlement (PEF) (TPL-0010) — each settles the shared-pattern ownership it touches (disputes, custody, regulatory content, equipment care → spawning `CON` docs on second consumer) | B2 | Each Approved; ubiquitous language in glossary; taxonomy pending-markers retired |
| B6 | BPR — collection-to-settlement process (first end-to-end business process, TPL-0014) | B2 (capabilities); richer after B5 | Approved; every step cites capability IDs |
| B7 | Tactical artifacts for B5 contexts: aggregates first, then policies/specifications; entities/value objects/repositories per granularity rule (TPL-0017…0022) | B5 per context | Indexed in ARCH INDEX; coverage table in TRACEABILITY.md ticks up |
| B8 | PSV platform services for B5 contexts (TPL-0015) | B5 + B4 (tenancy/event ADRs) | Approved; each maps to one context |
| B9 | Personas document + first PRDs per BRD-0001 scope (TPL-0003) | B3 | Approved |
| B10 | First PDT product definition composing B8 services (TPL-0016) | B3, B8 | Approved |
| B11 | Platform SRS + first service SRSs with co-authored API/EVT/DBD contracts (TPL-0004/0005/0008/0006) | B8, B9 | Approved; QR-0003 matrix columns start filling |
| B12 | First AGT agent charter + AIM model cards (advisory/forecasting per DIA capabilities) (TPL-0023/0007) | B5 (DIA context later), B8 | Approved with guardrails and harm metrics |

## 4. Completed-Items Log

| Item | Completed | Result |
| --- | --- | --- |
| Repository foundation, standards, governance, templates | 2026-08-02 | STD/GOV/TPL suites |
| Capability model authored | 2026-08-02 | CAP-0001…0011 (Draft) |
| Quality suite + indexes | 2026-08-02 | QR-0001…0004, INDEX, TAXONOMY |
| EA framework | 2026-08-02 | 5 layers, 11 new types, GOV-0003, validator |
| GitHub publication | 2026-08-02 | `valorantstech/lacteva`; F-06 resolved |
| Hygiene pass: navigation, XREF automation, validator extensions, coverage report | 2026-08-02 | NAVIGATION, XREF, QR-0005, QR-0006, validator v2 checks |
| Lacteva Collect implementation package (chapters 1–3) — drafted ahead of Track B order under the draft-parallelism rule; approval gated on B2 (CAP) and B3 (BRD) | 2026-08-02 | PSP-0001…0010, PDT-0001, package traceability & review notes |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-02 | Lacteva Collect Product Team | Logged Lacteva Collect package as completed draft work; queue items unchanged. |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial queue: 5 operations items, 12 content-pipeline items, all derived from existing roadmap/architecture. |
