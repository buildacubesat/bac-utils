# SPDX-License-Identifier: MIT
"""Shapely shapes for the KiCad primitives the stitcher has to keep clear of.

Coordinates are board millimetres with Y pointing down, as in the file. A
footprint rotation of ``θ`` degrees is counter-clockwise on screen, so a
local point ``(x, y)`` lands at ``(X + x cos θ + y sin θ, Y − x sin θ + y cos θ)``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from bac_common.sexp import Node

__all__ = [
    "Transform",
    "arc_points",
    "pts_points",
    "pad_shape",
    "pad_hole",
    "track_shape",
    "graphic_shape",
    "polygon_from_pts",
    "union",
]

ARC_STEP_DEG = 7.5


class Transform:
    """Footprint placement: rotate by ``rot`` degrees, then move to ``(x, y)``."""

    __slots__ = ("x", "y", "rot", "_cos", "_sin")

    def __init__(self, x: float = 0.0, y: float = 0.0, rot: float = 0.0) -> None:
        self.x, self.y, self.rot = x, y, rot
        rad = math.radians(rot)
        self._cos, self._sin = math.cos(rad), math.sin(rad)

    def point(self, x: float, y: float) -> tuple[float, float]:
        return (self.x + x * self._cos + y * self._sin, self.y - x * self._sin + y * self._cos)

    def apply(self, shape: BaseGeometry) -> BaseGeometry:
        return shapely.affinity.translate(_rotate_local(shape, self.rot), self.x, self.y)


IDENTITY = Transform()


def _rotate_local(shape: BaseGeometry, rot: float) -> BaseGeometry:
    """Rotate ``shape`` about the origin by ``rot`` degrees, counter-clockwise on a y-down screen."""
    return shapely.affinity.rotate(shape, -rot, origin=(0, 0)) if rot else shape


def _xy(node: Node | None) -> tuple[float, float]:
    if node is None:
        return (0.0, 0.0)
    return (float(node.value(1)), float(node.value(2)))


def arc_points(
    start: tuple[float, float], mid: tuple[float, float], end: tuple[float, float]
) -> list[tuple[float, float]]:
    """Points along the circular arc through ``start``, ``mid`` and ``end``."""
    ax, ay = start
    bx, by = mid
    cx, cy = end
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return [start, mid, end]
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    a0 = math.atan2(ay - uy, ax - ux)
    a1 = math.atan2(by - uy, bx - ux)
    a2 = math.atan2(cy - uy, cx - ux)
    # sweep from a0 to a2 passing through a1
    sweep = (a2 - a0) % (2 * math.pi)
    to_mid = (a1 - a0) % (2 * math.pi)
    if to_mid > sweep:
        sweep -= 2 * math.pi
    n = max(2, int(abs(math.degrees(sweep)) / ARC_STEP_DEG) + 1)
    inner = [(ux + r * math.cos(a0 + sweep * i / n), uy + r * math.sin(a0 + sweep * i / n)) for i in range(1, n)]
    return [start, *inner, end]


def pts_points(pts: Node) -> list[tuple[float, float]]:
    """The vertices of a ``(pts ...)`` list, arcs sampled."""
    out: list[tuple[float, float]] = []
    for item in pts.children():
        if item.head == "xy":
            out.append(_xy(item))
        elif item.head == "arc":
            arc = arc_points(_xy(item.child("start")), _xy(item.child("mid")), _xy(item.child("end")))
            if out and out[-1] == arc[0]:
                arc = arc[1:]
            out.extend(arc)
    return out


def polygon_from_pts(pts: Node) -> Polygon | None:
    points = pts_points(pts)
    if len(points) < 3:
        return None
    poly = Polygon(points)
    return poly if poly.is_valid else shapely.make_valid(poly)


def _circle_points(center: tuple[float, float], radius: float) -> list[tuple[float, float]]:
    n = max(24, int(2 * math.pi * radius / 0.05))
    n = min(n, 256)
    return [
        (center[0] + radius * math.cos(2 * math.pi * i / n), center[1] + radius * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def graphic_shape(node: Node, width_default: float = 0.0) -> tuple[BaseGeometry | None, bool]:
    """The shape of a ``gr_*``/``fp_*`` graphic, and whether it is a closed outline.

    Lines and arcs come back as (unbuffered) line strings; rects, circles and
    polygons as polygons. The second value tells an outline assembler whether
    the item already closes on itself.
    """
    head = node.head or ""
    kind = head.split("_", 1)[-1]
    if kind == "line":
        return LineString([_xy(node.child("start")), _xy(node.child("end"))]), False
    if kind == "arc":
        return LineString(arc_points(_xy(node.child("start")), _xy(node.child("mid")), _xy(node.child("end")))), False
    if kind == "circle":
        center, edge = _xy(node.child("center")), _xy(node.child("end"))
        return Polygon(_circle_points(center, math.dist(center, edge))), True
    if kind == "rect":
        (x0, y0), (x1, y1) = _xy(node.child("start")), _xy(node.child("end"))
        return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]), True
    if kind == "poly":
        pts = node.child("pts")
        return (polygon_from_pts(pts) if pts else None), True
    return None, False


def _stroke_width(node: Node) -> float:
    stroke = node.child("stroke")
    if stroke and stroke.child("width"):
        return float(stroke.child("width").value(1))
    width = node.child("width")
    return float(width.value(1)) if width else 0.0


def graphic_copper(node: Node) -> BaseGeometry | None:
    """A graphic as copper: strokes buffered by half their width, fills as they are."""
    shape, closed = graphic_shape(node)
    if shape is None:
        return None
    width = _stroke_width(node)
    fill = node.child("fill")
    filled = bool(fill) and fill.value(1) in ("yes", "solid")
    if closed and not filled:
        shape = shape.exterior if isinstance(shape, Polygon) else shape
    if width > 0:
        return shape.buffer(width / 2)
    return shape if closed else None


def track_shape(node: Node) -> BaseGeometry | None:
    """A ``segment`` or ``arc`` track as copper."""
    width = float(node.child("width").value(1)) if node.child("width") else 0.0
    if node.head == "segment":
        line = LineString([_xy(node.child("start")), _xy(node.child("end"))])
    elif node.head == "arc":
        line = LineString(arc_points(_xy(node.child("start")), _xy(node.child("mid")), _xy(node.child("end"))))
    else:
        return None
    return line.buffer(width / 2, quad_segs=8)


def _pad_outline(pad: Node) -> BaseGeometry:
    """The pad's copper in its own frame (unrotated, centred on the origin)."""
    shape = pad.value(3)
    size = pad.child("size")
    w, h = (float(size.value(1)), float(size.value(2))) if size else (0.0, 0.0)
    if shape == "circle":
        return Point(0, 0).buffer(w / 2, quad_segs=12)
    if shape == "oval":
        if w >= h:
            return LineString([(-(w - h) / 2, 0), ((w - h) / 2, 0)]).buffer(h / 2, quad_segs=12)
        return LineString([(0, -(h - w) / 2), (0, (h - w) / 2)]).buffer(w / 2, quad_segs=12)
    if shape == "roundrect":
        ratio_node = pad.child("roundrect_rratio")
        ratio = float(ratio_node.value(1)) if ratio_node else 0.25
        r = ratio * min(w, h)
        inner = shapely.box(-w / 2 + r, -h / 2 + r, w / 2 - r, h / 2 - r)
        return inner.buffer(r, quad_segs=6) if r > 0 else shapely.box(-w / 2, -h / 2, w / 2, h / 2)
    if shape == "custom":
        parts: list[BaseGeometry] = []
        options = pad.child("options")
        anchor = options.child("anchor").value(1) if options and options.child("anchor") else "rect"
        parts.append(
            Point(0, 0).buffer(w / 2, quad_segs=12) if anchor == "circle" else shapely.box(-w / 2, -h / 2, w / 2, h / 2)
        )
        primitives = pad.child("primitives")
        if primitives:
            for prim in primitives.children():
                copper = graphic_copper(prim)
                if copper is None:
                    # an unfilled closed primitive without a stroke: KiCad fills custom pad polygons
                    shape_only, _ = graphic_shape(prim)
                    copper = shape_only
                if copper is not None:
                    parts.append(copper)
        return union(parts)
    # rect, trapezoid and anything unknown: the bounding box
    return shapely.box(-w / 2, -h / 2, w / 2, h / 2)


def pad_shape(pad: Node, fp: Transform) -> BaseGeometry:
    """A pad's copper on the board."""
    at = pad.child("at")
    x, y, rot = (
        (float(at.value(1)), float(at.value(2)), float(at.value(3)) if at.value(3) else 0.0) if at else (0.0, 0.0, 0.0)
    )
    outline = _rotate_local(_pad_outline(pad), rot)
    bx, by = fp.point(x, y)
    return shapely.affinity.translate(outline, bx, by)


def pad_hole(pad: Node, fp: Transform) -> BaseGeometry | None:
    """A pad's drill hole on the board, or ``None`` for an SMD pad."""
    drill = pad.child("drill")
    if drill is None:
        return None
    atoms = [a.value for a in drill.atoms()[1:]]
    if atoms and atoms[0] == "oval":
        dw, dh = float(atoms[1]), float(atoms[2]) if len(atoms) > 2 else float(atoms[1])
        if dw >= dh:
            hole: BaseGeometry = LineString([(-(dw - dh) / 2, 0), ((dw - dh) / 2, 0)]).buffer(dh / 2, quad_segs=12)
        else:
            hole = LineString([(0, -(dh - dw) / 2), (0, (dh - dw) / 2)]).buffer(dw / 2, quad_segs=12)
    elif atoms:
        hole = Point(0, 0).buffer(float(atoms[0]) / 2, quad_segs=12)
    else:
        return None
    offset = drill.child("offset")
    if offset:
        hole = shapely.affinity.translate(hole, float(offset.value(1)), float(offset.value(2)))
    at = pad.child("at")
    x, y, rot = (
        (float(at.value(1)), float(at.value(2)), float(at.value(3)) if at.value(3) else 0.0) if at else (0.0, 0.0, 0.0)
    )
    hole = _rotate_local(hole, rot)
    bx, by = fp.point(x, y)
    return shapely.affinity.translate(hole, bx, by)


def union(shapes: Iterable[BaseGeometry | None]) -> BaseGeometry:
    parts = [s for s in shapes if s is not None and not s.is_empty]
    if not parts:
        return Polygon()
    return shapely.unary_union(parts)
