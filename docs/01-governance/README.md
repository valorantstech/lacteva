# 01 — Governance

This folder defines **how documents become authoritative**. Two workflows cover the whole lifecycle:

| ID | Title | Answers |
| --- | --- | --- |
| [GOV-0001](GOV-0001-review-workflow.md) | Review Workflow | How is a change reviewed? Who reviews it? What do reviewers check? |
| [GOV-0002](GOV-0002-approval-workflow.md) | Approval Workflow | Which documents need formal sign-off, from whom, and how is it recorded? |
| [GOV-0003](GOV-0003-architecture-review-checklists.md) | Architecture Review Checklists | What do reviewers additionally check per Enterprise Architecture artifact type? |

## The Short Version

1. Every change enters via pull request and is **reviewed** per GOV-0001 — no exceptions, including changes by senior staff.
2. Contract-like and decision documents (ADRs, requirements, APIs, events, database designs, AI documentation, standards) additionally require **approval** per GOV-0002 before their status becomes `Approved`.
3. Only `Approved` documents are authoritative.

Governance documents are themselves subject to these workflows; changing them requires Architecture Board approval.
