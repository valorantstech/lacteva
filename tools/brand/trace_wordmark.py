#!/usr/bin/env python3
"""Vectorize the owner's wordmark from the binding reference (BRAND-004).

    python3 tools/brand/trace_wordmark.py          # retrace, rewrite wordmark.json
    python3 tools/brand/trace_wordmark.py --check  # retrace and diff, write nothing

WHY THIS EXISTS AT ALL

WO-31 Amendment 1 is explicit: the wordmark is the owner's artwork, not a
font. `reference/lacteva-wordmark-reference.png` (646 x 183) is binding, and
no committed surface may ship a font-rendered approximation of it. Setting
"LACTEVA" in some extra-bold grotesque and calling it close would be exactly
the substitution the amendment forbids — the letterforms have flat terminals,
a specific A, and a drop seated in the final A's counter, and a font that
happened to be installed would agree with none of it.

So the artwork is traced. What is committed is the OUTLINE, in the same 646 x
183 space the reference is drawn in, and every surface scales that.

HOW THE TRACE WORKS, AND WHY IT IS ACCURATE

A naive tracer thresholds the bitmap and walks pixel edges, which produces a
staircase: every diagonal in the A and V becomes a flight of stairs, and no
amount of smoothing afterwards recovers where the true edge was.

This one uses the antialiasing as data. A pixel on a shape's edge is a
MEASUREMENT of how much ink covered it, so:

  * the reference is unpainted back into a COVERAGE field per ink — solving
    `pixel = white*(1-a) + ink*a` for `a` gives the fraction of that pixel the
    ink covered, to roughly a 255th;
  * the outline is the a = 0.5 iso-contour of that field, extracted by
    marching squares with linear interpolation between samples.

The result is sub-pixel: the edge lands where the ink actually stopped, not on
a pixel boundary. That is what makes the "pixel-equivalent at 2x" bar
reachable — at 2x, a half-pixel error at 1x would be a whole pixel of visible
staircase, and there is none.

The contour is then a dense polygon (one vertex per cell crossing), which is
faithful but enormous. Two passes reduce it without moving it:

  * CORNERS are found first, by turning angle over a short window. A flat
    terminal is a corner and must stay a corner; a curve fitted THROUGH it
    would round off the very thing that makes these letterforms what they are.
  * the smooth runs between corners are fitted with cubic Beziers by
    Schneider's algorithm — least squares with the end tangents held, split at
    the worst point and refitted until every sample is within FIT_TOLERANCE of
    the curve.

Straight runs collapse to a line rather than a cubic, because a letter's stem
is straight and an `L` says so in a quarter of the bytes.

WHAT IS EMITTED

`wordmark.json`, which is generated data and committed: the outlines, the
sampled colours, and the metrics other code needs to place the lockup. CI does
not re-trace (the checks assert the committed outlines and the emitted paths
agree with each other) — this script and the reference beside it are the
provenance, so a reviewer can rerun it and see the same numbers.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REFERENCE = HERE / "reference/lacteva-wordmark-reference.png"
OUT = HERE / "wordmark.json"

# --- the sampled identity ---------------------------------------------------
# Every colour below was MEASURED from the reference, not chosen. The method is
# in `sample_colours()`; the numbers are recorded here so a reader can see them
# without running anything, and the tracer re-derives them on every run.

#: LACTE. Three values have been in play and only one ships. The base spec
#: proposed #1E2F5A; Amendment 1 said sample the reference instead; Amendment
#: 2 ruled that the file wins and named #022551. Tracing the eroded interior
#: independently lands on #032550 — one level away on two channels, which is
#: this PNG's own compression noise, not a disagreement. The RULING is what is
#: emitted; `_confirm()` below fails if the artwork ever stops agreeing with
#: it, so the pin can never quietly drift away from the thing it pins.
NAVY = "#022551"
#: SUPERSEDED, recorded so nobody re-derives it from the base spec: #1E2F5A.
NAVY_SUPERSEDED = "#1E2F5A"
#: VA runs a VERTICAL gradient, top to bottom. Fitted by least squares over the
#: eroded interior of the green letters: a linear ramp in y explains it to a
#: mean absolute residual of about 2.4/255, which is inside the PNG's noise.
#: A horizontal fit was tried first and does not describe the artwork.
VA_TOP = "#6AA227"
VA_BOTTOM = "#4C8C22"
#: The tagline's two flanking rules. Three pixels thick, so only their middle
#: row is at full coverage.
RULE = "#428B19"
#: "Smart Dairy. Stronger Tomorrow."
TAGLINE = "#3E4248"

#: How far a re-derived ink may sit from the constant above before this script
#: refuses to run. Two levels per channel: enough for the reference's
#: artefacts, far too little for a real change in the artwork.
COLOUR_TOLERANCE = 4.0

#: Rows the two bands occupy, used to keep each layer's ink model honest: the
#: VA gradient is fitted on the cap band and must not be extrapolated over the
#: tagline forty pixels below it.
CAP_BAND = (0, 124)
TAGLINE_BAND = (124, 183)

#: How far a fitted curve may sit from the traced contour, in reference pixels.
#: 0.35 is a third of a pixel at 1x and two thirds at the 2x acceptance bar —
#: below what the PNG's own JPEG-ish artefacts move the edge by.
FIT_TOLERANCE = 0.35
#: Turning angle, in degrees, over `CORNER_WINDOW` samples, above which a
#: vertex is a corner and is never fitted through.
CORNER_ANGLE = 38.0
CORNER_WINDOW = 3
#: A run whose samples all sit within this of the straight chord is a line.
LINE_TOLERANCE = 0.22

WHITE = (255.0, 255.0, 255.0)


# ---------------------------------------------------------------------------
# colour
# ---------------------------------------------------------------------------


def _rgb(value: str) -> tuple[float, float, float]:
    v = value.lstrip("#")
    return tuple(float(int(v[i : i + 2], 16)) for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(c))) for c in rgb))


def _coverage(pixel, ink) -> float:
    """How much of this pixel the ink covered, from `pixel = white(1-a) + ink*a`.

    Solved as a projection so a pixel that is slightly off-hue (this PNG has
    compression artefacts) still yields the coverage of its best explanation
    rather than three disagreeing per-channel answers.
    """
    dx = [WHITE[i] - ink[i] for i in range(3)]
    denominator = sum(d * d for d in dx)
    if denominator <= 1e-9:
        return 0.0
    numerator = sum((WHITE[i] - pixel[i]) * dx[i] for i in range(3))
    return max(0.0, min(1.0, numerator / denominator))


def _residual(pixel, ink, alpha) -> float:
    """How wrong `ink` at `alpha` is as an explanation of `pixel`."""
    return sum(
        abs(pixel[i] - (WHITE[i] * (1 - alpha) + ink[i] * alpha)) for i in range(3)
    )


def sample_colours(image) -> dict:
    """Re-derive every ink from the reference, so the constants cannot rot.

    The interiors are ERODED before they are measured. An edge pixel is a
    blend of ink and paper, so averaging it in drags every ink toward white —
    which is how a sampled palette ends up a shade too pale for no visible
    reason.
    """
    width, _ = image.size
    px = image.load()

    def mask(predicate, band):
        return {
            (x, y)
            for y in range(*band)
            for x in range(width)
            if predicate(px[x, y])
        }

    def erode(cells, radius=2):
        return [
            (x, y)
            for (x, y) in cells
            if all(
                (x + dx, y + dy) in cells
                for dx in range(-radius, radius + 1)
                for dy in range(-radius, radius + 1)
            )
        ]

    def is_navy(p):
        return p[2] > p[0] + 30 and p[1] < 120

    def is_green(p):
        return p[1] > p[0] + 25 and p[1] > p[2] + 25

    def is_grey(p):
        return abs(p[0] - p[1]) < 16 and abs(p[1] - p[2]) < 16 and p[0] < 200

    def mean(cells):
        if not cells:
            return None
        return tuple(sum(px[x, y][i] for x, y in cells) / len(cells) for i in range(3))

    navy = mean(erode(mask(is_navy, CAP_BAND)))

    # The VA gradient: least squares of each channel against y, over the
    # eroded interior only.
    greens = erode(mask(is_green, CAP_BAND))
    n = len(greens)
    sy = sum(y for _, y in greens)
    syy = sum(y * y for _, y in greens)
    ramp = []
    for channel in range(3):
        sv = sum(px[x, y][channel] for x, y in greens)
        svy = sum(px[x, y][channel] * y for x, y in greens)
        slope = (n * svy - sy * sv) / (n * syy - sy * sy)
        ramp.append(((sv - slope * sy) / n, slope))

    ys = [y for _, y in greens]
    top_y, bottom_y = min(ys), max(ys)

    def at(y):
        return tuple(a + b * y for a, b in ramp)

    # The rules are three pixels thick, so their middle row is the only one at
    # full coverage; eroding by two would erase them entirely.
    rules = erode(mask(is_green, TAGLINE_BAND), radius=1)
    tagline = erode(mask(is_grey, TAGLINE_BAND), radius=1)

    return {
        "navy": _hex(navy),
        "vaTop": _hex(at(top_y)),
        "vaBottom": _hex(at(bottom_y)),
        "vaBand": [top_y, bottom_y],
        "vaRamp": ramp,
        "rule": _hex(mean(rules)),
        "tagline": _hex(mean(tagline)),
    }


# ---------------------------------------------------------------------------
# the coverage field
# ---------------------------------------------------------------------------


def coverage_field(image, layers, band):
    """One coverage field per layer, over `band`'s rows.

    A pixel is assigned to the layer that best EXPLAINS it. Doing it that way
    rather than by a hue test means the boundary between two touching inks is
    decided by which composite is closer to what is actually there, and a
    pixel that is half navy and half green (there are none here, but a tracer
    should not depend on that) lands with the one it mostly is.

    The field is padded by one cell of zero on every side so a shape running
    to the edge of the crop still closes.
    """
    width, _ = image.size
    px = image.load()
    y0, y1 = band
    rows = y1 - y0
    fields = {
        name: [[0.0] * (width + 2) for _ in range(rows + 2)] for name in layers
    }

    for y in range(y0, y1):
        for x in range(width):
            pixel = px[x, y]
            if pixel[0] > 246 and pixel[1] > 246 and pixel[2] > 246:
                continue
            best_name, best_alpha, best_residual = None, 0.0, 1e9
            for name, ink_of in layers.items():
                ink = ink_of(y)
                alpha = _coverage(pixel, ink)
                if alpha <= 0.02:
                    continue
                residual = _residual(pixel, ink, alpha)
                if residual < best_residual:
                    best_name, best_alpha, best_residual = name, alpha, residual
            if best_name is not None:
                fields[best_name][y - y0 + 1][x + 1] = best_alpha
    return fields


# ---------------------------------------------------------------------------
# marching squares
# ---------------------------------------------------------------------------


def iso_contours(field, level=0.5):
    """Closed contours of the `level` iso-line, sub-pixel, as point lists.

    Sample `field[r][c]` is the value at the CENTRE of pixel (c-1, r-1) of the
    original crop, so the contour comes out in the reference's own coordinate
    space with no further mapping.

    Ambiguous (saddle) cells are resolved by the cell's average, which is the
    standard fix and the one that keeps a thin stem from being pinched in two.
    """
    rows, cols = len(field), len(field[0])
    segments = []

    def point(ax, ay, av, bx, by, bv):
        # Linear interpolation is what buys the sub-pixel accuracy: the edge
        # is placed where the coverage ramp actually crosses a half.
        t = 0.5 if abs(bv - av) < 1e-12 else (level - av) / (bv - av)
        t = max(0.0, min(1.0, t))
        return (ax + (bx - ax) * t, ay + (by - ay) * t)

    for r in range(rows - 1):
        for c in range(cols - 1):
            tl, tr = field[r][c], field[r][c + 1]
            bl, br = field[r + 1][c], field[r + 1][c + 1]
            index = (
                (1 if tl > level else 0)
                | (2 if tr > level else 0)
                | (4 if br > level else 0)
                | (8 if bl > level else 0)
            )
            if index in (0, 15):
                continue
            # Corner coordinates in reference space.
            x0, y0 = c - 1 + 0.5, r - 1 + 0.5
            x1, y1 = x0 + 1, y0 + 1
            # The four edge crossings, computed up front. They were closures
            # over the loop variables once, which is a bug waiting for the
            # day someone defers one of them by a single iteration.
            top = point(x0, y0, tl, x1, y0, tr)
            right = point(x1, y0, tr, x1, y1, br)
            bottom = point(x1, y1, br, x0, y1, bl)
            left = point(x0, y1, bl, x0, y0, tl)

            # Segments are emitted so that the INSIDE (above `level`) is on
            # the left of travel; that gives outer contours and holes opposite
            # windings, which is what lets one path with a fill rule draw a
            # letter with a counter.
            if index == 1:
                segments.append((left, top))
            elif index == 2:
                segments.append((top, right))
            elif index == 3:
                segments.append((left, right))
            elif index == 4:
                segments.append((right, bottom))
            elif index == 5:
                if (tl + tr + br + bl) / 4 > level:
                    segments.append((left, bottom))
                    segments.append((right, top))
                else:
                    segments.append((left, top))
                    segments.append((right, bottom))
            elif index == 6:
                segments.append((top, bottom))
            elif index == 7:
                segments.append((left, bottom))
            elif index == 8:
                segments.append((bottom, left))
            elif index == 9:
                segments.append((bottom, top))
            elif index == 10:
                if (tl + tr + br + bl) / 4 > level:
                    segments.append((top, right))
                    segments.append((bottom, left))
                else:
                    segments.append((top, left))
                    segments.append((bottom, right))
            elif index == 11:
                segments.append((bottom, right))
            elif index == 12:
                segments.append((right, left))
            elif index == 13:
                segments.append((right, top))
            elif index == 14:
                segments.append((top, left))

    return _chain(segments)


def _chain(segments):
    """Link directed segments end-to-start into closed loops.

    Marching squares emits a soup of oriented segments; a letter is whatever
    loops they form. Because every segment is directed with the ink on its
    left, an outer contour and the counter inside it come out wound in
    opposite directions, which is exactly what a non-zero fill rule needs to
    punch the hole in the A without anyone deciding which loop is which.
    """
    def key(p):
        return (round(p[0], 4), round(p[1], 4))

    starts: dict = {}
    for index, (a, _) in enumerate(segments):
        starts.setdefault(key(a), []).append(index)

    used = [False] * len(segments)
    loops = []
    for index in range(len(segments)):
        if used[index]:
            continue
        used[index] = True
        first, current = segments[index]
        loop = [first, current]
        while True:
            following = None
            for candidate in starts.get(key(current), ()):
                if not used[candidate]:
                    following = candidate
                    break
            if following is None:
                break
            used[following] = True
            current = segments[following][1]
            if key(current) == key(loop[0]):
                break
            loop.append(current)
        if len(loop) > 6:
            loops.append(loop)
    return [_dedupe(loop) for loop in loops if len(loop) > 6]


def _dedupe(points, epsilon=1e-6):
    out = [points[0]]
    for p in points[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > epsilon:
            out.append(p)
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < epsilon:
        out.pop()
    return out


# ---------------------------------------------------------------------------
# corners, and the curve fit between them
# ---------------------------------------------------------------------------


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _mul(a, k):
    return (a[0] * k, a[1] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _norm(a):
    length = math.hypot(*a)
    return (0.0, 0.0) if length < 1e-12 else (a[0] / length, a[1] / length)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def find_corners(points, angle=CORNER_ANGLE, window=CORNER_WINDOW):
    """Indices where the contour genuinely turns a corner.

    These letterforms are flat-terminal grotesque caps: the stems meet the
    terminals at hard angles, and the A and V are built from straight
    diagonals. Fitting a curve THROUGH one of those joins would round it, and
    a rounded terminal is a different typeface. So corners are found first and
    every fitted run stops at one.

    Non-maximum suppression keeps one index per corner: a 90-degree turn
    sampled at half-pixel spacing trips the angle test at several consecutive
    vertices, and keeping them all would emit a fistful of degenerate runs.
    """
    count = len(points)
    if count < 2 * window + 3:
        return []
    threshold = math.radians(angle)
    turns = [0.0] * count
    for i in range(count):
        before = _norm(_sub(points[i], points[(i - window) % count]))
        after = _norm(_sub(points[(i + window) % count], points[i]))
        if before == (0.0, 0.0) or after == (0.0, 0.0):
            continue
        turns[i] = abs(
            math.atan2(
                before[0] * after[1] - before[1] * after[0], _dot(before, after)
            )
        )
    corners = []
    for i in range(count):
        if turns[i] < threshold:
            continue
        if all(
            turns[i] >= turns[(i + d) % count]
            for d in range(-window, window + 1)
        ):
            corners.append(i)
    # Two corners a sample apart are one corner seen twice.
    pruned = []
    for i in corners:
        if pruned and (i - pruned[-1]) <= window:
            continue
        pruned.append(i)
    if len(pruned) > 1 and (pruned[0] + count - pruned[-1]) <= window:
        pruned.pop()
    return pruned


def _generate_bezier(points, u, t1, t2):
    """Least-squares cubic through `points`, endpoints and tangents held.

    Schneider's construction: with the endpoints pinned and both tangent
    DIRECTIONS fixed, only the two handle lengths are free, so the fit is a
    2x2 normal-equation solve rather than anything iterative.
    """
    p0, p3 = points[0], points[-1]
    c = [[0.0, 0.0], [0.0, 0.0]]
    x = [0.0, 0.0]
    for i, point in enumerate(points):
        ui = u[i]
        b0 = (1 - ui) ** 3
        b1 = 3 * ui * (1 - ui) ** 2
        b2 = 3 * (1 - ui) * ui**2
        b3 = ui**3
        a0 = _mul(t1, b1)
        a1 = _mul(t2, b2)
        c[0][0] += _dot(a0, a0)
        c[0][1] += _dot(a0, a1)
        c[1][1] += _dot(a1, a1)
        tmp = _sub(
            point,
            _add(_mul(p0, b0 + b1), _mul(p3, b2 + b3)),
        )
        x[0] += _dot(a0, tmp)
        x[1] += _dot(a1, tmp)
    c[1][0] = c[0][1]

    det = c[0][0] * c[1][1] - c[1][0] * c[0][1]
    span = _dist(p0, p3)
    if abs(det) < 1e-12:
        alpha_l = alpha_r = span / 3
    else:
        alpha_l = (x[0] * c[1][1] - x[1] * c[0][1]) / det
        alpha_r = (c[0][0] * x[1] - c[1][0] * x[0]) / det
    # A negative or vanishing handle means the solve fell apart (collinear
    # samples, usually). The Wu/Barsky fallback — a third of the chord each —
    # is well behaved and is what a straight run wants anyway.
    if alpha_l < 1e-6 * span or alpha_r < 1e-6 * span:
        alpha_l = alpha_r = span / 3
    return [p0, _add(p0, _mul(t1, alpha_l)), _add(p3, _mul(t2, alpha_r)), p3]


def _bezier_at(bez, t):
    u = 1 - t
    return (
        u**3 * bez[0][0]
        + 3 * u**2 * t * bez[1][0]
        + 3 * u * t**2 * bez[2][0]
        + t**3 * bez[3][0],
        u**3 * bez[0][1]
        + 3 * u**2 * t * bez[1][1]
        + 3 * u * t**2 * bez[2][1]
        + t**3 * bez[3][1],
    )


def _max_error(points, bez, u):
    worst, at = 0.0, len(points) // 2
    for i, point in enumerate(points):
        distance = _dist(_bezier_at(bez, u[i]), point)
        if distance > worst:
            worst, at = distance, i
    return worst, at


def _parameterize(points):
    u = [0.0]
    for i in range(1, len(points)):
        u.append(u[-1] + _dist(points[i], points[i - 1]))
    total = u[-1]
    return [t / total for t in u] if total > 1e-12 else [0.0] * len(points)


def _reparameterize(points, bez, u):
    """One Newton step per sample, pulling each toward its true foot on the curve."""
    out = []
    for i, point in enumerate(points):
        t = u[i]
        d1 = [_mul(_sub(bez[k + 1], bez[k]), 3.0) for k in range(3)]
        d2 = [_mul(_sub(d1[k + 1], d1[k]), 2.0) for k in range(2)]
        s = 1 - t
        q = _bezier_at(bez, t)
        q1 = _add(_add(_mul(d1[0], s * s), _mul(d1[1], 2 * s * t)), _mul(d1[2], t * t))
        q2 = _add(_mul(d2[0], s), _mul(d2[1], t))
        diff = _sub(q, point)
        denominator = _dot(q1, q1) + _dot(diff, q2)
        out.append(t if abs(denominator) < 1e-12 else t - _dot(diff, q1) / denominator)
    return out


def _is_line(points, tolerance=LINE_TOLERANCE):
    """True when every sample sits within `tolerance` of the chord.

    A stem, a crossbar and the flat of a terminal are straight. Emitting them
    as `L` is not only smaller — it keeps them exactly straight, where a
    fitted cubic would put a few hundredths of a pixel of sag into a line the
    eye reads as dead straight at a headline size.
    """
    a, b = points[0], points[-1]
    span = _dist(a, b)
    if span < 1e-9:
        return False
    nx, ny = -(b[1] - a[1]) / span, (b[0] - a[0]) / span
    return all(
        abs((p[0] - a[0]) * nx + (p[1] - a[1]) * ny) <= tolerance for p in points
    )


def fit_run(points, t1, t2, tolerance=FIT_TOLERANCE, depth=0):
    """Schneider's fitCubic: fit, and split at the worst sample if it misses."""
    if len(points) < 2:
        return []
    if len(points) == 2 or _is_line(points, tolerance=LINE_TOLERANCE):
        return [("L", points[-1])]

    u = _parameterize(points)
    bez = _generate_bezier(points, u, t1, t2)
    error, split = _max_error(points, bez, u)

    if error < tolerance:
        return [("C", bez[1], bez[2], bez[3])]

    # Close enough to be worth saving: reparameterizing usually lands it.
    if error < tolerance * 4 and depth < 12:
        for _ in range(4):
            u = _reparameterize(points, bez, u)
            bez = _generate_bezier(points, u, t1, t2)
            error, split = _max_error(points, bez, u)
            if error < tolerance:
                return [("C", bez[1], bez[2], bez[3])]

    if depth > 24 or split <= 0 or split >= len(points) - 1:
        return [("C", bez[1], bez[2], bez[3])]

    # Split at the worst sample, with a tangent taken across it so the two
    # halves meet smoothly.
    centre = _norm(_sub(points[split - 1], points[split + 1]))
    left = fit_run(points[: split + 1], t1, centre, tolerance, depth + 1)
    right = fit_run(
        points[split:], _mul(centre, -1.0), t2, tolerance, depth + 1
    )
    return left + right


def fit_contour(points, tolerance=FIT_TOLERANCE):
    """A whole closed contour as path segments, corners preserved."""
    count = len(points)
    corners = find_corners(points)
    if len(corners) < 2:
        # A contour with no corner at all — the drop, the C's bowl. Split it
        # into quarters so no single fit has to span the whole loop.
        corners = [round(i * count / 4) for i in range(4)]

    segments = []
    for index, start in enumerate(corners):
        end = corners[(index + 1) % len(corners)]
        run = (
            points[start : end + 1]
            if end > start
            else points[start:] + points[: end + 1]
        )
        if len(run) < 2:
            continue
        t1 = _norm(_sub(run[min(2, len(run) - 1)], run[0]))
        t2 = _norm(_sub(run[max(-3, -len(run))], run[-1]))
        segments.extend(fit_run(run, t1, t2, tolerance))
    return points[corners[0]], segments


# ---------------------------------------------------------------------------
# emitting
# ---------------------------------------------------------------------------


def _n(value: float) -> str:
    """Two decimals, no trailing zeros — a hundredth of a reference pixel.

    The fit tolerance is a third of a pixel, so a hundredth is well below the
    precision anything downstream can use, and it keeps the emitted path data
    to something a reviewer can actually read.
    """
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def contours_to_path(contours, tolerance=FIT_TOLERANCE) -> str:
    """Every contour of one ink as a single SVG `d` string."""
    parts = []
    for contour in contours:
        start, segments = fit_contour(contour, tolerance)
        parts.append(f"M{_n(start[0])} {_n(start[1])}")
        for segment in segments:
            if segment[0] == "L":
                parts.append(f"L{_n(segment[1][0])} {_n(segment[1][1])}")
            else:
                _, c1, c2, end = segment
                parts.append(
                    f"C{_n(c1[0])} {_n(c1[1])} {_n(c2[0])} {_n(c2[1])} "
                    f"{_n(end[0])} {_n(end[1])}"
                )
        parts.append("Z")
    return "".join(parts)


def _bbox(contours):
    xs = [p[0] for contour in contours for p in contour]
    ys = [p[1] for contour in contours for p in contour]
    return [
        round(min(xs), 2),
        round(min(ys), 2),
        round(max(xs), 2),
        round(max(ys), 2),
    ]


def _confirm(measured: dict) -> dict:
    """The pinned inks must still be what the artwork contains.

    The constants at the top of this file are what every surface ships, and a
    pin that nobody checks is a copy waiting to go stale — the exact failure
    LACTEVA-BRAND-002 was raised for. So the trace re-derives each ink and
    refuses to run if the reference has drifted away from what is pinned.
    Navy is the one that matters most: it is pinned by RULING (Amendment 2)
    rather than by measurement, so this is the only thing standing between
    that ruling and an artwork it no longer describes.
    """
    problems = []
    for name, pinned in (
        ("navy", NAVY),
        ("vaTop", VA_TOP),
        ("vaBottom", VA_BOTTOM),
        ("rule", RULE),
        ("tagline", TAGLINE),
    ):
        a, b = _rgb(pinned), _rgb(measured[name])
        drift = max(abs(a[i] - b[i]) for i in range(3))
        if drift > COLOUR_TOLERANCE:
            problems.append(
                f"{name}: pinned {pinned}, the reference traces to "
                f"{measured[name]} ({drift:.0f}/255 apart)"
            )
    if problems:
        raise SystemExit(
            "the reference no longer matches the pinned identity:\n  "
            + "\n  ".join(problems)
        )
    return {
        "navy": NAVY,
        "vaTop": VA_TOP,
        "vaBottom": VA_BOTTOM,
        "rule": RULE,
        "tagline": TAGLINE,
    }


def trace(image) -> dict:
    """The whole wordmark, as generated data."""
    measured = sample_colours(image)
    pinned = _confirm(measured)
    # Trace against the PINNED inks, not the measured ones, so the coverage
    # field is unpainted with exactly the colour the surfaces will paint with.
    navy_ink = _rgb(pinned["navy"])
    rule_ink = _rgb(pinned["rule"])
    tagline_ink = _rgb(pinned["tagline"])
    ramp = measured["vaRamp"]

    def green_at(y):
        return tuple(a + b * y for a, b in ramp)

    cap = coverage_field(
        image,
        {"navy": lambda y: navy_ink, "green": green_at},
        CAP_BAND,
    )
    foot = coverage_field(
        image,
        {"tagline": lambda y: tagline_ink, "rule": lambda y: rule_ink},
        TAGLINE_BAND,
    )

    layers = {}
    for name, field, band in (
        ("navy", cap["navy"], CAP_BAND),
        ("green", cap["green"], CAP_BAND),
        ("tagline", foot["tagline"], TAGLINE_BAND),
        ("rule", foot["rule"], TAGLINE_BAND),
    ):
        contours = iso_contours(field)
        # The field was built over a band, so shift the contours back into the
        # reference's own coordinates. Everything downstream then works in one
        # space: the 646 x 183 the owner drew in.
        contours = [[(x, y + band[0]) for (x, y) in contour] for contour in contours]
        layers[name] = {
            "path": contours_to_path(contours),
            "contours": len(contours),
            "bbox": _bbox(contours),
        }

    width, height = image.size
    return {
        "_generated": (
            "GENERATED by tools/brand/trace_wordmark.py from "
            "reference/lacteva-wordmark-reference.png — do not edit by hand."
        ),
        "reference": {
            "file": "reference/lacteva-wordmark-reference.png",
            "width": width,
            "height": height,
        },
        "colours": pinned,
        # What the artwork itself traces to, kept beside what ships so a
        # reviewer can see the two agree without rerunning anything.
        "measured": {
            key: measured[key]
            for key in ("navy", "vaTop", "vaBottom", "rule", "tagline")
        },
        # The VA gradient is vertical and spans these rows of the reference.
        # Emitted as the band rather than as "the letters' box" because the
        # ramp was fitted against absolute y, and a surface that re-based it
        # on its own bounding box would tilt the colour.
        "gradient": {
            "axis": "vertical",
            "y0": measured["vaBand"][0],
            "y1": measured["vaBand"][1],
            "from": pinned["vaTop"],
            "to": pinned["vaBottom"],
        },
        "layers": layers,
        "fit": {
            "tolerance": FIT_TOLERANCE,
            "cornerAngle": CORNER_ANGLE,
            "lineTolerance": LINE_TOLERANCE,
        },
    }


def main(argv) -> int:
    if not REFERENCE.exists():
        print(f"the binding reference is missing: {REFERENCE.relative_to(ROOT)}")
        return 1
    image = Image.open(REFERENCE).convert("RGB")
    data = trace(image)
    rendered = json.dumps(data, indent=2) + "\n"

    if "--check" in argv:
        if not OUT.exists():
            print(f"{OUT.relative_to(ROOT)} has never been generated")
            return 1
        if OUT.read_text(encoding="utf-8") != rendered:
            print(
                f"{OUT.relative_to(ROOT)} is not what the tracer produces.\n"
                "    Run: python3 tools/brand/trace_wordmark.py"
            )
            return 1
        print("wordmark: the committed outlines are what the reference traces to")
        return 0

    OUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    for name, layer in data["layers"].items():
        print(
            f"  {name:8s} {layer['contours']:2d} contours, "
            f"{len(layer['path']):5d} chars, bbox {layer['bbox']}"
        )
    print("  colours " + ", ".join(f"{k}={v}" for k, v in data["colours"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
