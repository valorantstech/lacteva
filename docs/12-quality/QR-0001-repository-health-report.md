---
id: QR-0001
title: Repository Health Report
type: qr
status: Approved
version: "1.1"
owner: Documentation Engineering
created: 2026-08-02
last-updated: 2026-08-02
related: [QR-0002, QR-0003, QR-0004]
---

# QR-0001 — Repository Health Report

## 1. Scope and Method

Full review of the repository as of 2026-08-02 (58 markdown files: 6 standards, 2 governance documents, 12 templates, 11 capability documents, 1 glossary, 21 README/index files, 5 root/infrastructure files).

Two methods, findings labeled accordingly:

- **Automated audit** — a script checked: relative-link resolution, front-matter completeness and ID/filename agreement, capability-ID cross-reference validity, master-map vs domain-document inventory and name agreement, and abbreviation usage vs glossary coverage.
- **Manual review** — consistency of naming across documents, namespace collisions, conceptual duplication, and governance-practice conformance.

## 2. Verified Health Metrics (automated)

| Check | Result | Verdict |
| --- | --- | --- |
| Front matter completeness (all formal documents) | 8/8 required keys present in all 31 formal documents | PASS |
| Front-matter ID vs filename agreement | 0 mismatches / 31 | PASS |
| Capability inventory integrity (master map vs domain documents) | 86/86 IDs present in both; 0 orphans either direction | PASS |
| Capability name agreement (master vs domain headings) | 0 mismatches / 86 | PASS |
| Capability cross-reference validity (dependency mentions) | 0 dangling references repository-wide | PASS |
| Relative link resolution | 4 unresolved of ~200; see finding F-01 | PARTIAL |
| Abbreviations used vs glossary | 10 undefined; see finding F-02 | FAIL → remediated |

## 3. Findings and Dispositions

### F-01 — Broken illustrative links in standards (severity: low) — REMEDIATED

STD-0001 §6 and STD-0003 §6 contained example links written as real Markdown links pointing at a non-existent example document (`ADR-0007-…`). Two further hits were false positives by design: STD-0006 §3's embed example sits inside a fenced code block, and TPL-0005 §1's OpenAPI link contains template placeholders (`NNNN`) that authors replace.

**Fix applied:** examples rewritten as patterns in code font; STD-0001 now mandates code font for illustrative links (STD-0001 v1.1, STD-0003 v1.1). **Follow-up:** the future link checker in `tools/` must skip fenced code blocks and template files.

### F-02 — Glossary coverage gaps (severity: medium) — REMEDIATED

Ten abbreviations were used in approved or draft documents without glossary definitions (SNF, OTIF, UHT, FSSAI, KPI, SLA, B2B, MoSCoW, RPS, IaC), violating STD-0001 §4's terminology rule. Three heavily used domain terms (Adulteration, Cold Chain, Traceability) were likewise undefined.

**Fix applied:** all added in GLOSSARY v1.2.

### F-03 — Namespace collision: `GOV` (severity: low) — ACCEPTED, DECISION RECORDED

`GOV` is both a document prefix (`GOV-0001`) and a subdomain code inside the capability model (`CPR.GOV.01`). The two namespaces are syntactically disjoint — document IDs are `PREFIX-NNNN`, capability IDs are `DOM.SUB.NN` — so no ambiguity can arise in a well-formed reference.

**Decision:** accepted; renaming the subdomain would cost more clarity than it buys. **Rule recorded:** subdomain codes exist only inside three-part capability IDs and MUST never be used bare in prose.

### F-04 — Stale naming in domain-models index (severity: low) — REMEDIATED

`docs/03-architecture/domain-models/README.md` listed candidate bounded contexts using pre-capability-model names ("Farm & Herd Management", "Quality Assessment", "Payments & Settlement") that no longer match the approved-vocabulary domain names in CAP-0001.

**Fix applied:** candidate list realigned to capability domain names and codes, with a link to the roadmap.

### F-05 — Approval debt on the capability model (severity: medium) — OPEN

All 11 CAP documents are `Draft 0.1`. Per [GOV-0002](../01-governance/GOV-0002-approval-workflow.md) they need Architecture Board + domain-owner approval to become authoritative — but those roles are not yet staffed, and CODEOWNERS references placeholder teams. Until approvals happen, the repository's largest content asset is formally non-authoritative, and every future document tracing to capability IDs builds on unapproved ground.

**Recommendation:** staff minimal approver roles (even provisionally) and run the CAP suite through GOV-0002 **before** domain-model work begins. This is Phase 0 of the roadmap ([QR-0004](QR-0004-documentation-roadmap.md)).

### F-06 — No version control (severity: high) — RESOLVED 2026-08-02

The repository was not under effective version control when audited; CONTRIBUTING, GOV-0001, and GOV-0002 presuppose branches, PRs, and CODEOWNERS enforcement.

**Resolution:** repository committed and pushed to GitHub (`valorantstech/lacteva`, default branch `main`). **Residual follow-ups (tracked as roadmap items 0.1/0.4):** protect the default branch (require PRs + CODEOWNERS review, no direct pushes), and wire `tools/validate/validate_docs.py` into CI so the standards gate every PR.

### F-07 — Standards are enforced by nothing (severity: medium) — OPEN

All conformance (front matter, IDs, links, diagram rules) is currently manual. `tools/README.md` already specifies the four CI validators needed. The automated audit behind this report is a working prototype of three of them.

**Recommendation:** implement the validators as the first code in `tools/` once git and CI exist (roadmap Phase 0/1).

### F-08 — Conceptual duplication patterns (severity: informational)

Manual review found recurring concept patterns across capabilities. Analysis and disposition in [QR-0002 §4](QR-0002-gap-analysis.md), summarized: dispute resolution (4 occurrences), equipment/asset care (3), and onboarding layering (2) are deliberate per-context capabilities, but each should be modeled **once** as a shared concept when domain modeling begins, to prevent divergent future implementations.

## 4. Governance-Practice Conformance

| Practice | State |
| --- | --- |
| Every folder has a purpose-stating README | Yes (22/22) |
| Domain indexes list their documents | Yes, current |
| Templates used for all formal documents | Yes (CAP catalogs use the recorded TPL-0009 amendment) |
| Change logs maintained per document | Yes; all version bumps have rows |
| Repository CHANGELOG maintained | Yes |
| Review/approval workflow followed | Partially — documents are authored to the standard, but no PR mechanics exist yet (F-06) and approvals are pending (F-05) |

## 5. Overall Assessment

**Content integrity: strong.** The document set is internally consistent to a degree verifiable by machine — inventories agree, references resolve, vocabulary is now fully covered by the glossary.

**Process reality: weak.** The governance system is well-designed but not yet operating: no git, no CI, no staffed approvers. The repository is a very good manuscript of an engineering knowledge base; Phase 0 of [QR-0004](QR-0004-documentation-roadmap.md) turns it into an operating one.

Health grade by area: Content **A**, Consistency **A−** (post-remediation), Governance design **A**, Governance operation **D**, Tooling **F (specified, not built)**.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | 2026-08-02 | Documentation Engineering | F-06 resolved: repository committed and pushed to GitHub; residual branch-protection and CI follow-ups noted. |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial audit report; findings F-01…F-08 with remediations applied same day. |
