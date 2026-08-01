# xref/ — Automatic Cross-Reference Generator

Generates [`docs/XREF.md`](../../docs/XREF.md): for every ID-bearing document, the documents it cites and the documents citing it, plus a fan-in ranking (change-risk concentrators) and an unreferenced-document check.

## Usage

```bash
python3 tools/xref/generate_xref.py           # regenerate docs/XREF.md
python3 tools/xref/generate_xref.py --check   # CI mode: exit 1 if stale
```

## Rules

- `docs/XREF.md` is **generated — never hand-edited**. Regenerate it in the same PR as any change that adds/removes document-ID references.
- Mentions inside code fences are ignored; only references to documents that actually exist are counted (dangling IDs are the validator's job: [`tools/validate/`](../validate/README.md)).
- The map records which references **exist**; which references are **legal** is defined in the [architecture cross-reference index](../../docs/03-architecture/CROSS-REFERENCE.md).
