# SPDX-License-Identifier: MIT
"""The parts of a board the stitcher needs, read from the parsed file.

Per copper layer: the ground fill (where a via connects), the fixed copper
of other nets (tracks, pads, vias, graphics – what a via must keep clear
of) and the other nets' zone fills, which KiCad refills around a new via
and which therefore only count as obstacles on request. Board-wide: the outline
with its cutouts, every drill hole, the courtyards, rule areas that forbid
vias, and the ground vias already there.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import shapely
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize

from bac_common.errors import BacError
from bac_common.sexp import Node

from .config import GROUP_NAME
from .geometry import (
    Transform,
    graphic_copper,
    graphic_shape,
    pad_hole,
    pad_shape,
    polygon_from_pts,
    track_shape,
    union,
)

__all__ = ["Via", "Footprint", "Board", "read_board"]


@dataclass(frozen=True, slots=True)
class Via:
    x: float
    y: float
    size: float
    drill: float
    net: str
    uuid: str
    stitched: bool = False


@dataclass(slots=True)
class Footprint:
    reference: str
    courtyard: BaseGeometry | None
    pads: int
    min_pad_pitch: float

    def is_fine_pitch(self, pitch: float, min_pads: int) -> bool:
        return self.pads >= min_pads and self.min_pad_pitch < pitch


@dataclass(slots=True)
class Board:
    net: str
    copper_layers: list[str]
    outline: Polygon
    ground_fill: dict[str, BaseGeometry]
    other_copper: dict[str, BaseGeometry]
    other_zones: dict[str, BaseGeometry]
    holes: BaseGeometry
    via_keepout: BaseGeometry
    footprints: list[Footprint]
    vias: list[Via]
    epsilon_r: float | None
    stitch_group: Node | None
    stitch_uuids: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)

    @property
    def ground_vias(self) -> list[Via]:
        return [v for v in self.vias if v.net == self.net]


def _expand_layers(names: list[str], copper: list[str]) -> list[str]:
    out: list[str] = []
    for name in names:
        if name == "*.Cu":
            out.extend(copper)
        elif name == "F&B.Cu":
            out.extend(n for n in copper if n in ("F.Cu", "B.Cu"))
        elif name in copper:
            out.append(name)
    return out


def _layers_of(node: Node, copper: list[str]) -> list[str]:
    layers = node.child("layers")
    if layers:
        return _expand_layers([a.value for a in layers.atoms()[1:]], copper)
    layer = node.child("layer")
    return _expand_layers([layer.value(1)], copper) if layer else []


def _net_of(node: Node) -> str:
    net = node.child("net")
    return net.value(1) if net else ""


def _copper_layers(root: Node) -> list[str]:
    layers = root.child("layers")
    if layers is None:
        raise BacError("The board has no (layers) block.")
    out: list[str] = []
    for entry in layers.children():
        atoms = entry.atoms()
        if (
            len(atoms) >= 3
            and atoms[1].value.endswith(".Cu")
            and atoms[2].value in ("signal", "power", "mixed", "jumper")
        ):
            out.append(atoms[1].value)
    if not out:
        raise BacError("The board has no copper layers.")
    return out


def _epsilon_r(root: Node) -> float | None:
    setup = root.child("setup")
    stackup = setup.child("stackup") if setup else None
    if stackup is None:
        return None
    values = [float(n.child("epsilon_r").value(1)) for n in stackup.children("layer") if n.child("epsilon_r")]
    return sum(values) / len(values) if values else None


def _footprint_transform(fp: Node) -> Transform:
    at = fp.child("at")
    if at is None:
        return Transform()
    return Transform(float(at.value(1)), float(at.value(2)), float(at.value(3)) if at.value(3) else 0.0)


def _outline(edge_items: list[BaseGeometry], where: str) -> Polygon:
    lines: list[BaseGeometry] = []
    for shape in edge_items:
        if isinstance(shape, Polygon):
            lines.append(shape.exterior)
        else:
            lines.append(shape)
    if not lines:
        raise BacError(f"{where}: no Edge.Cuts outline found.")
    noded = shapely.unary_union([shapely.set_precision(line, 1e-4) for line in lines])
    faces = list(polygonize(noded))
    if not faces:
        raise BacError(
            f"{where}: the Edge.Cuts items do not close into an outline.", "Check for gaps between segments."
        )
    outer = max(faces, key=lambda f: f.area)
    return outer


def _zone_fills(zone: Node, copper: list[str]) -> dict[str, BaseGeometry]:
    out: dict[str, list[BaseGeometry]] = {}
    for fill in zone.children("filled_polygon"):
        layer = fill.child("layer")
        pts = fill.child("pts")
        if layer is None or pts is None or layer.value(1) not in copper:
            continue
        poly = polygon_from_pts(pts)
        if poly is not None:
            out.setdefault(layer.value(1), []).append(poly)
    return {layer: union(parts) for layer, parts in out.items()}


def _keepout_forbids_vias(zone: Node) -> bool:
    keepout = zone.child("keepout")
    if keepout is None:
        return False
    vias = keepout.child("vias")
    return bool(vias) and vias.value(1) == "not_allowed"


def _min_pitch(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return math.inf
    return min(math.dist(a, b) for a, b in itertools.combinations(points, 2))


def read_board(root: Node, net: str, where: str = "") -> Board:
    copper = _copper_layers(root)
    ground: dict[str, list[BaseGeometry]] = {layer: [] for layer in copper}
    other: dict[str, list[BaseGeometry]] = {layer: [] for layer in copper}
    zones: dict[str, list[BaseGeometry]] = {layer: [] for layer in copper}
    holes: list[BaseGeometry] = []
    keepouts: list[BaseGeometry] = []
    edges: list[BaseGeometry] = []
    footprints: list[Footprint] = []
    vias: list[Via] = []
    warnings: list[str] = []

    def copper_item(shape: BaseGeometry | None, layers: list[str], item_net: str) -> None:
        if shape is None or shape.is_empty:
            return
        target = ground if item_net == net else other
        for layer in layers:
            target[layer].append(shape)

    for item in root.children():
        head = item.head
        if head in ("segment", "arc"):
            copper_item(track_shape(item), _layers_of(item, copper), _net_of(item))
        elif head == "via":
            at = item.child("at")
            size = float(item.child("size").value(1)) if item.child("size") else 0.0
            drill = float(item.child("drill").value(1)) if item.child("drill") else 0.0
            via_net = _net_of(item)
            uuid = item.child("uuid").value(1) if item.child("uuid") else ""
            x, y = float(at.value(1)), float(at.value(2))
            vias.append(Via(x, y, size, drill, via_net, uuid))
            layers = _layers_of(item, copper) or copper
            if len(layers) == 2 and layers[0] in copper and layers[1] in copper:
                i, j = sorted(copper.index(n) for n in layers)
                layers = copper[i : j + 1]
            copper_item(Point(x, y).buffer(size / 2, quad_segs=8), layers, via_net)
            holes.append(Point(x, y).buffer(drill / 2, quad_segs=8))
        elif head == "zone":
            _read_zone(item, copper, net, ground, zones, keepouts)
        elif head and head.startswith("gr_"):
            layer = item.child("layer")
            if layer and layer.value(1) == "Edge.Cuts":
                shape, _ = graphic_shape(item)
                if shape is not None:
                    edges.append(shape)
            elif layer and layer.value(1) in copper:
                copper_item(graphic_copper(item), [layer.value(1)], _net_of(item))
        elif head == "footprint":
            _read_footprint(item, copper, net, ground, other, zones, holes, keepouts, edges, footprints)

    group = next((g for g in root.children("group") if g.value(1) == GROUP_NAME), None)
    stitch_uuids: set[str] = set()
    if group is not None and group.child("members"):
        stitch_uuids = {a.value for a in group.child("members").atoms()[1:]}
    vias = [Via(v.x, v.y, v.size, v.drill, v.net, v.uuid, v.uuid in stitch_uuids) for v in vias]

    board = Board(
        net=net,
        copper_layers=copper,
        outline=_outline(edges, where),
        ground_fill={layer: union(parts) for layer, parts in ground.items()},
        other_copper={layer: union(parts) for layer, parts in other.items()},
        other_zones={layer: union(parts) for layer, parts in zones.items()},
        holes=union(holes),
        via_keepout=union(keepouts),
        footprints=footprints,
        vias=vias,
        epsilon_r=_epsilon_r(root),
        stitch_group=group,
        stitch_uuids=stitch_uuids,
        warnings=warnings,
    )
    if all(fill.is_empty for fill in board.ground_fill.values()):
        raise BacError(
            f"{where}: no filled {net} zone found.", "Fill the zones in KiCad (B) and save before stitching."
        )
    return board


def _read_zone(
    zone: Node,
    copper: list[str],
    net: str,
    ground: dict[str, list[BaseGeometry]],
    zones: dict[str, list[BaseGeometry]],
    keepouts: list[BaseGeometry],
) -> None:
    if zone.child("keepout") is not None:
        if _keepout_forbids_vias(zone) and _layers_of(zone, copper):
            polygon = zone.child("polygon")
            poly = polygon_from_pts(polygon.child("pts")) if polygon and polygon.child("pts") else None
            if poly is not None:
                keepouts.append(poly)
        return
    zone_net = _net_of(zone)
    for layer, fill in _zone_fills(zone, copper).items():
        (ground if zone_net == net else zones)[layer].append(fill)


def _read_footprint(
    fp: Node,
    copper: list[str],
    net: str,
    ground: dict[str, list[BaseGeometry]],
    other: dict[str, list[BaseGeometry]],
    zones: dict[str, list[BaseGeometry]],
    holes: list[BaseGeometry],
    keepouts: list[BaseGeometry],
    edges: list[BaseGeometry],
    footprints: list[Footprint],
) -> None:
    tf = _footprint_transform(fp)
    reference = ""
    for prop in fp.children("property"):
        if prop.value(1) == "Reference":
            reference = prop.value(2)
    courtyard_parts: list[BaseGeometry] = []
    pad_centres: list[tuple[float, float]] = []
    for item in fp.children():
        head = item.head or ""
        if head == "pad":
            kind = item.value(2)
            pad_net = _net_of(item)
            shape = pad_shape(item, tf)
            at = item.child("at")
            pad_centres.append(tf.point(float(at.value(1)), float(at.value(2))) if at else tf.point(0, 0))
            hole = pad_hole(item, tf)
            if hole is not None:
                holes.append(hole)
            if kind == "np_thru_hole":
                # the hole itself, and whatever copper the pad shows, on every layer
                for layer in copper:
                    other[layer].append(shape)
                continue
            layers = _layers_of(item, copper)
            if kind == "thru_hole" and not layers:
                layers = copper
            target = ground if pad_net == net else other
            for layer in layers:
                target[layer].append(shape)
        elif head.startswith("fp_"):
            layer = item.child("layer")
            name = layer.value(1) if layer else ""
            if name == "Edge.Cuts":
                shape, _ = graphic_shape(item)
                if shape is not None:
                    edges.append(tf.apply(shape))
            elif name in ("F.CrtYd", "B.CrtYd"):
                shape, _ = graphic_shape(item)
                if shape is not None:
                    courtyard_parts.append(tf.apply(shape))
            elif name in copper:
                shape = graphic_copper(item)
                if shape is not None:
                    other[name].append(tf.apply(shape))
        elif head == "zone":
            _read_zone(item, copper, net, ground, zones, keepouts)
    courtyard = None
    if courtyard_parts:
        courtyard = shapely.unary_union(courtyard_parts).convex_hull
    footprints.append(Footprint(reference, courtyard, len(pad_centres), _min_pitch(pad_centres)))
