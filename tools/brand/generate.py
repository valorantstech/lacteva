#!/usr/bin/env python3
"""Generate every Lacteva brand asset from the one geometry (LACTEVA-BRAND-002).

    python3 tools/brand/generate.py

Idempotent: run it again and the same bytes come out. That is the point — the
mark had drifted into three hand-drawn cousins, and the way to stop that
happening again is for no raster or SVG in this repository to be drawn by
hand. `mark.py` holds the numbers; this file puts them on every surface.

Requires `pycairo` and `Pillow`, both already present in the environment used
by the docs tooling. No ImageMagick, no Inkscape, no network.

Surfaces written:

  tools/brand lacteva-lockup*.svg                  (the full lockup, for WO-32)
              lacteva-wordmark*.svg                (the traced wordmark alone)
              lacteva-mark.svg                     (the can, on a light ground)
              play/*                               (the store kit)
  marketing   src/app/icon.svg                     (the SVG master, mark-only)
  portal      src/app/favicon.ico                  (multi-resolution)
  mobile      android .../mipmap-*/ic_launcher.png (legacy, five densities)
              android .../mipmap-anydpi-v26/*.xml  (adaptive)
              android .../drawable/ic_launcher_foreground.xml
              android .../values/ic_launcher_background.xml
              web/favicon.png, web/icons/*         (incl. maskable)
              ios .../AppIcon.appiconset/*.png     (every size Contents.json names)

The two inline SVGs — the marketing `logo.tsx` and the portal shell — cannot
import from a Python module, so they carry the path string literally and
`tools/brand/check_inline.py` (run by the portal and marketing suites) asserts
they still match what this file would produce.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

import cairo
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mark  # noqa: E402
import svgpath  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]

DAIRY_RGB = (0x1B / 255, 0x5E / 255, 0x20 / 255)
MILK_RGB = (0xFD / 255, 0xFB / 255, 0xF4 / 255)
# The band's far corners (LACTEVA-BRAND-003 / MOBILE-007): two stops banded
# visibly across a surface this wide, so the gradient gets the third the
# boards give it.
DAIRY_DEEP_RGB = (0x0E / 255, 0x3D / 255, 0x14 / 255)
DAIRY_NIGHT_RGB = (0x12 / 255, 0x3A / 255, 0x18 / 255)

# Android's maskable contract: a 108dp canvas of which the centre 72dp is
# visible and only a 66dp CIRCLE is guaranteed. Everything the foreground
# draws must live inside that circle on every launcher shape there is.
ADAPTIVE_CANVAS = 108.0
SAFE_RADIUS = 33.0
SAFE_MARGIN = 0.92  # keep a little back from the edge of the guarantee


def _rounded_field(ctx: cairo.Context) -> None:
    r, f = mark.CORNER, mark.FIELD
    ctx.new_path()
    ctx.arc(r, r, r, math.pi, 1.5 * math.pi)
    ctx.arc(f - r, r, r, 1.5 * math.pi, 0)
    ctx.arc(f - r, f - r, r, 0, 0.5 * math.pi)
    ctx.arc(r, f - r, r, 0.5 * math.pi, math.pi)
    ctx.close_path()


def _outline(ctx: cairo.Context, outline) -> None:
    start, segments = outline
    ctx.new_path()
    ctx.move_to(*start)
    for c1, c2, end in segments:
        ctx.curve_to(c1[0], c1[1], c2[0], c2[1], end[0], end[1])
    ctx.close_path()


def _drop(ctx: cairo.Context, scale=1.0, cx=mark.FIELD / 2, cy=mark.FIELD / 2) -> None:
    _outline(ctx, mark.drop_outline(scale, cx, cy))


def _can(ctx: cairo.Context, scale=1.0, cx=mark.FIELD / 2, cy=mark.FIELD / 2) -> None:
    _outline(ctx, mark.can_outline(scale, cx, cy))


def render(
    size: int, *, dark_ground=False, full_bleed=False, maskable=False
) -> Image.Image:
    """One rendering of the icon at `size` px: field, can, drop.

    `full_bleed` fills the whole square instead of the rounded field, for the
    platforms that supply their own shape. `maskable` additionally shrinks the
    MARK into Android's guaranteed safe CIRCLE — iOS does not need it, because
    its mask is a superellipse that keeps far more of the square, and a can
    sized for a circle looks lost inside one.

    BRAND-004 made the can the outer shape, so what gets measured against the
    safe circle is the can; the drop is inside it by construction and needs no
    separate guarantee.
    """
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)
    ctx.scale(size / mark.FIELD, size / mark.FIELD)

    ground_rgb = MILK_RGB if dark_ground else DAIRY_RGB
    body_rgb = DAIRY_RGB if dark_ground else _hex_rgb(mark.LOGO_CREAM)
    drop_rgb = _hex_rgb(mark.LOGO_CREAM) if dark_ground else _hex_rgb(mark.LOGO_DEEP)

    if full_bleed:
        ctx.rectangle(0, 0, mark.FIELD, mark.FIELD)
    else:
        _rounded_field(ctx)
    ctx.set_source_rgb(*ground_rgb)
    ctx.fill()

    placement = _safe_placement() if maskable else (1.0, mark.FIELD / 2, mark.FIELD / 2)
    _can(ctx, *placement)
    ctx.set_source_rgb(*body_rgb)
    ctx.fill()
    _drop(ctx, *placement)
    ctx.set_source_rgb(*drop_rgb)
    ctx.fill()

    surface.flush()
    data = bytes(surface.get_data())
    # cairo gives premultiplied BGRA; these fills are fully opaque, so a
    # channel swap is all that is needed.
    img = Image.frombuffer("RGBA", (size, size), data, "raw", "BGRA", surface.get_stride(), 1)
    return img.convert("RGBA")


def _safe_placement() -> tuple[float, float, float]:
    """(scale, cx, cy) in the 64 grid that fits the MARK in the safe circle."""
    reach = mark.max_radius(1.0, mark.FIELD / 2, mark.FIELD / 2)
    allowed = (SAFE_RADIUS / ADAPTIVE_CANVAS) * mark.FIELD * SAFE_MARGIN
    return allowed / reach, mark.FIELD / 2, mark.FIELD / 2


def write(path: pathlib.Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(path, mode) as handle:
        handle.write(data)
    print(f"  {path.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Google Play store assets (LACTEVA-LAUNCH-001a)
# ---------------------------------------------------------------------------
#
# The two images the Play Console will not accept a listing without. Both are
# generated from the same geometry as everything else, so the store shows the
# mark the product actually has.
#
# THE SPEC APPLIED, and how each decision was made safe against a policy this
# machine cannot fetch:
#
#   * Hi-res icon — 512 x 512 PNG, under 1 MB. Play documents "32-bit PNG"
#     and separately composites its own rounded mask and shadow. The rounded
#     field this product uses would therefore be rounded TWICE, and its
#     transparent corners would show the store's own ground through the gap.
#     So the icon is FULL BLEED and FULLY OPAQUE: a 32-bit PNG whose alpha
#     channel is 255 everywhere. That satisfies "32-bit PNG" and "no
#     transparency" at once, whichever the live policy says today, and it is
#     asserted rather than assumed — see `check_play.py`.
#
#   * Feature graphic — 1024 x 500, and this one genuinely must not be
#     transparent: it is a banner Play draws behind its own controls. It is
#     written as RGB with no alpha channel at all, so there is nothing to get
#     wrong.
#
# SAFE MARGINS. Play crops the feature graphic on some surfaces and lays a
# play button over its centre on others. Everything that carries meaning is
# kept inside the central box below, which leaves a tenth of the width and a
# eighth of the height clear on every side.
PLAY_ICON = 512
FEATURE_W, FEATURE_H = 1024, 500
FEATURE_MARGIN_X, FEATURE_MARGIN_Y = 104, 62


def _brand_gradient(width: float, height: float) -> cairo.LinearGradient:
    """The product's 150 degree dairy gradient, over a box of this size.

    CSS measures the angle clockwise from "to top", so 150 degrees points down
    and to the right: the unit vector is (sin 150, -cos 150) = (0.5, 0.866).
    Cairo takes two points instead, so the vector is scaled to cross the box
    and centred on it.
    """
    dx, dy = 0.5, 0.866
    cx, cy = width / 2, height / 2
    reach = (abs(dx) * width + abs(dy) * height) / 2
    gradient = cairo.LinearGradient(
        cx - dx * reach, cy - dy * reach, cx + dx * reach, cy + dy * reach
    )
    gradient.add_color_stop_rgb(0, *DAIRY_RGB)
    gradient.add_color_stop_rgb(0.78, *DAIRY_DEEP_RGB)
    gradient.add_color_stop_rgb(1, *DAIRY_NIGHT_RGB)
    return gradient


def _rich_drop(ctx: cairo.Context, scale: float, cx: float, cy: float) -> None:
    """The enriched mark: lit body, one warm highlight, one meniscus.

    The same three layers `mark.rich_mark_svg()` draws, in the same order and
    from the same numbers — `mark.rich_details()` is the one source, so the
    store banner cannot drift from the sign-in screen.
    """
    detail = mark.rich_details()
    grid = mark.FIELD

    def place(x: float, y: float) -> tuple[float, float]:
        return cx + (x - grid / 2) * scale, cy + (y - grid / 2) * scale

    ctx.save()
    _drop(ctx, scale, cx, cy)
    x0, y0, x1, y1 = ctx.path_extents()
    body = cairo.LinearGradient(
        x0 + (x1 - x0) * 0.2, y0, x0 + (x1 - x0) * 0.8, y1
    )
    for stop in detail["body"]:
        body.add_color_stop_rgb(stop["offset"], *_hex_rgb(stop["color"]))
    ctx.set_source(body)
    ctx.fill_preserve()
    ctx.clip()

    highlight = detail["highlight"]
    hx, hy = place(highlight["cx"], highlight["cy"])
    rx, ry = highlight["rx"] * scale, highlight["ry"] * scale
    glow = cairo.RadialGradient(hx, hy, 0, hx, hy, max(rx, ry))
    glow.add_color_stop_rgba(0, *_hex_rgb(mark.MILK_LIT), 0.9)
    glow.add_color_stop_rgba(1, *_hex_rgb(mark.MILK_LIT), 0)
    ctx.save()
    ctx.translate(hx, hy)
    ctx.scale(rx, ry)
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()
    ctx.set_source(glow)
    ctx.fill()

    meniscus = detail["meniscus"]
    mx1, my1 = place(meniscus["x1"], meniscus["y1"])
    mx2, my2 = place(meniscus["x2"], meniscus["y2"])
    radius = meniscus["r"] * scale
    # The arc between two points, drawn as its circle clipped to the drop —
    # which is where a meniscus belongs, and why the SVG clips it too.
    span = math.hypot(mx2 - mx1, my2 - my1)
    if 0 < span <= 2 * radius:
        mid = ((mx1 + mx2) / 2, (my1 + my2) / 2)
        offset = math.sqrt(max(radius**2 - (span / 2) ** 2, 0))
        nx, ny = -(my2 - my1) / span, (mx2 - mx1) / span
        centre = (mid[0] + nx * offset, mid[1] + ny * offset)
        ctx.new_path()
        ctx.arc(
            centre[0],
            centre[1],
            radius,
            math.atan2(my1 - centre[1], mx1 - centre[0]),
            math.atan2(my2 - centre[1], mx2 - centre[0]),
        )
        ctx.set_line_width(meniscus["width"] * scale)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_source_rgba(*DAIRY_RGB, meniscus["opacity"])
        ctx.stroke()
    ctx.restore()


def _hex_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))


def play_icon() -> Image.Image:
    """512 x 512, full bleed, fully opaque. See the note above for why."""
    return render(PLAY_ICON, full_bleed=True)


def _lockup(ctx: cairo.Context, x: float, y: float, height: float, *, on_ink: bool) -> float:
    """Draw the full lockup with its top-left at (x, y). Returns its width.

    The placement comes from `mark.lockup_geometry()`, which the SVG lockup
    uses too — two renderers laying out the same lockup from their own
    arithmetic is how a lockup ends up with two different gaps.

    `on_ink` is Amendment 1's one-colour derivation: the SAME outlines, filled
    once in cream. Not a second wordmark — the identical traced paths. Navy on
    a deep green ground would be unreadable, and a gradient on it would be
    mud, so the derivation exists precisely for surfaces like this banner.
    """
    geometry = mark.lockup_geometry()
    scale = height / geometry["height"]
    data = mark.wordmark()

    ctx.save()
    ctx.translate(x, y)
    ctx.scale(scale, scale)

    can = geometry["can"]
    box = mark.can_bbox()
    ctx.save()
    ctx.translate(can["x"], can["y"])
    ctx.scale(can["scale"], can["scale"])
    ctx.translate(-box[0], -box[1])
    _can(ctx)
    ctx.set_source_rgb(*(_hex_rgb(mark.LOGO_CREAM) if on_ink else _hex_rgb(mark.LOGO_DAIRY)))
    ctx.fill()
    _drop(ctx)
    ctx.set_source_rgb(*(_hex_rgb(mark.LOGO_DEEP) if on_ink else _hex_rgb(mark.LOGO_CREAM)))
    ctx.fill()
    ctx.restore()

    ctx.save()
    ctx.translate(geometry["text"]["x"], geometry["text"]["y"])
    for layer, colour in (
        ("navy", mark.LOGO_NAVY),
        ("green", mark.LOGO_VA_TOP),
        ("rule", mark.LOGO_RULE),
        ("tagline", mark.LOGO_TAGLINE),
    ):
        _path(ctx, mark.wordmark_layer(layer))
        if on_ink:
            ctx.set_source_rgb(*_hex_rgb(mark.LOGO_CREAM))
        elif layer == "green":
            gradient = data["gradient"]
            ramp = cairo.LinearGradient(0, gradient["y0"], 0, gradient["y1"])
            ramp.add_color_stop_rgb(0, *_hex_rgb(gradient["from"]))
            ramp.add_color_stop_rgb(1, *_hex_rgb(gradient["to"]))
            ctx.set_source(ramp)
        else:
            ctx.set_source_rgb(*_hex_rgb(colour))
        ctx.fill()
    ctx.restore()
    ctx.restore()
    return geometry["width"] * scale


def _path(ctx: cairo.Context, d: str) -> None:
    """Trace SVG path data onto the context, using the shared walker."""
    ctx.new_path()
    for run in svgpath.subpaths(d):
        ctx.move_to(*run[0][0])
        for _, c1, c2, end in run:
            ctx.curve_to(c1[0], c1[1], c2[0], c2[1], end[0], end[1])
        ctx.close_path()


def feature_graphic() -> Image.Image:
    """1024 x 500: the full lockup, in cream, on the dairy gradient.

    WO-30 drew the wordmark here with cairo's toy font API against whatever
    "sans-serif" resolved to on the build machine, which meant the banner was
    not reproducible and, worse, was a font-rendered approximation of a
    wordmark the owner had already drawn. BRAND-004 Amendment 1 forbids that
    outright. It now draws the TRACED outlines, so the banner is byte-stable
    on any machine and carries the real artwork.
    """
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, FEATURE_W, FEATURE_H)
    ctx = cairo.Context(surface)
    ctx.rectangle(0, 0, FEATURE_W, FEATURE_H)
    ctx.set_source(_brand_gradient(FEATURE_W, FEATURE_H))
    ctx.fill()

    # The light in the corner, as every brand surface in this product has it.
    glow = cairo.RadialGradient(
        FEATURE_W - 150, -40, 0, FEATURE_W - 150, -40, 420
    )
    glow.add_color_stop_rgba(0, *MILK_RGB, 0.13)
    glow.add_color_stop_rgba(1, *MILK_RGB, 0)
    ctx.rectangle(0, 0, FEATURE_W, FEATURE_H)
    ctx.set_source(glow)
    ctx.fill()

    # Everything below lives inside the safe box: Play crops this banner on
    # some surfaces and lays a play button over its centre on others.
    box_w = FEATURE_W - 2 * FEATURE_MARGIN_X
    box_h = FEATURE_H - 2 * FEATURE_MARGIN_Y
    geometry = mark.lockup_geometry()
    height = min(box_h, box_w * geometry["height"] / geometry["width"])
    width = height * geometry["width"] / geometry["height"]
    _lockup(
        ctx,
        (FEATURE_W - width) / 2,
        (FEATURE_H - height) / 2,
        height,
        on_ink=True,
    )

    surface.flush()
    data = bytes(surface.get_data())
    # cairo's RGB24 is still four bytes per pixel with the top one unused;
    # reading it as BGRA and dropping the channel is what makes it RGB.
    img = Image.frombuffer(
        "RGBA", (FEATURE_W, FEATURE_H), data, "raw", "BGRA", surface.get_stride(), 1
    )
    # RGB, so the banner has no alpha channel to get wrong.
    return img.convert("RGB")


def _dart_mark() -> str:
    """The mark as Dart, because Flutter has no SVG renderer here.

    Adding `flutter_svg` to draw two shapes would be a dependency, a licence
    and a parser on the critical path of an app that already ships. The paths
    are cubics and a Flutter `Path` is cubics, so the generator simply emits
    the same numbers in the other language — and `check_inline.py` regenerates
    this file and compares, so it cannot drift any more than the SVG can.

    BRAND-004 adds the CAN. The drop keeps its own function and its own
    bounds because the sign-in reveal draws the lit drop alone and its
    choreography is not this work order's to change; the can is emitted beside
    it so no Flutter surface ever has cause to draw the mark from its own
    numbers.
    """
    d = mark.rich_details()
    hl, me = d["highlight"], d["meniscus"]

    def n(v: float) -> str:
        return f"{v:.3f}".rstrip("0").rstrip(".")

    def dart_path(outline) -> str:
        start, segments = outline
        lines = [f"  ..moveTo({n(start[0])} * s, {n(start[1])} * s)"]
        for c1, c2, end in segments:
            lines.append(
                f"  ..cubicTo({n(c1[0])} * s, {n(c1[1])} * s, "
                f"{n(c2[0])} * s, {n(c2[1])} * s, "
                f"{n(end[0])} * s, {n(end[1])} * s)"
            )
        lines.append("  ..close();")
        return "\n".join(lines)

    dx, dy, dw, dh = mark.drop_bbox()
    cx, cy, cw, ch = mark.can_bbox()

    return f'''// GENERATED by tools/brand/generate.py — do not edit by hand.
//
// The Lacteva mark, in Dart (LACTEVA-BRAND-004 geometry, BRAND-003 rendering).
// `tools/brand/check_inline.py` regenerates this file and compares it, so an
// edit here is a build failure rather than a second mark.
import \'dart:ui\';

/// The drop\'s tight bounding box in the {int(mark.FIELD)} grid the geometry is authored in.
const Rect kMarkBounds = Rect.fromLTWH(
  {n(dx)},
  {n(dy)},
  {n(dw)},
  {n(dh)},
);

/// The drop outline, in grid units scaled by [s].
///
/// This is the shape knocked OUT of the can. It is also what the sign-in
/// reveal lights, which is why it has a function of its own.
Path lactevaDropPath(double s) => Path()
{dart_path(mark.drop_outline())}

/// The can\'s tight bounding box in the same grid.
const Rect kCanBounds = Rect.fromLTWH(
  {n(cx)},
  {n(cy)},
  {n(cw)},
  {n(ch)},
);

/// The can body, in grid units scaled by [s] (LACTEVA-BRAND-004).
///
/// Fill this, then fill [lactevaDropPath] in the ground colour, and the drop
/// is a knockout. Filling both into ONE path with an even-odd fill type does
/// the same thing in a single pass where a surface wants that.
Path lactevaCanPath(double s) => Path()
{dart_path(mark.can_outline())}

/// The warm specular highlight, in grid units.
///
/// Emitted as LTWH rather than as a centre and radii because `Rect.fromCenter`
/// is not a const constructor, and this file must be entirely const.
const Rect kMarkHighlight = Rect.fromLTWH(
  {n(hl["cx"] - hl["rx"])},
  {n(hl["cy"] - hl["ry"])},
  {n(hl["rx"] * 2)},
  {n(hl["ry"] * 2)},
);

/// The meniscus arc: start, end, radius, stroke width and opacity.
const Offset kMarkMeniscusFrom = Offset({n(me["x1"])}, {n(me["y1"])});
const Offset kMarkMeniscusTo = Offset({n(me["x2"])}, {n(me["y2"])});
const double kMarkMeniscusRadius = {n(me["r"])};
const double kMarkMeniscusWidth = {n(me["width"])};
const double kMarkMeniscusOpacity = {n(me["opacity"])};
'''


def main() -> int:
    marketing = ROOT / "apps/marketing-site"
    portal = ROOT / "apps/admin-portal"
    mobile = ROOT / "apps/mobile"

    print("the shared contract")
    # Read by the portal and marketing vitest suites so each can check its own
    # inline copy without importing across apps or shelling out to Python.
    write(
        pathlib.Path(__file__).resolve().parent / "mark.json",
        json.dumps(
            {
                # `path` is the DROP, and stays the drop: every client already
                # reads that key, and BRAND-004 did not move the drop out of
                # the mark, it knocked it into a can.
                "path": mark.drop_path(),
                "dropViewBox": mark.drop_view_box(),
                # LACTEVA-BRAND-004. The can is the outer shape now.
                "can": mark.can_path(),
                "canViewBox": mark.can_view_box(),
                # Both in one string, for a surface that fills once with
                # `evenodd` and gets a true knockout.
                "mark": mark.mark_path(),
                "field": {"size": int(mark.FIELD), "corner": mark.CORNER},
                "dairy": mark.DAIRY,
                "milk": mark.MILK,
                # The identity's own colours. These are LOGO colours and they
                # are NOT Design System tokens — no navy enters a token, a
                # component or a theme (WO-31).
                "logo": {
                    "dairy": mark.LOGO_DAIRY,
                    "cream": mark.LOGO_CREAM,
                    "deep": mark.LOGO_DEEP,
                    "navy": mark.LOGO_NAVY,
                    "vaTop": mark.LOGO_VA_TOP,
                    "vaBottom": mark.LOGO_VA_BOTTOM,
                    "rule": mark.LOGO_RULE,
                    "tagline": mark.LOGO_TAGLINE,
                    "taglineText": mark.TAGLINE,
                },
                # The traced wordmark, so a client can draw the lockup without
                # reading a second file or setting a font.
                "wordmark": {
                    "reference": mark.wordmark()["reference"],
                    "gradient": mark.wordmark()["gradient"],
                    "capsViewBox": mark.wordmark_caps_view_box(),
                    "layers": {
                        name: mark.wordmark_layer(name)
                        for name in ("navy", "green", "rule", "tagline")
                    },
                },
                "lockup": mark.lockup_geometry(),
                # LACTEVA-BRAND-003. The enriched rendering, as numbers rather
                # than as a picture, so a TypeScript component and a Dart
                # painter can each draw it without either re-deriving the
                # board's geometry or importing the other's.
                "rich": mark.rich_details(),
            },
            indent=2,
        )
        + "\n",
    )

    print("the lockup — the assets WO-32 consumes")
    # Written here rather than into apps/marketing-site: WO-31 Amendment 2
    # limits this generator's writes into that tree to the two surfaces it
    # already owned, and T3 picks these up in WO-32.
    here = pathlib.Path(__file__).resolve().parent
    write(here / "lacteva-lockup.svg", mark.lockup_svg())
    write(here / "lacteva-lockup-on-ink.svg", mark.lockup_svg(on_ink=True))
    write(here / "lacteva-wordmark.svg", mark.wordmark_svg())
    write(here / "lacteva-wordmark-on-ink.svg", mark.wordmark_svg(on_ink=True))
    write(here / "lacteva-mark.svg", mark.mark_on_light_svg())

    print("marketing")
    write(marketing / "src/app/icon.svg", mark.mark_svg())

    print("google play")
    play = pathlib.Path(__file__).resolve().parent / "play"
    play.mkdir(parents=True, exist_ok=True)
    icon = play_icon()
    assert icon.size == (PLAY_ICON, PLAY_ICON)
    assert min(icon.getchannel("A").getdata()) == 255, "the store icon must be opaque"
    icon.save(play / "icon-512.png", format="PNG")
    print(f"  {(play / 'icon-512.png').relative_to(ROOT)}")
    banner = feature_graphic()
    assert banner.size == (FEATURE_W, FEATURE_H)
    assert banner.mode == "RGB", "the feature graphic must carry no alpha channel"
    banner.save(play / "feature-graphic-1024x500.png", format="PNG")
    print(f"  {(play / 'feature-graphic-1024x500.png').relative_to(ROOT)}")

    print("the rich mark")
    # A file, so the geometry has one authored home; the clients that need it
    # in their own language get it below.
    write(
        pathlib.Path(__file__).resolve().parent / "lacteva-mark-rich.svg",
        mark.rich_mark_svg(),
    )
    write(mobile / "lib/src/brand/mark.g.dart", _dart_mark())

    print("portal")
    ico = ROOT / "apps/admin-portal/src/app/favicon.ico"
    ico.parent.mkdir(parents=True, exist_ok=True)
    render(256).save(
        ico,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"  {ico.relative_to(ROOT)}")
    _ = portal

    print("mobile — android legacy mipmaps")
    for density, px in (
        ("mdpi", 48),
        ("hdpi", 72),
        ("xhdpi", 96),
        ("xxhdpi", 144),
        ("xxxhdpi", 192),
    ):
        target = mobile / f"android/app/src/main/res/mipmap-{density}/ic_launcher.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        render(px).save(target, format="PNG")
        print(f"  {target.relative_to(ROOT)}")

    print("mobile — android adaptive")
    scale, _, _ = _safe_placement()
    # The foreground is authored on Android's 108 grid, so the path is emitted
    # in those units directly.
    fg_scale = scale * (ADAPTIVE_CANVAS / mark.FIELD)
    centre = ADAPTIVE_CANVAS / 2
    can_data = mark.can_path(fg_scale, centre, centre)
    drop_data = mark.drop_path(fg_scale, centre, centre)
    # The CAN is the outer shape, so the can is what gets measured against the
    # safe circle; the drop is inside it by construction.
    reach = mark.max_radius(fg_scale, centre, centre)
    assert reach <= SAFE_RADIUS, f"foreground reaches {reach:.2f}dp, safe circle is {SAFE_RADIUS}"
    print(f"  (foreground reaches {reach:.2f}dp of the {SAFE_RADIUS}dp safe circle)")

    res = mobile / "android/app/src/main/res"
    write(
        res / "drawable/ic_launcher_foreground.xml",
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
        '    android:width="108dp" android:height="108dp"\n'
        '    android:viewportWidth="108" android:viewportHeight="108">\n'
        f'    <path android:fillColor="{mark.LOGO_CREAM}" android:pathData="{can_data}"/>\n'
        f'    <path android:fillColor="{mark.LOGO_DEEP}" android:pathData="{drop_data}"/>\n'
        "</vector>\n",
    )
    # The MONOCHROME layer is tinted a single colour by the launcher, so the
    # two-path foreground would arrive as a solid can with no drop in it. One
    # path with an even-odd fill makes the drop a real hole, which is the only
    # rendering of this mark that survives being flattened to one colour.
    write(
        res / "drawable/ic_launcher_monochrome.xml",
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
        '    android:width="108dp" android:height="108dp"\n'
        '    android:viewportWidth="108" android:viewportHeight="108">\n'
        '    <path android:fillColor="#FFFFFFFF" android:fillType="evenOdd"\n'
        f'        android:pathData="{can_data + drop_data}"/>\n'
        "</vector>\n",
    )
    write(
        res / "values/ic_launcher_background.xml",
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        f'    <color name="ic_launcher_background">{mark.LOGO_DAIRY}</color>\n'
        "</resources>\n",
    )
    adaptive = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/ic_launcher_background"/>\n'
        '    <foreground android:drawable="@drawable/ic_launcher_foreground"/>\n'
        '    <monochrome android:drawable="@drawable/ic_launcher_monochrome"/>\n'
        "</adaptive-icon>\n"
    )
    write(res / "mipmap-anydpi-v26/ic_launcher.xml", adaptive)
    write(res / "mipmap-anydpi-v26/ic_launcher_round.xml", adaptive)

    print("mobile — web")
    render(32).save(mobile / "web/favicon.png", format="PNG")
    print(f"  {(mobile / 'web/favicon.png').relative_to(ROOT)}")
    for name, px, maskable in (
        ("Icon-192.png", 192, False),
        ("Icon-512.png", 512, False),
        ("Icon-maskable-192.png", 192, True),
        ("Icon-maskable-512.png", 512, True),
    ):
        target = mobile / "web/icons" / name
        render(px, full_bleed=maskable, maskable=maskable).save(target, format="PNG")
        print(f"  {target.relative_to(ROOT)}")

    print("mobile — ios")
    appicon = mobile / "ios/Runner/Assets.xcassets/AppIcon.appiconset"
    contents = json.loads((appicon / "Contents.json").read_text())
    for entry in contents.get("images", []):
        filename = entry.get("filename")
        if not filename:
            continue
        px = round(float(entry["size"].split("x")[0]) * float(entry["scale"].rstrip("x")))
        # iOS applies its own mask and forbids transparency, so the field is
        # drawn full-bleed and the system rounds it.
        render(px, full_bleed=True).convert("RGB").save(appicon / filename, format="PNG")
    print(f"  {appicon.relative_to(ROOT)}/ ({len(contents.get('images', []))} entries)")

    print("\nDone. Inline SVGs are checked by tools/brand/check_inline.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
