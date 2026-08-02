---
id: TPL-0007
title: AI Model Card Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
baseline: ARCH-BASELINE-V1
---

# TPL-0007 — AI Model Card Template

> Template guidance: Copy everything below the rule into `docs/08-ai/AIM-NNNN-<short-title>.md`. Every production AI/ML capability — trained model, fine-tune, or LLM-based feature — has a model card **before** it serves tenant traffic. For LLM-based features, "training data" sections become prompt/grounding-data sections; fill them in that spirit, not with "Not applicable". Lacteva is AI-first: this document is how we keep that trustworthy.

---

```yaml
---
id: AIM-NNNN
title: <Model/AI-system title>
type: aim
status: Draft
version: "0.1"
owner: <owning team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<SRS-ID>, <DBD-IDs for data sources>, <ADR-IDs>]
---
```

# AIM-NNNN — \<Title\>

## 1. Overview

- **Task:** \<what the model does, e.g. 7-day milk-yield forecast per animal\>
- **Type:** \<gradient-boosted regressor / time-series / LLM feature (base model + version) / …\>
- **Model artifact version(s) covered:** \<MAJOR.MINOR.PATCH range per STD-0004 §5\>
- **Owning service:** \<service exposing it; link SRS/API\>
- **Business motivation:** \<traces to BRD/PRD requirement IDs\>

## 2. Intended Use

- **Intended users and decisions supported:** \<who acts on the output and how\>
- **Out-of-scope uses:** \<uses the model is not validated for — be explicit; e.g. "not for veterinary diagnosis"\>
- **Human oversight:** \<fully automated / human-in-the-loop; what the human sees and can override\>

## 3. Inputs and Outputs

| Direction | Name | Type / Unit | Description |
| --- | --- | --- | --- |
| Input | \<feature/field\> | \<type, unit\> | \<meaning; source table/event (DBD/EVT ref)\> |
| Output | \<prediction/response\> | \<type, unit\> | \<meaning; including uncertainty representation\> |

## 4. Data

### 4.1 Training / Grounding Data

- **Sources:** \<datasets, date ranges, tenant consent basis\>
- **Tenant data usage:** \<whether tenant data trains shared models; isolation and consent rules — mandatory statement\>
- **Preprocessing:** \<cleaning, filtering, feature engineering summary\>
- **Known gaps:** \<breeds, climates, herd sizes, countries under-represented\>

### 4.2 Evaluation Data

\<held-out sets, their provenance, and why they represent production traffic\>

## 5. Evaluation

> Template guidance: Report metrics per meaningful segment, not just global averages — a model that works only for large European herds fails Lacteva's mission. State the acceptance thresholds that gate release.

| Metric | Definition | Global | Segment: \<e.g. herd < 20\> | Segment: \<region\> | Threshold |
| --- | --- | --- | --- | --- | --- |
| \<metric\> | \<definition\> | \<value\> | \<value\> | \<value\> | \<gate\> |

- **Baseline compared against:** \<previous model / heuristic / naive baseline\>
- **Evaluation cadence:** \<per release / scheduled re-evaluation\>

## 6. Limitations, Risks, and Fairness

- **Known failure modes:** \<conditions with degraded performance\>
- **Bias considerations:** \<segments at risk of systematic error and the checks applied\>
- **Consequence of wrong output:** \<what a bad prediction costs the user; why the oversight model in §2 is adequate\>

## 7. Operations

- **Serving:** \<batch/online; latency budget; fallback behavior when the model is unavailable\>
- **Monitoring:** \<drift metrics, performance metrics, alert thresholds\>
- **Retraining:** \<trigger (schedule/drift), pipeline, approval required for promotion\>
- **Rollback:** \<how a model version is rolled back; how long previous versions stay deployable\>

## 8. Versioning and Provenance

| Model Version | Date | Data Snapshot | Change | Evaluation Report |
| --- | --- | --- | --- | --- |
| \<x.y.z\> | \<date\> | \<snapshot id\> | \<what changed\> | \<link\> |

## 9. Compliance

\<regulatory obligations applicable in target markets (e.g. EU AI Act classification), assessment status, and Legal/Compliance approval reference when required per GOV-0002\>

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
