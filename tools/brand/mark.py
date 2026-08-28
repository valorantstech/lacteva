"""The Lacteva mark and wordmark, defined once (LACTEVA-BRAND-004; D-2).

Every surface in this repository derives its brand geometry from this module,
and `check_inline.py` fails the build if any copy of it drifts. That rule is
older than this file's contents: BRAND-002 found the mark existing three times
with three geometries and a highlight that appeared on one of them, and
nothing failed, because nothing was checking.

WHAT THE MARK IS NOW (BRAND-004, owner decision 2026-08-28)

A milk CAN with a drop knocked out of its belly. The can replaced the rounded
green field that BRAND-002 refined; the drop it carries is the same idea the
product has always used, now cut out of the metal rather than sitting on a
tile.

The can arrived as owner-approved path data on a 64 grid, and it is
reconstructed here from named parameters rather than pasted as a string, so
that a reader can see WHERE the shoulder flares and HOW tall the collar is
instead of counting along a run of `h` and `v` commands. `check_inline.py`
asserts the reconstruction still emits the owner's path character for
character — the parameters are a description of the artwork, never a redesign
of it.

WHAT WAS RULED AWAY

WO-31 shipped first with a colour splash inside the drop: a blue gradient, a
leaf, a white spray, four dots. Amendment 1 reverted all of it before any of
it was written. The drop is a plain knockout, which is why there is no clip
group, no second gradient and no size-dependent reduction ladder in this file
— a knockout reads at 16px and at 512px without being told to.

THE WORDMARK IS TRACED, NOT SET

Amendment 1 is explicit that no committed surface may carry a font-rendered
approximation of LACTEVA. The letterforms are the owner's artwork, so they are
vectorized from `reference/lacteva-wordmark-reference.png` by
`trace_wordmark.py` into `wordmark.json`, and this module reads that data.
Nothing here draws a letter; it places outlines that were measured.

COLOUR

The icon keeps the pinned product palette (`DAIRY`, `MILK`), which the
cross-client parity tests own. Everything the LOGO introduces — the navy, the
VA gradient, the rule and tagline greys — lives in the `LOGO_*` block below
and goes NOWHERE near the Design System V1.1 UI tokens. WO-31 is emphatic on
this and it is worth restating: no navy enters a token, a component or a
theme. A logo is a picture of the brand; a token is a contract with every
screen, and the two have different lifetimes.
"""

from __future__ import annotations

import functools
import json
import math
import pathlib

# --- the pinned product palette (referenced, never redefined) ---------------
DAIRY = "#1B5E20"
MILK = "#FDFBF4"

# --- LOGO_* : the identity's own colours, and only the identity's -----------
#: The can on a light ground.
LOGO_DAIRY = DAIRY
#: The can on ink, and the drop on a light ground.
LOGO_CREAM = MILK
#: The drop on ink. Deeper than DAIRY so the knockout still reads when the
#: body is cream rather than green.
LOGO_DEEP = "#0E3D14"
#: LACTE. Ruled by Amendment 2 from the reference itself.
LOGO_NAVY = "#022551"
#: Recorded so nobody re-derives it from the superseded base spec.
LOGO_NAVY_SUPERSEDED = "#1E2F5A"
#: VA's vertical gradient, sampled from the artwork.
LOGO_VA_TOP = "#6AA227"
LOGO_VA_BOTTOM = "#4C8C22"
#: The tagline's flanking rules, and the tagline itself.
LOGO_RULE = "#428B19"
LOGO_TAGLINE = "#3E4248"
#: The words, so no surface retypes them and gets the punctuation wrong.
TAGLINE = "Smart Dairy. Stronger Tomorrow."

# ---------------------------------------------------------------------------
# The can, on the 64 grid the owner drew it in
# ---------------------------------------------------------------------------

FIELD = 64.0
#: The rounded tile some surfaces still need BEHIND the mark — a launcher
#: icon has to fill its square with something. 26.6% rather than 25%: at a
#: 16px favicon a 25% radius is four physical pixels and antialiasing eats
#: most of it, so the field reads almost square.
CORNER = 17.0

#: The lid: a flat plate across the top of the neck.
LID_LEFT, LID_RIGHT, LID_TOP = 22.0, 42.0, 12.0
#: The neck, between the lid and the collar.
NECK_BOTTOM = 16.0
#: The collar: the wider band the handle would hang from.
COLLAR_LEFT, COLLAR_RIGHT, COLLAR_BOTTOM = 18.0, 46.0, 22.0
#: Where the shoulder starts to flare out toward the body.
SHOULDER_TOP = 24.0
#: The body: straight flanks, rounded foot.
BODY_LEFT, BODY_RIGHT = 16.0, 48.0
BODY_TOP, BODY_BOTTOM = 37.0, 57.0
BODY_CORNER = 6.0
#: The shoulder flare, as the control offsets of the cubic that draws it.
#: The two sides are NOT mirrors — the owner's left flare leaves the body
#: wall vertically (its first control point has no x offset) while the right
#: one turns immediately. Reproducing one by negating the other would quietly
#: straighten the left shoulder, so both are recorded.
FLARE_C1 = (4.0, 3.0)
FLARE_C2 = (6.0, 8.0)
FLARE_END = (6.0, 13.0)
LEFT_FLARE_C1 = (0.0, -5.0)
LEFT_FLARE_C2 = (2.0, -10.0)
LEFT_FLARE_END = (6.0, -13.0)

#: The drop knocked out of the belly. Its apex, the centre of its bulb and the
#: bulb's radius — the numbers the RICH rendering re-derives its light from,
#: which is why they are named here rather than buried in a path string.
DROP_APEX = (32.0, 30.0)
DROP_BULB = (32.0, 44.9)
DROP_BULB_R = 7.8
#: The flank cubic's control offsets from the apex.
DROP_C1 = (4.2, 5.9)
DROP_C2 = (7.8, 10.4)

#: The owner's own path data, recorded verbatim as it arrived in the work
#: order. `check_inline.py` walks BOTH this and the reconstruction above and
#: asserts they trace the same outline to within a thousandth of a grid unit.
#: Comparing the shapes rather than the strings is deliberate: two notations
#: for one curve are equal even when their characters differ, and it is the
#: curve the owner approved.
OWNER_CAN_BODY = (
    "M22 12h20v4h4v6h-4v2c4 3 6 8 6 13v14a6 6 0 0 1-6 6H22a6 6 0 0 1-6-6V37"
    "c0-5 2-10 6-13v-2h-4v-6h4v-4Z"
)
OWNER_DROP = (
    "M32 30c4.2 5.9 7.8 10.4 7.8 14.9a7.8 7.8 0 1 1-15.6 0C24.2 40.4 27.8 "
    "35.9 32 30Z"
)


def _n(v: float) -> str:
    """Three decimals, no trailing zeros — path data a human can read."""
    return f"{v:.3f}".rstrip("0").rstrip(".")


def _i(v: float) -> str:
    """The same number when it is known to be whole, for the owner's own form."""
    return f"{v:g}"


def _bezier_arc(cx: float, cy: float, r: float, a0: float, a1: float):
    """Circular arc from angle a0 to a1 (radians) as cubic Bezier segments.

    The standard construction: an arc of angle t is approximated to well
    within a printer's tolerance by a cubic whose control points sit
    (4/3)*tan(t/4)*r along the tangents. Split so no segment exceeds 90
    degrees.
    """
    sweep = a1 - a0
    count = max(1, math.ceil(abs(sweep) / (math.pi / 2)))
    step = sweep / count
    k = 4 / 3 * math.tan(step / 4) * r
    segments = []
    for i in range(count):
        s = a0 + i * step
        e = s + step
        p0 = (cx + r * math.cos(s), cy + r * math.sin(s))
        p1 = (p0[0] - k * math.sin(s), p0[1] + k * math.cos(s))
        p3 = (cx + r * math.cos(e), cy + r * math.sin(e))
        p2 = (p3[0] + k * math.sin(e), p3[1] - k * math.cos(e))
        segments.append((p1, p2, p3))
    return segments


def _place(scale: float, cx: float, cy: float):
    def inner(p):
        return (cx + (p[0] - FIELD / 2) * scale, cy + (p[1] - FIELD / 2) * scale)

    return inner


def drop_outline(scale: float = 1.0, cx: float = FIELD / 2, cy: float = FIELD / 2):
    """The drop as (start, [(c1, c2, end), ...]), closed, all cubics.

    Dart has no arc-in-a-path primitive that survives a const expression, and
    measuring a bounding box is far easier on cubics than on an arc flag, so
    the one arc in the owner's drop is expanded here. `check_inline.py` proves
    the expansion still is the owner's drop by sampling both.
    """
    ax, ay = DROP_APEX
    bx, by = DROP_BULB
    r = DROP_BULB_R
    place = _place(scale, cx, cy)

    right_c1 = (ax + DROP_C1[0], ay + DROP_C1[1])
    right_c2 = (ax + DROP_C2[0], ay + DROP_C2[1])
    right_end = (bx + r, by)
    left_c1 = (bx - r, ay + DROP_C2[1])
    left_c2 = (ax - DROP_C1[0], ay + DROP_C1[1])

    segments = [
        (right_c1, right_c2, right_end),
        # The bulb, swept the way the owner's arc flags sweep it: from the
        # right tangent point, under the bulb, to the left one.
        *_bezier_arc(bx, by, r, 0.0, math.pi),
        (left_c1, left_c2, (ax, ay)),
    ]
    return place((ax, ay)), [
        (place(a), place(b), place(c)) for (a, b, c) in segments
    ]


def can_outline(scale: float = 1.0, cx: float = FIELD / 2, cy: float = FIELD / 2):
    """The can body as (start, [(c1, c2, end), ...]), closed, all cubics."""
    place = _place(scale, cx, cy)

    #: The outline as commands, in drawing order. Straight runs are recorded
    #: as lines here and converted to cubics below, so the emitted path has
    #: ONE segment type — which is what lets Dart, cairo and the bounding-box
    #: sampler all walk it with the same three lines of code.
    commands: list[tuple] = []

    def to(p):
        commands.append(("L", p))

    start = (LID_LEFT, LID_TOP)
    to((LID_RIGHT, LID_TOP))
    to((LID_RIGHT, NECK_BOTTOM))
    to((COLLAR_RIGHT, NECK_BOTTOM))
    to((COLLAR_RIGHT, COLLAR_BOTTOM))
    to((LID_RIGHT, COLLAR_BOTTOM))
    to((LID_RIGHT, SHOULDER_TOP))
    commands.append(
        (
            "C",
            (LID_RIGHT + FLARE_C1[0], SHOULDER_TOP + FLARE_C1[1]),
            (LID_RIGHT + FLARE_C2[0], SHOULDER_TOP + FLARE_C2[1]),
            (LID_RIGHT + FLARE_END[0], SHOULDER_TOP + FLARE_END[1]),
        )
    )
    to((BODY_RIGHT, BODY_BOTTOM - BODY_CORNER))
    for segment in _bezier_arc(
        BODY_RIGHT - BODY_CORNER,
        BODY_BOTTOM - BODY_CORNER,
        BODY_CORNER,
        0.0,
        math.pi / 2,
    ):
        commands.append(("C", *segment))
    to((LID_LEFT, BODY_BOTTOM))
    for segment in _bezier_arc(
        BODY_LEFT + BODY_CORNER,
        BODY_BOTTOM - BODY_CORNER,
        BODY_CORNER,
        math.pi / 2,
        math.pi,
    ):
        commands.append(("C", *segment))
    to((BODY_LEFT, BODY_TOP))
    commands.append(
        (
            "C",
            (BODY_LEFT + LEFT_FLARE_C1[0], BODY_TOP + LEFT_FLARE_C1[1]),
            (BODY_LEFT + LEFT_FLARE_C2[0], BODY_TOP + LEFT_FLARE_C2[1]),
            (BODY_LEFT + LEFT_FLARE_END[0], BODY_TOP + LEFT_FLARE_END[1]),
        )
    )
    to((LID_LEFT, COLLAR_BOTTOM))
    to((COLLAR_LEFT, COLLAR_BOTTOM))
    to((COLLAR_LEFT, NECK_BOTTOM))
    to((LID_LEFT, NECK_BOTTOM))
    to((LID_LEFT, LID_TOP))

    segments = []
    previous = start
    for entry in commands:
        if entry[0] == "L":
            end = entry[1]
            # Control points ON the chord, so the cubic IS a straight line.
            c1 = (
                previous[0] + (end[0] - previous[0]) / 3,
                previous[1] + (end[1] - previous[1]) / 3,
            )
            c2 = (
                previous[0] + 2 * (end[0] - previous[0]) / 3,
                previous[1] + 2 * (end[1] - previous[1]) / 3,
            )
            segments.append((c1, c2, end))
            previous = end
        else:
            _, c1, c2, end = entry
            segments.append((c1, c2, end))
            previous = end

    return place(start), [
        (place(a), place(b), place(c)) for (a, b, c) in segments
    ]


def _as_path(start, segments) -> str:
    parts = [f"M{_n(start[0])} {_n(start[1])}"]
    for c1, c2, end in segments:
        parts.append(
            f"C{_n(c1[0])} {_n(c1[1])} {_n(c2[0])} {_n(c2[1])} {_n(end[0])} {_n(end[1])}"
        )
    parts.append("Z")
    return "".join(parts)


def drop_path(scale: float = 1.0, cx: float = FIELD / 2, cy: float = FIELD / 2) -> str:
    """The drop as an SVG `d` string (also valid Android vector pathData)."""
    return _as_path(*drop_outline(scale, cx, cy))


def can_path(scale: float = 1.0, cx: float = FIELD / 2, cy: float = FIELD / 2) -> str:
    """The can body as an SVG `d` string."""
    return _as_path(*can_outline(scale, cx, cy))


def mark_path(scale: float = 1.0, cx: float = FIELD / 2, cy: float = FIELD / 2) -> str:
    """Body and drop as ONE path, for surfaces that fill with `evenodd`.

    A single path means a single fill, which means the drop is a true
    knockout: whatever is behind the mark shows through it, at every size and
    on every ground, without anyone choosing a colour for it.
    """
    return can_path(scale, cx, cy) + drop_path(scale, cx, cy)


def _outline_bbox(outline, samples: int = 2400):
    start, segments = outline
    xs, ys = [start[0]], [start[1]]
    p0 = start
    per = max(2, samples // max(1, len(segments)))
    for c1, c2, end in segments:
        for i in range(per + 1):
            t = i / per
            u = 1 - t
            xs.append(
                u**3 * p0[0] + 3 * u**2 * t * c1[0] + 3 * u * t**2 * c2[0] + t**3 * end[0]
            )
            ys.append(
                u**3 * p0[1] + 3 * u**2 * t * c1[1] + 3 * u * t**2 * c2[1] + t**3 * end[1]
            )
        p0 = end
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def drop_bbox():
    """The drop's tight bounding box in the 64 grid, curve extremes included."""
    return _outline_bbox(drop_outline())


def can_bbox():
    """The can's tight bounding box in the 64 grid."""
    return _outline_bbox(can_outline())


def _view_box(box) -> str:
    x, y, w, h = box
    return f"{_n(round(x, 2))} {_n(round(y, 2))} {_n(round(w, 2))} {_n(round(h, 2))}"


def drop_view_box() -> str:
    """`viewBox` cropping the 64 grid to the drop alone."""
    return _view_box(drop_bbox())


def can_view_box() -> str:
    """`viewBox` cropping the 64 grid to the can alone."""
    return _view_box(can_bbox())


def max_radius(scale: float, cx: float, cy: float, samples: int = 1440) -> float:
    """Farthest the drawn MARK reaches from (cx, cy).

    The can is the outer shape now, so this measures the can — the drop is
    inside it by construction. Used to PROVE the Android adaptive foreground
    stays inside the maskable safe circle rather than asserting it.
    """
    start, segments = can_outline(scale, cx, cy)
    worst = math.hypot(start[0] - cx, start[1] - cy)
    p0 = start
    per = max(2, samples // max(1, len(segments)))
    for c1, c2, end in segments:
        for i in range(per + 1):
            t = i / per
            u = 1 - t
            x = (
                u**3 * p0[0] + 3 * u**2 * t * c1[0] + 3 * u * t**2 * c2[0] + t**3 * end[0]
            )
            y = (
                u**3 * p0[1] + 3 * u**2 * t * c1[1] + 3 * u * t**2 * c2[1] + t**3 * end[1]
            )
            worst = max(worst, math.hypot(x - cx, y - cy))
        p0 = end
    return worst


def field_path() -> str:
    """The rounded field, as an SVG `d` string (for Android's vector drawable,
    which has no `rect`)."""
    r, s = CORNER, FIELD
    return (
        f"M{_n(r)} 0"
        f"H{_n(s - r)}"
        f"A{_n(r)} {_n(r)} 0 0 1 {_n(s)} {_n(r)}"
        f"V{_n(s - r)}"
        f"A{_n(r)} {_n(r)} 0 0 1 {_n(s - r)} {_n(s)}"
        f"H{_n(r)}"
        f"A{_n(r)} {_n(r)} 0 0 1 0 {_n(s - r)}"
        f"V{_n(r)}"
        f"A{_n(r)} {_n(r)} 0 0 1 {_n(r)} 0"
        "Z"
    )


def mark_svg(size: int = FIELD, *, dark_ground: bool = False) -> str:
    """The complete icon: a rounded field, the can on it, the drop knocked out.

    `dark_ground` is for a surface that is already dark and supplies its own
    ground; the field is dropped and the can goes cream, which is the on-ink
    derivation WO-31 specifies.

    The drop is drawn in `LOGO_DEEP` rather than in the field colour. A true
    knockout would work too, but a launcher icon is composited over whatever
    wallpaper the person chose, and a hole would show it.
    """
    body, drop = LOGO_CREAM, LOGO_DEEP
    ground = (
        ""
        if dark_ground
        else (
            f'  <rect width="{int(FIELD)}" height="{int(FIELD)}"'
            f' rx="{_n(CORNER)}" fill="{LOGO_DAIRY}"/>\n'
        )
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(FIELD)} {int(FIELD)}">\n'
        f"{ground}"
        f'  <path d="{can_path()}" fill="{body}"/>\n'
        f'  <path d="{drop_path()}" fill="{drop}"/>\n'
        f"</svg>\n"
    )


def mark_on_light_svg() -> str:
    """The can alone, no field, for a light ground: dairy body, cream drop."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{can_view_box()}">\n'
        f'  <path d="{can_path()}" fill="{LOGO_DAIRY}"/>\n'
        f'  <path d="{drop_path()}" fill="{LOGO_CREAM}"/>\n'
        f"</svg>\n"
    )


# ---------------------------------------------------------------------------
# The RICH mark (LACTEVA-BRAND-003, re-derived onto BRAND-004's drop)
# ---------------------------------------------------------------------------
#
# Same drop, lit. The flat mark keeps the 16px jobs — favicon, launcher,
# anywhere the silhouette is the only thing that survives — and this rendering
# owns the surfaces where the mark is large and the ground is dark: the mobile
# and portal sign-in reveals.
#
# Depth comes from LIGHT, not effects. Three elements and no more: a body
# gradient running milk into a cream shadow, one warm specular highlight where
# the light source is, and one meniscus stroke, which is what the inside
# surface of liquid actually looks like.
#
# BRAND-004 changed the drop's size and position — it is a knockout in a can
# now, not a shape on a tile — and every number below FOLLOWS, because they
# are derived from the bulb rather than written down. That is the whole point
# of deriving them: the light moved with the drop and nobody had to move it.

#: The cream shadow at the foot of the body gradient.
MILK_SHADOW = "#E4DEC9"
#: The lit edge — pure white, the only place the product uses it.
MILK_LIT = "#FFFFFF"

#: The approved board's own bulb, the frame its highlight and meniscus were
#: drawn in (`LogoReveal.dc.html`). Mapped from ITS geometry onto OURS rather
#: than copied as literals: the board draws a bulb of radius 31.5 in a 120
#: box, and a pasted coordinate would put the highlight somewhere else.
_BOARD_BULB_R = 31.5
#: Highlight: centre offset from the board's bulb centre, then its radii.
_BOARD_HIGHLIGHT = ((-13.0, -16.5), (15.0, 21.0))
#: Meniscus: start offset, arc radius, end offset, stroke width.
_BOARD_MENISCUS = ((-18.0, 23.5), 19.0, (-3.0, 40.5), 4.0)


def _board_scale() -> float:
    """How much of the board's drawing one of our units is worth."""
    return DROP_BULB_R / _BOARD_BULB_R


def rich_details():
    """The highlight and meniscus, placed on OUR 64 grid.

    Returned as plain numbers so every client — Python, TypeScript, Dart — can
    draw the same thing without re-deriving it, and so `mark.json` can carry
    the contract the inline copies are checked against.
    """
    k = _board_scale()
    bx, by = DROP_BULB

    (hdx, hdy), (hrx, hry) = _BOARD_HIGHLIGHT
    (sdx, sdy), arc_r, (edx, edy), width = _BOARD_MENISCUS

    return {
        "highlight": {
            "cx": round(bx + hdx * k, 3),
            "cy": round(by + hdy * k, 3),
            "rx": round(hrx * k, 3),
            "ry": round(hry * k, 3),
        },
        "meniscus": {
            "x1": round(bx + sdx * k, 3),
            "y1": round(by + sdy * k, 3),
            "r": round(arc_r * k, 3),
            "x2": round(bx + edx * k, 3),
            "y2": round(by + edy * k, 3),
            "width": round(width * k, 3),
            #: The board's `stroke-opacity`. Low on purpose: a meniscus is a
            #: change in how the light bends, not a drawn line.
            "opacity": 0.18,
        },
        "body": [
            {"offset": 0.0, "color": MILK_LIT},
            {"offset": 0.55, "color": MILK},
            {"offset": 1.0, "color": MILK_SHADOW},
        ],
        #: The body gradient's axis, as SVG objectBoundingBox fractions.
        "bodyAxis": {"x1": 0.2, "y1": 0.0, "x2": 0.8, "y2": 1.0},
        #: The specular glow: white at the centre, gone at the rim.
        "glow": {"cx": 0.35, "cy": 0.28, "r": 0.55},
    }


def rich_mark_svg() -> str:
    """The enriched drop, alone, cropped to itself."""
    d = rich_details()
    h, m = d["highlight"], d["meniscus"]
    a, g = d["bodyAxis"], d["glow"]
    stops = "".join(
        f'\n      <stop offset="{_n(s["offset"])}" stop-color="{s["color"]}"/>'
        for s in d["body"]
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{drop_view_box()}">\n'
        "  <defs>\n"
        f'    <linearGradient id="lacteva-milkbody" x1="{_n(a["x1"])}" y1="{_n(a["y1"])}"'
        f' x2="{_n(a["x2"])}" y2="{_n(a["y2"])}">{stops}\n'
        "    </linearGradient>\n"
        f'    <radialGradient id="lacteva-milkglow" cx="{_n(g["cx"])}" cy="{_n(g["cy"])}" r="{_n(g["r"])}">\n'
        f'      <stop offset="0" stop-color="{MILK_LIT}"/>\n'
        f'      <stop offset="1" stop-color="{MILK_LIT}" stop-opacity="0"/>\n'
        "    </radialGradient>\n"
        # The meniscus is CLIPPED to the drop: mapped faithfully, the board's
        # arc runs a little past the bottom of the bulb, and drawn honestly
        # that tail would be a green whisker hanging off the mark.
        f'    <clipPath id="lacteva-drop"><path d="{drop_path()}"/></clipPath>\n'
        "  </defs>\n"
        f'  <path d="{drop_path()}" fill="url(#lacteva-milkbody)"/>\n'
        f'  <ellipse cx="{_n(h["cx"])}" cy="{_n(h["cy"])}" rx="{_n(h["rx"])}" ry="{_n(h["ry"])}"'
        ' fill="url(#lacteva-milkglow)" opacity="0.9"/>\n'
        f'  <path d="M{_n(m["x1"])} {_n(m["y1"])}A{_n(m["r"])} {_n(m["r"])} 0 0 0 {_n(m["x2"])} {_n(m["y2"])}"'
        f' fill="none" stroke="{DAIRY}" stroke-opacity="{_n(m["opacity"])}"'
        f' stroke-width="{_n(m["width"])}" stroke-linecap="round"'
        ' clip-path="url(#lacteva-drop)"/>\n'
        "</svg>\n"
    )


# ---------------------------------------------------------------------------
# The WORDMARK and the lockup (LACTEVA-BRAND-004, Amendment 1)
# ---------------------------------------------------------------------------
#
# Nothing below draws a letter. `trace_wordmark.py` vectorizes the owner's
# reference into `wordmark.json` and this reads it, because Amendment 1
# forbids a font-rendered approximation on any committed surface and a
# generator that "set" LACTEVA in whatever grotesque happened to be installed
# would be exactly that.
#
# The traced artwork lives in the reference's own 646 x 183 space. Every
# placement below is expressed in that space and scaled as a whole, so the
# letter spacing, the rule lengths and the tagline's position stay in the
# proportions the owner approved rather than being re-laid-out per surface.

WORDMARK_JSON = pathlib.Path(__file__).resolve().parent / "wordmark.json"

#: How much taller than the LACTEVA caps the can stands in the lockup. The
#: caps are 83 units and the can is 45 in its own grid; at 1.34 the can's
#: shoulder sits level with the cap line and its foot with the baseline,
#: which is what makes the two read as one object rather than as a picture
#: next to some words.
LOCKUP_CAN_RATIO = 1.34
#: The gap between the can and the L, as a fraction of the can's width. A
#: third is close enough to touch that they group, far enough that the can's
#: flare does not crowd the L's stem.
LOCKUP_GAP_RATIO = 0.34


@functools.lru_cache(maxsize=1)
def wordmark() -> dict:
    """The traced artwork, as generated data."""
    if not WORDMARK_JSON.exists():  # pragma: no cover - a fresh checkout has it
        raise SystemExit(
            f"{WORDMARK_JSON.name} is missing. "
            "Run: python3 tools/brand/trace_wordmark.py"
        )
    return json.loads(WORDMARK_JSON.read_text(encoding="utf-8"))


def wordmark_layer(name: str) -> str:
    """One traced ink's path data: `navy`, `green`, `tagline` or `rule`."""
    return wordmark()["layers"][name]["path"]


def wordmark_caps_bbox():
    """The LACTEVA caps alone — both inks, tagline and rules excluded.

    A header lockup wants the word and not the strapline, and cropping to the
    union of the two letter layers is the only way to get it without anyone
    typing a viewBox by hand.
    """
    navy = wordmark()["layers"]["navy"]["bbox"]
    green = wordmark()["layers"]["green"]["bbox"]
    x0 = min(navy[0], green[0])
    y0 = min(navy[1], green[1])
    x1 = max(navy[2], green[2])
    y1 = max(navy[3], green[3])
    return x0, y0, x1 - x0, y1 - y0


def wordmark_caps_view_box() -> str:
    """`viewBox` cropping the traced artwork to the LACTEVA caps."""
    return _view_box(wordmark_caps_bbox())


def _va_gradient(prefix: str, on_ink: bool) -> tuple[str, str]:
    """The VA gradient as (defs, fill). On ink there is no gradient to keep."""
    if on_ink:
        return "", LOGO_CREAM
    g = wordmark()["gradient"]
    ident = f"{prefix}-va"
    defs = (
        f'    <linearGradient id="{ident}" gradientUnits="userSpaceOnUse"'
        f' x1="0" y1="{_n(g["y0"])}" x2="0" y2="{_n(g["y1"])}">\n'
        f'      <stop offset="0" stop-color="{g["from"]}"/>\n'
        f'      <stop offset="1" stop-color="{g["to"]}"/>\n'
        "    </linearGradient>\n"
    )
    return defs, f"url(#{ident})"


def wordmark_svg(*, on_ink: bool = False, tagline: bool = True, prefix: str = "lacteva") -> str:
    """The owner's wordmark, traced, in its own 646 x 183 space.

    `on_ink` is the one-colour derivation Amendment 1 calls for: the same
    outlines, all cream. Not a different drawing — the identical paths, filled
    once. That is what makes it a derivation rather than a second wordmark.
    """
    data = wordmark()
    reference = data["reference"]
    height = reference["height"] if tagline else data["layers"]["navy"]["bbox"][3] + 1
    defs, va_fill = _va_gradient(prefix, on_ink)
    navy_fill = LOGO_CREAM if on_ink else LOGO_NAVY

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {reference["width"]} {_n(height)}">\n'
    ]
    if defs:
        parts.append("  <defs>\n" + defs + "  </defs>\n")
    parts.append(f'  <path d="{wordmark_layer("navy")}" fill="{navy_fill}"/>\n')
    parts.append(f'  <path d="{wordmark_layer("green")}" fill="{va_fill}"/>\n')
    if tagline:
        rule_fill = LOGO_CREAM if on_ink else LOGO_RULE
        tagline_fill = LOGO_CREAM if on_ink else LOGO_TAGLINE
        parts.append(f'  <path d="{wordmark_layer("rule")}" fill="{rule_fill}"/>\n')
        parts.append(
            f'  <path d="{wordmark_layer("tagline")}" fill="{tagline_fill}"/>\n'
        )
    parts.append("</svg>\n")
    return "".join(parts)


def lockup_geometry(*, tagline: bool = True):
    """Where the can and the traced artwork sit relative to each other.

    Returned as numbers rather than as a picture so the Play banner (drawn in
    cairo) and the SVG below place them identically. Two renderers laying out
    the same lockup from their own arithmetic is how a lockup ends up with two
    different gaps.
    """
    data = wordmark()
    reference = data["reference"]
    caps = data["layers"]["navy"]["bbox"]
    cap_top, cap_bottom = caps[1], caps[3]
    cap_height = cap_bottom - cap_top

    can_height = cap_height * LOCKUP_CAN_RATIO
    _, _, can_w, can_h = can_bbox()
    scale = can_height / can_h
    can_width = can_w * scale
    gap = can_width * LOCKUP_GAP_RATIO

    text_height = reference["height"] if tagline else cap_bottom + 1
    height = max(text_height, can_height)
    # The can is centred on the CAP band, not on the whole block: hanging it
    # level with a tagline that sits forty units lower would drag it off the
    # line the eye actually reads along.
    can_y = cap_top + cap_height / 2 - can_height / 2

    return {
        "width": can_width + gap + reference["width"],
        "height": height,
        "can": {
            "x": 0.0,
            "y": can_y,
            "width": can_width,
            "height": can_height,
            "scale": scale,
        },
        "text": {"x": can_width + gap, "y": 0.0},
        "reference": reference,
    }


def lockup_svg(*, on_ink: bool = False, tagline: bool = True, prefix: str = "lacteva") -> str:
    """The full lockup: the can, then LACTEVA, then the tagline."""
    geometry = lockup_geometry(tagline=tagline)
    can = geometry["can"]
    body = LOGO_CREAM if on_ink else LOGO_DAIRY
    drop = LOGO_DEEP if on_ink else LOGO_CREAM
    defs, va_fill = _va_gradient(prefix, on_ink)
    navy_fill = LOGO_CREAM if on_ink else LOGO_NAVY

    box = can_bbox()
    # Map the can's own 64-grid crop onto its slot in the lockup.
    transform = (
        f"translate({_n(can['x'])} {_n(can['y'])}) "
        f"scale({_n(can['scale'])}) "
        f"translate({_n(-box[0])} {_n(-box[1])})"
    )

    parts = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {_n(geometry["width"])} {_n(geometry["height"])}">\n'
        )
    ]
    if defs:
        parts.append("  <defs>\n" + defs + "  </defs>\n")
    parts.append(f'  <g transform="{transform}">\n')
    parts.append(f'    <path d="{can_path()}" fill="{body}"/>\n')
    parts.append(f'    <path d="{drop_path()}" fill="{drop}"/>\n')
    parts.append("  </g>\n")
    parts.append(f'  <g transform="translate({_n(geometry["text"]["x"])} 0)">\n')
    parts.append(f'    <path d="{wordmark_layer("navy")}" fill="{navy_fill}"/>\n')
    parts.append(f'    <path d="{wordmark_layer("green")}" fill="{va_fill}"/>\n')
    if tagline:
        rule_fill = LOGO_CREAM if on_ink else LOGO_RULE
        tagline_fill = LOGO_CREAM if on_ink else LOGO_TAGLINE
        parts.append(f'    <path d="{wordmark_layer("rule")}" fill="{rule_fill}"/>\n')
        parts.append(
            f'    <path d="{wordmark_layer("tagline")}" fill="{tagline_fill}"/>\n'
        )
    parts.append("  </g>\n")
    parts.append("</svg>\n")
    return "".join(parts)
