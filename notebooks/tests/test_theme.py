# SPDX-License-Identifier: MIT
"""Chart colors that the kernel must not decide.

`mo.app_meta().theme` reports marimo's setting, "light" under "system", so a notebook cannot
know the surface its charts land on. marimo's frontend does: on a dark surface it hands
vega-embed the dark theme, which sets text, axis lines and ticks – unless the spec names
those colors itself. These tests keep every notebook of the class, and the pricing notebook
that shares the two cells, from naming them: one series palette that reads on both surfaces,
no label, title, axis or subtitle colors in the conventions cell, and no `.vega-embed` rule
in the style cell (the charts render on canvas inside a shadow root, out of its reach).
"""

import re
from pathlib import Path

import pytest

NOTEBOOKS = Path(__file__).resolve().parents[1]
FILES = sorted(NOTEBOOKS.glob("bac-*/bac_*.py")) + sorted(NOTEBOOKS.glob("bac-*/demo/bac_*.py"))
FILES.append(NOTEBOOKS.parents[0] / "ops" / "bac-pricing" / "src" / "bac_pricing" / "notebook.py")

PALETTE = '["#2E7ED8", "#7D7D7D", "#9D7800", "#0E903A", "#E4463E"]'  # chart-shared-1..5 in tokens.json
FORBIDDEN = ("labelColor=", "titleColor=", "domainColor=", "tickColor=", "subtitleColor=", "configure_legend(")

_STYLE = re.compile(r"<style>(.*?)</style>", re.S)
_CONVENTIONS = re.compile(r'    IS_DARK = mo\.app_meta\(\)\.theme == "dark"\n(.*?)\n    return[ (]', re.S)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_one_palette_and_no_text_colors_in_the_conventions_cell(path):
    source = path.read_text(encoding="utf-8")
    assert source.count("PALETTE = ") == 1 and f"PALETTE = {PALETTE}" in source, "the palette is one set"
    for word in FORBIDDEN:
        assert word not in source, f"{word} names a color the frontend should set"
    for call in re.finditer(r"\.configure_title\(([^)]*)\)|alt\.Title\(([^)]*)\)", source):
        assert "color=" not in (call.group(1) or call.group(2)), call.group(0)
    cell = _CONVENTIONS.search(source)
    assert cell, "no chart-conventions cell"
    assert ".configure_title(anchor=" in cell.group(1) and 'background="transparent"' in cell.group(1)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_style_cell_does_not_try_to_style_charts(path):
    style = _STYLE.search(path.read_text(encoding="utf-8"))
    assert style and ".vega-embed" not in style.group(1)
