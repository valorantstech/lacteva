# 00 — Standards

The standards in this folder are **binding** for every contributor. They exist so that a repository maintained by hundreds of engineers reads as if it were written by one careful author.

Standards are themselves documents: they carry IDs, versions, and pass through the same review and approval workflows as everything else. To change a standard, open a PR against it (see [`CONTRIBUTING.md`](../../CONTRIBUTING.md)); standards changes require Architecture Board approval per [GOV-0002](../01-governance/GOV-0002-approval-workflow.md).

## Index

| ID | Title | Governs |
| --- | --- | --- |
| [STD-0001](STD-0001-markdown-writing-standards.md) | Markdown Writing Standards | Prose style, structure, front matter, links, tables |
| [STD-0002](STD-0002-naming-conventions.md) | Naming Conventions | File, folder, branch, and identifier naming |
| [STD-0003](STD-0003-document-numbering.md) | Document Numbering Conventions | Document ID prefixes, sequences, and registries |
| [STD-0004](STD-0004-versioning-strategy.md) | Versioning Strategy | Document versions, statuses, and lifecycle |
| [STD-0005](STD-0005-mermaid-standards.md) | Mermaid Standards | When and how to use Mermaid diagrams |
| [STD-0006](STD-0006-plantuml-standards.md) | PlantUML Standards | When and how to use PlantUML diagrams |
| [STD-0007](STD-0007-phoenix-software-engineering-standard.md) | Phoenix Software Engineering Standard | Project identity, the fifteen engineering principles, and the Definition of Done |

## Precedence

If standards ever conflict, the more specific standard wins; if still ambiguous, [STD-0001](STD-0001-markdown-writing-standards.md) is the tiebreaker and an issue must be opened to resolve the conflict in the standards themselves.

[STD-0007](STD-0007-phoenix-software-engineering-standard.md) is the exception to that shape. STD-0001 through STD-0006 govern how documents are *written*; STD-0007 governs how engineering is *done* here, so it applies to code, tests, and operations as much as to prose. On architecture it defers to [ARCHITECTURE_BASELINE_V1](../../ARCHITECTURE_BASELINE_V1.md); on prose it defers to STD-0001; on engineering conduct it wins, including over an in-flight work order.
