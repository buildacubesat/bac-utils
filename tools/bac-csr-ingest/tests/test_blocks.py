# SPDX-License-Identifier: MIT
from bac_csr_ingest.blocks import parse_entry, parse_file, render_entry, replace_block_body


def test_parse_canonical():
    e = parse_entry("- **[Title](https://x.y/a.pdf)** `PDF` – Desc here")
    assert e and (e.title, e.url, e.file_type, e.description) == ("Title", "https://x.y/a.pdf", "PDF", "Desc here")


def test_parse_tolerant_variants():
    assert parse_entry("- [T](https://x.y/a.pdf) - desc").file_type == "PDF"
    assert parse_entry("* [T](https://x.y/) — desc").file_type == "Link"  # convention-check: allow A1
    assert parse_entry("- [T](https://x.y/a.pdf): desc").description == "desc"
    e = parse_entry("- **[T](https://x.y/a)**")
    assert e.description == "" and e.file_type == "Link"


def test_parse_rejects_non_entries():
    assert parse_entry("Some prose with [a link](https://x.y)") is None
    assert parse_entry("  - [nested](https://x.y)") is None
    assert parse_entry("- plain bullet") is None


def test_parse_file_headings_and_unparsed():
    text = (
        "# A\n## B\n<!-- CSR-RESOURCES:START b -->\n- [t](https://x.y/1) - d\nprose\n\n<!-- CSR-RESOURCES:END b -->\n"
    )
    blocks, problems = parse_file(text, "docs/a.md")
    assert not problems
    (b,) = blocks
    assert b.heading_context == ["A", "B"]
    assert [e.url for e in b.entries] == ["https://x.y/1"]
    assert [u.line_no for u in b.unparsed] == [5]
    assert (b.start_line, b.end_line) == (3, 7)


def test_marker_problems():
    _, p = parse_file("<!-- CSR-RESOURCES:START a -->\n- [t](https://x)\n", "f.md")
    assert "without END" in p[0].message
    _, p = parse_file("<!-- CSR-RESOURCES:END a -->\n", "f.md")
    assert "without START" in p[0].message
    b, p = parse_file("<!-- CSR-RESOURCES:START a -->\n<!-- CSR-RESOURCES:END b -->\n", "f.md")
    assert "does not match" in p[0].message and b[0].block_id == "a"


def test_parse_paren_url_and_continuation():
    e = parse_entry("- **[T](https://ecss.nl/x/ECSS-E-ST-10-03-Rev.1(31May2022).pdf)** `PDF` – d")
    assert e.url == "https://ecss.nl/x/ECSS-E-ST-10-03-Rev.1(31May2022).pdf"
    text = "<!-- CSR-RESOURCES:START b -->\n- **[t](https://x.y/1)**\n  desc line\n- [u](https://x.y/2)\n<!-- CSR-RESOURCES:END b -->\n"
    (b,), _ = parse_file(text, "f.md")
    assert not b.unparsed and [e.description for e in b.entries] == ["desc line", ""]


def test_render_roundtrip():
    line = render_entry("T", "https://x.y/a.pdf", "PDF", "d")
    assert line == "- **[T](https://x.y/a.pdf)** `PDF` – d"
    assert parse_entry(line).description == "d"
    assert render_entry("T", "https://x.y", "Link", "") == "- **[T](https://x.y)** `Link`"


def test_replace_block_body_preserves_surroundings():
    text = "before\n<!-- CSR-RESOURCES:START a -->\nold\n<!-- CSR-RESOURCES:END a -->\nafter\n"
    blocks, _ = parse_file(text, "f.md")
    out = replace_block_body(text, blocks[0], "\n- new\n")
    assert out == "before\n<!-- CSR-RESOURCES:START a -->\n- new\n<!-- CSR-RESOURCES:END a -->\nafter\n"
