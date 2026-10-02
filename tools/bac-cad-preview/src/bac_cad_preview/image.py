# SPDX-License-Identifier: MIT
"""Output framing: the crop → pad → square → resize step of bac-kicad-generate-artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

OUTPUT_SIZE = 720  # square, px
PAD_FRAC = 0.10  # padding per side, relative to the content bbox


@dataclass
class Framed:
    image: Image.Image  # RGBA, OUTPUT_SIZE square
    scale: float  # output px per render px
    offset: tuple[float, float]  # render px → output px: out = (render - offset) * scale


def crop_pad_square_resize_rgba(img: Image.Image, target_size: int = OUTPUT_SIZE, pad_frac: float = PAD_FRAC) -> Framed:
    """Same geometry as the artifacts tool; also returns the mapping from render to output pixels."""
    img = img.convert("RGBA")
    bbox = img.getbbox()
    if not bbox:
        raise ValueError("Image is empty (fully transparent)")
    left, upper, right, lower = bbox
    width = right - left
    height = lower - upper
    pad_x = int(width * pad_frac)
    pad_y = int(height * pad_frac)
    padded_box = (
        max(0, left - pad_x),
        max(0, upper - pad_y),
        min(img.width, right + pad_x),
        min(img.height, lower + pad_y),
    )
    img = img.crop(padded_box)
    new_size = max(img.width, img.height)
    square = Image.new("RGBA", (new_size, new_size), (0, 0, 0, 0))
    off = ((new_size - img.width) // 2, (new_size - img.height) // 2)
    square.paste(img, off)
    scale = target_size / new_size
    origin = (padded_box[0] - off[0], padded_box[1] - off[1])
    return Framed(square.resize((target_size, target_size), Image.LANCZOS), scale, origin)


def write_webp(img: Image.Image, path: Path) -> int:
    """Lossless WebP (as cwebp -z 9 produced); returns the file size in bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    img.save(tmp, format="WEBP", lossless=True, quality=100, method=6)
    tmp.replace(path)
    return path.stat().st_size
