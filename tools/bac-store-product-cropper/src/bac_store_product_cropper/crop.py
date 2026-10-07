# SPDX-License-Identifier: MIT
"""The crop rectangle and its arithmetic – no Tk in here, so it is testable.

A :class:`CropState` is a rectangle of fixed aspect ratio (width over
height) inside an image, described by its centre and width in image
pixels. Panning moves the centre, zooming scales the width about a point,
and :meth:`CropState.clamp` keeps the rectangle inside the image and above
a minimum size. :func:`preview_size` gives the preview canvas the same
aspect ratio as the crop, so the picture on screen is what gets exported –
0.1.0 drew every crop into a square and stretched everything but 1:1.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["MIN_CROP", "ZOOM_STEP", "CropState", "preview_size", "output_size", "wheel_steps"]

MIN_CROP = 256
"""Smallest crop width in image pixels (or the image's own width when that is smaller)."""
ZOOM_STEP = 0.05
"""One wheel notch scales the crop by 5 %."""


@dataclass(slots=True)
class CropState:
    width: int
    height: int
    aspect: float
    cx: float = 0.0
    cy: float = 0.0
    cw: float = 0.0
    cw0: float = 0.0
    """The initial (largest) crop width, the reference for the zoom percentage."""

    @classmethod
    def initial(cls, width: int, height: int, aspect: float) -> CropState:
        if width < 1 or height < 1:
            raise ValueError("image must have a size")
        if aspect <= 0:
            raise ValueError("aspect must be positive")
        state = cls(width, height, float(aspect))
        state.reset()
        return state

    # -- derived -----------------------------------------------------------------

    @property
    def ch(self) -> float:
        return self.cw / self.aspect

    @property
    def zoom_percent(self) -> int:
        return max(1, round(self.cw0 / self.cw * 100)) if self.cw else 100

    @property
    def max_width(self) -> float:
        """The widest crop of this aspect that fits the image."""
        return min(float(self.width), self.height * self.aspect)

    def box(self) -> tuple[int, int, int, int]:
        """Integer ``(left, top, right, bottom)`` for ``Image.crop``, always inside the image."""
        half_w, half_h = self.cw / 2, self.ch / 2
        left = max(0, min(self.width - 1, round(self.cx - half_w)))
        top = max(0, min(self.height - 1, round(self.cy - half_h)))
        right = max(left + 1, min(self.width, round(self.cx + half_w)))
        bottom = max(top + 1, min(self.height, round(self.cy + half_h)))
        return left, top, right, bottom

    # -- moves -------------------------------------------------------------------

    def reset(self) -> None:
        """The largest centred crop."""
        self.cw = self.max_width
        self.cw0 = self.cw
        self.cx, self.cy = self.width / 2, self.height / 2

    def clamp(self) -> None:
        self.cw = max(min(MIN_CROP, self.max_width), min(self.cw, self.max_width))
        half_w, half_h = self.cw / 2, self.ch / 2
        self.cx = max(half_w, min(self.width - half_w, self.cx))
        self.cy = max(half_h, min(self.height - half_h, self.cy))

    def pan(self, dx_px: float, dy_px: float, preview_width: int) -> None:
        """Move by a preview-pixel delta: the crop follows the dragged picture."""
        scale = self.cw / preview_width
        self.cx -= dx_px * scale
        self.cy -= dy_px * scale
        self.clamp()

    def zoom(self, steps: int, u: float = 0.0, v: float = 0.0) -> None:
        """``steps`` > 0 zooms in. ``(u, v)`` is the cursor as a fraction of the preview from its centre
        (−0.5 … 0.5), so the point under the cursor stays put."""
        if steps == 0:
            return
        factor = ((1 - ZOOM_STEP) if steps > 0 else (1 + ZOOM_STEP)) ** abs(steps)
        old_w, old_h = self.cw, self.ch
        self.cw *= factor
        self.cx += u * (old_w - self.cw)
        self.cy += v * (old_h - self.ch)
        self.clamp()


def preview_size(aspect: float, max_px: int) -> tuple[int, int]:
    """The largest ``(width, height)`` of ratio ``aspect`` inside a ``max_px`` square."""
    if aspect >= 1:
        return max_px, max(1, round(max_px / aspect))
    return max(1, round(max_px * aspect)), max_px


def output_size(box: tuple[int, int, int, int], max_width: int) -> tuple[int, int]:
    """The exported size: the crop downscaled so its width is at most ``max_width``; never upscaled."""
    width, height = box[2] - box[0], box[3] - box[1]
    if width <= max_width:
        return width, height
    scale = max_width / width
    return max_width, max(1, round(height * scale))


def wheel_steps(delta: int | float | None, num: int | None) -> int:
    """Normalise a Tk wheel event: ``delta`` (Windows/macOS, ±120 per notch) or ``num`` (X11 buttons 4/5)."""
    if delta:
        return int(delta / 120) or (1 if delta > 0 else -1)
    if num == 4:
        return 1
    if num == 5:
        return -1
    return 0
