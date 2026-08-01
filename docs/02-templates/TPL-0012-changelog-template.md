---
id: TPL-0012
title: Change Log Template
type: tpl
status: Approved
version: "1.0"
owner: Architecture Board
created: 2026-08-02
last-updated: 2026-08-02
---

# TPL-0012 — Change Log Template

> Template guidance: Two change-log forms exist in this repository; use the right one.
>
> 1. **In-document change log** — the `## Change Log` table every formal document ends with (shown first below).
> 2. **Component change log** — a `CHANGELOG.md` for a service, library, or the repository itself, following Keep a Changelog (shown second).

---

## Form 1 — In-Document Change Log

Append as the final section of every formal document:

```markdown
## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.1 | <YYYY-MM-DD> | <team/author> | <what changed and why, one line> |
| 1.0 | <YYYY-MM-DD> | <team/author> | Approved version. Approvers: <roles/names>. |
| 0.1 | <YYYY-MM-DD> | <team/author> | Initial draft. |
```

Rules:

- Newest row first.
- Every version bump per [STD-0004](../00-standards/STD-0004-versioning-strategy.md) adds exactly one row.
- The row for an approved version names the approvers (see [GOV-0002 §3](../01-governance/GOV-0002-approval-workflow.md)).
- Rows are never edited or deleted after merge.

---

## Form 2 — Component `CHANGELOG.md`

```markdown
# Changelog

All notable changes to <component> are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: <semantic versioning / STD-0004 §5 contract rules>.

## [Unreleased]

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security

## [1.0.0] - <YYYY-MM-DD>

### Added

- <change, written for the consumer of the component, not the author>
```

Rules:

- Entries describe the change's effect on consumers ("`POST /v1/collections` now accepts `sourceDeviceId`"), not the internal work ("refactored handler").
- Breaking changes are listed first in their release, bolded, prefixed **BREAKING:**.
- The `[Unreleased]` section is updated in the same PR as the change; releases move entries under a version heading.

## Change Log

| Version | Date | Author | Change |
| --- | --- | --- | --- |
| 1.0 | 2026-08-02 | Documentation Engineering | Initial approved version. |
