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

from . import rocinante, wordmark

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

# Tagline – under the wordmark in the logo-with-tagline, set like the Rocinante subtitle
TAGLINE = "SPACE FOR EVERYONE"
TAGLINE_FILL = 0.72  # the text takes this share of the wordmark's width; the rules fill the rest
TAGLINE_TRACKING = 2 / 7  # em, as the Rocinante subtitle
TAGLINE_DROP = 2.34  # wordmark baseline to tagline baseline, in tagline sizes (as Rocinante)

# Badge – a filled, rounded hexagon behind the mark for stickers, avatars and busy backgrounds
BADGE_OFFSET = 60  # from the cube's hexagon outwards
BADGE_CORNER = 60  # rounding, measured from the vertex
BADGE_MERGE_FILLET = 30  # the concave corners where the logo badge's two shapes meet
BADGE_HAIRLINE = 2
BADGES = {  # fill, mark, hairline (--border-strong light / dark)
    "light": ("#ffffff", "#000000", "#D0D0D0"),
    "dark": ("#1F1E1D", "#ffffff", "#3F3E3D"),
}

COLORS = {"black": "#000000", "white": "#ffffff", "currentcolor": "currentColor"}
KINDS = ("symbol", "wordmark", "logo", "logo-tagline")


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _pt(p: tuple[float, float]) -> str:
    return f"{_f(p[0])} {_f(p[1])}"


def wrap(
    kind: str,
    body: str,
    width: float,
    height: float,
    construction: str,
    brand: str = "Build a CubeSat",
    version: str = VERSION,
) -> str:
    """The document around a mark: viewBox only, accessible title and desc, Dublin Core metadata."""
    title = f"{brand} {kind.replace('-', ' ').title()} {version}"
    rights = f"Copyright {YEAR} nihil.space GmbH"
    who = "Build a CubeSat (BAC)" if brand == "Build a CubeSat" else f"{brand} (BAC flight software)"
    desc = (
        f"{who} brand {kind.replace('-', ' ')}, version {version[1:]}. {construction} {rights}. "
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


Point = tuple[float, float]


def _toward(p: Point, q: Point, dist: float) -> Point:
    dx, dy = q[0] - p[0], q[1] - p[1]
    n = math.hypot(dx, dy)
    return (p[0] + dx / n * dist, p[1] + dy / n * dist)


def rounded(polygon: list[Point], corner: float, concave: float | None = None) -> tuple[str, list[Point]]:
    """A closed path through ``polygon`` with every corner rounded ``corner`` from the vertex.

    Concave corners (the polygon is clockwise, y grows downwards) take ``concave`` instead when
    given. Returns the path data and, per vertex, the point on the curve where a line meeting the
    corner should end.
    """
    parts, on_curve = [], []
    n = len(polygon)
    for i, p in enumerate(polygon):
        prev, nxt = polygon[i - 1], polygon[(i + 1) % n]
        cross = (p[0] - prev[0]) * (nxt[1] - p[1]) - (p[1] - prev[1]) * (nxt[0] - p[0])
        r = concave if concave is not None and cross < 0 else corner
        # never past the middle of an edge, or two roundings would cross
        c = min(r, math.dist(p, prev) / 2, math.dist(p, nxt) / 2)
        a, b = _toward(p, prev, c), _toward(p, nxt, c)
        parts.append(("M" if i == 0 else "L") + f"{_pt(a)} Q{_pt(p)} {_pt(b)}")
        on_curve.append(((a[0] + 2 * p[0] + b[0]) / 4, (a[1] + 2 * p[1] + b[1]) / 4))  # the curve's midpoint
    return " ".join(parts) + " Z", on_curve


def cube_hexagon(cx: float, top: float, grow: float = 0) -> list[Point]:
    """The cube's silhouette, clockwise from the top vertex, offset outwards by ``grow``."""
    half = EDGE * math.sqrt(3) / 2 + grow
    dy = grow / math.cos(math.radians(30))  # the diagonal edges move out by grow, the vertices by this
    return [
        (cx, top - dy),
        (cx + half, top + EDGE / 2 - dy / 2),
        (cx + half, top + 2.5 * EDGE + dy / 2),
        (cx, top + 3 * EDGE + dy),
        (cx - half, top + 2.5 * EDGE + dy / 2),
        (cx - half, top + EDGE / 2 - dy / 2),
    ]


def symbol_group(color: str, ox: float = 0, oy: float = 0) -> str:
    """The cube as a stroked group; (ox, oy) moves its canvas for use inside the logo."""
    half = EDGE * math.sqrt(3) / 2
    width, height = SYMBOL_CANVAS
    cx, top = ox + width / 2, oy + (height - 3 * EDGE) / 2
    left, right = cx - half, cx + half
    outline, on_curve = rounded(cube_hexagon(cx, top), CORNER)

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


def logo_parts(fonts_dir: Path, color: str, tagline: bool = False) -> tuple[str, float, float, str]:
    """Symbol and wordmark (and the tagline) on the logo canvas: (body, width, height, construction)."""
    sym_w, sym_h = SYMBOL_CANVAS
    scale = 3 * EDGE * TEXT_FRACTION / (CAP + LEADING)
    block = (CAP + LEADING) * scale
    group, width, _ = wordmark_group(fonts_dir, color, sym_w + GAP, 0, scale)
    tag_size = 0.0
    if tagline:
        from fontTools.ttLib import TTFont

        mono = TTFont(fonts_dir / wordmark.MONO_FONT_FILE)
        _, w_at_1 = wordmark.line(mono, TAGLINE, 1, 0, 0, TAGLINE_TRACKING)  # width per unit of size
        tag_size = TAGLINE_FILL * width / w_at_1
    extra = TAGLINE_DROP * tag_size  # the tagline's baseline drop under the wordmark
    top = (sym_h - block - extra) / 2
    group, width, _ = wordmark_group(fonts_dir, color, sym_w + GAP, top, scale)
    body = symbol_group(color) + group
    construction = (
        f"Horizontal lockup: symbol with the wordmark at {TEXT_FRACTION:.0%} of the cube height, gap {GAP};"
        f" Nunito {FONT_WEIGHT}, tracking {TRACKING} em, outlined."
    )
    if tagline:
        frag, _ = wordmark.subtitle(
            mono, TAGLINE, tag_size, TAGLINE_TRACKING, sym_w + GAP + width / 2, top + block + extra, width, color
        )
        body += f'  <g id="tagline">\n{frag}  </g>\n'
        construction += (
            f' Tagline "{TAGLINE}" in IBM Plex Mono, tracking {TAGLINE_TRACKING:.3f} em, sized to {TAGLINE_FILL:.0%}'
            f" of the wordmark's width and centred under it, rules filling the rest, outlined."
        )
    canvas_w = sym_w + GAP + width + (sym_w - EDGE * math.sqrt(3)) / 2
    return body, canvas_w, sym_h, construction


def logo_svg(fonts_dir: Path, color: str, tagline: bool = False) -> str:
    """The symbol on its own canvas, the wordmark centred on the cube to its right."""
    body, w, h, construction = logo_parts(fonts_dir, color, tagline)
    return wrap("logo-tagline" if tagline else "logo", body, w, h, construction)


def badge_path(cx: float, top: float, text_box: tuple[float, float, float, float] | None = None) -> str:
    """The badge: the cube's hexagon grown by BADGE_OFFSET, corners rounded.

    With ``text_box`` (x, y, width, height of the wordmark) the hexagon is merged with a rectangle
    grown by the same offset around the text and reaching left to the cube's centre line, so the
    two meet on the hexagon's diagonals; the merged outline is rounded, the two concave corners
    where they meet with a smaller fillet.
    """
    hexagon = cube_hexagon(cx, top, BADGE_OFFSET)
    if text_box is None:
        return rounded(hexagon, BADGE_CORNER)[0]
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union

    x, y, w, h = text_box
    o = BADGE_OFFSET
    merged = unary_union([Polygon(hexagon), box(cx, y - o, x + w + o, y + h + o)])
    outline = [(px, py) for px, py in merged.exterior.coords[:-1]]
    if merged.exterior.is_ccw:  # keep the clockwise order the hexagon has (y grows downwards)
        outline.reverse()
    return rounded(outline, BADGE_CORNER, BADGE_MERGE_FILLET)[0]


def badge_svg(fonts_dir: Path, variant: str, logo: bool) -> str:
    """The symbol or the logo on a filled badge; the canvas grows by the badge's overhang."""
    fill, mark, hairline = BADGES[variant]
    sym_w, sym_h = SYMBOL_CANVAS
    cx, top = sym_w / 2, (sym_h - 3 * EDGE) / 2
    dy = BADGE_OFFSET / math.cos(math.radians(30))
    over_y = dy + BADGE_HAIRLINE - top  # the badge reaches beyond the symbol canvas vertically
    half = EDGE * math.sqrt(3) / 2
    over_x = BADGE_OFFSET + BADGE_HAIRLINE - (sym_w / 2 - half)
    pad = max(over_x, over_y, 0) + 10
    if logo:
        body, w, h, construction = logo_parts(fonts_dir, mark)
        # the right side clears the wordmark by the same offset as the badge clears the cube
        scale = 3 * EDGE * TEXT_FRACTION / (CAP + LEADING)
        block = (CAP + LEADING) * scale
        text_w = w - sym_w - GAP - (sym_w - 2 * half) / 2
        text_box = (pad + sym_w + GAP, pad + (sym_h - block) / 2, text_w, block)
        margin = pad + sym_w / 2 - half - BADGE_OFFSET  # canvas edge to badge, as on the left
        canvas_w = text_box[0] + text_w + BADGE_OFFSET + margin
        kind = "logo-badge"
    else:
        body, w, h, construction = symbol_group(mark), sym_w, sym_h, f"Isometric 2U cube, stroke {STROKE}."
        text_box = None
        canvas_w = w + 2 * pad
        kind = "symbol-badge"
    shape = badge_path(cx + pad, top + pad, text_box)
    badge = f'  <path id="badge" d="{shape}" fill="{fill}" stroke="{hairline}" stroke-width="{BADGE_HAIRLINE}"/>\n'
    body = badge + f'  <g transform="translate({_f(pad)} {_f(pad)})">\n' + body + "  </g>\n"
    construction += (
        f" On a {variant} badge: the cube's hexagon grown by {BADGE_OFFSET}"
        f"{' merged with a rectangle grown by the same offset around the wordmark' if logo else ''},"
        f"{f' the merge filleted {BADGE_MERGE_FILLET},' if logo else ''}"
        f" corners rounded {BADGE_CORNER},"
        f" hairline {BADGE_HAIRLINE}."
    )
    return wrap(kind, body, canvas_w, h + 2 * pad, construction)


@dataclass(frozen=True, slots=True)
class Asset:
    kind: str
    color: str
    name: str

    def render(self, fonts_dir: Path) -> str:
        if self.kind.startswith("rocinante-"):
            part = self.kind.split("-", 1)[1]
            if part == "symbol":
                return rocinante.symbol_svg(self.color, wrap)
            if part == "wordmark":
                return rocinante.wordmark_svg(fonts_dir, self.color, wrap)
            return rocinante.logo_svg(fonts_dir, self.color, wrap)
        if self.kind.endswith("-badge"):
            return badge_svg(fonts_dir, self.color, logo=self.kind == "logo-badge")
        hex_ = COLORS[self.color]
        if self.kind == "symbol":
            return symbol_svg(hex_)
        if self.kind == "wordmark":
            return wordmark_svg(fonts_dir, hex_)
        return logo_svg(fonts_dir, hex_, tagline=self.kind == "logo-tagline")


def assets() -> Iterator[Asset]:
    """Every file the tool writes, in a stable order."""
    for kind in KINDS:
        for color in COLORS:
            yield Asset(kind, color, f"bac-{kind}-{color}-{VERSION}.svg")
    for kind in ("symbol-badge", "logo-badge"):
        for variant in BADGES:
            yield Asset(kind, variant, f"bac-{kind}-{variant}-{VERSION}.svg")
    for part in ("symbol", "wordmark", "logo"):
        for variant in (*COLORS, "colour"):
            yield Asset(f"rocinante-{part}", variant, f"rocinante-{part}-{variant}-{rocinante.VERSION}.svg")


def find_design(start: Path) -> Path | None:
    """The bac-design checkout: ``start`` itself or a sibling ``bac-design`` of any ancestor."""
    for folder in (start, *start.parents):
        if (folder / "guides").is_dir() and (folder / "assets").is_dir():
            return folder
        sibling = folder / "bac-design"
        if (sibling / "guides").is_dir() and (sibling / "assets").is_dir():
            return sibling
    return None
