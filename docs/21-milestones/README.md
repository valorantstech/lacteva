# 21 — Milestone Records

What was built, when, and what it cost to find out. Every `DEMO-*`, `PILOT-*`
and `LACTEVA-*` completion record, audit and investigation produced while the
platform was built — sixty-five documents, point-in-time by nature.

They are **history, not instruction**. A record here describes the state of the
world on the day it was written; where one disagrees with the code, the code is
right and the record is simply older. For what is currently true, read
[ARCHITECTURE_BASELINE_V1](../../ARCHITECTURE_BASELINE_V1.md),
[CHANGELOG](../../CHANGELOG.md), and the governed `docs/` tree.

They moved here from the repository root (LACTEVA-ARCH-002). At the root they
buried the twelve files a person actually needs, and their point-in-time claims
read at a glance as current fact — which is the specific harm this folder
exists to end. Nothing was deleted, and `git log --follow` still reaches every
one of them.

- Naming: as written — `DEMO-NNN-FINAL.md`, `LACTEVA-P0-*`, `PILOT-*`. These
  predate the `NNNN` numbering in
  [STD-0003](../00-standards/STD-0003-document-numbering.md) and keep the names
  the commits, the changelog and each other already use.
- Front matter, ids and versions are unchanged by the move.

## Rules

- **Append, never revise.** A milestone record is evidence of what was believed
  and proven at a moment. Correcting one in place destroys the only thing it is
  good for; a later record supersedes an earlier one.
- Three documents here are marked `Superseded` because they describe a
  repository layout this work order replaced:
  [REPOSITORY_AUDIT](REPOSITORY_AUDIT.md),
  [REPOSITORY_MIGRATION_PLAN](REPOSITORY_MIGRATION_PLAN.md) and
  [DEVELOPMENT_ROADMAP](DEVELOPMENT_ROADMAP.md).
- The live DR runbook is deliberately **not** here: `DEMO-011-DR-RUNBOOK.md`
  stays at the repository root because systemd units and the backup scripts
  name that path, and an operator reaches for it during an incident.

## Contents

| Family | Count | What it records |
| --- | --- | --- |
| `DEMO-*-FINAL.md` and companions | 37 | Each build increment: what shipped, what was proven, what was deliberately not built |
| `LACTEVA-*` | 22 | Readiness audits, hardening milestones and investigations |
| `PILOT-001-FINAL.md`, `PILOT-F03-FINAL.md` | 2 | The first pilot exercises |
| `REPOSITORY_*`, `DEVELOPMENT_ROADMAP.md` | 3 | Superseded repository-shape documents |
| `DEMO-024-FEATURE-MATRIX.csv` | 1 | The competitive feature matrix, as data |
