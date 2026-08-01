# tools/

Internal developer tooling: repository lint/validation scripts, documentation checkers, code generators, and developer-experience utilities.

Empty during the documentation-foundation phase.

## Planned First Tools

The standards in [`docs/00-standards/`](../docs/00-standards/README.md) are written to be machine-checkable. **First delivery:** [`validate/validate_docs.py`](validate/README.md) implements the front-matter, ID, and link validators plus capability-reference checking; the diagram checker remains open. Planned validator set:

- **Front-matter validator** — every document has valid YAML front matter per [STD-0001 §2](../docs/00-standards/STD-0001-markdown-writing-standards.md) (required keys, valid status/version values).
- **ID checker** — document IDs are unique, match their filename per [STD-0002](../docs/00-standards/STD-0002-naming-conventions.md), and appear in their domain index.
- **Link checker** — all relative links and anchors resolve.
- **Diagram checker** — Mermaid blocks parse; every `.puml` has an in-sync `.svg` per [STD-0006 §3](../docs/00-standards/STD-0006-plantuml-standards.md).

## Rules (binding once code lands)

- Each tool has a `README.md` with usage; tools runnable in CI are also runnable locally with one command.
- Tools that enforce a standard link the standard they enforce; when a standard changes, its tool changes in the same or an immediately following PR.
