# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest
from bac_media_convert import webp
from bac_media_convert.batch import IMAGE_EXTENSIONS, collect, mark_existing, plan
from media_testkit import make_image
from PIL import Image

from bac_common.errors import BacError, UsageError


def test_collect_lists_folders_and_takes_files_as_given(photos, tmp_path):
    files = collect([photos], IMAGE_EXTENSIONS)
    assert [f.name for f in files] == ["small.tif", "tall.png", "wide.jpg"]

    odd = tmp_path / "odd.bmp"
    make_image(odd, (10, 10))
    files = collect([photos / "wide.jpg", odd], IMAGE_EXTENSIONS)
    assert [f.name for f in files] == ["odd.bmp", "wide.jpg"]

    with pytest.raises(UsageError, match="No such file"):
        collect([tmp_path / "missing"], IMAGE_EXTENSIONS)


def test_collect_deduplicates_same_file_given_twice(photos):
    files = collect([photos / "wide.jpg", photos, Path(str(photos / "wide.jpg"))], IMAGE_EXTENSIONS)
    assert [f.name for f in files] == ["small.tif", "tall.png", "wide.jpg"]


def test_plan_detects_collisions(tmp_path):
    a_jpg, a_png = make_image(tmp_path / "a.jpg", (4, 4)), make_image(tmp_path / "a.png", (4, 4))
    with pytest.raises(UsageError) as info:
        plan([a_jpg, a_png], None, lambda p: f"{p.stem}.webp")
    assert "a.jpg and a.png → a.webp" in (info.value.detail or "")

    jobs = plan([a_jpg, a_png], tmp_path / "out", lambda p: f"{p.stem}-{p.suffix[1:]}.webp")
    assert [j.target.name for j in jobs] == ["a-jpg.webp", "a-png.webp"]
    assert all(j.target.parent == tmp_path / "out" for j in jobs)


def test_mark_existing_and_force(tmp_path):
    src = make_image(tmp_path / "a.jpg", (4, 4))
    jobs = plan([src], None, lambda p: f"{p.stem}.webp")
    (tmp_path / "a.webp").write_bytes(b"old")
    mark_existing(jobs, force=False)
    assert jobs[0].status == "skipped" and jobs[0].note == "exists"
    jobs = plan([src], None, lambda p: f"{p.stem}.webp")
    mark_existing(jobs, force=True)
    assert jobs[0].status == "pending"
    same = plan([src], None, lambda p: p.name)
    mark_existing(same, force=True)
    assert same[0].status == "skipped" and "own input" in same[0].note


def test_square_crop_and_fit():
    wide = Image.new("RGB", (600, 300))
    assert webp.square_crop(wide).size == (300, 300)
    tall = Image.new("RGB", (200, 500))
    assert webp.square_crop(tall).size == (200, 200)
    square = Image.new("RGB", (50, 50))
    assert webp.square_crop(square) is square
    assert webp.fit_max_side(Image.new("RGB", (8000, 4000)), 3840).size == (3840, 1920)
    small = Image.new("RGB", (40, 40))
    assert webp.fit_max_side(small, 3840) is small


def test_export_webp_keeps_alpha_and_converts_palette(tmp_path):
    rgba = Image.new("RGBA", (8, 8), (0, 0, 255, 128))
    size = webp.export_webp(rgba, tmp_path / "out" / "a.webp")
    assert size > 0
    with Image.open(tmp_path / "out" / "a.webp") as back:
        assert back.format == "WEBP" and back.mode == "RGBA"
    pal = Image.new("P", (8, 8))
    webp.export_webp(pal, tmp_path / "p.webp")
    with Image.open(tmp_path / "p.webp") as back:
        assert back.mode == "RGB"


def test_convert_square_webp_end_to_end(photos):
    width, height, size = webp.convert_square_webp(photos / "wide.jpg", photos / "wide.webp", max_side=100)
    assert (width, height) == (100, 100) and size > 0
    with pytest.raises(BacError, match="Cannot read image"):
        webp.convert_square_webp(photos / "notes.txt", photos / "notes.webp")


def test_icc_profile_travels_with_the_pixels(tmp_path):
    src = tmp_path / "p3.png"
    image = Image.new("RGB", (8, 8), (10, 20, 30))
    image.save(src, icc_profile=b"fake-profile-bytes-long-enough")
    size = webp.export_webp(webp.load_oriented(src), tmp_path / "p3.webp")
    assert size > 0
    with Image.open(tmp_path / "p3.webp") as back:
        assert back.info.get("icc_profile") == b"fake-profile-bytes-long-enough"


def test_exif_orientation_is_applied(tmp_path):
    src = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (60, 20), (10, 200, 10))
    exif = image.getexif()
    exif[0x0112] = 6  # rotate 90° clockwise on display
    image.save(src, exif=exif.tobytes())
    assert webp.load_oriented(src).size == (20, 60)
