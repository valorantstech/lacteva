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

## Precedence

If standards ever conflict, the more specific standard wins; if still ambiguous, [STD-0001](STD-0001-markdown-writing-standards.md) is the tiebreaker and an issue must be opened to resolve the conflict in the standards themselves.
