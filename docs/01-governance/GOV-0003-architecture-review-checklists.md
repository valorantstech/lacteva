---
id: GOV-0003
title: Architecture Review Checklists
type: gov
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
related: [GOV-0001, GOV-0002]
---

# GOV-0003 — Architecture Review Checklists

## 1. Purpose

Per-artifact-type checklists that reviewers of Enterprise Architecture artifacts apply **in addition to** the general checklists of [GOV-0001](GOV-0001-review-workflow.md). A checklist item failing is a review-blocking finding unless the author justifies the exception in the PR.

## 2. Universal Architecture Checklist (every EA artifact)

- [ ] Front matter carries `layer:`; domain-layer artifacts carry `context: DOM-NNNN`
- [ ] Traces upward per [TRACEABILITY.md](../03-architecture/TRACEABILITY.md) rules — no orphans
- [ ] Citation directions legal per [CROSS-REFERENCE.md](../03-architecture/CROSS-REFERENCE.md) matrix
- [ ] Authoring-order dependencies satisfied per [DEPENDENCY-MAP.md](../03-architecture/DEPENDENCY-MAP.md) (upstream approved before this enters approval)
- [ ] No technology names outside the technology layer and ADRs
- [ ] Layer index + [ARCH INDEX](../03-architecture/INDEX.md) updated in this PR
- [ ] All terms glossary-consistent; new terms added; taxonomy row updated

## 3. Per-Type Checklists

### CON — Concept
- [ ] ≥ 2 real consumers named (threshold rule)
- [ ] Distinctions table separates every near-neighbor term
- [ ] Glossary entry exists and points here; Concept Trace Register updated

### BPR — Business Process
- [ ] Every step cites a capability ID; no step invents an ability
- [ ] All end states listed, including failures; exceptions have compensation
- [ ] Market variants inside this document, not forked documents
- [ ] Flow diagram ≤ 15 nodes (else decomposed)

### DOM — Bounded Context (with TPL-0010)
- [ ] Explicit not-responsible-for statement
- [ ] Every ubiquitous-language term in glossary (context-qualified where needed)
- [ ] Context relationships use DDD pattern vocabulary; both sides updated
- [ ] Shared-pattern ownership (QR-0002 §4) settled for any pattern this context touches

### AGG — Aggregate
- [ ] Invariants genuinely span members (else the aggregate is too big) and each states its why
- [ ] Boundary rationale addresses both "why this big" and "why not bigger"
- [ ] Other aggregates referenced by identity only
- [ ] Every operation lists states + emitted events

### ENT / VAL — Entity / Value Object
- [ ] Standalone-document threshold met (cross-aggregate use or non-trivial rules) — else inline in AGG
- [ ] ENT: identity defined, stable, with assignment moment
- [ ] VAL: invalid instances unconstructible (validity rules complete); equality defined; at least one valid and one invalid example

### REP — Repository
- [ ] Exactly one aggregate served
- [ ] Access patterns justified by named consumers with volumes
- [ ] Selections reference SPC specifications, not ad-hoc predicates
- [ ] Staleness/concurrency expectations stated in business terms

### POL — Policy
- [ ] Statement normative (RFC 2119) and complete
- [ ] Authority and regulatory trace named
- [ ] All market/tenant-variable values are parameters — no hard-coded local values
- [ ] Enforcement points and violation handling concrete

### SPC — Specification
- [ ] One candidate object, one yes/no question
- [ ] Every clause independently testable; combination rule explicit
- [ ] Indeterminate (missing-data) answer defined
- [ ] Satisfying and failing examples present

### PSV — Platform Service
- [ ] Exactly one bounded context (`context:` set)
- [ ] Capabilities-realized list complete with extent
- [ ] "Never does" exclusions present
- [ ] Quality attribute priorities ranked with rationale
- [ ] Collaborations abstract (business terms, no endpoints)

### PDT — Product
- [ ] Proposition timeless (no release language)
- [ ] Composition lists PSVs/AGTs that exist at least as drafts
- [ ] Boundaries vs sibling products explicit
- [ ] Not confused with a PRD (no requirement lists)

### AGT — AI Agent
- [ ] Permitted-actions list exhaustive; every action names PSV + bounding policy
- [ ] Autonomy matrix covers all action classes; money/legal actions never autonomous without explicit GOV-0002-approved exception
- [ ] Consent basis per observed input (ETE.DGV.01)
- [ ] Escalation, transparency, and kill condition defined
- [ ] Harm metric with alarm threshold present

### ADR (with TPL-0001)
- [ ] ≥ 2 real options; consequences include negatives
- [ ] Drivers ranked; decision traces to drivers
- [ ] Compliance mechanism stated
- [ ] Supersession links bidirectional (when applicable)

## 4. Checklist Maintenance

Checklists evolve with the templates: a template change PR MUST update its checklist here in the same PR. New artifact types get a checklist before their first artifact is reviewed.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Architecture Board | Initial checklists: universal + 12 artifact types. |
