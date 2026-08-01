# Contributing to the Lacteva Repository

This guide applies to **all** contributions — documentation and code. It is deliberately strict: with hundreds of contributors, consistency is what keeps this repository usable as the single source of truth.

## Before You Contribute

1. Read the standards in [`docs/00-standards/`](docs/00-standards/README.md). They cover Markdown style, naming, numbering, versioning, and diagrams.
2. Find the correct template in [`docs/02-templates/`](docs/02-templates/README.md). Documents that do not start from a template will be rejected in review.
3. Check the relevant index (each `docs/` domain has a `README.md` with a document index) to avoid duplicating an existing document.

## Contribution Workflow

1. **Branch.** Create a branch from the default branch using the naming scheme in [STD-0002 Naming Conventions](docs/00-standards/STD-0002-naming-conventions.md):
   - `docs/<doc-id>-<short-description>` for documentation (e.g., `docs/adr-0007-event-bus-selection`)
   - `feat/…`, `fix/…`, `chore/…` for code
2. **Author.** Copy the template, assign the next document ID per [STD-0003 Document Numbering](docs/00-standards/STD-0003-document-numbering.md), and fill in every section. Sections that genuinely do not apply must say `Not applicable — <reason>`, never be deleted.
3. **Self-review.** Run through the author checklist in the [Review Workflow](docs/01-governance/GOV-0001-review-workflow.md#author-checklist).
4. **Open a pull request.** Use the PR template. One document (or one coherent change) per PR — reviewers must be able to hold the whole change in their head.
5. **Review.** Reviews follow [GOV-0001 Review Workflow](docs/01-governance/GOV-0001-review-workflow.md). Address every comment explicitly — either change the document or explain why not.
6. **Approval.** Documents needing formal sign-off (ADRs, requirements, API contracts, etc.) follow [GOV-0002 Approval Workflow](docs/01-governance/GOV-0002-approval-workflow.md).
7. **Merge.** Squash-merge with a [Conventional Commits](https://www.conventionalcommits.org/) title, e.g. `docs(adr): add ADR-0007 event bus selection`.

## Commit Message Convention

```
<type>(<scope>): <summary>
```

- **type**: `docs`, `feat`, `fix`, `chore`, `refactor`, `test`, `ci`
- **scope**: the domain or component, e.g. `adr`, `api`, `glossary`, `standards`
- **summary**: imperative mood, lower case, no trailing period, ≤ 72 characters

## Pull Request Rules

- Keep PRs small and single-purpose. A new document and an unrelated fix are two PRs.
- Update the domain index (`README.md` of the folder) in the **same PR** that adds a document.
- Update the document's own change log section and, when applicable, the repository [`CHANGELOG.md`](CHANGELOG.md).
- New or changed diagrams must follow [STD-0005 Mermaid](docs/00-standards/STD-0005-mermaid-standards.md) or [STD-0006 PlantUML](docs/00-standards/STD-0006-plantuml-standards.md) standards.
- CODEOWNERS-designated reviewers are mandatory and may not be bypassed.

## What Gets a Contribution Rejected

- Document does not use the applicable template.
- Missing or malformed YAML front matter.
- Document ID collides with an existing ID or skips the sequence.
- Terms used that contradict the [glossary](docs/11-glossary/GLOSSARY.md) without proposing a glossary update.
- Diagrams that do not follow the diagram standards.
- PRs that bundle unrelated changes.

## Questions and Proposals

- To propose a change to a **standard**, open a PR against the standard itself — standards are documents and follow the same workflows.
- To propose a new **document type or template**, open a PR adding the template to `docs/02-templates/` with rationale in the PR description.
