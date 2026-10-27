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
    assert len(names) == len(set(names)) == 28 + 84  # 21 coloured SVGs × two sizes × PNG and WebP
    assert all(
        re.fullmatch(r"(png|webp)/(bac|rocinante)-[a-z-]+-v\d+r\d+-(512|2048)\.(png|webp)", n) for n in names[28:]
    )
    names = svgs
    pattern = (
        r"bac-(symbol|wordmark|logo|logo-tagline)-(black|white|currentcolor)-v\d+r\d+\.svg"
        r"|bac-(symbol|logo)-badge-(light|dark)-v\d+r\d+\.svg"
        r"|rocinante-(symbol|wordmark|logo)-(black|white|currentcolor|colour)-v\d+r\d+\.svg"
    )
    assert all(re.fullmatch(pattern, n) for n in names), names


def test_symbol_is_a_true_isometric_cube_on_the_guide_grid():
    svg = assets.symbol_svg("#000000")
    assert 'viewBox="0 0 400 650"' in svg
    assert 'stroke-width="15"' in svg and "width=" not in svg.split(">", 1)[0].replace("stroke-width", "")
    # the outline's six vertices: the cube is 200√3 wide and 600 tall, centred on the canvas
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


def test_currentcolor_variant_carries_no_literal_colour():
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
    assert r.exit_code == 0 and r.output.count("Written") == 29
    r = invoke(cli._main, ["--design", str(DESIGN), "-o", str(out), "--check", "--no-raster"])
    assert r.exit_code == 0 and "Stale: " not in r.output
    stale = out / "bac-logo-black-v4r1.svg"
    stale.write_text(stale.read_text(encoding="utf-8").replace("#000000", "#111111"), encoding="utf-8")
    r = invoke(cli._main, ["--design", str(DESIGN), "-o", str(out), "--check", "--no-raster"])
    assert r.exit_code == 1 and "Stale: bac-logo-black-v4r1.svg" in r.output
    r = invoke(cli._main, ["--design", str(DESIGN), "-o", str(out), "--dry-run", "--no-raster"])
    assert r.exit_code == 0 and "Would write" in r.output and "#111111" in stale.read_text(encoding="utf-8")


def test_badge_encloses_the_symbol_and_rocinante_ring_has_three_gaps():
    from bac_brand_assets import rocinante

    badge = assets.badge_svg(Path("."), "light", logo=False)
    assert 'id="badge"' in badge and "#D0D0D0" in badge and 'id="symbol"' in badge
    ring = rocinante.ring_path(0, 0)
    assert ring.count("A") == 3 and ring.count("M") == 3
    svg = rocinante.symbol_svg("colour", assets.wrap)
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
