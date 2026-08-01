# Layer 01 — Business Layer

What the business does and how work flows through it. Two artifact families:

- **Business capabilities (`CAP`)** — the stable abilities. They live in [`docs/05-capabilities/`](../../05-capabilities/README.md) (their own documentation domain, established before this workspace) and are *referenced* from here, never duplicated.
- **Business processes (`BPR`)** — this folder. Ordered flows of work that exercise capabilities to produce an outcome: e.g. "morning collection round", "monthly settlement run", "new member onboarding". A capability is an ability; a process is a journey through abilities.

## Capability vs Process — the boundary

| | Capability (CAP) | Process (BPR) |
| --- | --- | --- |
| Nature | Ability, timeless | Flow, has start/end and triggers |
| Changes | Rarely | Whenever operations improve |
| Question | "Can we grade milk?" | "How does a delivery get graded, priced, and settled?" |
| Steps | Has none | Each step names the capability ID it exercises |

## Rules

- Template: [TPL-0014](../../02-templates/TPL-0014-business-process-template.md). Naming: `BPR-NNNN-<process-name>.md`.
- Every process step cites a capability ID (`FPR.HLT.02`-style); a step with no capability is a model gap — raise it against [CAP-0001](../../05-capabilities/CAP-0001-business-capability-master-map.md).
- Market variants are sections within one BPR (mirroring the capability model's global-variability rule), never separate per-country processes.
- Approval: domain owner + Architecture Board member.

## Index

| ID | Process | Capabilities Exercised (domains) | Status |
| --- | --- | --- | --- |
| — | *None yet. First candidates: collection-to-settlement flow (MCL→QFS→PEF), member onboarding (ETE→CPR→MCL), recall execution (QFS→CMA).* | | |
