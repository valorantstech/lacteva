#!/usr/bin/env python3
"""Walk an SVG path and sample points along it (LACTEVA-BRAND-004).

This exists so `check_inline.py` can prove something string comparison
cannot: that the parametric can in `mark.py` and the owner's own path data
recorded beside it are the SAME OUTLINE.

They are not the same string, and should not be. The owner drew the can in
relative notation with two arcs; `mark.py` describes it as named parameters
and emits absolute cubics, because Dart cannot hold an arc in a const
expression and a bounding box is far easier to measure on cubics. Both are
correct, and a checker that compared characters would report a difference on
every one of those legitimate choices while catching none of the differences
that matter.

So both are walked and sampled, and the two point sets are compared. A
redesign moves points; a change of notation does not.

Supported: M m L l H h V v C c S s Q q T t A a Z z — the whole of the path
grammar this repository emits, plus the smooth and quadratic forms so that a
future hand-authored reference does not silently fail to parse. An unknown
command raises rather than being skipped, because a checker that quietly
ignores what it does not understand is worse than no checker.
"""

from __future__ import annotations

import math
import re

# Numbers first, so `1e5` is one token rather than a `1`, an `e` and a `5`.
# The final alternative is a catch-all on purpose: it lets an unknown
# character reach the parser and be REFUSED there. Matching only the commands
# this module knows would drop anything else on the floor, and a checker that
# quietly ignores what it does not understand is worse than no checker.
_TOKEN = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?|[A-Za-z]|[^\s,]")


def _tokens(d: str):
    return _TOKEN.findall(d)


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _cubic(p0, p1, p2, p3, t):
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def _arc_to_cubics(start, rx, ry, rotation, large, sweep, end):
    """Endpoint-parameterized arc to a list of cubic segments.

    The standard F.6 conversion from the SVG specification. Written out rather
    than approximated because the can's foot and the drop's bulb are both
    arcs, and an approximation here would show up as exactly the kind of
    sub-unit disagreement this module exists to rule out.
    """
    if start == end:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [(start, start, end, end)]
    phi = math.radians(rotation)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx2 = (start[0] - end[0]) / 2
    dy2 = (start[1] - end[1]) / 2
    x1 = cos_phi * dx2 + sin_phi * dy2
    y1 = -sin_phi * dx2 + cos_phi * dy2

    # Scale the radii up if they are too small to span the endpoints.
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        scale = math.sqrt(lam)
        rx, ry = rx * scale, ry * scale

    numerator = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    denominator = rx * rx * y1 * y1 + ry * ry * x1 * x1
    factor = math.sqrt(max(0.0, numerator / denominator)) if denominator else 0.0
    if large == sweep:
        factor = -factor
    cx1 = factor * rx * y1 / ry
    cy1 = -factor * ry * x1 / rx
    cx = cos_phi * cx1 - sin_phi * cy1 + (start[0] + end[0]) / 2
    cy = sin_phi * cx1 + cos_phi * cy1 + (start[1] + end[1]) / 2

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        length = math.hypot(ux, uy) * math.hypot(vx, vy)
        value = 0.0 if length == 0 else max(-1.0, min(1.0, dot / length))
        result = math.acos(value)
        return -result if ux * vy - uy * vx < 0 else result

    theta = angle(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    delta = angle(
        (x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry
    )
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    count = max(1, math.ceil(abs(delta) / (math.pi / 2)))
    step = delta / count
    k = 4 / 3 * math.tan(step / 4)

    segments = []
    current = start
    for i in range(count):
        a0 = theta + i * step
        a1 = a0 + step

        def on(a):
            x = rx * math.cos(a)
            y = ry * math.sin(a)
            return (cos_phi * x - sin_phi * y + cx, sin_phi * x + cos_phi * y + cy)

        def tangent(a):
            x = -rx * math.sin(a)
            y = ry * math.cos(a)
            return (cos_phi * x - sin_phi * y, sin_phi * x + cos_phi * y)

        p3 = on(a1)
        t0, t1 = tangent(a0), tangent(a1)
        p1 = (current[0] + k * t0[0], current[1] + k * t0[1])
        p2 = (p3[0] - k * t1[0], p3[1] - k * t1[1])
        segments.append((current, p1, p2, p3))
        current = p3
    return segments


def subpaths(d: str):
    """Every subpath of `d`, as a list of cubic segments (p0, p1, p2, p3)."""
    tokens = _tokens(d)
    index = 0
    command = None
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    previous_control = None
    result = []
    run = []

    def number():
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    def line(end):
        nonlocal current
        run.append(
            (current, _lerp(current, end, 1 / 3), _lerp(current, end, 2 / 3), end)
        )
        current = end

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1
            if command in "Zz":
                if run and current != start:
                    line(start)
                if run:
                    result.append(run)
                    run = []
                current = start
                previous_control = None
                continue
        elif command is None:
            raise ValueError(f"path data starts with a number: {d[:32]!r}")
        elif command == "M":
            command = "L"
        elif command == "m":
            command = "l"

        relative = command.islower()
        base = current if relative else (0.0, 0.0)
        upper = command.upper()

        if upper == "M":
            if run:
                result.append(run)
                run = []
            current = (base[0] + number(), base[1] + number())
            start = current
            previous_control = None
        elif upper == "L":
            line((base[0] + number(), base[1] + number()))
            previous_control = None
        elif upper == "H":
            line((base[0] + number(), current[1]))
            previous_control = None
        elif upper == "V":
            line((current[0], base[1] + number()))
            previous_control = None
        elif upper in ("C", "S", "Q", "T"):
            if upper == "C":
                p1 = (base[0] + number(), base[1] + number())
                p2 = (base[0] + number(), base[1] + number())
                p3 = (base[0] + number(), base[1] + number())
            elif upper == "S":
                p1 = (
                    2 * current[0] - previous_control[0]
                    if previous_control
                    else current[0],
                    2 * current[1] - previous_control[1]
                    if previous_control
                    else current[1],
                )
                p2 = (base[0] + number(), base[1] + number())
                p3 = (base[0] + number(), base[1] + number())
            else:
                if upper == "Q":
                    q = (base[0] + number(), base[1] + number())
                else:
                    q = (
                        2 * current[0] - previous_control[0]
                        if previous_control
                        else current[0],
                        2 * current[1] - previous_control[1]
                        if previous_control
                        else current[1],
                    )
                p3 = (base[0] + number(), base[1] + number())
                # A quadratic is a cubic whose handles sit two thirds of the
                # way to the single control point.
                p1 = _lerp(current, q, 2 / 3)
                p2 = _lerp(p3, q, 2 / 3)
                previous_control = q
                run.append((current, p1, p2, p3))
                current = p3
                continue
            run.append((current, p1, p2, p3))
            previous_control = p2
            current = p3
        elif upper == "A":
            rx, ry, rotation = number(), number(), number()
            large, sweep = number(), number()
            end = (base[0] + number(), base[1] + number())
            for segment in _arc_to_cubics(
                current, rx, ry, rotation, large, sweep, end
            ):
                run.append(segment)
            current = end
            previous_control = None
        else:
            raise ValueError(f"unsupported path command {command!r}")

    if run:
        result.append(run)
    return result


def sample(d: str, per_segment: int = 24):
    """Points along every subpath of `d`, in order."""
    points = []
    for run in subpaths(d):
        for p0, p1, p2, p3 in run:
            for i in range(per_segment):
                points.append(_cubic(p0, p1, p2, p3, i / per_segment))
    return points


def max_deviation(a: str, b: str, per_segment: int = 24) -> float:
    """The worst distance from a point on `a` to the nearest point on `b`.

    Symmetric (the worse of the two directions), so one path being a subset of
    the other cannot pass.
    """
    pa = sample(a, per_segment)
    pb = sample(b, per_segment)
    if not pa or not pb:
        return float("inf")

    def worst(source, target):
        result = 0.0
        for point in source:
            nearest = min(
                (point[0] - q[0]) ** 2 + (point[1] - q[1]) ** 2 for q in target
            )
            result = max(result, math.sqrt(nearest))
        return result

    return max(worst(pa, pb), worst(pb, pa))
