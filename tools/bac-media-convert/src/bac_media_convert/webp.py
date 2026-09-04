# SPDX-License-Identifier: MIT
"""Square WebP export on Pillow – the helper other tools reuse.

The shop wants product images square, no larger than 3840 px on a side,
as WebP at quality 90 with the slowest (best) encoder method. This module
is the one place that knows those numbers; ``bac-shop-product-cropper``
will import :func:`export_webp` for its size-targeted export.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

from bac_common.errors import BacError

__all__ = [
    "DEFAULT_MAX_SIDE",
    "DEFAULT_QUALITY",
    "DEFAULT_METHOD",
    "load_oriented",
    "square_crop",
    "fit_max_side",
    "export_webp",
    "convert_square_webp",
]

DEFAULT_MAX_SIDE = 3840
DEFAULT_QUALITY = 90
DEFAULT_METHOD = 6


def load_oriented(path: Path) -> Image.Image:
    """Open an image and apply its EXIF orientation, so a phone photo is cropped the way it is displayed."""
    try:
        with Image.open(path) as raw:
            raw.load()
            oriented = ImageOps.exif_transpose(raw)
            return oriented if oriented is not None else raw.copy()
    except Image.DecompressionBombError as exc:
        raise BacError(f"Image is too large to open safely: {path.name}", str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise BacError(f"Cannot read image {path.name}", str(exc)) from exc


def square_crop(image: Image.Image) -> Image.Image:
    """Centre crop to ``min(w, h)`` square. Already-square images are returned unchanged."""
    width, height = image.size
    side = min(width, height)
    if width == height:
        return image
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))


def fit_max_side(image: Image.Image, max_side: int) -> Image.Image:
    """Downscale so the longer side is at most ``max_side``; never upscale."""
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image
    scale = max_side / longest
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def export_webp(
    image: Image.Image,
    target: Path,
    *,
    quality: int = DEFAULT_QUALITY,
    method: int = DEFAULT_METHOD,
) -> int:
    """Write ``image`` as WebP and return the file size in bytes.

    Palette and greyscale images are converted; transparency is kept. The
    ICC colour profile travels with the pixels (a Display P3 phone photo
    would otherwise look washed out); camera EXIF does not.
    """
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        out = image.convert("RGBA")
    elif image.mode != "RGB":
        out = image.convert("RGB")
    else:
        out = image
    target.parent.mkdir(parents=True, exist_ok=True)
    options: dict[str, object] = {"quality": quality, "method": method}
    profile = image.info.get("icc_profile")
    if profile:
        options["icc_profile"] = profile
    try:
        out.save(target, format="WEBP", **options)
    except (OSError, ValueError) as exc:
        raise BacError(f"Cannot write {target.name}", str(exc)) from exc
    return target.stat().st_size


def convert_square_webp(
    source: Path,
    target: Path,
    *,
    max_side: int = DEFAULT_MAX_SIDE,
    quality: int = DEFAULT_QUALITY,
    method: int = DEFAULT_METHOD,
) -> tuple[int, int, int]:
    """Centre-crop, downscale and export. Returns ``(width, height, bytes)`` of the result."""
    image = fit_max_side(square_crop(load_oriented(source)), max_side)
    size = export_webp(image, target, quality=quality, method=method)
    return image.width, image.height, size
