# services/

Home of Lacteva's platform microservices — one subfolder per service, named per [STD-0002](../docs/00-standards/STD-0002-naming-conventions.md) (kebab-case, noun-based, e.g. `milk-collection-service/`).

This folder is intentionally empty during the documentation-foundation phase. Before the first service lands here, the platform ADRs (language/framework baseline, service template, CI conventions) must be approved in [`docs/03-architecture/adr/`](../docs/03-architecture/adr/README.md).

## Rules for Every Service (binding once code lands)

- Each service folder contains its own `README.md` (purpose, owner team, how to run), a `CHANGELOG.md` per [TPL-0012](../docs/02-templates/TPL-0012-changelog-template.md), and links to its governing documents (SRS, API, DBD, EVT).
- A service owns its datastore ([`docs/07-data/`](../docs/07-data/README.md) rules) and exposes contracts only through approved `API`/`EVT` specifications.
- Cross-service imports of another service's internals are prohibited; shared code lives in [`libs/`](../libs/README.md).
