# SPDX-License-Identifier: MIT
"""Solver-independent geometry: primitives for CSXCAD, shapes for the cavity model.

Units: mm. z = 0 is the ground copper; the patch sits at z = gap + top board.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

PRIORITY_DIELECTRIC = 0
PRIORITY_PORT = 5  # below the metals, as in the upstream patch tutorial
PRIORITY_METAL = 10
PRIORITY_SLEEVE = 20
PRIORITY_APERTURE = 100  # air cut through everything inside the bore

Point = tuple[float, float]


@dataclass(frozen=True)
class Primitive:
    kind: str  # polygon | linpoly | cylinder | box
    prop: str
    material: str  # metal | dielectric | air
    priority: int
    epsilon_r: float = 1.0
    loss_tangent: float = 0.0
    points: tuple[Point, ...] = ()
    elevation: float = 0.0
    length: float = 0.0  # linpoly extrusion along +z
    start: tuple[float, float, float] = (0.0, 0.0, 0.0)
    stop: tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = 0.0


@dataclass(frozen=True)
class Port:
    start: tuple[float, float, float]
    stop: tuple[float, float, float]
    direction: str
    impedance_ohm: float
    priority: int = PRIORITY_PORT


@dataclass(frozen=True)
class FieldPlane:
    """A plane for frequency-domain field dumps; the backend snaps the fixed coordinate to the nearest mesh line."""

    name: str
    start: tuple[float, float, float]
    stop: tuple[float, float, float]


@dataclass(frozen=True)
class Model:
    """Everything the solver needs, produced by an antenna type; nothing in here is specific to one antenna.

    fixed_lines: mesh lines that must exist (edges of thin sheets, feed positions).
    grid_lines: further lines the antenna type wants (e.g. a graded set across a thin gap); merged like fixed lines
        but with lower priority (dropped near a fixed line).
    refine: (half-extent, cell) of a fine uniform grid around the origin (0 = none).
    bounds: (xmin, xmax, ymin, ymax, zmin, zmax) of the structure; the backend adds the air margin.
    phase_centre: far-field phase centre.
    edge_props: property names whose edges get metal-edge refinement.
    field_planes: planes for E-field dumps when [dump] efield is on.
    """

    primitives: tuple[Primitive, ...]
    ports: tuple[Port, ...]
    fixed_lines: dict[str, tuple[float, ...]]
    refine: tuple[float, float] = (0.0, 0.0)
    notes: tuple[str, ...] = field(default_factory=tuple)
    grid_lines: dict[str, tuple[float, ...]] = field(default_factory=dict)
    bounds: tuple[float, float, float, float, float, float] | None = None
    phase_centre: tuple[float, float, float] = (0.0, 0.0, 0.0)
    edge_props: tuple[str, ...] = ()
    field_planes: tuple[FieldPlane, ...] = ()

    def extent(self) -> tuple[float, float, float, float, float, float]:
        """bounds, or the bounding box of the primitives when none was given."""
        if self.bounds is not None:
            return self.bounds
        xs, ys, zs = [], [], []
        for p in self.primitives:
            if p.kind in ("box", "cylinder"):
                xs += [p.start[0] - p.radius, p.stop[0] + p.radius]
                ys += [p.start[1] - p.radius, p.stop[1] + p.radius]
                zs += [p.start[2], p.stop[2]]
            else:
                xs += [q[0] for q in p.points]
                ys += [q[1] for q in p.points]
                zs += [p.elevation, p.elevation + p.length]
        for q in self.ports:
            xs += [q.start[0], q.stop[0]]
            ys += [q.start[1], q.stop[1]]
            zs += [q.start[2], q.stop[2]]
        return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


@dataclass(frozen=True)
class Shape:
    """Patch description for the cavity model."""

    outline: tuple[Point, ...]  # outer contour, CCW
    hole_radius: float  # open hole (magnetic wall), 0 = none
    short_radius: float  # PEC tube joining patch and ground, 0 = none
    feeds: tuple[Point, ...]
    fringe_width_mm: float  # strip width used for the Hammerstad edge extension


# ---------------------------------------------------------------- outlines


def circle(
    radius: float, segments: int = 48, cx: float = 0.0, cy: float = 0.0, start: float = 0.0, clockwise: bool = False
) -> tuple[Point, ...]:
    s = -1 if clockwise else 1
    return tuple(
        (
            cx + radius * math.cos(start + s * 2 * math.pi * i / segments),
            cy + radius * math.sin(start + s * 2 * math.pi * i / segments),
        )
        for i in range(segments)
    )


def cross_outline(arm_x: float, arm_y: float, width: float, width_y: float | None = None) -> tuple[Point, ...]:
    """Plus shape, CCW, starting at (-arm_x/2, 0). Arms are full tip-to-tip lengths."""
    ax, ay, w = arm_x / 2, arm_y / 2, width / 2
    wy = (width_y if width_y is not None else width) / 2
    return (
        (-ax, 0.0),
        (-ax, -w),
        (-wy, -w),
        (-wy, -ay),
        (wy, -ay),
        (wy, -w),
        (ax, -w),
        (ax, w),
        (wy, w),
        (wy, ay),
        (-wy, ay),
        (-wy, w),
        (-ax, w),
    )


def ring_outline(outer: float, tab_length: float, tab_width: float, segments: int = 96) -> tuple[Point, ...]:
    """Circle with a radial tab at +x, CCW, starting at 180 deg."""
    step = 2 * math.pi / segments
    pts: list[Point] = []

    def arc(a0: float, a1: float) -> None:
        n = max(1, int(round(abs(a1 - a0) / step)))
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n
            pts.append((outer * math.cos(a), outer * math.sin(a)))

    if tab_length > 0:
        half = tab_width / 2
        t = math.asin(min(1.0, half / outer))
        arc(math.pi, 2 * math.pi - t)
        x_root = math.sqrt(max(0.0, outer**2 - half**2))
        pts.extend([(x_root, -half), (outer + tab_length, -half), (outer + tab_length, half), (x_root, half)])
        arc(t, math.pi)
    else:
        arc(math.pi, 3 * math.pi)
    # drop a duplicate closing point if present
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-9:
        pts.pop()
    return tuple(pts)


def with_hole(outline: tuple[Point, ...], radius: float, segments: int = 48) -> tuple[Point, ...]:
    """Join a centred circular hole to an outline with a zero-width seam on the -x axis.

    `outline` must start on the -x axis (all outlines above do). CSXCAD's winding-number test
    then gives the hole winding 0.
    """
    start = outline[0]
    hole = [
        (
            radius * math.cos(math.pi - 2 * math.pi * i / segments),
            radius * math.sin(math.pi - 2 * math.pi * i / segments),
        )
        for i in range(segments + 1)
    ]
    return tuple(outline) + (start,) + tuple(hole)


def winding(points: tuple[Point, ...], x: float, y: float) -> int:
    """Same rule as CSPrimPolygon::IsInside."""
    w = 0
    for i in range(len(points)):
        x1, y1 = points[i - 1]
        x2, y2 = points[i]
        so, eo = y1 >= y, y2 >= y
        if so != eo:
            if (y2 - y) * (x2 - x1) <= (y2 - y1) * (x2 - x):
                if eo:
                    w += 1
            elif not eo:
                w -= 1
    return w


def check_model(model: Model) -> list[str]:
    problems = []
    for p in model.primitives:
        if p.kind == "cylinder":
            if math.dist(p.start, p.stop) <= 0:
                problems.append(f"{p.prop}: zero-length cylinder (CSXCAD treats it as covering the whole domain)")
            if p.radius <= 0:
                problems.append(f"{p.prop}: non-positive radius")
        if p.kind in {"polygon", "linpoly"} and len(p.points) < 3:
            problems.append(f"{p.prop}: degenerate polygon")
        if p.kind == "linpoly" and p.length <= 0:
            problems.append(f"{p.prop}: non-positive extrusion length")
    for i, port in enumerate(model.ports):
        axis = "xyz".index(port.direction) if port.direction in "xyz" else -1
        if axis < 0:
            problems.append(f"port {i}: direction must be x, y or z")
        elif any(port.start[d] != port.stop[d] for d in range(3) if d != axis):
            problems.append(f"port {i}: not a line along {port.direction}")
        if math.dist(port.start, port.stop) <= 0:
            problems.append(f"port {i}: zero length")
    return problems
