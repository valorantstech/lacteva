---
id: TPL-0021
title: Policy Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
baseline: ARCH-BASELINE-V1
---

# TPL-0021 — Policy (POL) Template

> Template guidance: Copy below the rule into `docs/03-architecture/02-domain-layer/<context-folder>/POL-NNNN-<policy-name>.md`. A policy is a named business rule with parameters and enforcement points — e.g. "milk acceptance policy", "withdrawal exclusion policy", "settlement deduction ceiling policy". Policies make rules changeable without re-modeling: the rule's *shape* is here; its *parameters* vary per market/tenant via ETE.LOC.01-governed configuration.

---

```yaml
---
id: POL-NNNN
title: <Policy name>
type: pol
layer: domain
context: <DOM-NNNN>
status: Draft
version: "0.1"
owner: <policy owner — the role accountable for the rule>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<SPC-IDs used>, <BPR/AGG enforcement points>, <SWC.REG obligations>]
---
```

# POL-NNNN — \<Policy Name\>

## 1. Policy Statement

\<the rule, stated normatively and completely, using RFC 2119 keywords; reference SPC specifications for its predicates\>

## 2. Rationale and Authority

- **Why this rule exists:** \<business/regulatory driver\>
- **Authority:** \<who owns the rule — regulator, scheme owner, cooperative board — and under what instrument\>
- **Regulatory trace:** \<obligation reference (SWC.REG.01 register entry) or "internal policy"\>

## 3. Scope

- **Applies to:** \<which objects/actors/situations\>
- **Does not apply to:** \<explicit exclusions\>

## 4. Parameters

> Template guidance: everything that varies by market, scheme, or tenant is a named parameter — the policy text never hard-codes a local value.

| Parameter | Meaning | Varies By | Example Values |
| --- | --- | --- | --- |
| \<name\> | \<meaning\> | Market / Scheme / Tenant | \<illustrative only\> |

## 5. Enforcement Points

| Where | How the Policy Binds |
| --- | --- |
| \<BPR step / AGG operation / PSV behavior\> | \<blocks, warns, requires approval…\> |

## 6. Violation Handling

\<what happens on violation: who is notified, what is blocked/reversed, how exceptions are granted and recorded\>

## 7. Review Cadence

- **Reviewed:** \<frequency / trigger (e.g. on regulatory change detection)\>
- **Change process:** parameter changes vs rule-shape changes (rule-shape = new policy version via GOV-0002)

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
