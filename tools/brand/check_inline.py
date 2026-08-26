#!/usr/bin/env python3
"""The inline copies of the mark must still be the mark (LACTEVA-BRAND-002).

    python3 tools/brand/check_inline.py

Two surfaces draw the mark inline rather than loading a file: the marketing
`logo.tsx` (its page ships no binary asset by rule) and the portal's app shell.
Neither can import from `mark.py`, so each carries the path data literally —
and a literal copy is exactly how this mark ended up existing three times with
three different geometries in the first place.

So the copies are checked. This runs in both client suites; if the generator's
numbers change and the inline copies are not regenerated, it fails and says
which file is stale.

Exit 0 = every surface agrees.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mark  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]

INLINE = [
    ("apps/marketing-site/src/components/logo.tsx", "the marketing lockup"),
    ("apps/admin-portal/src/components/app-shell.tsx", "the portal shell"),
]

# Files the generator writes, which must not be edited by hand either.
GENERATED_SVG = [("apps/marketing-site/src/app/icon.svg", "the marketing app icon")]


def main() -> int:
    path = mark.drop_path()
    problems: list[str] = []

    for relative, description in INLINE:
        source = (ROOT / relative).read_text(encoding="utf-8")
        if path not in source:
            problems.append(
                f"{relative} ({description}) does not carry the generated path.\n"
                f"    Run: python3 tools/brand/generate.py  — then update the inline copy."
            )

    expected_svg = mark.mark_svg()
    for relative, description in GENERATED_SVG:
        actual = (ROOT / relative).read_text(encoding="utf-8")
        if actual != expected_svg:
            problems.append(
                f"{relative} ({description}) is not what the generator produces.\n"
                f"    Run: python3 tools/brand/generate.py"
            )

    # The palette is pinned by the cross-client parity tests; this only checks
    # that the mark did not quietly acquire a colour of its own.
    for relative, _ in GENERATED_SVG:
        svg = (ROOT / relative).read_text(encoding="utf-8")
        for colour in (mark.DAIRY, mark.MILK):
            if colour not in svg:
                problems.append(f"{relative} no longer uses {colour}")

    if problems:
        print("The mark has drifted:\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"mark: one geometry, {len(INLINE) + len(GENERATED_SVG)} surfaces agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
