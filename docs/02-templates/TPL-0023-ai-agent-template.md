---
id: TPL-0023
title: AI Agent Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# TPL-0023 — AI Agent (AGT) Template

> Template guidance: Copy below the rule into `docs/03-architecture/03-application-layer/AGT-NNNN-<agent-name>.md`. An AGT is the **charter** of an AI agent: an autonomous or semi-autonomous actor that observes, decides, and acts on behalf of users or the platform. The charter is the review anchor for everything the agent may ever do — actions outside it are defects by definition. Models powering the agent get AIM model cards; this document governs the *actor*, not the models.

---

```yaml
---
id: AGT-NNNN
title: <Agent name — role-like, e.g. "Collection Anomaly Sentinel">
type: agt
layer: application
status: Draft
version: "0.1"
owner: <owning team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<PSV-IDs acted through>, <AIM-IDs>, <POL-ID guardrails>, <CON-IDs>]
---
```

# AGT-NNNN — \<Agent Name\>

## 1. Mission

- **Purpose:** \<the outcome the agent pursues, one sentence\>
- **On behalf of:** \<whose interests it serves — a tenant, a role, the platform\>
- **Capabilities served:** \<capability IDs\>

## 2. Autonomy Level

| Action Class | Autonomy |
| --- | --- |
| \<e.g. issue advisory notification\> | Autonomous |
| \<e.g. adjust a schedule\> | Propose — human approves |
| \<e.g. anything affecting money or legal standing\> | Never — escalate only |

## 3. Observes

| Input | Source | Consent Basis |
| --- | --- | --- |
| \<events/data observed\> | \<capability/PSV\> | \<per ETE.DGV.01 — mandatory column\> |

## 4. Permitted Actions

> Template guidance: exhaustive. The agent may do these things and NOTHING else; each action names the PSV it acts through and the policy bounding it.

| # | Action | Through | Bounded By |
| --- | --- | --- | --- |
| A1 | \<action\> | \<PSV-ID\> | \<POL-ID / parameter limits\> |

## 5. Guardrails

- **Hard limits:** \<rate/volume/value ceilings; protected actions; forbidden data uses\>
- **Escalation:** \<conditions that stop the agent and summon a human; to whom\>
- **Transparency:** \<how affected users know an agent acted; how they contest it\>
- **Kill condition:** \<who may suspend the agent and how fast that takes effect\>

## 6. Decision Accountability

- **Decision records:** every action is attributable and reconstructable: \<what is recorded\>
- **Model dependencies:** \<AIM-IDs; behavior when models are unavailable/low-confidence\>

## 7. Success and Harm Measures

| Measure | Definition | Threshold / Alarm |
| --- | --- | --- |
| \<benefit metric\> | \<definition\> | \<target\> |
| \<harm metric — mandatory, e.g. wrongful-action rate\> | \<definition\> | \<alarm level triggering review\> |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
