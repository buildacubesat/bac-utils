# SPDX-License-Identifier: MIT
"""QR codes for short URLs: SVG, PNG or WebP, optionally inverted or with a transparent background."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

FORMATS = ("svg", "png", "webp")
LEVELS = ("L", "M", "Q", "H")

__all__ = ["FORMATS", "LEVELS", "QrOptions", "qr_path", "write_qr"]


@dataclass(frozen=True, slots=True)
class QrOptions:
    fmt: str = "svg"
    invert: bool = False
    alpha: bool = False
    ec: str = "M"
    size: int = 1000
    output: Path | None = None


def qr_path(slug: str, options: QrOptions) -> Path:
    """``<output or ~>/bac-page-<slug>.<fmt>``."""
    return (options.output or Path.home()).expanduser() / f"bac-page-{slug}.{options.fmt}"


def write_qr(url: str, slug: str, options: QrOptions) -> Path:
    import qrcode
    import qrcode.constants

    levels = {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H,
    }
    dest = qr_path(slug, options)
    dest.parent.mkdir(parents=True, exist_ok=True)
    code = qrcode.QRCode(error_correction=levels[options.ec], box_size=10, border=4)
    code.add_data(url)
    code.make(fit=True)

    if options.fmt == "svg":
        import qrcode.image.svg

        image = code.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        svg = image.to_string().decode()
        svg = re.sub(r'(<svg[^>]*)(width="[^"]*")', f'\\1width="{options.size}"', svg)
        svg = re.sub(r'(<svg[^>]*)(height="[^"]*")', f'\\1height="{options.size}"', svg)
        if options.invert:
            svg = svg.replace('fill="#000000"', 'fill="TEMP"')
            svg = svg.replace('fill="#ffffff"', 'fill="#000000"')
            svg = svg.replace('fill="TEMP"', 'fill="#ffffff"')
        if options.alpha:
            svg = re.sub(r"<rect[^/]*/>", "", svg, count=1)
        dest.write_text(svg, encoding="utf-8")
        return dest

    from PIL import Image

    fg = (255, 255, 255) if options.invert else (0, 0, 0)
    bg = (0, 0, 0) if options.invert else (255, 255, 255)
    image = code.make_image(fill_color=fg, back_color=bg).convert("RGB")
    image = image.resize((options.size, options.size), Image.NEAREST)
    if options.alpha:
        # the background is pure black or pure white, so the gray level tells the two apart
        gray = image.convert("L")
        mask = gray.point(lambda v: 0 if v == bg[0] else 255)
        image = image.convert("RGBA")
        image.putalpha(mask)
    image.save(dest, **({"format": "WEBP"} if options.fmt == "webp" else {}))
    return dest
