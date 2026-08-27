"""The Lacteva mark, defined once (LACTEVA-BRAND-002; decision D-2).

The concept is unchanged and deliberately so: a milk drop in a rounded dairy
field. What changed is the drawing.

The interim mark existed three times — the marketing component, the marketing
`icon.svg`, and the portal shell — and the three had drifted into cousins with
different geometry, different viewBoxes and a "highlight" that appeared in one
and not the others. This module is the answer to that: every surface derives
from the numbers below, and a test asserts the inline copies still match.

WHAT WAS REFINED

* **Tangent continuity.** The interim flank was a cubic that met a circular
  bulb at a point where the two curves had different tangents — a visible
  corner on the drop's shoulder at any size above a favicon. The outline here
  is built from the tangent construction itself: the flanks leave the apex
  along the true tangent lines to the bulb and arrive at the tangent points,
  so the shoulder is smooth by arithmetic rather than by eye.

* **Optical centring.** A teardrop's mass sits in its bulb, so a drop whose
  bounding box is centred reads as sitting low. The whole form is lifted by
  `OPTICAL_LIFT` — small, because the correction is for the eye, not the
  ruler.

* **Corner radius.** 26.6% rather than 25%. At a 16px favicon a 25% radius is
  four physical pixels and antialiasing eats most of it, so the field reads
  almost square; easing it up keeps the intended roundness where the mark is
  smallest.

* **The highlight is gone.** It was drawn in the FIELD colour on top of the
  drop — a dark mark where a specular highlight should be light — it existed
  on only one of the three surfaces, and below about 48px it collapsed into a
  smudge. One clean silhouette survives masking, reads at 16px, and is the
  same shape on every surface, which is the entire point of this work order.

COLOUR is pinned elsewhere and merely referenced here: dairy #1B5E20 field,
milk #FDFBF4 drop. The palette is guarded by the cross-client parity tests and
is not this module's to change.
"""

from __future__ import annotations

import math

# --- the pinned palette (referenced, never redefined) -----------------------
DAIRY = "#1B5E20"
MILK = "#FDFBF4"

# --- the field --------------------------------------------------------------
FIELD = 64.0
CORNER = 17.0  # 26.6% of the side

# --- the drop ---------------------------------------------------------------
# Proportions carried from the interim mark (bulb ~41% of the field wide, the
# whole drop ~59% tall) so this reads as the same mark refined, not a new one.
BULB_R = 13.0
BULB_CY = 37.8
APEX_Y = 13.0
# The eye's correction, applied ONCE. Measured, not guessed: the drop's
# bounding box centres at 30.7 while its AREA centroid sits at 34.1, so the two
# pull in opposite directions. Placing the midpoint of the pair on the field
# centre is what makes a bulb-heavy form look centred, and 1.9 is the lift that
# lands it there exactly.
OPTICAL_LIFT = 1.9

# A falling drop's tip is never mathematically sharp — surface tension rounds
# it. The interim mark's apex was a needle, which at 192px reads as a spike and
# at 16px disappears into a single grey pixel. This is the radius of the small
# arc that replaces the point.
APEX_TIP = 2.5

# How full the flanks are. 0 draws the straight tangent lines — correct, but
# it reads as a map pin. A little outward bulge puts the liquid back.
FLANK_BULGE = 0.06


def _bezier_arc(cx: float, cy: float, r: float, a0: float, a1: float):
    """Circular arc from angle a0 to a1 (radians) as cubic Bézier segments.

    The standard construction: an arc of angle t is approximated to well
    within a printer's tolerance by a cubic whose control points sit
    (4/3)·tan(t/4)·r along the tangents. Split so no segment exceeds 90°.
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


def drop_outline(scale: float = 1.0, cx: float = FIELD / 2, cy: float = FIELD / 2):
    """The drop as (start_point, [(c1, c2, end), ...]), closed.

    `scale` and (`cx`, `cy`) place the same geometry on any canvas: the
    adaptive-icon foreground needs it smaller and centred in a 108 grid, the
    favicon needs it whole in a 64 one. Nothing is redrawn for either.
    """
    # Work in the 64 grid, then map.
    bx, by = FIELD / 2, BULB_CY - OPTICAL_LIFT
    ax, ay = FIELD / 2, APEX_Y - OPTICAL_LIFT
    r = BULB_R

    d = by - ay
    if d <= r:  # pragma: no cover - a drop whose apex is inside its own bulb
        raise ValueError("the apex must sit outside the bulb for a tangent to exist")
    alpha = math.acos(r / d)  # half-angle between the axis and each tangent

    # Tangent points, measured as angles around the bulb centre.
    phi_right = -(math.pi / 2) + alpha
    phi_left = -(math.pi / 2) - alpha

    def place(p):
        return (cx + (p[0] - FIELD / 2) * scale, cy + (p[1] - FIELD / 2) * scale)

    apex = (ax, ay)
    t_right = (bx + r * math.cos(phi_right), by + r * math.sin(phi_right))
    t_left = (bx + r * math.cos(phi_left), by + r * math.sin(phi_left))

    def flank(p_from, p_to, outward):
        """A cubic along the tangent line, bulged slightly outward."""
        dx, dy = p_to[0] - p_from[0], p_to[1] - p_from[1]
        length = math.hypot(dx, dy)
        nx, ny = -dy / length, dx / length  # unit normal
        push = FLANK_BULGE * length * outward
        c1 = (p_from[0] + dx / 3 + nx * push, p_from[1] + dy / 3 + ny * push)
        c2 = (p_from[0] + 2 * dx / 3 + nx * push, p_from[1] + 2 * dy / 3 + ny * push)
        return c1, c2

    def along(p_to):
        """A point `APEX_TIP` down the tangent from the apex towards `p_to`."""
        dx, dy = p_to[0] - apex[0], p_to[1] - apex[1]
        length = math.hypot(dx, dy)
        return (apex[0] + dx / length * APEX_TIP, apex[1] + dy / length * APEX_TIP)

    tip_right, tip_left = along(t_right), along(t_left)

    # The outline starts where the rounded tip leaves the LEFT flank and runs
    # clockwise: over the tip, down the right flank, around the bulb, back up
    # the left flank to where it began.
    segments = [
        # The tip: a cubic with both control points ON the apex — the
        # quadratic through it, tangent to each flank where it leaves, so the
        # tip is smooth rather than mitred.
        (apex, apex, tip_right),
        (*flank(tip_right, t_right, outward=1.0), t_right),
        *_bezier_arc(bx, by, r, phi_right, phi_left + 2 * math.pi),
        (*flank(t_left, tip_left, outward=1.0), tip_left),
    ]

    return place(tip_left), [
        (place(a), place(b), place(c)) for (a, b, c) in segments
    ]


def _n(v: float) -> str:
    """Three decimals, no trailing zeros — path data a human can read."""
    return f"{v:.3f}".rstrip("0").rstrip(".")


def drop_path(scale: float = 1.0, cx: float = FIELD / 2, cy: float = FIELD / 2) -> str:
    """The drop as an SVG `d` string (also valid Android vector pathData)."""
    start, segments = drop_outline(scale, cx, cy)
    parts = [f"M{_n(start[0])} {_n(start[1])}"]
    for c1, c2, end in segments:
        parts.append(
            f"C{_n(c1[0])} {_n(c1[1])} {_n(c2[0])} {_n(c2[1])} {_n(end[0])} {_n(end[1])}"
        )
    parts.append("Z")
    return "".join(parts)


def max_radius(scale: float, cx: float, cy: float, samples: int = 720) -> float:
    """Farthest the drawn drop reaches from (cx, cy).

    Used to PROVE the Android adaptive foreground stays inside the maskable
    safe circle rather than asserting it: the outline is sampled and measured.
    """
    start, segments = drop_outline(scale, cx, cy)
    worst = math.hypot(start[0] - cx, start[1] - cy)
    p0 = start
    for c1, c2, end in segments:
        for i in range(samples // len(segments) + 1):
            t = i / (samples // len(segments) or 1)
            u = 1 - t
            x = (
                u**3 * p0[0]
                + 3 * u**2 * t * c1[0]
                + 3 * u * t**2 * c2[0]
                + t**3 * end[0]
            )
            y = (
                u**3 * p0[1]
                + 3 * u**2 * t * c1[1]
                + 3 * u * t**2 * c2[1]
                + t**3 * end[1]
            )
            worst = max(worst, math.hypot(x - cx, y - cy))
        p0 = end
    return worst


def drop_bbox(samples: int = 2000):
    """The drop's tight bounding box in the 64 grid, curve extremes included.

    Lets a surface that wants the drop ALONE — the portal's shell wordmark —
    crop to it without redrawing anything: same path data, different viewBox.
    """
    start, segments = drop_outline()
    xs, ys = [start[0]], [start[1]]
    p0 = start
    per = max(2, samples // len(segments))
    for c1, c2, end in segments:
        for i in range(per + 1):
            t = i / per
            u = 1 - t
            xs.append(u**3 * p0[0] + 3 * u**2 * t * c1[0] + 3 * u * t**2 * c2[0] + t**3 * end[0])
            ys.append(u**3 * p0[1] + 3 * u**2 * t * c1[1] + 3 * u * t**2 * c2[1] + t**3 * end[1])
        p0 = end
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def drop_view_box() -> str:
    """`viewBox` cropping the 64 grid to the drop alone."""
    x, y, w, h = drop_bbox()
    return f"{_n(round(x, 2))} {_n(round(y, 2))} {_n(round(w, 2))} {_n(round(h, 2))}"


def field_path() -> str:
    """The rounded field, as an SVG `d` string (for Android's vector drawable,
    which has no <rect>)."""
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


# ---------------------------------------------------------------------------
# The RICH mark (LACTEVA-BRAND-003)
# ---------------------------------------------------------------------------
#
# Same drop, lit. The flat mark keeps the 16px jobs — favicon, launcher,
# anywhere the silhouette is the only thing that survives — and this rendering
# owns the surfaces where the mark is large and the ground is dark: the mobile
# and portal sign-in reveals.
#
# Depth comes from LIGHT, not effects. Three elements and no more:
#
#   * a body gradient running top-left to bottom-right, milk into a cream
#     shadow, so the drop has a lit side and a shaded belly;
#   * one warm specular highlight, high and left, where the light source is;
#   * one meniscus stroke — a low-opacity green arc inside the lower left of
#     the bulb, which is what the inside surface of liquid actually looks like.
#
# The interim mark's highlight was drawn in the FIELD colour ON TOP of the drop
# and died below 48px. This one is a soft radial that fades to nothing, and it
# is never used at a size where it could smudge, because the flat mark exists.
#
# The stops and the highlight/meniscus placement are the approved board's
# (`LogoReveal.dc.html`), mapped from ITS geometry onto OURS rather than
# copied as literals — the board draws a bulb of radius 31.5 in a 120 box, we
# draw radius 13 in a 64 one, and a pasted coordinate would put the highlight
# somewhere else entirely.

#: The cream shadow at the foot of the body gradient.
MILK_SHADOW = "#E4DEC9"
#: The lit edge — pure white, the only place the product uses it.
MILK_LIT = "#FFFFFF"

#: The board's own bulb, the frame its highlight and meniscus were drawn in.
_BOARD_BULB_R = 31.5
_BOARD_BULB = (60.0, 68.5)
#: Highlight: centre offset from the board's bulb centre, then its radii.
_BOARD_HIGHLIGHT = ((-13.0, -16.5), (15.0, 21.0))
#: Meniscus: start offset, arc radius, end offset, stroke width.
_BOARD_MENISCUS = ((-18.0, 23.5), 19.0, (-3.0, 40.5), 4.0)


def _board_scale() -> float:
    """How much of the board's drawing one of our units is worth."""
    return BULB_R / _BOARD_BULB_R


def rich_details():
    """The highlight and meniscus, placed on OUR 64 grid.

    Returned as plain numbers so every client — Python, TypeScript, Dart — can
    draw the same thing without re-deriving it, and so `mark.json` can carry
    the contract the inline copies are checked against.
    """
    k = _board_scale()
    bx, by = FIELD / 2, BULB_CY - OPTICAL_LIFT

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
    """The enriched drop, alone, cropped to itself.

    No field: this rendering is used large and on a dark ground, where a green
    rounded square around a milk drop would be a second shape competing with
    the first. The flat mark keeps the field, and keeps the small sizes.
    """
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
        # The meniscus is CLIPPED to the drop. Mapped faithfully, the board's
        # arc runs a little past the bottom of the bulb — on the board's own
        # dark ground that tail is invisible, but drawn honestly it would be a
        # green whisker hanging off the mark. A meniscus is the inside surface
        # of the liquid, so the inside of the drop is exactly where it is
        # allowed to be.
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


def mark_svg(size: int = FIELD, *, dark_ground: bool = False) -> str:
    """The complete mark: drop in field. `dark_ground` flips the two."""
    field, drop = (MILK, DAIRY) if dark_ground else (DAIRY, MILK)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(FIELD)} {int(FIELD)}">\n'
        f'  <rect width="{int(FIELD)}" height="{int(FIELD)}" rx="{_n(CORNER)}" fill="{field}"/>\n'
        f'  <path d="{drop_path()}" fill="{drop}"/>\n'
        f"</svg>\n"
    )
