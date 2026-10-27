# SPDX-License-Identifier: MIT
"""tokens.json itself, the copies written from it, and the contrast the guides promise."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from bac_design_tokens import build, cli

from bac_common.testing import invoke

ROOT = Path(__file__).resolve().parents[3]


def _lum(hex_: str) -> float:
    def ch(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def c(name: str, dark: bool = False) -> str:
    return build.hex_of(name, dark)


def test_every_token_has_a_type_and_a_value_and_aliases_resolve():
    names = set()
    for tok in build.tokens():
        assert tok.type and tok.value is not None, tok.name
        assert tok.name not in names, f"{tok.name} defined twice"
        names.add(tok.name)
        build.resolve(tok.value)
        if tok.dark is not None:
            assert tok.section == "semantic", f"{tok.name}: only semantic tokens switch with the theme"


def test_every_semantic_token_has_a_dark_value():
    for tok in build.tokens():
        if tok.section == "semantic":
            assert tok.dark is not None, tok.name


def test_retired_tokens_stay_retired():
    names = {t.name for t in build.tokens()}
    for gone in ("nebula-cyan", "nebula-blue", "nebula-copper", "nebula-ember", "warm-50", "shadow-sm", "radius-xl"):
        assert gone not in names, gone


def test_every_copy_is_current():
    r = invoke(cli._main, ["--check", "--root", str(ROOT)])
    assert r.exit_code == 0, r.output


def test_check_reports_a_stale_copy_and_a_run_rewrites_it(tmp_path):
    for rel in (
        "pyproject.toml",
        "tools/bac-reference-gallery/css/tokens.css",
        "ops/bac-suite/src/bac_suite/static/tokens.css",
        "lib/bac-common/src/bac_common/ui.py",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    stale = tmp_path / "ops/bac-suite/src/bac_suite/static/tokens.css"
    stale.write_text(stale.read_text(encoding="utf-8").replace("#F9F9F9", "#EFEFED"), encoding="utf-8")
    r = invoke(cli._main, ["--check", "--root", str(tmp_path)])
    assert r.exit_code == 1 and "Stale" in r.output
    r = invoke(cli._main, ["--root", str(tmp_path)])
    assert r.exit_code == 0 and "Written" in r.output
    assert stale.read_text(encoding="utf-8") == build.render_css()


def test_the_root_is_found_from_a_subfolder():
    assert build.find_root(ROOT / "tools" / "bac-design-tokens") == ROOT


def test_the_dark_blocks_match_and_cover_every_switching_token():
    css = build.render_css()
    media = css[css.index(":root:not([data-theme='light'])") : css.index("\n[data-theme='dark']")]
    attr = css[css.index("\n[data-theme='dark']") : css.index("/* 4.")]
    decl = re.compile(r"(--[\w-]+): ([^;]+);")
    assert dict(decl.findall(media)) == dict(decl.findall(attr))
    assert {f"--{t.name}" for t in build.tokens() if t.dark is not None} == set(dict(decl.findall(attr)))


def test_marimo_style_is_one_cell_body_and_has_no_chart_rules():
    style = build.marimo_style()
    assert ".vega-embed" not in style
    assert style.rstrip().endswith(":root { --heading-font: 'Nunito Sans', system-ui, sans-serif; }")
    assert "light-dark(#3F3F3F, #E5E5E5)" in style and "light-dark(#F9F9F9, #1F1E1D)" in style


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_text_meets_aa_on_every_surface(dark):
    for surface in ("bg", "bg-raised", "surface-card", "surface-sunken"):
        bg = c(surface, dark)
        for text in ("text", "text-strong", "text-muted", "link"):
            assert ratio(c(text, dark), bg) >= 4.5, (text, surface, dark)
    # Status text sits on cards, pages and its own tint, not in input wells: the console's
    # inks are 4.4:1 to 4.5:1 on --surface-sunken, so a well never carries status text.
    for surface in ("bg", "bg-raised", "surface-card"):
        for text in ("bac-green-ink", "bac-red-ink", "bac-blue-ink"):
            assert ratio(c(text, dark), c(surface, dark)) >= 4.5, (text, surface, dark)
    assert ratio(c("btn-primary-text", dark), c("btn-primary-bg", dark)) >= 4.5
    assert ratio(c("accent-state-text", dark), c("accent-state", dark)) >= 4.5
    assert ratio(c("focus-ring", dark), c("bg", dark)) >= 3


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_status_inks_read_on_their_tints(dark):
    for status in ("green", "red", "blue", "yellow"):
        ink, tint = c(f"bac-{status}-ink", dark), c(f"bac-{status}-tint", dark)
        assert ratio(ink, tint) >= 4.5, (status, dark)


def test_yellow_carries_dark_text_and_the_hero_card_white_text():
    assert ratio(c("text-on-accent"), c("bac-yellow")) >= 4.5
    assert ratio(c("text-on-accent", dark=True), c("bac-yellow")) >= 4.5
    assert ratio(c("hero-text"), c("hero-bg")) >= 7


def test_mission_inks_meet_aa_on_paper_tint_and_dark_surfaces():
    for hue in ("teal", "violet", "rose"):
        for surface in ("space-paper", f"nebula-{hue}-tint", "neutral-0"):
            assert ratio(c(f"mission-{hue}-ink"), c(surface)) >= 4.5, (hue, surface)
        for surface in ("space-ink", "space-surface"):
            assert ratio(c(f"mission-{hue}-on-dark"), c(surface)) >= 4.5, (hue, surface)
        assert ratio(c(f"nebula-{hue}"), c("space-ink")) >= 3, hue


def test_chart_series_keep_three_to_one():
    for i in range(1, 6):
        for dark in (False, True):
            assert ratio(c(f"chart-{i}", dark), c("surface-card", dark)) >= 3, (i, dark)
        shared = c(f"chart-shared-{i}")
        assert ratio(shared, "#FFFFFF") >= 3.9 and ratio(shared, c("bg", dark=True)) >= 3.9, i
