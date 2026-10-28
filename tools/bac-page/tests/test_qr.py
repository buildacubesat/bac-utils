# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest
from bac_page.qr import QrOptions, qr_path, write_qr
from PIL import Image


def test_qr_path_defaults_to_home_and_names_the_slug(tmp_path):
    assert qr_path("eps", QrOptions()) == tmp_path / "bac-page-eps.svg"  # HOME is tmp_path
    assert qr_path("eps", QrOptions(fmt="png", output=tmp_path / "out")) == tmp_path / "out" / "bac-page-eps.png"


def test_svg_is_sized_inverted_and_made_transparent(tmp_path):
    plain = write_qr("https://bac.page/x", "x", QrOptions(size=640, output=tmp_path))
    svg = plain.read_text()
    # the path image has no background rect, so an SVG is transparent with or without --alpha (as in 0.4)
    assert 'width="640"' in svg and 'height="640"' in svg and 'fill="#000000"' in svg and "<rect" not in svg
    both = write_qr("https://bac.page/y", "y", QrOptions(invert=True, alpha=True, output=tmp_path))
    text = both.read_text()
    assert "<rect" not in text and 'fill="#ffffff"' in text and 'fill="#000000"' not in text


@pytest.mark.parametrize("fmt", ["png", "webp"])
def test_raster_formats_with_alpha(tmp_path, fmt):
    opaque = write_qr("https://bac.page/x", "x", QrOptions(fmt=fmt, size=200, output=tmp_path))
    with Image.open(opaque) as img:
        assert img.size == (200, 200) and img.format == fmt.upper()
    alpha = write_qr("https://bac.page/x", "xa", QrOptions(fmt=fmt, size=200, alpha=True, output=tmp_path))
    with Image.open(alpha) as img:
        img = img.convert("RGBA")
        assert img.getchannel("A").getextrema() == (0, 255)
        assert img.getpixel((0, 0))[3] == 0  # the quiet zone is background, hence transparent
    inverted = write_qr("https://bac.page/x", "xi", QrOptions(fmt=fmt, size=200, invert=True, output=tmp_path))
    with Image.open(inverted) as img:
        assert img.convert("RGB").getpixel((0, 0)) == (0, 0, 0)


def test_error_correction_levels_change_the_module_count(tmp_path):
    low = write_qr("https://bac.page/x", "l", QrOptions(ec="L", output=tmp_path)).read_text()
    high = write_qr("https://bac.page/x", "h", QrOptions(ec="H", output=tmp_path)).read_text()
    assert len(high) > len(low)
