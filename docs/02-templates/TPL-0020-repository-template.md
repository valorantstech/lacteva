---
id: TPL-0020
title: Repository Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
baseline: ARCH-BASELINE-V1
---

# TPL-0020 — Repository (REP) Template

> Template guidance: Copy below the rule into `docs/03-architecture/02-domain-layer/<context-folder>/REP-NNNN-<aggregate-name>-repository.md`. A repository (DDD sense) is the access abstraction for ONE aggregate: how the domain retrieves and stores instances, in business terms. It is NOT a database design — the future DBD document realizes this abstraction and cites it. One repository per aggregate; needing a second is a sign the aggregate is wrong.

---

```yaml
---
id: REP-NNNN
title: <Aggregate name> Repository
type: rep
layer: domain
context: <DOM-NNNN>
status: Draft
version: "0.1"
owner: <context owner team>
created: <YYYY-MM-DD>
last-updated: <YYYY-MM-DD>
related: [<AGG-ID served>]
---
```

# REP-NNNN — \<Aggregate Name\> Repository

## 1. Serves

- **Aggregate:** \<AGG-ID\> — whole instances only; members are never accessed except through their aggregate.

## 2. Access Patterns

> Template guidance: the business's real retrieval needs — each pattern will justify an index or query design later. "By identity" is always first.

| # | Pattern | Who Needs It | Expected Frequency / Volume |
| --- | --- | --- | --- |
| A1 | By identity | \<consumer\> | \<scale\> |
| A2 | \<e.g. all collections for a producer in a period\> | \<e.g. settlement calculation\> | \<scale\> |

## 3. Selection Criteria

\<which `SPC` specifications this repository can select by (SPC-IDs) — repositories select by named specifications, not ad-hoc predicates\>

## 4. Consistency and Concurrency Expectations

- **Read-your-writes needed by:** \<consumers and why\>
- **Staleness tolerance for queries:** \<per pattern, in business terms\>
- **Concurrent modification handling:** \<business rule when two actors change one instance\>

## 5. Volume and Retention Reality

- **Instance count at target scale:** \<order of magnitude\>
- **Growth:** \<per period\>
- **Retention/archival expectation:** \<business need — realized later per DBD lifecycle rules\>

## 6. Realization Trace

| Realized By | Status |
| --- | --- |
| DBD | \<DBD-ID or "Not started"\> |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 0.1 | \<date\> | \<author\> | Initial draft. |
