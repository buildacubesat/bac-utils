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
    assert names == [a.name for a in assets.assets()]
    assert len(names) == len(set(names)) == 9
    assert all(re.fullmatch(r"bac-(symbol|wordmark|logo)-(black|white|currentcolor)-v\d+r\d+\.svg", n) for n in names)


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
    assert "—" not in svg  # no em dash anywhere


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
    r = invoke(cli._main, ["--design", str(DESIGN), "-o", str(out)])
    assert r.exit_code == 0 and r.output.count("Written") == 10
    r = invoke(cli._main, ["--design", str(DESIGN), "-o", str(out), "--check"])
    assert r.exit_code == 0 and "Stale" not in r.output.replace("Stale    :  0", "")
    stale = out / "bac-logo-black-v4r1.svg"
    stale.write_text(stale.read_text(encoding="utf-8").replace("#000000", "#111111"), encoding="utf-8")
    r = invoke(cli._main, ["--design", str(DESIGN), "-o", str(out), "--check"])
    assert r.exit_code == 1 and "Stale: bac-logo-black-v4r1.svg" in r.output
    r = invoke(cli._main, ["--design", str(DESIGN), "-o", str(out), "--dry-run"])
    assert r.exit_code == 0 and "Would write" in r.output and "#111111" in stale.read_text(encoding="utf-8")


@needs_font
def test_the_committed_assets_are_current():
    r = invoke(cli._main, ["--design", str(DESIGN), "--check"])
    assert r.exit_code == 0, r.output
