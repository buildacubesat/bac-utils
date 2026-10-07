# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest
from bac_store_product_cropper.crop import MIN_CROP, CropState, output_size, preview_size, wheel_steps
from bac_store_product_cropper.export import ExportOptions, export_sized, prepare, save_crop
from PIL import Image


def test_initial_crop_is_the_largest_centred_rectangle():
    wide = CropState.initial(800, 400, 1.0)
    assert (wide.cw, wide.ch, wide.cx, wide.cy) == (400, 400, 400, 200)
    assert wide.box() == (200, 0, 600, 400)
    tall = CropState.initial(300, 600, 1.0)
    assert tall.box() == (0, 150, 300, 450)
    four_three = CropState.initial(800, 400, 4 / 3)
    assert four_three.cw == pytest.approx(533.33, abs=0.01)
    assert four_three.ch == pytest.approx(400)
    assert wide.zoom_percent == 100


def test_bad_initial_values():
    with pytest.raises(ValueError):
        CropState.initial(0, 10, 1.0)
    with pytest.raises(ValueError):
        CropState.initial(10, 10, 0)


def test_pan_is_clamped_to_the_image():
    s = CropState.initial(800, 400, 1.0)
    s.pan(-10_000, 0, 900)  # drag far left → crop moves right to the edge
    assert s.box() == (400, 0, 800, 400)
    s.pan(10_000, 10_000, 900)
    assert s.box() == (0, 0, 400, 400)


def test_zoom_in_keeps_the_point_under_the_cursor_and_respects_the_minimum():
    s = CropState.initial(2000, 2000, 1.0)
    s.zoom(1)  # 5 % in, about the centre
    assert s.cw == pytest.approx(1900)
    assert (s.cx, s.cy) == (1000, 1000)
    assert s.zoom_percent == 105
    s.reset()
    s.zoom(1, 0.5, 0.5)  # cursor at the bottom-right corner: that corner stays
    assert s.cx + s.cw / 2 == pytest.approx(2000)
    assert s.cy + s.ch / 2 == pytest.approx(2000)
    s.zoom(500)
    assert s.cw == MIN_CROP
    s.zoom(-500)  # out again, never past the image
    assert s.cw == 2000
    s.zoom(0)
    assert s.cw == 2000


def test_minimum_crop_on_a_tiny_image():
    s = CropState.initial(100, 80, 1.0)
    s.zoom(50)
    assert s.cw == 80  # the image is smaller than MIN_CROP; the floor is the image
    assert s.box() == (10, 0, 90, 80)


def test_preview_size_keeps_the_aspect():
    assert preview_size(1.0, 900) == (900, 900)
    assert preview_size(2.0, 900) == (900, 450)
    assert preview_size(0.5, 900) == (450, 900)
    assert preview_size(4 / 3, 900) == (900, 675)


def test_output_size_never_upscales():
    assert output_size((0, 0, 400, 300), 3840) == (400, 300)
    assert output_size((0, 0, 4000, 3000), 2000) == (2000, 1500)
    assert output_size((0, 0, 4000, 1), 2000) == (2000, 1)


def test_wheel_steps():
    assert wheel_steps(120, None) == 1
    assert wheel_steps(-240, None) == -2
    assert wheel_steps(30, None) == 1  # macOS small deltas still count as one notch
    assert wheel_steps(0, 4) == 1
    assert wheel_steps(None, 5) == -1
    assert wheel_steps(None, None) == 0


def test_options_validate():
    ExportOptions().validate()
    with pytest.raises(ValueError, match="start quality must not be below"):
        ExportOptions(start_quality=5, min_quality=10).validate()
    with pytest.raises(ValueError, match="aspect"):
        ExportOptions(aspect=0).validate()
    with pytest.raises(ValueError, match="between 1 and 100"):
        ExportOptions(start_quality=101).validate()
    with pytest.raises(ValueError, match="negative"):
        ExportOptions(target_kb=-1).validate()
    with pytest.raises(ValueError, match="method"):
        ExportOptions(method=7).validate()


class RecordingWriter:
    """Pretends each quality step saves ``sizes[q]`` bytes."""

    def __init__(self, sizes: dict[int, int]):
        self.sizes, self.calls = sizes, []

    def __call__(self, image, target, *, quality, method):
        self.calls.append(quality)
        target.write_bytes(b"x" * self.sizes[quality])
        return self.sizes[quality]


def test_export_sized_steps_down_until_under_target(tmp_path: Path):
    image = Image.new("RGB", (10, 10))
    writer = RecordingWriter({30: 300 * 1024, 25: 250 * 1024, 20: 150 * 1024, 15: 1, 10: 1})
    size, q = export_sized(image, tmp_path / "a.webp", ExportOptions(target_kb=200), writer=writer)
    assert (size, q) == (150 * 1024, 20)
    assert writer.calls == [30, 25, 20]
    assert (tmp_path / "a.webp").stat().st_size == 150 * 1024


def test_export_sized_floor_is_tried_and_kept(tmp_path: Path):
    image = Image.new("RGB", (10, 10))
    writer = RecordingWriter({28: 900, 23: 800, 18: 700, 13: 600, 10: 500})
    size, q = export_sized(image, tmp_path / "a.webp", ExportOptions(target_kb=0, start_quality=28), writer=writer)
    assert (size, q) == (900, 28) and writer.calls == [28]  # no target: one encode
    writer.calls.clear()
    opts = ExportOptions(target_kb=0.1, start_quality=28, min_quality=10)  # type: ignore[arg-type]
    size, q = export_sized(image, tmp_path / "a.webp", opts, writer=writer)
    assert writer.calls == [28, 23, 18, 13, 10]
    assert (size, q) == (500, 10)


def test_prepare_and_save_crop_with_the_real_writer(tmp_path: Path):
    image = Image.new("RGB", (4000, 2000), (10, 200, 30))
    out = prepare(image, (1000, 0, 3000, 2000), 1000)
    assert out.size == (1000, 1000)
    saved = save_crop(image, (1000, 0, 3000, 2000), tmp_path / "out" / "p.webp", ExportOptions(max_width=1000))
    assert (saved.width, saved.height) == (1000, 1000)
    assert saved.size == (tmp_path / "out" / "p.webp").stat().st_size
    assert saved.kb < 200
    with Image.open(tmp_path / "out" / "p.webp") as back:
        assert back.format == "WEBP" and back.size == (1000, 1000)
