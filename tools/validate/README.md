# validate/ — Repository Documentation Validator

First working tool of the repository: enforces the machine-checkable rules of the standards suite. This implements three of the four validators specified in [`tools/README.md`](../README.md) (front matter, IDs/prefixes, links) plus the capability-reference check; the diagram checker remains to be built.

## Usage

```bash
python3 tools/validate/validate_docs.py            # from repo root or anywhere
python3 tools/validate/validate_docs.py --root /path/to/repo
```

Exit code `0` = clean; `1` = violations, each printed as `file: problem`. Intended as a CI gate (roadmap Phase 0.4, [QR-0004](../../docs/12-quality/QR-0004-documentation-roadmap.md)) and a pre-PR local check.

## What It Checks

| Check | Enforces | Notes |
| --- | --- | --- |
| Front matter completeness + valid status | [STD-0001 §2](../../docs/00-standards/STD-0001-markdown-writing-standards.md) | README/CHANGELOG-class files exempt |
| `context:` present on domain tactical artifacts (`agg`, `ent`, `val`, `rep`, `pol`, `spc`) | Domain-layer rules ([02-domain-layer](../../docs/03-architecture/02-domain-layer/README.md)) | Templates exempt |
| Document prefix registered; ID matches filename; IDs unique | [STD-0003](../../docs/00-standards/STD-0003-document-numbering.md) | Registry duplicated in the script — update both in one PR |
| Relative links resolve | [STD-0001 §6](../../docs/00-standards/STD-0001-markdown-writing-standards.md) | Skips code fences, inline code, template files, placeholder patterns |
| Capability references resolve against the model | [CAP-0001](../../docs/05-capabilities/CAP-0001-business-capability-master-map.md) | Catches typo'd `XXX.YYY.NN` citations anywhere |

## Known Limitations (deliberate for now)

- The prefix registry is duplicated from STD-0003 — a future version should parse the standard's table instead.
- No diagram validation (Mermaid parse / PlantUML-SVG sync) yet — fourth validator per `tools/README.md`.
- Index-table completeness ("is every document listed in its domain index?") is checked by reviewers, not yet by this script.
