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
    # LACTEVA-BRAND-003: the RICH rendering. Same geometry, lit — so it is
    # checked against the same path. A surface that drew the enriched mark
    # from its own numbers would be the BRAND-002 defect wearing better
    # clothes.
    ("apps/admin-portal/src/components/brand-mark.tsx", "the portal rich mark"),
]

# Files the generator writes, which must not be edited by hand either.
GENERATED_SVG = [("apps/marketing-site/src/app/icon.svg", "the marketing app icon")]

# Generated in a language of its own. Flutter has no SVG renderer here, so the
# generator emits Dart; the check regenerates and compares, which is the same
# guarantee the SVG gets.
GENERATED_DART = [
    ("apps/mobile/lib/src/brand/mark.g.dart", "the Flutter mark"),
]

# The rich rendering's own numbers, wherever a surface has to name them.
RICH_STOPS = [
    ("apps/admin-portal/src/components/brand-mark.tsx", "the portal rich mark"),
    ("apps/marketing-site/src/components/logo.tsx", "the marketing rich mark"),
]


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

    rich_svg = ROOT / "tools/brand/lacteva-mark-rich.svg"
    if rich_svg.read_text(encoding="utf-8") != mark.rich_mark_svg():
        problems.append(
            "tools/brand/lacteva-mark-rich.svg is not what the generator produces.\n"
            "    Run: python3 tools/brand/generate.py"
        )

    import generate  # noqa: E402  — imported here so the check has one source

    for relative, description in GENERATED_DART:
        actual = (ROOT / relative).read_text(encoding="utf-8")
        if actual != generate._dart_mark():
            problems.append(
                f"{relative} ({description}) is not what the generator produces.\n"
                f"    Run: python3 tools/brand/generate.py"
            )

    # A rich surface must carry the highlight, the meniscus and every body
    # stop. Checking only the outline would let the LIGHT drift while the
    # silhouette stayed honest, which is exactly the half-drift BRAND-002
    # found: one surface had a highlight and the others did not.
    rich = mark.rich_details()
    required = [
        str(rich["highlight"]["cx"]),
        str(rich["highlight"]["cy"]),
        str(rich["meniscus"]["r"]),
        *[stop["color"] for stop in rich["body"]],
    ]
    for relative, description in RICH_STOPS:
        source = (ROOT / relative).read_text(encoding="utf-8")
        missing = [value for value in required if value not in source]
        if missing:
            problems.append(
                f"{relative} ({description}) has drifted from the rich mark: "
                f"missing {', '.join(missing)}.\n"
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

    surfaces = len(INLINE) + len(GENERATED_SVG) + len(GENERATED_DART) + 1
    print(f"mark: one geometry, {surfaces} surfaces agree (flat and rich)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
