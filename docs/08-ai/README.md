# 08 — AI Documentation

Lacteva is AI-first: forecasting, quality intelligence, anomaly detection, and advisory features are core product, not add-ons. That makes AI documentation **contract-grade**. Every production AI/ML capability — trained model, fine-tune, or LLM-based feature — has an approved model card (`AIM`) **before it serves tenant traffic**.

- Template: [TPL-0007](../02-templates/TPL-0007-ai-model-card-template.md)
- Naming: `AIM-NNNN-<model-title>.md` per [STD-0002](../00-standards/STD-0002-naming-conventions.md)
- Versioning: model artifacts use `MAJOR.MINOR.PATCH`; the AIM document records the versions it covers, per [STD-0004 §5](../00-standards/STD-0004-versioning-strategy.md)
- Approval: AI platform owner + owning team lead; Legal/Compliance additionally when a model affects pricing, credit, or regulatory reporting ([GOV-0002](../01-governance/GOV-0002-approval-workflow.md))

## Non-Negotiables for Every AIM

- **Tenant data usage statement** — whether and how tenant data trains shared models, and the consent basis. No silent cross-tenant learning.
- **Segmented evaluation** — metrics reported per meaningful segment (herd size, region, breed), not just global averages; a model that only works for large European herds fails the mission.
- **Out-of-scope uses stated explicitly** — e.g. "not validated for veterinary diagnosis".
- **Fallback behavior** — what the product does when the model is unavailable or low-confidence.

## Index

| ID | Model / AI System | Task | Status |
| --- | --- | --- | --- |
| — | *No model cards yet — the first AIM documents accompany the first AI feature designs.* | | |
