# SPDX-License-Identifier: MIT
"""PNG and WebP renderings of the marks, for the places that cannot take an SVG.

Two sizes per mark, named by the longest side; transparent background. The currentColor
files are not rendered – they have no colour of their own.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import dataclass

SIZES = (512, 2048)
FORMATS = ("png", "webp")


@dataclass(frozen=True, slots=True)
class Raster:
    svg_name: str
    size: int
    fmt: str

    @property
    def name(self) -> str:
        return f"{self.fmt}/{self.svg_name[:-4]}-{self.size}.{self.fmt}"


def rasters(svg_names: list[str]) -> Iterator[Raster]:
    for svg_name in svg_names:
        if "currentcolor" in svg_name:
            continue
        for size in SIZES:
            for fmt in FORMATS:
                yield Raster(svg_name, size, fmt)


def render(svg: str, raster: Raster) -> bytes:
    """The SVG text rendered with the longest side at ``raster.size`` pixels."""
    import re

    import cairosvg
    from PIL import Image

    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    assert vb is not None
    w, h = float(vb.group(1)), float(vb.group(2))
    kw = {"output_width": raster.size} if w >= h else {"output_height": raster.size}
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), **kw)
    if raster.fmt == "png":
        return png
    out = io.BytesIO()
    Image.open(io.BytesIO(png)).save(out, format="WEBP", lossless=True, quality=100, method=4)
    return out.getvalue()
