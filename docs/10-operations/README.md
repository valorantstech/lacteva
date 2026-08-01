# 10 — Operations

Operational documentation: runbooks, incident-response procedures, and on-call references (`OPS` prefix). This domain populates as services approach production.

## What Belongs Here

- **Runbooks** — step-by-step procedures for operating a service: deploy, roll back, scale, common failure modes and their remedies.
- **Incident response** — severity definitions, escalation paths, postmortem process.
- **On-call references** — dashboards, alert catalogs, paging policies.

## Rules

- Naming: `OPS-NNNN-<short-title>.md` per [STD-0002](../00-standards/STD-0002-naming-conventions.md). An `OPS` runbook template will be added to `02-templates/` alongside the first runbook and this README updated to link it.
- Approval: owning team lead + on-call lead ([GOV-0002](../01-governance/GOV-0002-approval-workflow.md)).
- A runbook that has drifted from reality is worse than no runbook: every incident postmortem includes a "runbook accurate?" check, and inaccuracies are fixed in the postmortem's follow-up PRs.
- Secrets, credentials, and customer data never appear in runbooks — link to the secrets manager by reference.

## Index

| ID | Runbook | Service | Status |
| --- | --- | --- | --- |
| — | *No operational documents yet — runbooks are written as services approach production readiness.* | | |
