# SPDX-License-Identifier: MIT
"""The pages themselves: markup and stylesheet rules, then contrast and rendering in a real Chromium."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from bac_reference_gallery import cli
from gallery_testkit import BROWSER, CONTRAST_JS, LAYOUT_JS, PAGES, TOOL_DIR, needs_browser, png_size
from pypdf import PdfReader

from bac_common.testing import invoke

CSS = TOOL_DIR / "css"
EM_DASH = chr(0x2014)
FOUR_POINTED_STAR = chr(0x2726)
EXAMPLES = TOOL_DIR / "examples"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _block(css: str, opener: str) -> dict[str, str]:
    """The custom properties declared in the brace block that follows ``opener``."""
    start = css.index(opener)
    depth, i = 0, css.index("{", start)
    body_start = i + 1
    while True:
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = re.sub(r"/\*.*?\*/", "", css[body_start:i], flags=re.S)
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_every_page_declares_language_and_colour_schemes(page):
    html = _text(page)
    assert '<html lang="en">' in html
    assert '<meta name="color-scheme"' in html


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_table_headers_have_scope_and_images_have_alt(page):
    html = _text(page)
    assert not re.search(r"<th\b(?![^>]*\bscope=)", html), "a <th> without scope"
    assert not re.search(r"<img\b(?![^>]*\balt=)", html), "an <img> without alt"


def test_no_em_dash_anywhere_in_the_gallery():
    for path in TOOL_DIR.rglob("*"):
        if path.suffix in {".html", ".css", ".svg", ".md", ".py", ".toml"} and "__pycache__" not in path.parts:
            assert EM_DASH not in _text(path), path


def test_the_kickers_carry_no_glyph_of_their_own():
    for page in EXAMPLES.glob("*.html"):
        for text in re.findall(r'class="eyebrow kicker">([^<]*)<', _text(page)):
            assert not text.startswith("·"), page.name


def test_the_product_sheet_carries_no_volatile_data():
    html = _text(EXAMPLES / "product-sheet.html")
    for forbidden in ("$", "USD", "@buildacubesat", "discount", FOUR_POINTED_STAR):
        assert forbidden not in html, forbidden
    assert "bac-dev-kit-2u-v1r1" in html
    assert 'data-theme="light"' in html


def test_the_dark_mode_demo_uses_tokens_not_hex():
    html = _text(EXAMPLES / "interface-patterns.html")
    demo = html[html.index('data-theme="dark"') : html.index('<div class="terminal">')]
    assert not re.search(r"#[0-9A-Fa-f]{3,6}\b", demo)


def test_the_index_links_resolve():
    html = _text(TOOL_DIR / "index.html")
    links = re.findall(r'(?:href|src)="([^"]+)"', html)
    assert links
    for link in links:
        assert (TOOL_DIR / link).is_file(), link


def test_tokens_light_and_both_dark_blocks_agree():
    css = _text(CSS / "tokens.css")
    light = _block(css, ":root,\n[data-theme='light']")
    dark_media = _block(css, ":root:not([data-theme='light'])")
    dark_attr = _block(css, "\n[data-theme='dark']")
    # the two dark blocks must declare the same tokens with the same values
    assert {k: v.strip() for k, v in dark_media.items()} == {k: v.strip() for k, v in dark_attr.items()}
    assert set(dark_media) <= set(light), set(dark_media) - set(light)
    assert light["--text-muted"] == "var(--warm-600)" and dark_media["--text-muted"] == "var(--warm-400)"
    assert light["--link"] == "var(--bac-blue-press)"


def test_tokens_mirror_the_identity_guide_palette():
    canonical = _block(_text(CSS / "tokens.css"), "/* 1. Canonical tokens")
    expected = {
        "--bac-yellow": "#F7D400",
        "--bac-blue": "#4277FD",
        "--bac-green": "#84C45A",
        "--bac-red": "#CE6C63",
        "--nebula-cyan": "#087C9B",
        "--nebula-blue": "#3B35B8",
        "--nebula-copper": "#C88732",
        "--nebula-violet": "#21105F",
        "--nebula-ember": "#A94E52",
        "--warm-50": "#EFEFED",
        "--warm-500": "#888884",
        "--warm-800": "#3F3F3F",
        "--warm-950": "#201E1C",
        "--space-ink": "#171320",
        "--space-paper": "#F6F0E6",
        "--dur-normal": "200ms",
        "--ease-standard": "cubic-bezier(0.2, 0, 0.1, 1)",
    }
    for name, value in expected.items():
        assert canonical[name] == value, name


@pytest.mark.parametrize("sheet", ["gallery.css", "index.css"])
def test_stylesheets_have_focus_and_reduced_motion(sheet):
    css = _text(CSS / sheet)
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "@import url('./tokens.css')" in css
    assert "--warm-500" not in css


@pytest.mark.parametrize("sheet", sorted(CSS.glob("*.css")), ids=lambda p: p.name)
def test_every_stylesheet_is_dual_licensed(sheet):
    assert _text(sheet).splitlines()[0] == "/* SPDX-License-Identifier: MIT OR CC-BY-SA-4.0 */"


def test_license_file_carries_the_mit_text():
    mit = _text(TOOL_DIR.parents[1] / "LICENSE").strip()
    license_md = _text(TOOL_DIR / "LICENSE.md")
    assert mit in license_md
    assert "MIT or CC BY-SA 4.0" in license_md


@needs_browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_text_meets_wcag_aa(scheme):
    from playwright.sync_api import sync_playwright

    failures: dict[str, list[str]] = {}
    with sync_playwright() as pw:
        kwargs = {"executable_path": str(BROWSER)} if BROWSER else {}
        chromium = pw.chromium.launch(headless=True, **kwargs)
        page = chromium.new_page(viewport={"width": 1600, "height": 1000}, color_scheme=scheme)
        for path in PAGES:
            page.goto(path.as_uri(), wait_until="load")
            found = page.evaluate(CONTRAST_JS)
            if found:
                failures[path.stem] = found
        chromium.close()
    assert not failures, failures


@needs_browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_nothing_spills_out_of_a_board_or_a_card(scheme):
    from playwright.sync_api import sync_playwright

    problems: dict[str, list[str]] = {}
    with sync_playwright() as pw:
        kwargs = {"executable_path": str(BROWSER)} if BROWSER else {}
        chromium = pw.chromium.launch(headless=True, **kwargs)
        page = chromium.new_page(viewport={"width": 1600, "height": 1000}, color_scheme=scheme)
        for path in PAGES[1:]:  # the boards; the index page scrolls by design
            page.goto(path.as_uri(), wait_until="load")
            found = page.evaluate(LAYOUT_JS)
            if found:
                problems[path.stem] = found
        chromium.close()
    assert not problems, problems


@needs_browser
@pytest.mark.parametrize(
    ("scheme", "pinned", "expected"), [("dark", "light", "rgb(63, 63, 63)"), ("light", "dark", "rgb(239, 239, 237)")]
)
def test_a_pinned_subtree_takes_its_own_text_colour(tmp_path, scheme, pinned, expected):
    from playwright.sync_api import sync_playwright

    page_file = tmp_path / "pinned.html"
    tokens = (CSS / "tokens.css").as_uri()
    page_file.write_text(
        f'<!doctype html><html lang="en"><head><link rel="stylesheet" href="{tokens}"></head>'
        f'<body style="color:var(--text)"><div id="x" data-theme="{pinned}">text</div></body></html>',
        encoding="utf-8",
    )
    with sync_playwright() as pw:
        kwargs = {"executable_path": str(BROWSER)} if BROWSER else {}
        chromium = pw.chromium.launch(headless=True, **kwargs)
        page = chromium.new_page(color_scheme=scheme)
        page.goto(page_file.as_uri(), wait_until="load")
        color = page.evaluate("getComputedStyle(document.getElementById('x')).color")
        chromium.close()
    assert color == expected


@needs_browser
def test_a_real_render_sizes_png_and_pdf_from_the_board(monkeypatch, tmp_path):
    monkeypatch.setenv("BAC_CHROMIUM_PATH", str(BROWSER))
    out = tmp_path / "out"
    r = invoke(cli._main, ["--out-dir", str(out), "--only", "ops-vs-mission", "--only", "product-sheet"])
    assert r.exit_code == 0, r.output
    assert png_size(out / "png" / "ops-vs-mission.png") == (1600, 1000)
    assert png_size(out / "png" / "product-sheet.png") == (1055, 1491)
    sizes = []
    for name in ("ops-vs-mission", "product-sheet"):
        (page,) = PdfReader(str(out / "pdf" / f"{name}.pdf")).pages
        sizes.append((round(float(page.mediabox.width)), round(float(page.mediabox.height))))
    assert sizes == [(1200, 750), (791, 1118)]  # CSS pixels at 0.75 pt each


@needs_browser
def test_dark_mode_switches_ops_surfaces_but_not_the_product_sheet(monkeypatch, tmp_path):
    image = pytest.importorskip("PIL.Image")
    monkeypatch.setenv("BAC_CHROMIUM_PATH", str(BROWSER))
    for theme in ("light", "dark"):
        argv = ["--out-dir", str(tmp_path), "--format", "png", "--theme", theme]
        r = invoke(cli._main, [*argv, "--only", "ops-vs-mission", "--only", "product-sheet"])
        assert r.exit_code == 0, r.output
    suffix = {"light": "", "dark": "-dark"}
    board = {t: image.open(tmp_path / "png" / f"ops-vs-mission{suffix[t]}.png").convert("RGB") for t in suffix}
    sheet = {t: image.open(tmp_path / "png" / f"product-sheet{suffix[t]}.png").convert("RGB") for t in suffix}
    assert board["light"].getpixel((5, 5)) == (0xEF, 0xEF, 0xED)  # --bg, light
    assert board["dark"].getpixel((5, 5)) == (0x20, 0x1E, 0x1C)  # --bg, dark
    assert sheet["light"].getpixel((500, 1400)) == sheet["dark"].getpixel((500, 1400))  # pinned light
