# SPDX-License-Identifier: MIT
"""Image fixtures for the bac-media-convert tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def make_image(path: Path, size: tuple[int, int], mode: str = "RGB", color=(200, 30, 30)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path)
    return path
