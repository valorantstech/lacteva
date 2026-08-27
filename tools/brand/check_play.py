#!/usr/bin/env python3
"""The store listing may not say what the website may not say (LAUNCH-001a).

    python3 tools/brand/check_play.py

A listing sits in a store nobody greps. The marketing site has carried an
executable claim guard since MKT-004, and every honest sentence on the website
was written under it — but the same product's Play description would have been
drafted with nothing checking it at all, which is exactly the asymmetry that
lets an overclaim ship.

So the patterns are READ OUT of the marketing suite's own
`claims.test.ts` rather than copied here. A copied list is a second list, and
this repository has been bitten four times by a second copy of something that
was supposed to have one home. If a pattern is added there, it applies here on
the next run without anyone remembering to mirror it.

Also checked, because a rejected upload costs a day:

  * the store limits Play enforces on title, short and full description;
  * the two generated assets' dimensions, and that each carries the
    transparency the spec wants — asserted rather than assumed.

Exit 0 = the listing is safe to paste into the console.
"""

from __future__ import annotations

import pathlib
import re
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[2]
LISTING = ROOT / "docs/20-business/LACTEVA-PLAY-LISTING.md"
CLAIMS = ROOT / "apps/marketing-site/src/app/claims.test.ts"

#: Play's own limits on the three text fields.
LIMITS = {"title": 30, "short": 80, "full": 4000}

#: What the generator writes, and what each file must be.
ASSETS = [
    ("tools/brand/play/icon-512.png", (512, 512), "opaque"),
    ("tools/brand/play/feature-graphic-1024x500.png", (1024, 500), "no-alpha"),
]

#: Play rejects anything over 1 MB for either image.
MAX_BYTES = 1024 * 1024


def claim_patterns() -> list[tuple[re.Pattern[str], str]]:
    """Every forbidden pattern the marketing guard enforces, as Python regexes.

    The two flavours differ in almost nothing that matters here: `\\b`, `\\d`,
    `\\s`, alternation and the one fixed-width lookbehind all mean the same
    thing in both. A pattern that did NOT translate would raise below rather
    than be silently skipped, which is the failure mode worth designing for.
    """
    source = CLAIMS.read_text(encoding="utf-8")
    entries = re.findall(
        r"\{\s*pattern:\s*/(.+?)/([a-z]*),\s*why:\s*\"(.*?)\"", source, re.S
    )
    if not entries:
        raise SystemExit(
            f"no claim patterns found in {CLAIMS.relative_to(ROOT)} — the guard "
            "this depends on has moved or changed shape"
        )
    compiled: list[tuple[re.Pattern[str], str]] = []
    for body, flags, why in entries:
        compiled.append(
            (re.compile(body, re.IGNORECASE if "i" in flags else 0), why)
        )
    return compiled


def listing_fields() -> dict[str, str]:
    """The three copy blocks, by the marker that precedes each fence."""
    text = LISTING.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    for name in LIMITS:
        match = re.search(
            rf"<!-- listing:{name} -->\s*```\n(.*?)```", text, re.S
        )
        if not match:
            raise SystemExit(
                f"{LISTING.relative_to(ROOT)} has no `listing:{name}` block — "
                "the checker cannot vouch for copy it cannot find"
            )
        fields[name] = match.group(1).strip()
    return fields


def main() -> int:
    problems: list[str] = []
    fields = listing_fields()
    patterns = claim_patterns()

    for name, text in fields.items():
        for pattern, why in patterns:
            if pattern.search(text):
                problems.append(
                    f"the {name} description says {pattern.pattern!r} — {why}"
                )
        limit = LIMITS[name]
        if len(text) > limit:
            problems.append(
                f"the {name} description is {len(text)} characters; "
                f"Play's limit is {limit}"
            )

    for relative, size, transparency in ASSETS:
        path = ROOT / relative
        if not path.exists():
            problems.append(
                f"{relative} is missing. Run: python3 tools/brand/generate.py"
            )
            continue
        if path.stat().st_size > MAX_BYTES:
            problems.append(
                f"{relative} is {path.stat().st_size // 1024} KB; Play's limit is 1024 KB"
            )
        image = Image.open(path)
        if image.size != size:
            problems.append(f"{relative} is {image.size}, must be {size}")
        if transparency == "opaque":
            # A 32-bit PNG is fine; a transparent one shows the store's own
            # ground through the corners Play has already rounded.
            if "A" in image.getbands() and min(image.getchannel("A").getdata()) != 255:
                problems.append(f"{relative} has transparent pixels")
        elif transparency == "no-alpha" and "A" in image.getbands():
            problems.append(
                f"{relative} carries an alpha channel; the feature graphic "
                "must have none"
            )

    if problems:
        print("The Play listing is not ready:\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"play listing: {len(fields)} copy blocks clear of "
        f"{len(patterns)} claim patterns, {len(ASSETS)} assets to spec"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
