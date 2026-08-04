# Layer 05 — Security

Cross-cutting security architecture: trust boundaries, authentication and key management, data isolation, and the operational procedures that keep them true. Established by SEC-001 (Phase B).

Security is documented as its own layer rather than scattered through the technology layer because it *cuts across* every other one: a business rule, an application service, and a database table each have a security stance, and an auditor needs to read them together.

## Rules

- Nothing in this layer may weaken a business rule. Security hardens how behaviour is reached, never what it decides.
- Every control names its threat and its proving test. A control without a test is a claim.
- Residual risk is stated, not omitted. A threat model that mitigates everything is not being honest.
- Operational procedures live here too — a rotation nobody can perform is not a rotation.

## Index

| Document | Purpose |
| --- | --- |
| [SECURITY.md](SECURITY.md) | Trust boundaries, controls, failure modes, rollback |
| [THREAT-MODEL.md](THREAT-MODEL.md) | Twelve threats, mitigations, residual risk, proving tests |
| [JWT-ROTATION.md](JWT-ROTATION.md) | Key registry and the rotation runbook (scheduled and emergency) |
| [RLS-GUIDE.md](RLS-GUIDE.md) | Row-level security: policy design, testing strategy, operations |
| [SECURITY-CHECKLIST.md](SECURITY-CHECKLIST.md) | Pre-production gate, monitoring signals, incident response |

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-05 | Architecture Board | Layer established by SEC-001. |
