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

ROOT = pathlib.Path(__file__).resolve().parents[2]

DAIRY_RGB = (0x1B / 255, 0x5E / 255, 0x20 / 255)
MILK_RGB = (0xFD / 255, 0xFB / 255, 0xF4 / 255)

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


def _drop(ctx: cairo.Context, scale=1.0, cx=mark.FIELD / 2, cy=mark.FIELD / 2) -> None:
    start, segments = mark.drop_outline(scale, cx, cy)
    ctx.new_path()
    ctx.move_to(*start)
    for c1, c2, end in segments:
        ctx.curve_to(c1[0], c1[1], c2[0], c2[1], end[0], end[1])
    ctx.close_path()


def render(
    size: int, *, dark_ground=False, drop_only=False, full_bleed=False, maskable=False
) -> Image.Image:
    """One rendering of the mark at `size` px.

    `drop_only` omits the field (the adaptive foreground layer draws the drop
    over a separate background layer). `full_bleed` fills the whole square
    instead of the rounded field, for the platforms that supply their own
    shape. `maskable` additionally shrinks the drop into Android's guaranteed
    safe CIRCLE — iOS does not need it, because its mask is a superellipse
    that keeps far more of the square, and a drop sized for a circle looks
    lost inside one.
    """
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)
    ctx.scale(size / mark.FIELD, size / mark.FIELD)

    field_rgb, drop_rgb = (MILK_RGB, DAIRY_RGB) if dark_ground else (DAIRY_RGB, MILK_RGB)

    if not drop_only:
        if full_bleed:
            ctx.rectangle(0, 0, mark.FIELD, mark.FIELD)
        else:
            _rounded_field(ctx)
        ctx.set_source_rgb(*field_rgb)
        ctx.fill()

    if maskable:
        # The launcher may crop to a circle, so the drop is drawn at the same
        # scale the adaptive foreground uses rather than the full one.
        _drop(ctx, *_safe_placement())
    else:
        _drop(ctx)
    ctx.set_source_rgb(*drop_rgb)
    ctx.fill()

    surface.flush()
    data = bytes(surface.get_data())
    # cairo gives premultiplied BGRA; these fills are fully opaque, so a
    # channel swap is all that is needed.
    img = Image.frombuffer("RGBA", (size, size), data, "raw", "BGRA", surface.get_stride(), 1)
    return img.convert("RGBA")


def _safe_placement() -> tuple[float, float, float]:
    """(scale, cx, cy) in the 64 grid that fits the drop in the safe circle."""
    reach = mark.max_radius(1.0, mark.FIELD / 2, mark.FIELD / 2)
    allowed = (SAFE_RADIUS / ADAPTIVE_CANVAS) * mark.FIELD * SAFE_MARGIN
    return allowed / reach, mark.FIELD / 2, mark.FIELD / 2


def write(path: pathlib.Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(path, mode) as handle:
        handle.write(data)
    print(f"  {path.relative_to(ROOT)}")


def _dart_mark() -> str:
    """The mark as Dart, because Flutter has no SVG renderer here.

    Adding `flutter_svg` to draw one shape would be a dependency, a licence
    and a parser on the critical path of an app that already ships. The path
    is cubics and a Flutter `Path` is cubics, so the generator simply emits
    the same numbers in the other language — and `check_inline.py` regenerates
    this file and compares, so it cannot drift any more than the SVG can.
    """
    start, segments = mark.drop_outline()
    x, y, w, h = mark.drop_bbox()
    d = mark.rich_details()
    hl, me = d["highlight"], d["meniscus"]

    def n(v: float) -> str:
        return f"{v:.3f}".rstrip("0").rstrip(".")

    lines = [
        f"  ..moveTo({n(start[0])} * s, {n(start[1])} * s)",
    ]
    for c1, c2, end in segments:
        lines.append(
            f"  ..cubicTo({n(c1[0])} * s, {n(c1[1])} * s, "
            f"{n(c2[0])} * s, {n(c2[1])} * s, "
            f"{n(end[0])} * s, {n(end[1])} * s)"
        )
    lines.append("  ..close();")
    body = "\n".join(lines)

    return f'''// GENERATED by tools/brand/generate.py — do not edit by hand.
//
// The Lacteva mark, in Dart (LACTEVA-BRAND-002 geometry, BRAND-003 rendering).
// `tools/brand/check_inline.py` regenerates this file and compares it, so an
// edit here is a build failure rather than a second mark.
import \'dart:ui\';

/// The drop\'s tight bounding box in the {int(mark.FIELD)} grid the geometry is authored in.
const Rect kMarkBounds = Rect.fromLTWH(
  {n(x)},
  {n(y)},
  {n(w)},
  {n(h)},
);

/// The drop outline, in grid units scaled by [s].
Path lactevaDropPath(double s) => Path()
{body}

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
                "path": mark.drop_path(),
                "dropViewBox": mark.drop_view_box(),
                "field": {"size": int(mark.FIELD), "corner": mark.CORNER},
                "dairy": mark.DAIRY,
                "milk": mark.MILK,
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

    print("marketing")
    write(marketing / "src/app/icon.svg", mark.mark_svg())

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
    scale, cx, cy = _safe_placement()
    # The foreground is authored on Android's 108 grid, so the path is emitted
    # in those units directly.
    fg_scale = scale * (ADAPTIVE_CANVAS / mark.FIELD)
    fg_path = mark.drop_path(fg_scale, ADAPTIVE_CANVAS / 2, ADAPTIVE_CANVAS / 2)
    reach = mark.max_radius(fg_scale, ADAPTIVE_CANVAS / 2, ADAPTIVE_CANVAS / 2)
    assert reach <= SAFE_RADIUS, f"foreground reaches {reach:.2f}dp, safe circle is {SAFE_RADIUS}"
    print(f"  (foreground reaches {reach:.2f}dp of the {SAFE_RADIUS}dp safe circle)")

    res = mobile / "android/app/src/main/res"
    write(
        res / "drawable/ic_launcher_foreground.xml",
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
        '    android:width="108dp" android:height="108dp"\n'
        '    android:viewportWidth="108" android:viewportHeight="108">\n'
        f'    <path android:fillColor="{mark.MILK}" android:pathData="{fg_path}"/>\n'
        "</vector>\n",
    )
    write(
        res / "values/ic_launcher_background.xml",
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        f'    <color name="ic_launcher_background">{mark.DAIRY}</color>\n'
        "</resources>\n",
    )
    adaptive = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/ic_launcher_background"/>\n'
        '    <foreground android:drawable="@drawable/ic_launcher_foreground"/>\n'
        '    <monochrome android:drawable="@drawable/ic_launcher_foreground"/>\n'
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
