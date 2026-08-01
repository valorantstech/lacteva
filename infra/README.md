# infra/

Infrastructure as code for the Lacteva platform: cloud resources, Kubernetes manifests, environment definitions, and delivery pipelines.

Empty during the documentation-foundation phase. The cloud provider, IaC tooling, and environment topology are platform ADRs to be authored in [`docs/03-architecture/adr/`](../docs/03-architecture/adr/README.md) before anything lands here.

## Rules (binding once code lands)

- All infrastructure is declared in code and applied through pipelines — no console-clicked resources; anything created manually during an incident is reconciled into code within 5 business days.
- Environments follow the naming in [STD-0002](../docs/00-standards/STD-0002-naming-conventions.md) (resource names carry environment suffixes).
- Secrets never appear in this folder in any form; reference the secrets manager.
- Changes affecting availability, cost profile, or tenant isolation require an ADR or an update to the relevant one.
