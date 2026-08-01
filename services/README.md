# services/

Home of Lacteva's platform services — one subfolder per service, named per [STD-0002](../docs/00-standards/STD-0002-naming-conventions.md) (kebab-case, noun-based).

| Service | Purpose | Status |
| --- | --- | --- |
| [`platform-core/`](platform-core/README.md) | Platform foundation: identity, organizations, authn/authz, configuration, audit, event/notification/storage/search infrastructure (modular monolith; modules are future service seams) | M0 delivered — see [DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) |

Note: the stack and service shape were directed externally ahead of the founding platform ADRs; backfilling those ADRs is queue item B4 ([QR-0006](../docs/12-quality/QR-0006-next-work-queue.md)) so decisions get their durable record.

## Rules for Every Service (binding once code lands)

- Each service folder contains its own `README.md` (purpose, owner team, how to run), a `CHANGELOG.md` per [TPL-0012](../docs/02-templates/TPL-0012-changelog-template.md), and links to its governing documents (SRS, API, DBD, EVT).
- A service owns its datastore ([`docs/07-data/`](../docs/07-data/README.md) rules) and exposes contracts only through approved `API`/`EVT` specifications.
- Cross-service imports of another service's internals are prohibited; shared code lives in [`libs/`](../libs/README.md).
