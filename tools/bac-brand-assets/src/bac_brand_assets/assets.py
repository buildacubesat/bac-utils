# SPDX-License-Identifier: MIT
"""The construction of the BAC marks and the SVG files written from it.

Every number here is the Identity Guide §8 description made executable: the symbol is a
2U cube in true 30° isometric projection, the wordmark is Nunito set in two justified lines,
the logo places the wordmark beside the symbol. Change a value here and in the guide in the
same change.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from . import wordmark

VERSION = "v4r1"
"""Hardware-style version of the marks (Project & Tooling Guide §2.2); part of every file name."""
YEAR = 2026

# Symbol – an isometric 2U cube on a 400 × 650 canvas
EDGE = 200  # cube edge
STROKE = 15
CORNER = 5  # rounding of the six outline corners, measured from the vertex
DOT_RX = 30  # the dot on the top face; ry follows from the isometric projection
SYMBOL_CANVAS = (400, 650)

# Wordmark – two lines, "BUILD A" justified to the width of "CUBESAT"
FONT_WEIGHT = 350
TRACKING = -0.03  # em, after every glyph
CAP = 100  # cap height, canvas units
LEADING = 150  # baseline to baseline
PAD = 25  # canvas margin around the wordmark

# Logo – the horizontal lockup of symbol and wordmark
TEXT_FRACTION = 0.70  # wordmark block height relative to the cube height
GAP = 70  # symbol canvas edge to wordmark

COLORS = {"black": "#000000", "white": "#ffffff", "currentcolor": "currentColor"}
KINDS = ("symbol", "wordmark", "logo")


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _pt(p: tuple[float, float]) -> str:
    return f"{_f(p[0])} {_f(p[1])}"


def wrap(kind: str, body: str, width: float, height: float, construction: str) -> str:
    """The document around a mark: viewBox only, accessible title and desc, Dublin Core metadata."""
    title = f"Build a CubeSat {kind.capitalize()} {VERSION}"
    rights = f"Copyright {YEAR} nihil.space GmbH"
    desc = (
        f"Build a CubeSat (BAC) brand {kind}, version {VERSION[1:]}. {construction} {rights}. "
        "A BAC Mark: not covered by any open licence, use governed by the BAC Trademark Policy "
        "(hello@buildacubesat.space)."
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_f(width)} {_f(height)}" role="img"
 aria-labelledby="title desc">
  <title id="title">{title}</title>
  <desc id="desc">{desc}</desc>
  <metadata>
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/">
      <rdf:Description rdf:about="">
        <dc:title>{title}</dc:title>
        <dc:creator>nihil.space GmbH</dc:creator>
        <dc:rights>{rights}. BAC Mark, all rights reserved; use governed by the BAC Trademark Policy.</dc:rights>
        <dc:date>{YEAR}</dc:date>
      </rdf:Description>
    </rdf:RDF>
  </metadata>
{body}</svg>
"""


def symbol_group(color: str, ox: float = 0, oy: float = 0) -> str:
    """The cube as a stroked group; (ox, oy) moves its canvas for use inside the logo."""
    half = EDGE * math.sqrt(3) / 2
    width, height = SYMBOL_CANVAS
    cx, top = ox + width / 2, oy + (height - 3 * EDGE) / 2
    left, right = cx - half, cx + half

    def toward(p: tuple[float, float], q: tuple[float, float], dist: float) -> tuple[float, float]:
        dx, dy = q[0] - p[0], q[1] - p[1]
        n = math.hypot(dx, dy)
        return (p[0] + dx / n * dist, p[1] + dy / n * dist)

    # the hexagonal outline, clockwise from the top vertex, each corner rounded
    hexagon = [
        (cx, top),
        (right, top + EDGE / 2),
        (right, top + 2.5 * EDGE),
        (cx, top + 3 * EDGE),
        (left, top + 2.5 * EDGE),
        (left, top + EDGE / 2),
    ]
    parts, on_curve = [], []
    for i, p in enumerate(hexagon):
        a, b = toward(p, hexagon[i - 1], CORNER), toward(p, hexagon[(i + 1) % 6], CORNER)
        parts.append(("M" if i == 0 else "L") + f"{_pt(a)} Q{_pt(p)} {_pt(b)}")
        on_curve.append(((a[0] + 2 * p[0] + b[0]) / 4, (a[1] + 2 * p[1] + b[1]) / 4))  # the curve's midpoint
    outline = " ".join(parts) + " Z"

    centre_top, centre_mid = (cx, top + EDGE), (cx, top + 2 * EDGE)
    left_mid, right_mid = (left, top + 1.5 * EDGE), (right, top + 1.5 * EDGE)
    # inner edges end on the rounded corners, not at the sharp vertices
    edges = (
        f"M{_pt(on_curve[5])} L{_pt(centre_top)} L{_pt(on_curve[1])} "
        f"M{_pt(centre_top)} L{_pt(on_curve[3])} "
        f"M{_pt(left_mid)} L{_pt(centre_top)} L{_pt(right_mid)} L{_pt(centre_mid)} Z"
    )
    ry = DOT_RX / math.sqrt(3)
    return (
        f'  <g id="symbol" fill="none" stroke="{color}" stroke-width="{STROKE}"'
        ' stroke-linejoin="round" stroke-linecap="round">\n'
        f'    <path id="outline" d="{outline}"/>\n'
        f'    <path id="edges" d="{edges}"/>\n'
        f'    <ellipse id="dot" cx="{_f(cx)}" cy="{_f(top + EDGE / 2)}" rx="{DOT_RX}" ry="{_f(ry)}"'
        f' fill="{color}" stroke="none"/>\n'
        "  </g>\n"
    )


def wordmark_group(
    fonts_dir: Path, color: str, ox: float = 0, oy: float = 0, scale: float = 1
) -> tuple[str, float, float]:
    """The two outlined lines; returns (group, width, height) with (ox, oy) the top-left of the cap box."""
    font = wordmark.load(fonts_dir, FONT_WEIGHT)
    cap, leading = CAP * scale, LEADING * scale
    size = cap * font["head"].unitsPerEm / font["OS/2"].sCapHeight
    tracking = TRACKING * size
    line2, width = wordmark.line(font, "CUBESAT", size, ox, oy + cap + leading, tracking)
    line1, _ = wordmark.line(font, "BUILD A", size, ox, oy + cap, tracking, justify_to=width)
    group = (
        f'  <g id="wordmark" fill="{color}">\n'
        f'    <path id="line1" d="{line1}"/>\n'
        f'    <path id="line2" d="{line2}"/>\n'
        "  </g>\n"
    )
    return group, width, cap + leading


def symbol_svg(color: str) -> str:
    return wrap("symbol", symbol_group(color), *SYMBOL_CANVAS, f"Isometric 2U cube, stroke {STROKE}.")


def wordmark_svg(fonts_dir: Path, color: str) -> str:
    group, width, height = wordmark_group(fonts_dir, color, PAD, PAD)
    construction = f"Nunito {FONT_WEIGHT}, tracking {TRACKING} em, outlined."
    return wrap("wordmark", group, width + 2 * PAD, height + 2 * PAD, construction)


def logo_svg(fonts_dir: Path, color: str) -> str:
    """The symbol on its own canvas, the wordmark centred on the cube to its right."""
    sym_w, sym_h = SYMBOL_CANVAS
    scale = 3 * EDGE * TEXT_FRACTION / (CAP + LEADING)
    group, width, height = wordmark_group(fonts_dir, color, sym_w + GAP, (sym_h - (CAP + LEADING) * scale) / 2, scale)
    canvas_w = sym_w + GAP + width + (sym_w - EDGE * math.sqrt(3)) / 2
    construction = (
        f"Horizontal lockup: symbol with the wordmark at {TEXT_FRACTION:.0%} of the cube height, gap {GAP};"
        f" Nunito {FONT_WEIGHT}, tracking {TRACKING} em, outlined."
    )
    return wrap("logo", symbol_group(color) + group, canvas_w, sym_h, construction)


@dataclass(frozen=True, slots=True)
class Asset:
    kind: str
    color: str
    name: str

    def render(self, fonts_dir: Path) -> str:
        hex_ = COLORS[self.color]
        if self.kind == "symbol":
            return symbol_svg(hex_)
        if self.kind == "wordmark":
            return wordmark_svg(fonts_dir, hex_)
        return logo_svg(fonts_dir, hex_)


def assets() -> Iterator[Asset]:
    """Every file the tool writes, in a stable order."""
    for kind in KINDS:
        for color in COLORS:
            yield Asset(kind, color, f"bac-{kind}-{color}-{VERSION}.svg")


def find_design(start: Path) -> Path | None:
    """The bac-design checkout: ``start`` itself or a sibling ``bac-design`` of any ancestor."""
    for folder in (start, *start.parents):
        if (folder / "guides").is_dir() and (folder / "assets").is_dir():
            return folder
        sibling = folder / "bac-design"
        if (sibling / "guides").is_dir() and (sibling / "assets").is_dir():
            return sibling
    return None
