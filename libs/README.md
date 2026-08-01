# libs/

Shared libraries used across services — one subfolder per library, named per [STD-0002](../docs/00-standards/STD-0002-naming-conventions.md) (`lacteva-` prefix for published packages, e.g. `lacteva-tenant-context/`).

Empty during the documentation-foundation phase.

## Rules (binding once code lands)

- A library exists only when at least two services need the same code; premature extraction is a review-blocking concern.
- Each library has its own `README.md`, `CHANGELOG.md` per [TPL-0012](../docs/02-templates/TPL-0012-changelog-template.md), and semantic versioning — services pin versions; no floating "latest".
- Libraries never contain business logic owned by a single bounded context; that belongs to the owning service.
