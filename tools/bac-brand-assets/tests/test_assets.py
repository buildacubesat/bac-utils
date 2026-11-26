# SPDX-License-Identifier: MIT
"""The construction of the marks, the files written from it, and the CLI contract."""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest
from bac_brand_assets import __version__, assets, cli
from bac_brand_assets.wordmark import FONT_FILE

from bac_common.testing import assert_standard_flags, invoke

DESIGN = assets.find_design(Path(__file__).resolve().parents[3])
needs_font = pytest.mark.skipif(
    DESIGN is None or not (DESIGN / "fonts" / FONT_FILE).is_file(),
    reason="needs the bac-design checkout with fonts/ next to bac-utils",
)


def test_contract():
    assert_standard_flags(cli._main, cli.TOOL, __version__)


def test_list_prints_every_asset_once():
    r = invoke(cli._main, ["-l"])
    assert r.exit_code == 0
    names = r.stdout.split()
    svgs = [n for n in names if n.endswith(".svg")]
    assert svgs == [a.name for a in assets.assets()]
    assert len(names) == len(set(names)) == 40 + 124  # 31 colored SVGs × two sizes × PNG and WebP
    assert all(
        re.fullmatch(r"(png|webp)/(bac|rocinante)-[a-z-]+-v\d+r\d+-(512|2048)\.(png|webp)", n) for n in names[40:]
    )
    names = svgs
    pattern = (
        r"bac-(symbol|wordmark|logo|logo-tagline|logo-stacked|logo-stacked-tagline)-(black|white|currentcolor)-v\d+r\d+\.svg"
        r"|bac-(symbol|logo|logo-tagline|logo-stacked|logo-stacked-tagline)-badge-(light|dark)-v\d+r\d+\.svg"
        r"|rocinante-(symbol|wordmark|logo)-(black|white|currentcolor|color)-v\d+r\d+\.svg"
    )
    assert all(re.fullmatch(pattern, n) for n in names), names


def test_symbol_is_a_true_isometric_cube_on_the_guide_grid():
    svg = assets.symbol_svg("#000000")
    assert 'viewBox="0 0 400 650"' in svg
    assert 'stroke-width="15"' in svg and "width=" not in svg.split(">", 1)[0].replace("stroke-width", "")
    # the outline's six vertices: the cube is 200√3 wide and 600 tall, centered on the canvas
    half = assets.EDGE * math.sqrt(3) / 2
    for x, y in [(200, 25), (200 + half, 125), (200 + half, 525), (200, 625), (200 - half, 525), (200 - half, 125)]:
        assert f"Q{x:.2f}".rstrip("0").rstrip(".") + f" {y}" in svg, (x, y)
    # the dot sits at the centre of the top face with the isometric 1:√3 axis ratio
    assert 'cx="200" cy="125" rx="30" ry="17.32"' in svg


def test_every_file_carries_title_desc_and_the_trademark_notice():
    svg = assets.symbol_svg("#ffffff")
    assert '<title id="title">Build a CubeSat Symbol v4r1</title>' in svg
    assert "BAC Trademark Policy" in svg and "nihil.space GmbH" in svg
    assert "<dc:title>Build a CubeSat Symbol v4r1</dc:title>" in svg
    assert "cc:license" not in svg  # the marks are not openly licensed
    assert chr(0x2014) not in svg  # no em dash anywhere


def test_currentcolor_variant_carries_no_literal_color():
    svg = assets.symbol_svg("currentColor")
    assert "#000000" not in svg and "#ffffff" not in svg
    assert svg.count("currentColor") == 2  # stroke and the dot's fill


def test_the_checkout_is_not_found_in_an_empty_tree(tmp_path):
    assert assets.find_design(tmp_path) is None
    r = invoke(cli._main, ["--design", str(tmp_path)])
    assert r.exit_code == 1 and FONT_FILE in r.output


@needs_font
def test_wordmark_lines_are_justified_to_the_same_width():
    group, width, height = assets.wordmark_group(DESIGN / "fonts", "#000000")
    assert height == assets.CAP + assets.LEADING
    line1, line2 = re.findall(r' d="([^"]+)"', group)
    right = lambda d: max(float(x) for x, _ in re.findall(r"(-?[\d.]+) (-?[\d.]+)", d))  # noqa: E731
    assert abs(right(line1) - right(line2)) < 6  # the A and the T end within their side bearings


@needs_font
def test_the_written_files_are_current_and_check_reports_a_stale_one(tmp_path):
    out = tmp_path / "assets"
    r = invoke(cli._main, ["--design", str(DESIGN), "-o", str(out), "--no-raster"])
    assert r.exit_code == 0 and r.output.count("Written") == 41
    r = invoke(cli._main, ["--design", str(DESIGN), "-o", str(out), "--check", "--no-raster"])
    assert r.exit_code == 0 and "Stale: " not in r.output
    stale = out / "bac-logo-black-v4r1.svg"
    stale.write_text(stale.read_text(encoding="utf-8").replace("#000000", "#111111"), encoding="utf-8")
    r = invoke(cli._main, ["--design", str(DESIGN), "-o", str(out), "--check", "--no-raster"])
    assert r.exit_code == 1 and "Stale: bac-logo-black-v4r1.svg" in r.output
    r = invoke(cli._main, ["--design", str(DESIGN), "-o", str(out), "--dry-run", "--no-raster"])
    assert r.exit_code == 0 and "Would write" in r.output and "#111111" in stale.read_text(encoding="utf-8")


@needs_font
def test_tagline_badge_covers_the_tagline_with_the_badge_offset():
    _, _, _, _, (x, y, w, h) = assets.logo_parts(DESIGN / "fonts", "#000000")
    _, _, _, _, (tx, ty, tw, th) = assets.logo_parts(DESIGN / "fonts", "#000000", tagline=True)
    assert (tx, tw) == (x, w) and th > h  # the text box grows down to the tagline's baseline
    assert abs(ty + th / 2 - 325) < 0.01  # and stays centered on the cube
    badge = assets.badge_svg(DESIGN / "fonts", "light", logo=True, tagline=True)
    plain = assets.badge_svg(DESIGN / "fonts", "light", logo=True)
    assert "Build a CubeSat Logo Tagline Badge v4r1" in badge and 'id="tagline"' in badge
    assert re.search(r'viewBox="0 0 ([\d.]+)', badge).group(1) == re.search(r'viewBox="0 0 ([\d.]+)', plain).group(1)


@needs_font
def test_stacked_logo_centers_the_wordmark_under_the_cube():
    body, width, height, construction, (x, y, w, h) = assets.stacked_parts(DESIGN / "fonts", "#000000")
    assert abs(x + w / 2 - width / 2) < 0.01  # wordmark centered on the canvas, as the symbol is
    assert y == 625 + assets.STROKE / 2 + assets.STACKED_GAP  # gap from the cube's lowest point
    assert abs(h - 3 * assets.EDGE * assets.STACKED_TEXT_FRACTION) < 0.01
    assert abs(height - (y + h + assets.PAD)) < 0.01
    assert f"Nunito {assets.STACKED_FONT_WEIGHT}" in construction and 'id="symbol"' in body
    badge = assets.stacked_badge_svg(DESIGN / "fonts", "dark")
    assert "Build a CubeSat Logo Stacked Badge v4r1" in badge and "#1F1E1D" in badge


def test_badge_encloses_the_symbol_and_rocinante_ring_has_three_gaps():
    from bac_brand_assets import rocinante

    badge = assets.badge_svg(Path("."), "light", logo=False)
    assert 'id="badge"' in badge and "#D0D0D0" in badge and 'id="symbol"' in badge
    ring = rocinante.ring_path(0, 0)
    assert ring.count("A") == 3 and ring.count("M") == 3
    svg = rocinante.symbol_svg("color", assets.wrap)
    assert "Rocinante Symbol v2r1" in svg and "#1F1F1F" in svg and "#004C8B" in svg


@needs_font
def test_a_raster_is_rendered_at_the_longest_side_with_transparency():
    import io

    from bac_brand_assets import raster
    from PIL import Image

    svg = assets.symbol_svg("#000000")
    png = raster.render(svg, raster.Raster("bac-symbol-black-v4r1.svg", 512, "png"))
    im = Image.open(io.BytesIO(png))
    assert im.size == (315, 512) and im.mode == "RGBA" and im.getpixel((0, 0))[3] == 0
    webp = raster.render(svg, raster.Raster("bac-symbol-black-v4r1.svg", 512, "webp"))
    assert webp[:4] == b"RIFF" and Image.open(io.BytesIO(webp)).size == (315, 512)
    assert not any("currentcolor" in r.name for r in raster.rasters([a.name for a in assets.assets()]))


@needs_font
def test_the_committed_assets_are_current():
    r = invoke(cli._main, ["--design", str(DESIGN), "--check"])
    assert r.exit_code == 0, r.output


@needs_font
def test_stacked_tagline_sits_under_the_wordmark_at_its_width():
    _, w0, h0, _, (x, y, w, h) = assets.stacked_parts(DESIGN / "fonts", "#000000")
    body, w1, h1, construction, (tx, ty, tw, th) = assets.stacked_parts(DESIGN / "fonts", "#000000", tagline=True)
    assert (tx, ty, tw, w1) == (x, y, w, w0) and th > h  # same wordmark, the box reaches down to the tagline
    assert abs(h1 - (ty + th + assets.PAD)) < 0.01 and 'id="tagline"' in body and "SPACE FOR EVERYONE" in construction
    badge = assets.stacked_badge_svg(DESIGN / "fonts", "light", tagline=True)
    assert "Build a CubeSat Logo Stacked Tagline Badge v4r1" in badge and 'id="tagline"' in badge
