# SPDX-License-Identifier: MIT
"""Front matter, headings and links from the Markdown; the stylesheet; the CLI contract and --check."""

from __future__ import annotations

from pathlib import Path

import pytest
from bac_design_export import __version__, cli, document, render

from bac_common.testing import assert_standard_flags, invoke

DESIGN = cli.find_design(Path(__file__).resolve().parents[3])
needs_design = pytest.mark.skipif(DESIGN is None, reason="needs the bac-design checkout next to bac-utils")

GUIDE = """# BAC Example Guide

**Build a CubeSat – Example standard.** Version 1.2, 2026-10-29 · Authors: Mänu

> **Note.** A callout.

## 1. First Section

See the [policy](bac-trademark-policy.md) and [assets](../assets/README.md).

### 1.1 Sub

| **Token** | **Value** |
|----|----|
| --bac-yellow | #F7D400 |

## 2. Second Section

## Version History
"""


def write_guide(tmp_path: Path, text: str = GUIDE) -> Path:
    path = tmp_path / "guides" / "bac-example-guide.md"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_contract():
    assert_standard_flags(cli._main, cli.TOOL, __version__)


def test_front_matter_from_the_bold_line(tmp_path):
    doc = document.read(write_guide(tmp_path))
    assert doc.title == "BAC Example Guide"
    assert doc.lead == "Example standard"
    assert (doc.version, doc.date, doc.meta) == ("1.2", "2026-10-29", "Authors: Mänu")
    assert doc.eyebrow == "Version 1.2 · 2026-10-29"
    assert "**Build a CubeSat" not in doc.body


def test_a_document_without_the_bold_line_keeps_its_title_only(tmp_path):
    doc = document.read(write_guide(tmp_path, "# Checklist\n\n- Source: elsewhere\n"))
    assert (doc.title, doc.lead, doc.version, doc.eyebrow) == ("Checklist", "", "", "")
    assert "Source: elsewhere" in doc.body


def test_headings_carry_their_number_in_its_own_span(tmp_path):
    doc = document.read(write_guide(tmp_path))
    assert [(h.level, h.number, h.text) for h in doc.headings] == [
        (2, "1", "First Section"),
        (3, "1.1", "Sub"),
        (2, "2", "Second Section"),
        (2, "", "Version History"),
    ]
    assert '<h2 id="1-first-section"><span class="num">1</span><span class="text">First Section</span></h2>' in doc.body


def test_relative_links_point_at_the_repository(tmp_path):
    body = document.read(write_guide(tmp_path)).body
    assert f'href="{document.REPO_URL}/guides/bac-trademark-policy.md"' in body
    assert f'href="{document.REPO_URL}/assets/README.md"' in body


def test_tables_and_callouts_render(tmp_path):
    body = document.read(write_guide(tmp_path)).body
    assert "<table>" in body and "<th><strong>Token</strong></th>" in body
    assert "<blockquote>" in body


def test_the_stylesheet_takes_its_values_from_the_tokens():
    css = render.tokens_css()
    assert "--bac-yellow: #F7D400" in css and "--kicker:" in css
    assert "fonts.googleapis.com" not in css, "the export works offline"
    stacks = render.symbol_stacks()
    assert "--font-body: 'Nunito Sans', 'BAC Symbols', system-ui" in stacks
    # print.css names no colour of its own: every colour is a token
    import re

    assert not re.search(r"#[0-9A-Fa-f]{3,6}\b", render.print_css())


def test_running_header_escapes_quotes(tmp_path):
    doc = document.read(write_guide(tmp_path))
    doc.title = 'A "quoted" title'
    assert 'content: "A \\"quoted\\" title"' in render.running_css(doc)


def test_list_and_unknown_names(tmp_path):
    write_guide(tmp_path)
    (tmp_path / "fonts").mkdir()
    r = invoke(cli._main, ["-l", "--design", str(tmp_path)])
    assert r.exit_code == 0 and r.stdout.split() == ["bac-example-guide"]
    r = invoke(cli._main, ["nope", "--design", str(tmp_path)])
    assert r.exit_code == 2


def test_no_checkout_is_a_config_error(tmp_path):
    r = invoke(cli._main, ["--design", str(tmp_path)])
    assert r.exit_code == 1 and "bac-design" in r.stderr


@needs_design
def test_export_then_check_is_current(tmp_path):
    out = tmp_path / "exports"
    name = "bac-rocinante-naming"
    r = invoke(cli._main, [name, "--design", str(DESIGN), "-o", str(out)])
    assert r.exit_code == 0, r.output
    pdf = out / f"{name}.pdf"
    assert render.pdf_creator(pdf).startswith(f"bac-design-export {__version__} · source ")
    r = invoke(cli._main, [name, "--design", str(DESIGN), "-o", str(out), "--check"])
    assert r.exit_code == 0, r.output
    pdf.write_bytes(b"%PDF-1.7 stale")
    r = invoke(cli._main, [name, "--design", str(DESIGN), "-o", str(out), "--check"])
    assert r.exit_code == 1


def test_code_blocks_wrap_while_inline_code_stays_on_one_line():
    css = render.print_css()
    pre = css[css.index("pre {") :]
    assert "white-space: pre-wrap" in pre[: pre.index("}")]
    assert "white-space: inherit" in css[css.index("pre code {") :].split("}")[0]
