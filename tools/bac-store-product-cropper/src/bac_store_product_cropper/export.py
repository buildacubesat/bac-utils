# SPDX-License-Identifier: MIT
"""Crop, downscale and export – the functions a later store artifact tool can import.

The WebP writer is :func:`bac_media_convert.webp.export_webp`; this module
adds the size target: encode at a starting quality and step down until the
file is small enough or the floor is reached.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bac_media_convert.webp import DEFAULT_METHOD, export_webp
from PIL import Image

from .crop import output_size

__all__ = ["ExportOptions", "Saved", "prepare", "export_sized", "save_crop"]

Writer = Callable[..., int]
"""``writer(image, target, quality=, method=) -> bytes written`` – ``export_webp``'s shape."""


@dataclass(frozen=True, slots=True)
class ExportOptions:
    aspect: float = 1.0
    """Crop width over height."""
    max_width: int = 3840
    target_kb: int = 200
    """0 disables the size target: one encode at ``start_quality``."""
    start_quality: int = 30
    min_quality: int = 10
    step: int = 5
    method: int = DEFAULT_METHOD

    def validate(self) -> None:
        if not self.aspect > 0:
            raise ValueError("aspect must be positive")
        if self.max_width < 1:
            raise ValueError("max width must be at least 1 px")
        if self.target_kb < 0:
            raise ValueError("target size cannot be negative")
        for name in ("start_quality", "min_quality"):
            value = getattr(self, name)
            if not 1 <= value <= 100:
                raise ValueError(f"{name.replace('_', ' ')} must be between 1 and 100")
        if self.start_quality < self.min_quality:
            raise ValueError("start quality must not be below the minimum quality")
        if self.step < 1:
            raise ValueError("quality step must be at least 1")
        if not 0 <= self.method <= 6:
            raise ValueError("WebP method must be between 0 and 6")


@dataclass(frozen=True, slots=True)
class Saved:
    size: int
    """Bytes on disk."""
    quality: int
    width: int
    height: int

    @property
    def kb(self) -> float:
        return self.size / 1024


def prepare(image: Image.Image, box: tuple[int, int, int, int], max_width: int) -> Image.Image:
    """Crop to ``box`` and downscale to ``max_width`` (never upscale)."""
    cropped = image.crop(box)
    size = output_size(box, max_width)
    if size != cropped.size:
        cropped = cropped.resize(size, Image.Resampling.LANCZOS)
    return cropped


def export_sized(
    image: Image.Image, target: Path, options: ExportOptions, *, writer: Writer = export_webp
) -> tuple[int, int]:
    """Write ``image`` as WebP under the size target. Returns ``(bytes, quality used)``.

    Qualities go ``start, start - step, …`` down to ``min_quality`` (the
    floor is always tried last when the steps skip it); the first file under
    ``target_kb`` wins, otherwise the smallest quality's file stays on disk.
    """
    limit = options.target_kb * 1024
    if not limit:
        quality = options.start_quality
        return writer(image, target, quality=quality, method=options.method), quality
    qualities = list(range(options.start_quality, options.min_quality, -options.step)) + [options.min_quality]
    size, quality = 0, qualities[0]
    for quality in qualities:
        size = writer(image, target, quality=quality, method=options.method)
        if size <= limit:
            break
    return size, quality


def save_crop(
    image: Image.Image,
    box: tuple[int, int, int, int],
    target: Path,
    options: ExportOptions,
    *,
    writer: Writer = export_webp,
) -> Saved:
    """Crop, downscale and export in one call; what the GUI runs on Enter."""
    out = prepare(image, box, options.max_width)
    size, quality = export_sized(out, target, options, writer=writer)
    return Saved(size, quality, out.width, out.height)
