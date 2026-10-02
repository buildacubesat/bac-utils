# SPDX-License-Identifier: MIT
"""X/Y/Z scale gizmo: axes one main unit long in true model scale, drawn with the
view rotation, with an end bar at the unit."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

AXIS_COLORS = {"X": "#CE6C63", "Y": "#84C45A", "Z": "#6C9BCE"}
AXIS_LABELS = {"X": "Xp", "Y": "Yp", "Z": "Zp"}  # BAC convention: Xp/Xm for the +X/-X directions
LABEL_COLOR = "#8C8C8C"
DOT_COLOR = "#6E6E6E"
HALO_COLOR = (255, 255, 255, 120)  # drawn under the gizmo, only where it overlaps the model
UNIT_SERIES = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
MAX_AXIS_PX = 90  # longest allowed main-unit axis in output px
MARGIN_PX = 14
SUPERSAMPLE = 3

_FONT_CANDIDATES = [
    "Nunito-SemiBold.ttf",
    "Nunito-Regular.ttf",
    "IBMPlexSans-Medium.ttf",
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "LiberationSans-Bold.ttf",
    "Arial Bold.ttf",
    "arialbd.ttf",
]
_FONT_DIRS = [
    Path("~/.fonts").expanduser(),
    Path("~/.local/share/fonts").expanduser(),
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path("C:/Windows/Fonts"),
]


@dataclass
class GizmoSpec:
    unit_mm: float
    px_per_mm: float  # output px per mm
    rot: np.ndarray  # 3×3 view rotation
    size: int  # output image size (square)
    margin: int = MARGIN_PX
    show_label: bool = True


def choose_unit(px_per_mm: float, max_px: int = MAX_AXIS_PX) -> float:
    """Largest unit of the 1-2-5 series whose axis fits in max_px (at least the smallest)."""
    fitting = [u for u in UNIT_SERIES if u * px_per_mm <= max_px]
    return fitting[-1] if fitting else UNIT_SERIES[0]


def format_unit(unit_mm: float) -> str:
    if unit_mm >= 1000:
        return f"{unit_mm / 1000:g} m"
    return f"{unit_mm:g} mm"


@lru_cache(maxsize=8)
def _find_font(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """First installed candidate font at `px`, else Pillow's default; the directory walk runs once per size."""
    for name in _FONT_CANDIDATES:
        for d in _FONT_DIRS:
            if not d.exists():
                continue
            hits = list(d.rglob(name))
            if hits:
                try:
                    return ImageFont.truetype(str(hits[0]), px)
                except OSError:
                    continue
    try:
        return ImageFont.load_default(size=px)
    except TypeError:  # pragma: no cover – very old Pillow
        return ImageFont.load_default()


def axis_screen_dirs(rot: np.ndarray) -> dict[str, tuple[float, float]]:
    """Unit axes projected to output-image directions (x right, y down), per mm."""
    out = {}
    for name, e in zip("XYZ", np.eye(3), strict=True):
        v = rot @ e
        out[name] = (float(v[0]), float(-v[1]))
    return out


def _text_at(
    d: ImageDraw.ImageDraw, center: tuple[float, float], text: str, font, fill, angle: float, stroke: int
) -> None:
    """Draw text centred at `center`, rotated by `angle` degrees (counterclockwise)."""
    if abs(angle) < 0.01:
        d.text(center, text, font=font, fill=fill, anchor="mm", stroke_width=stroke, stroke_fill=fill)
        return
    bb = d.textbbox((0, 0), text, font=font, anchor="lt")
    pad = stroke + 2
    w, h = bb[2] - bb[0] + 2 * pad, bb[3] - bb[1] + 2 * pad
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text(
        (pad - bb[0], pad - bb[1]), text, font=font, fill=fill, anchor="lt", stroke_width=stroke, stroke_fill=fill
    )
    tile = tile.rotate(angle, resample=Image.BICUBIC, expand=True)
    d._image.alpha_composite(tile, (round(center[0] - tile.width / 2), round(center[1] - tile.height / 2)))


def draw_gizmo(base: Image.Image, spec: GizmoSpec) -> Image.Image:
    """Return a copy of `base` with the gizmo composited bottom left.

    Each axis runs from an origin dot to a bar at one main unit; the unit text
    is written along the most horizontal axis so the dot-to-bar distance reads
    as a dimension."""
    ss = SUPERSAMPLE
    S = spec.size
    L = spec.unit_mm * spec.px_per_mm  # axis length, output px
    dirs = axis_screen_dirs(spec.rot)

    font_axis = _find_font(13 * ss)
    font_unit = _find_font(11 * ss)
    line_w = 2 * ss
    bar_half = 6 * ss  # end bar, half length
    dot_r = 2.6 * ss
    label_gap = 6 * ss  # from the end bar to the nearest edge of the letters

    scratch = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    # Geometry in gizmo-local supersampled coordinates (origin 0,0).
    segments: list[tuple[tuple[float, float], tuple[float, float], str, int]] = []
    labels: list[
        tuple[tuple[float, float], str, str, ImageFont.ImageFont, float]
    ] = []  # centre, text, colour, font, angle
    unit_text = format_unit(spec.unit_mm)
    # the unit text follows the most horizontal axis, written underneath it
    bottom_axis = max(dirs, key=lambda n: abs(dirs[n][0]) if math.hypot(*dirs[n]) * L >= 10 else -1.0)
    for name, (dx, dy) in dirs.items():
        length = math.hypot(dx, dy) * L * ss
        color = AXIS_COLORS[name]
        if length < 1e-6:
            labels.append(((0.0, 0.0), AXIS_LABELS[name], color, font_axis, 0.0))
            continue
        ux, uy = dx / math.hypot(dx, dy), dy / math.hypot(dx, dy)
        tip = (ux * length, uy * length)
        segments.append(((0.0, 0.0), tip, color, line_w))
        nx, ny = -uy, ux  # perpendicular
        segments.append(
            (
                (tip[0] - nx * bar_half, tip[1] - ny * bar_half),
                (tip[0] + nx * bar_half, tip[1] + ny * bar_half),
                color,
                line_w,
            )
        )
        # place the letters so their near edge, not their centre, sits label_gap past the bar
        bb = scratch.textbbox((0, 0), AXIS_LABELS[name], font=font_axis, anchor="mm")
        half_extent = abs(ux) * (bb[2] - bb[0]) / 2 + abs(uy) * (bb[3] - bb[1]) / 2
        dist = length + label_gap + half_extent
        labels.append(((ux * dist, uy * dist), AXIS_LABELS[name], color, font_axis, 0.0))
        if name == bottom_axis and spec.show_label:
            # unit text centred under the span, baseline along the axis, reading left to right
            tx, ty = (ux, uy) if ux >= 0 else (-ux, -uy)
            side = 1.0 if ny >= 0 else -1.0  # perpendicular pointing down the image
            off = bar_half + 7 * ss
            angle = -math.degrees(math.atan2(ty, tx))  # PIL rotates counterclockwise; image y points down
            pos = (ux * length * 0.5 + nx * side * off, uy * length * 0.5 + ny * side * off)
            labels.append((pos, unit_text, LABEL_COLOR, font_unit, angle))

    # Bounding box of everything, to anchor the block in the corner.
    xs, ys = [-dot_r, dot_r], [-dot_r, dot_r]
    for a, b, _, w in segments:
        for px_, py_ in (a, b):
            xs += [px_ - w, px_ + w]
            ys += [py_ - w, py_ + w]
    for (lx, ly), text, _, font, angle in labels:
        bb = scratch.textbbox((0, 0), text, font=font, anchor="mm")
        a = math.radians(-angle)
        for cx_, cy_ in ((bb[0], bb[1]), (bb[2], bb[1]), (bb[2], bb[3]), (bb[0], bb[3])):
            xs.append(lx + cx_ * math.cos(a) - cy_ * math.sin(a))
            ys.append(ly + cx_ * math.sin(a) + cy_ * math.cos(a))
    min_x, max_x, max_y = min(xs), max(xs), max(ys)
    ox = spec.margin * ss - min_x
    oy = (S - spec.margin) * ss - max_y
    if ox + max_x > (S - spec.margin) * ss:  # wider than the image allows: keep the origin side visible
        ox = (S - spec.margin) * ss - max_x

    def paint(d: ImageDraw.ImageDraw, color_of, extra: int, stroke: int) -> None:
        for a, b, color, w in segments:
            d.line([(ox + a[0], oy + a[1]), (ox + b[0], oy + b[1])], fill=color_of(color), width=w + extra)
            r = (w + extra) / 2
            for px_, py_ in (a, b):  # round caps
                d.ellipse([ox + px_ - r, oy + py_ - r, ox + px_ + r, oy + py_ + r], fill=color_of(color))
        r = dot_r + extra / 2
        d.ellipse([ox - r, oy - r, ox + r, oy + r], fill=color_of(DOT_COLOR))
        for (lx, ly), text, color, font, angle in labels:
            _text_at(d, (ox + lx, oy + ly), text, font, color_of(color), angle, stroke)

    # Halo under lines and letters so the gizmo stays legible where it overlaps the model.
    halo = Image.new("RGBA", (S * ss, S * ss), (0, 0, 0, 0))
    hw = round(1.2 * ss)
    paint(ImageDraw.Draw(halo), lambda _c: HALO_COLOR, 2 * hw, hw)
    layer = Image.new("RGBA", (S * ss, S * ss), (0, 0, 0, 0))
    paint(ImageDraw.Draw(layer), lambda c: c, 0, 0)

    out = base.convert("RGBA").copy()
    halo_small = halo.resize((S, S), Image.LANCZOS)
    model_alpha = out.getchannel("A")
    halo_small.putalpha(ImageChops.multiply(halo_small.getchannel("A"), model_alpha))
    out.alpha_composite(halo_small)
    out.alpha_composite(layer.resize((S, S), Image.LANCZOS))
    return out
