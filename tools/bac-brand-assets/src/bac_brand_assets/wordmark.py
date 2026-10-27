# SPDX-License-Identifier: MIT
"""Setting the wordmark in Nunito and outlining it to SVG path data."""

from __future__ import annotations

from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

FONT_FILE = "Nunito[wght].ttf"


def load(fonts_dir: Path, weight: float) -> TTFont:
    """The variable Nunito from the bac-design checkout, instanced at ``weight``."""
    return instantiateVariableFont(TTFont(fonts_dir / FONT_FILE), {"wght": weight})


def line(
    font: TTFont, text: str, size: float, x: float, y: float, tracking: float = 0, justify_to: float | None = None
) -> tuple[str, float]:
    """Outline ``text`` with its baseline at ``y``; returns (path data, advance width).

    ``tracking`` is added after every glyph (canvas units); ``justify_to`` widens the
    spaces so the line ends at that width.
    """
    glyphs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    scale = size / font["head"].unitsPerEm
    names = [cmap[ord(c)] for c in text]
    advances = [hmtx[n][0] * scale + tracking for n in names]
    width = sum(advances) - tracking
    gap = 0.0
    if justify_to is not None and " " in text:
        gap = (justify_to - width) / text.count(" ")
    pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    cx = x
    for char, name, advance in zip(text, names, advances, strict=True):
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, cx, y)))
        cx += advance + (gap if char == " " else 0)
    return pen.getCommands(), justify_to if justify_to is not None else width
