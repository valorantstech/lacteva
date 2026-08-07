---
id: STD-0007
title: Phoenix Software Engineering Standard
type: standard
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-08
last-updated: 2026-08-08
related: [STD-0001, STD-0004, GOV-0002, GOV-0003, CLAUDE-CONTEXT]
baseline: ARCH-BASELINE-V1
---

# STD-0007 — Phoenix Software Engineering Standard

## 1. Purpose and status

This is a **permanent engineering directive**, not a work order. It has no scope, no deliverables, and no completion. It governs every change made to this repository from its adoption onward, and it outlives the work order that happens to be in flight.

Where a work order and this standard disagree about *how* work is done, this standard wins and the conflict is recorded. Where this standard and [ARCHITECTURE_BASELINE_V1](../../ARCHITECTURE_BASELINE_V1.md) disagree about *what the architecture is*, the baseline wins — this document governs engineering conduct, not architectural content.

## 2. Project identity

This repository is **not a standalone application**. It is the flagship product of a software company.

| | |
| --- | --- |
| **Company** | Phoenix Software |
| **Product** | Lacteva |
| **Category** | Enterprise dairy platform |

The distinction is load-bearing rather than cosmetic. A standalone application may serve the customer in front of it; a flagship product must serve customers who have not arrived yet, on deployments nobody has provisioned, in countries nobody has sold into. That is why variability is configuration and not forks, why `Organization.id` is the tenant id in every query, and why a market-specific constant in business logic is a defect rather than a shortcut.

### 2.1 Who Lacteva must serve

The platform must, over its lifetime, serve all of:

- individual farmers
- collection centers
- dairy cooperatives
- private dairies
- milk unions
- multi-country deployments

These are not market segments to be chosen between. They are **six operating scales that must coexist in one architecture**, from a single farmer with a phone to a union federating hundreds of societies across borders. A design that serves one by making another impossible has failed, even if it ships.

The architecture must support **years of evolution**. Concretely: today's module boundaries are tomorrow's service seams; today's event contracts are consumed by modules that do not exist yet; today's schema is restored from a backup taken by a version nobody is running any more.

## 3. Engineering principles

These fifteen are binding. They are ordered as written, not by importance.

| # | Principle | What it means in this repository |
| --- | --- | --- |
| 1 | **Architecture before implementation** | The shape is decided, and recorded, before code is written. Extend within established shapes ([CLAUDE_CONTEXT §9](../ai/CLAUDE_CONTEXT.md)). |
| 2 | **Business rules before code** | A rule gets a [Business Rules Register](../03-architecture/01-business-layer/BUSINESS-RULES.md) entry (`BR-NNNN`), then enforcing code citing the ID, then a verifying test — in the same change. Register↔code divergence is a defect. |
| 3 | **Security by default** | The secure path is the default path and the insecure one requires an explicit, named override. Nothing sensitive in source; configuration through environment. |
| 4 | **Multi-tenancy by default** | Every table declares an isolation strategy; every query is tenant-filtered *and* the database enforces it with row-level security. A new table without a policy does not ship. |
| 5 | **Offline-first where applicable** | Collection happens where connectivity fails. The device records; the platform decides (BR-0021). Offline is a transport concern, never a business-rule concern. |
| 6 | **Every production guarantee must be executable** | See §4 — this is the principle with the most history behind it. |
| 7 | **No feature without automated tests** | Including the failure paths, the permission checks, the tenant isolation, and the concurrency rule. A bug fix lands with the regression test that fails without it. |
| 8 | **No feature without observability** | Metrics in the one registry, structured logs of facts, health contribution where a component can fail, and the correlation id carried through (BR-0024). |
| 9 | **No duplicated concepts** | One canonical model per concept, owned by exactly one module, referenced elsewhere by id. |
| 10 | **Reusable platform capabilities over feature-specific implementations** | See §5. |
| 11 | **Maintainability over cleverness** | The clever version is a liability the day its author is unavailable. |
| 12 | **Every architectural shortcut must be documented** | A recorded pragmatism is an engineering decision; an unrecorded one is a trap. The divergence register in [CLAUDE_CONTEXT](../ai/CLAUDE_CONTEXT.md) is where they live. |
| 13 | **Protect backwards compatibility whenever practical** | Events are versioned; migrations are additive where they can be; a backup taken by an older version stays restorable. "Whenever practical" is a real qualifier — see §6. |
| 14 | **Minimize technical debt** | Debt taken deliberately is recorded with its interest rate. Debt taken accidentally is a defect. |
| 15 | **Understandable by a new senior engineer six months from now** | The readability test for every change: not "can I follow this today", but "can somebody who was not in this conversation follow it without asking me". |

## 4. Principle 6 in detail: executable guarantees

**Documentation alone is insufficient.** A guarantee that has not been executed is an intention, however carefully it is written and however thoroughly it was reviewed.

This principle is stated more strongly than the others because this repository has the evidence for it. Two work orders did nothing but execute guarantees that were already written, already reviewed, already CI-wired — and found **nine defects**, of which four were fatal to the platform or to a recovery:

| Found by executing | Consequence |
| --- | --- |
| `SET LOCAL lacteva.tenant_id = $1` — a syntax error on PostgreSQL | The platform could not serve **one request** on its production engine ([VER-001](../03-architecture/06-operations/VER-001-VERIFICATION-REPORT.md)) |
| The application connected as a superuser | **Every** row-level security policy was inert; tenant isolation was application-level only |
| Backups aborted on a `time` column | Any deployment with one working collection center **could not be backed up at all** ([DR-001](../03-architecture/06-operations/DR-001-RECOVERY-REPORT.md)) |
| Nothing verified a backup before restoring it | A corrupt backup restored silently: a settlement worth 1.00 instead of 5647.50 |

Every one of those had passed review. None was findable by reading. All were found in the first minutes of running the code against a real engine.

**The operational rule.** A guarantee counts as proven only when it is executed against the technology it is claimed for. Consequences, all of which are already in force here:

- A PostgreSQL guarantee tested only on SQLite is **untested** — `is_postgres()` returns false, the function returns early, and the test goes green having exercised nothing.
- A verification pipeline that cannot be executed in the environment where the code is written **will not be executed.** Hence `infra/ci/verify-postgres.sh` and `infra/ci/dr-proof.sh`, which stand up real PostgreSQL from a wheel and need no Docker, no daemon, and no root.
- A **skipped** proof is worse than an absent one, because it is green. `LACTEVA_REQUIRE_POSTGRES=1` turns a missing database into a collection error.
- A proof must establish that the guard is **capable of refusing**, not merely that it is present. Checking `pg_policies` for rows was never evidence of enforcement.
- A test that reimplements the thing it tests is testing the copy. The RLS suite issued its own binding SQL for two work orders while the production binding raised a syntax error on every call.

## 5. Principle 10 in detail: build platform capabilities

Prefer the reusable capability over the specific implementation. The vendor is a detail behind a port; the capability is the thing the platform owns.

| Build this | Not this |
| --- | --- |
| Notification Engine | An SMS implementation |
| Payment Framework | A Razorpay implementation |
| Authentication Platform | A login endpoint |
| Reporting Engine | One report |

This is already the established pattern rather than an aspiration: `Notifier`, `EventBus`, `ObjectStorage` and the hardware adapters are ports with real and in-memory implementations, and MSG-001 added a production SMS gateway as a `ChannelProvider` behind the existing Notification Engine rather than as an SMS feature.

**The test.** Before implementing, ask what the *second* instance of this thing looks like — the second gateway, the second payment rail, the second report, the second country. If the answer requires touching the first implementation, the seam is in the wrong place.

**The counterweight.** Principle 10 is not licence to build a framework nobody has asked for. A capability with exactly one implementation and no second one in sight is speculative generality, which principle 11 rejects. Build the capability when the second case is real, foreseeable, or cheap to allow for — and record the judgement either way.

## 6. Review policy: correct, do not preserve

Future work orders should continue to challenge previous assumptions, **including those made in this document**.

When an earlier architectural decision is objectively incorrect:

1. **Document it** — what was decided, what is actually true, and how the gap survived.
2. **Correct it.**
3. **Update the documentation** that asserted the wrong thing, including its change log.
4. **Never preserve a mistake merely because it already exists.**

"Objectively incorrect" is the bar, and it is deliberately higher than "I would have done it differently". A decision is objectively incorrect when it is factually wrong, when it violates a stated principle, or when executing it produces a result that contradicts what it claims. Style disagreements are not defects; consistency (principle 9) usually outranks personal preference.

This policy has already been exercised in both directions, which is the point of stating it. DBR-001 raised two findings that ABR-002 then **withdrew** — they were derived from the default SQLAlchemy dialect rather than the PostgreSQL one, and were wrong. Correcting the record mattered as much as the findings that stood.

**Backwards compatibility interacts with this (principle 13).** Correcting a mistake that would break existing deployments is still correct, but the migration path is part of the correction, not an afterthought. Worked example: DR-001 added a schema revision to every backup manifest and refuses a mismatched restore — but an *unknown* revision only warns, because making every previously-taken backup unrestorable would be a worse failure than the one being guarded against.

## 7. Definition of Done

No work order is complete until all six have been **considered**, and the closing summary says what was concluded for each. "Considered and not applicable, because …" is a complete answer; silence is not.

| # | Dimension | The question |
| --- | --- | --- |
| 1 | **Implementation** | Is the whole requested scope delivered — not the easy part, with the rest unmentioned? |
| 2 | **Tests** | Do they fail without the change? Do they cover permissions, tenant isolation, failure paths, and concurrency? |
| 3 | **Documentation** | Is every document that asserted something now-false updated, with its change log? |
| 4 | **Architecture consistency** | Does this match the nearest neighbour, or has it introduced a third way of doing something? |
| 5 | **Operational impact** | What does an operator have to do, know, or watch that they did not before? What breaks at 3 a.m., and how would they know? |
| 6 | **Production readiness** | What is proven by execution, and what is still only asserted? State the remaining limitations plainly. |

Dimension 6 is where principle 6 is enforced, and it must be answered honestly: an unstated limitation reads as a covered case.

## 8. Relationship to existing standards

This standard sits **above** the authoring standards and **beside** the governance workflows. It does not replace any of them.

- [STD-0001](STD-0001-markdown-writing-standards.md) … [STD-0006](STD-0006-plantuml-standards.md) govern how documents are written. Unchanged.
- [GOV-0001](../01-governance/GOV-0001-review-workflow.md) / [GOV-0002](../01-governance/GOV-0002-approval-workflow.md) govern how work is reviewed and approved. Unchanged; §7 adds what a reviewer should expect a summary to answer.
- [CLAUDE_CONTEXT](../ai/CLAUDE_CONTEXT.md) is the operational onboarding guide. It now carries these principles in §0 and points here for the reasoning.

On conflict: the baseline wins on architecture, this standard wins on engineering conduct, and STD-0001 remains the tiebreaker on prose.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-08 | Architecture Board | Established by the Phoenix Software Engineering Standard directive: project identity (Phoenix Software / Lacteva), fifteen binding principles, executable-guarantee doctrine, platform-capability preference, review policy, and the six-dimension Definition of Done. |
