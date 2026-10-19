# SPDX-License-Identifier: MIT
"""An SVG of the plan: outline, ground copper, the valid region, existing and new vias, gaps."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from .board import Board
from .stitch import Result

__all__ = ["write_svg"]

INK = "#2A2A2A"
GROUND = "#D9D9D9"
VALID = "#CFE8BE"
EXISTING = "#7A7A7A"
NEW = "#4E9A2E"
FENCE = "#2D7F9A"
GAP = "#CE6C63"
COURTYARD = "#F7D400"


def _path(shape: BaseGeometry, scale: float, ox: float, oy: float) -> str:
    polys = shape.geoms if isinstance(shape, MultiPolygon) else [shape] if isinstance(shape, Polygon) else []
    parts = []
    for poly in polys:
        for ring in (poly.exterior, *poly.interiors):
            coords = list(ring.coords)
            if not coords:
                continue
            parts.append("M " + " L ".join(f"{(x - ox) * scale:.2f} {(y - oy) * scale:.2f}" for x, y in coords) + " Z")
    return " ".join(parts)


def _mask_cells(result: Result, mask: np.ndarray, step: float, scale: float, ox: float, oy: float, fill: str) -> str:
    """Rectangles for the run-length rows of a grid mask, so the SVG stays small."""
    out = []
    gx, gy = result.grid_x, result.grid_y
    h = step * scale
    for row in range(mask.shape[0]):
        cells = np.flatnonzero(mask[row])
        if cells.size == 0:
            continue
        breaks = np.flatnonzero(np.diff(cells) > 1)
        starts = np.concatenate(([0], breaks + 1))
        ends = np.concatenate((breaks, [cells.size - 1]))
        y = (gy[row, 0] - oy - step / 2) * scale
        for a, b in zip(starts, ends, strict=True):
            x0 = (gx[row, cells[a]] - ox - step / 2) * scale
            w = (cells[b] - cells[a] + 1) * step * scale
            out.append(f'<rect x="{x0:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}"/>')
    return "\n".join(out)


def write_svg(path: Path, board: Board, result: Result, *, step: float, avoided: list[str], via_size: float) -> None:
    minx, miny, maxx, maxy = board.outline.bounds
    pad = 3.0
    ox, oy = minx - pad, miny - pad
    width_mm, height_mm = maxx - minx + 2 * pad, maxy - miny + 2 * pad
    scale = 10.0
    w, h = width_mm * scale, height_mm * scale + 60
    r = via_size / 2 * scale

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<path d="{_path(board.outline, scale, ox, oy)}" fill="none" stroke="{INK}" stroke-width="2"/>',
        _mask_cells(result, result.target_mask, step, scale, ox, oy, GROUND),
        _mask_cells(result, result.valid_mask, step, scale, ox, oy, VALID),
    ]
    avoided_set = set(avoided)
    for fp in board.footprints:
        if fp.reference in avoided_set and fp.courtyard is not None:
            parts.append(
                f'<path d="{_path(fp.courtyard, scale, ox, oy)}" fill="none" stroke="{COURTYARD}" stroke-width="1.5"/>'
            )

    def circle(x: float, y: float, radius: float, style: str) -> str:
        return f'<circle cx="{(x - ox) * scale:.1f}" cy="{(y - oy) * scale:.1f}" r="{radius:.1f}" {style}/>'

    for via in board.ground_vias:
        parts.append(circle(via.x, via.y, via.size / 2 * scale, f'fill="{EXISTING}"'))
    for p in result.placed:
        parts.append(circle(p.x, p.y, r, f'fill="{FENCE if p.fence else NEW}"'))
    gap_style = f'fill="none" stroke="{GAP}" stroke-width="1.5" stroke-dasharray="4 3"'
    for x, y, _ in result.gaps:
        parts.append(circle(x, y, result.pitch * scale / 2, gap_style))
    # legend
    ly = height_mm * scale + 20
    legend = [
        (GROUND, "ground copper"),
        (VALID, "via allowed"),
        (EXISTING, f"existing ({result.existing})"),
        (NEW, f"new ({sum(not p.fence for p in result.placed)})"),
        (FENCE, f"fence ({sum(p.fence for p in result.placed)})"),
        (GAP, f"gap ({len(result.gaps)})"),
    ]
    font = f'font-family="sans-serif" font-size="11" fill="{INK}"'
    lx = 10.0
    for colour, label in legend:
        swatch = f'fill="{colour}" stroke="{INK}" stroke-width="0.5"'
        parts.append(f'<rect x="{lx:.0f}" y="{ly:.0f}" width="12" height="12" {swatch}/>')
        parts.append(f'<text x="{lx + 16:.0f}" y="{ly + 10:.0f}" {font}>{label}</text>')
        lx += 16 + 7 * len(label) + 14
    before, after = result.coverage_before * 100, result.coverage_after * 100
    caption = f"pitch {result.pitch:.2f} mm · coverage {before:.1f}% → {after:.1f}%"
    parts.append(f'<text x="10" y="{ly + 30:.0f}" {font}>{caption}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")
