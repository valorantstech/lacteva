#!/usr/bin/env python3
"""Every copy of the mark must still be the mark (LACTEVA-BRAND-004).

    python3 tools/brand/check_inline.py

Some surfaces draw the brand inline rather than loading a file: the marketing
lockup (its page ships no binary asset by rule), the portal's app shell and
the portal's rich mark. None of them can import from `mark.py`, so each
carries the path data literally — and a literal copy is exactly how this mark
came to exist three times with three different geometries in the first place.

So the copies are checked. Four different things are proved here, and they are
different on purpose:

  1. THE ARTWORK IS THE OWNER'S. `mark.py` rebuilds the can and the drop from
     named parameters instead of pasting the owner's path strings, which makes
     the file readable and makes a redesign possible by accident. So both
     reconstructions are walked against the owner's own recorded path data and
     must trace the same outline. Parameters that drift stop being a
     description and start being a new logo; this is what notices.

  2. THE INLINE COPIES CARRY THE GENERATED PATHS. Silhouette and light both —
     BRAND-002 found a mark whose outline agreed across surfaces while its
     highlight existed on only one of them, so checking the outline alone
     would have passed that defect.

  3. THE GENERATED FILES ARE WHAT THE GENERATOR PRODUCES, byte for byte.

  4. THE WORDMARK IS THE TRACED ARTWORK. `wordmark.json` is generated data and
     CI does not re-trace it (the reference and the tracer are committed as
     provenance, per WO-31 Amendment 2). What is checked here is that the
     committed outlines and everything emitted from them still agree, and that
     no surface has quietly acquired letterforms of its own.

Exit 0 = every surface agrees.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mark  # noqa: E402
import svgpath  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: How far the parametric reconstruction may sit from the owner's own path
#: data, in grid units. A thousandth of a unit on a 64 grid is a fifteen
#: thousandth of the mark's width — far below anything a renderer can show,
#: and far above the Bezier-vs-arc residual, which is the only difference the
#: two notations legitimately have.
OWNER_TOLERANCE = 0.002

#: Surfaces that carry path data literally, and which of the generated paths
#: each of them must contain.
INLINE = [
    ("apps/marketing-site/src/components/logo.tsx", "the marketing lockup", ("can", "drop")),
    ("apps/admin-portal/src/components/app-shell.tsx", "the portal shell",
     ("can", "drop", "wordmark-navy", "wordmark-green")),
    # WO-39: the portal's front door. The login, reset-password and
    # accept-invitation pages all draw this one composition, and it is the
    # first surface anywhere to carry the tagline and its rules — so this is
    # the only place those two layers are guarded against drift.
    ("apps/admin-portal/src/components/lockup.tsx", "the portal auth lockup",
     ("can", "drop", "wordmark-navy", "wordmark-green",
      "wordmark-rule", "wordmark-tagline")),
    # LACTEVA-BRAND-003: the RICH rendering. Same geometry, lit — so it is
    # checked against the same path. A surface that drew the enriched mark
    # from its own numbers would be the BRAND-002 defect wearing better
    # clothes.
    ("apps/admin-portal/src/components/brand-mark.tsx", "the portal rich mark", ("drop",)),
]

#: Files the generator writes, which must not be edited by hand either.
GENERATED_SVG = [
    ("apps/marketing-site/src/app/icon.svg", "the marketing app icon", "mark_svg"),
    ("tools/brand/lacteva-mark-rich.svg", "the rich mark", "rich_mark_svg"),
    ("tools/brand/lacteva-mark.svg", "the can on a light ground", "mark_on_light_svg"),
    ("tools/brand/lacteva-lockup.svg", "the full lockup", "lockup_svg"),
    ("tools/brand/lacteva-lockup-on-ink.svg", "the lockup on ink", "lockup_on_ink"),
    ("tools/brand/lacteva-wordmark.svg", "the wordmark", "wordmark_svg"),
    ("tools/brand/lacteva-wordmark-on-ink.svg", "the wordmark on ink", "wordmark_on_ink"),
]

#: Generated in a language of its own. Flutter has no SVG renderer here, so
#: the generator emits Dart; the check regenerates and compares, which is the
#: same guarantee the SVG gets.
GENERATED_DART = [("apps/mobile/lib/src/brand/mark.g.dart", "the Flutter mark")]

#: The rich rendering's own numbers, wherever a surface has to name them.
RICH_STOPS = [
    ("apps/admin-portal/src/components/brand-mark.tsx", "the portal rich mark"),
    ("apps/marketing-site/src/components/logo.tsx", "the marketing rich mark"),
]


def _generated_svg(kind: str) -> str:
    return {
        "mark_svg": mark.mark_svg,
        "rich_mark_svg": mark.rich_mark_svg,
        "mark_on_light_svg": mark.mark_on_light_svg,
        "lockup_svg": mark.lockup_svg,
        "lockup_on_ink": lambda: mark.lockup_svg(on_ink=True),
        "wordmark_svg": mark.wordmark_svg,
        "wordmark_on_ink": lambda: mark.wordmark_svg(on_ink=True),
    }[kind]()


def main() -> int:
    problems: list[str] = []
    paths = {
        "can": mark.can_path(),
        "drop": mark.drop_path(),
        "wordmark-navy": mark.wordmark_layer("navy"),
        "wordmark-green": mark.wordmark_layer("green"),
        "wordmark-rule": mark.wordmark_layer("rule"),
        "wordmark-tagline": mark.wordmark_layer("tagline"),
    }

    # 1 · the reconstruction is still the owner's artwork
    owner_checks = (
        ("the can body", mark.OWNER_CAN_BODY, paths["can"]),
        ("the drop", mark.OWNER_DROP, paths["drop"]),
    )
    for label, owner, built in owner_checks:
        deviation = svgpath.max_deviation(owner, built, 60)
        if deviation > OWNER_TOLERANCE:
            problems.append(
                f"{label} in mark.py no longer traces the owner's own path: "
                f"they differ by {deviation:.4f} grid units (limit "
                f"{OWNER_TOLERANCE}).\n"
                "    The parameters have stopped describing the approved "
                "artwork and started redesigning it."
            )

    # 2 · every inline copy carries what it is supposed to carry
    for relative, description, wanted in INLINE:
        source = (ROOT / relative).read_text(encoding="utf-8")
        for name in wanted:
            if paths[name] not in source:
                problems.append(
                    f"{relative} ({description}) does not carry the generated "
                    f"{name} path.\n"
                    "    Run: python3 tools/brand/generate.py  — then update "
                    "the inline copy."
                )

    # 3 · the generated files are what the generator produces
    import generate  # noqa: E402  — imported here so the check has one source

    for relative, description, kind in GENERATED_SVG:
        actual = (ROOT / relative).read_text(encoding="utf-8")
        if actual != _generated_svg(kind):
            problems.append(
                f"{relative} ({description}) is not what the generator produces.\n"
                "    Run: python3 tools/brand/generate.py"
            )

    for relative, description in GENERATED_DART:
        actual = (ROOT / relative).read_text(encoding="utf-8")
        if actual != generate._dart_mark():
            problems.append(
                f"{relative} ({description}) is not what the generator produces.\n"
                "    Run: python3 tools/brand/generate.py"
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
                "    Run: python3 tools/brand/generate.py  — then update the "
                "inline copy."
            )

    # 4 · the wordmark is the traced artwork, and still says what it says
    data = mark.wordmark()
    for layer in ("navy", "green", "rule", "tagline"):
        path = data["layers"][layer]["path"]
        if not path.startswith("M") or not path.endswith("Z") or len(path) < 200:
            problems.append(
                f"the traced wordmark's {layer} layer is not a real outline "
                f"({len(path)} chars).\n"
                "    Run: python3 tools/brand/trace_wordmark.py"
            )
    for name, pinned in (
        ("navy", mark.LOGO_NAVY),
        ("vaTop", mark.LOGO_VA_TOP),
        ("vaBottom", mark.LOGO_VA_BOTTOM),
        ("rule", mark.LOGO_RULE),
        ("tagline", mark.LOGO_TAGLINE),
    ):
        if data["colours"][name] != pinned:
            problems.append(
                f"the traced wordmark's {name} is {data['colours'][name]} but "
                f"mark.py emits {pinned} — one of the two has moved."
            )
    # The reference and the tracer are committed as provenance (Amendment 2).
    # They are not run here, but a missing one means nobody can ever check
    # this artwork again, which is worth failing over.
    for relative in (
        "tools/brand/reference/lacteva-wordmark-reference.png",
        "tools/brand/trace_wordmark.py",
    ):
        if not (ROOT / relative).exists():
            problems.append(f"{relative} is missing — the wordmark's provenance is gone")

    if problems:
        print("The mark has drifted:\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    # The label must count what was actually ENFORCED, not what was easy to
    # add up. `RICH_STOPS` is a second, different check on a file `INLINE`
    # already covers — the outline AND the light — so it is a check rather
    # than a surface.
    surfaces = {relative for relative, _, _ in INLINE}
    surfaces |= {relative for relative, _, _ in GENERATED_SVG}
    surfaces |= {relative for relative, _ in GENERATED_DART}
    checks = (
        len(owner_checks)
        + sum(len(wanted) for _, _, wanted in INLINE)
        + len(GENERATED_SVG)
        + len(GENERATED_DART)
        + len(RICH_STOPS)
        + 4  # the four traced layers
    )
    print(
        f"mark: one geometry, {len(surfaces)} surfaces agree across {checks} "
        "checks (owner artwork, flat, rich and traced wordmark)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
