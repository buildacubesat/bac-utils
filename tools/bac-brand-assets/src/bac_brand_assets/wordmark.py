# SPDX-License-Identifier: MIT
"""Setting the wordmark in Nunito and outlining it to SVG path data."""

from __future__ import annotations

from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

FONT_FILE = "Nunito[wght].ttf"
MONO_FONT_FILE = "IBMPlexMono-Regular.ttf"


def load(fonts_dir: Path, weight: float, file: str = FONT_FILE) -> TTFont:
    """A variable font from the bac-design checkout, instanced at ``weight`` (other axes at default)."""
    font = TTFont(fonts_dir / file)
    axes = {a.axisTag: a.defaultValue for a in font["fvar"].axes}
    axes["wght"] = weight
    return instantiateVariableFont(font, axes)


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


def subtitle(
    font: TTFont, text: str, size: float, tracking_em: float, cx: float, baseline: float, fill_width: float, color: str
) -> tuple[str, float]:
    """``text`` centred on ``cx`` with a rule either side filling out to ``fill_width``.

    Returns (SVG fragment, width). The rules sit at half the cap height, ``gap`` (the tracking)
    away from the text; when the text is wider than ``fill_width`` there are no rules.
    """
    d, w = line(font, text, size, 0, 0, tracking_em * size)
    cap = size * font["OS/2"].sCapHeight / font["head"].unitsPerEm
    x = cx - w / 2
    gap = tracking_em * size
    rule = (fill_width - w) / 2 - gap
    f = lambda v: f"{v:.2f}".rstrip("0").rstrip(".")  # noqa: E731
    out = f'    <path id="subtitle" fill="{color}" transform="translate({f(x)} {f(baseline)})" d="{d}"/>\n'
    if rule > gap:
        y = baseline - cap / 2
        rules = f"M{f(x - gap - rule)} {f(y)} H{f(x - gap)} M{f(x + w + gap)} {f(y)} H{f(x + w + gap + rule)}"
        out += f'    <path id="rules" d="{rules}" fill="none" stroke="{color}" stroke-width="{f(size * 0.086)}"/>\n'
    return out, max(w, fill_width)
