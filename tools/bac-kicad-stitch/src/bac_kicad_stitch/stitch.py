# SPDX-License-Identifier: MIT
"""Where a via may go, and which spots to take.

The board is rasterised to a grid of candidate points. A point is *valid*
when a via there is clean on every copper layer – clear of other nets'
copper by the clearance, clear of every hole by the hole-to-hole distance,
inside the outline by the edge clearance, outside rule areas that forbid
vias and outside the courtyards the settings avoid – and sits in the ground
fill of at least ``min_layers`` layers. The *target* is every point of the
ground fill on any layer.

Placement is farthest-point first: as long as some target point is farther
than the pitch from every ground via, the worst one picks a via among the
valid points within a pitch of it – the one farthest from every via, so
the vias spread instead of clustering. The result is deterministic (same
board, same settings, same vias). Target points with no valid point within
a pitch at all can never be covered and are reported as gaps. An optional
fence first puts vias along the board edge at the fence pitch.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry.base import BaseGeometry

from .board import Board, Via
from .config import Settings

__all__ = ["Result", "Placement", "plan"]


@dataclass(frozen=True, slots=True)
class Placement:
    x: float
    y: float
    fence: bool = False


@dataclass(slots=True)
class Result:
    pitch: float
    fence_pitch: float | None
    existing: int
    placed: list[Placement]
    coverage_before: float
    coverage_after: float
    target_area: float
    valid_area: float
    gaps: list[tuple[float, float, float]]  # x, y, distance to the nearest via
    gap_area: float
    avoided_footprints: list[str]
    target_mask: np.ndarray = field(repr=False)
    valid_mask: np.ndarray = field(repr=False)
    grid_x: np.ndarray = field(repr=False)
    grid_y: np.ndarray = field(repr=False)


def _contains(shape: BaseGeometry, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    if shape is None or shape.is_empty:
        return np.zeros(xs.shape, dtype=bool)
    shapely.prepare(shape)
    return shapely.contains_xy(shape, xs, ys)


def masks(board: Board, s: Settings) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """The candidate grid and, on it, the target and valid masks; plus the avoided footprint references."""
    minx, miny, maxx, maxy = board.outline.bounds
    step = s.step
    xs = np.arange(minx, maxx + step, step)
    ys = np.arange(miny, maxy + step, step)
    gx, gy = np.meshgrid(xs, ys)
    fx, fy = gx.ravel(), gy.ravel()

    r = s.via_radius
    inset = board.outline.buffer(-(s.edge_clearance + r + s.margin))
    valid = _contains(inset, fx, fy)

    # holes: the new drill must keep hole_to_hole from every other hole edge
    if not board.holes.is_empty:
        valid &= ~_contains(board.holes.buffer(s.hole_to_hole + s.via_drill / 2 + s.margin), fx, fy)
    if not board.via_keepout.is_empty:
        valid &= ~_contains(board.via_keepout.buffer(r + s.margin), fx, fy)

    avoided: list[str] = []
    if s.courtyards != "allow":
        parts = []
        for fp in board.footprints:
            if fp.courtyard is None:
                continue
            if s.courtyards == "avoid" or fp.is_fine_pitch(s.fine_pitch, s.fine_pitch_pads):
                parts.append(fp.courtyard)
                avoided.append(fp.reference)
        if parts:
            valid &= ~_contains(shapely.unary_union(parts).buffer(r), fx, fy)

    target = np.zeros(fx.shape, dtype=bool)
    in_fill_count = np.zeros(fx.shape, dtype=np.int16)
    for layer in board.copper_layers:
        fill = board.ground_fill.get(layer)
        if fill is not None and not fill.is_empty:
            target |= _contains(fill, fx, fy)
            in_fill_count += _contains(fill.buffer(-(r + s.margin)), fx, fy)
        obstacles = [board.other_copper.get(layer)]
        if s.keep_zones:
            obstacles.append(board.other_zones.get(layer))
        for other in obstacles:
            if other is not None and not other.is_empty:
                valid &= ~_contains(other.buffer(r + s.clearance + s.margin), fx, fy)
    valid &= in_fill_count >= s.min_layers
    target &= _contains(board.outline, fx, fy)
    return gx, gy, target, valid, avoided


def plan(board: Board, s: Settings) -> Result:
    pitch = s.effective_pitch(board.epsilon_r)
    gx, gy, target, valid, avoided = masks(board, s)
    fx, fy = gx.ravel(), gy.ravel()
    cell_area = s.step * s.step

    existing = board.ground_vias
    via_xy = [(v.x, v.y) for v in existing]

    # distance from every grid point to the nearest ground via
    dist = np.full(fx.shape, np.inf)
    if via_xy:
        tree = cKDTree(np.array(via_xy))
        dist, _ = tree.query(np.column_stack([fx, fy]))
    coverage_before = _coverage(dist, target, pitch)

    points = np.column_stack([fx, fy])
    valid_idx = np.flatnonzero(valid)
    cells = cKDTree(points)
    valid_tree = cKDTree(points[valid_idx]) if valid_idx.size else None
    placed: list[Placement] = []

    def add(index: int, fence: bool) -> None:
        x, y = float(fx[index]), float(fy[index])
        placed.append(Placement(x, y, fence))
        radius = float(dist[valid_idx].max()) if valid_idx.size else 0.0
        radius = max(radius, float(dist[target].max()) if target.any() else 0.0)
        if not np.isfinite(radius):
            d = np.hypot(fx - x, fy - y)
            np.minimum(dist, d, out=dist)
            return
        near = cells.query_ball_point((x, y), radius)
        if near:
            near = np.asarray(near)
            d = np.hypot(fx[near] - x, fy[near] - y)
            dist[near] = np.minimum(dist[near], d)

    fence_pitch = None
    if s.edge_fence and valid_idx.size:
        fence_pitch = s.fence_pitch(pitch)
        inset = board.outline.buffer(-(s.edge_clearance + s.via_radius + s.margin))
        rings = [g.exterior for g in getattr(inset, "geoms", [inset]) if not g.is_empty]
        for ring in rings:
            n = max(1, int(ring.length / fence_pitch))
            for i in range(n):
                p = ring.interpolate(i / n, normalized=True)
                d, j = valid_tree.query((p.x, p.y))
                if d > fence_pitch / 2:
                    continue
                index = int(valid_idx[j])
                if dist[index] < 0.6 * fence_pitch:
                    continue
                add(index, True)

    # target points with no valid point within the pitch can never be covered: those are the gaps
    target_idx = np.flatnonzero(target)
    coverable = np.zeros(fx.shape, dtype=bool)
    if valid_tree is not None and target_idx.size:
        nearest_valid, _ = valid_tree.query(points[target_idx], distance_upper_bound=pitch)
        coverable[target_idx[np.isfinite(nearest_valid)]] = True
    coverable_idx = np.flatnonzero(coverable)

    # farthest-point first: the worst-covered ground point picks the via that covers it and
    # is itself farthest from every via, so the vias spread instead of clustering at the gap
    while coverable_idx.size:
        worst = int(coverable_idx[np.argmax(dist[coverable_idx])])
        if dist[worst] <= pitch:
            break
        candidates = valid_idx[valid_tree.query_ball_point(points[worst], pitch, return_sorted=True)]
        add(int(candidates[np.argmax(dist[candidates])]), False)

    coverage_after = _coverage(dist, target, pitch)
    gap_mask = target & ~coverable
    gaps = _gap_centres(fx, fy, dist, gap_mask, pitch)
    return Result(
        pitch=pitch,
        fence_pitch=fence_pitch,
        existing=len(existing),
        placed=placed,
        coverage_before=coverage_before,
        coverage_after=coverage_after,
        target_area=float(target.sum()) * cell_area,
        valid_area=float(valid.sum()) * cell_area,
        gaps=gaps,
        gap_area=float(gap_mask.sum()) * cell_area,
        avoided_footprints=avoided,
        target_mask=target.reshape(gx.shape),
        valid_mask=valid.reshape(gx.shape),
        grid_x=gx,
        grid_y=gy,
    )


def _coverage(dist: np.ndarray, target: np.ndarray, pitch: float) -> float:
    n = int(target.sum())
    if n == 0:
        return 1.0
    return float((dist[target] <= pitch).sum()) / n


def _gap_centres(
    fx: np.ndarray, fy: np.ndarray, dist: np.ndarray, gap_mask: np.ndarray, pitch: float
) -> list[tuple[float, float, float]]:
    """One representative point per gap region: the farthest-from-any-via point, regions merged within a pitch."""
    idx = np.flatnonzero(gap_mask)
    if idx.size == 0:
        return []
    order = idx[np.argsort(-dist[idx])]
    chosen: list[tuple[float, float, float]] = []
    for i in order:
        x, y, d = float(fx[i]), float(fy[i]), float(dist[i])
        if all((x - cx) ** 2 + (y - cy) ** 2 > pitch * pitch for cx, cy, _ in chosen):
            chosen.append((x, y, d))
        if len(chosen) >= 50:
            break
    return chosen


def as_vias(result: Result, s: Settings) -> list[Via]:
    return [Via(p.x, p.y, s.via_size, s.via_drill, s.net, "", True) for p in result.placed]
