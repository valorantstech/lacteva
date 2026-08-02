# Layer 03 — Application Layer

The **logical** application architecture: which platform services, products, and AI agents exist, what each is responsible for, and how they compose — all still implementation-free. This layer is the bridge between domain models and engineering artifacts: an SRS realizes a `PSV`; a PRD realizes part of a `PDT`; an AIM model card realizes part of an `AGT`.

## Artifact Types

| Prefix | Artifact | Template | One-Line Definition |
| --- | --- | --- | --- |
| `PSV` | Platform Service | [TPL-0015](../../02-templates/TPL-0015-platform-service-template.md) | Logical service with a stable responsibility boundary, realizing capabilities within one context |
| `PDT` | Product | [TPL-0016](../../02-templates/TPL-0016-product-template.md) | Market-facing product: proposition, audience, and the platform services composing it |
| `AGT` | AI Agent | [TPL-0023](../../02-templates/TPL-0023-ai-agent-template.md) | Charter for an autonomous/semi-autonomous AI actor: mission, permitted actions, guardrails |

**PDT vs PRD:** a `PDT` is the stable architecture object (what the product *is*, for years); a `PRD` specifies requirements for a release of it. Do not confuse the prefixes.

## Rules

- Templates mandatory; naming `<PREFIX>-NNNN-<name>.md`.
- **A platform service maps to exactly one bounded context** (a context may have several services; a service never spans contexts — that would dissolve the consistency boundary). Cross-context collaboration happens via events and published interfaces.
- Every PSV lists the capability IDs it realizes; every PDT lists the PSVs composing it; every AGT lists the capabilities it serves and the PSV(s) it acts through.
- AI agents never act outside their charter: the `AGT` document's permitted-actions and guardrail sections are the review anchor for everything the agent later does.
- Approval: Architecture Board member + owning team lead; AGT additionally follows the AIM approval row of [GOV-0002](../../01-governance/GOV-0002-approval-workflow.md) when models are involved.

## Index

| ID | Artifact | Kind | Realizes | Status |
| --- | --- | --- | --- | --- |
| [PDT-0001](PDT-0001-lacteva-collect.md) | Lacteva Collect | Product | MCL/QFS collection trust loop | Draft |
| — | *PSVs follow the first domain models (formalizing `services/platform-core` modules is review item MR-4); agents follow the DIA domain model.* | | | |
