# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest
from bac_markdown_to_youtube.convert import convert

# The conversion table: Markdown in, YouTube description out.
CASES = [
    ("bold", "This is **bold** text", "This is *bold* text"),
    ("bold-underscore", "This is __bold__ text", "This is *bold* text"),
    ("italic", "This is *italic* and _also_ text", "This is _italic_ and _also_ text"),
    ("bold-italic", "This is ***both*** and ___too___", "This is *_both_* and *_too_*"),
    ("strikethrough", "Was ~~wrong~~ right", "Was -wrong- right"),
    ("punctuation-after", "Buy **now**, not **later**.", "Buy *now* , not *later* ."),
    ("bracket-before", "Note (**important**) here", "Note ( *important* ) here"),
    ("headings", "# Title\n\n## Part 1\n\n### Sub", "*Title*\n\n*Part 1*\n\n*Sub*"),
    ("heading-already-bold", "# **Title**", "*Title*"),
    ("link-alnum", "See [the docs](https://example.com/a_b_c) now", "See the docs: https://example.com/a_b_c now"),
    ("link-punctuation", "[Read more!](https://example.com)", "Read more! https://example.com"),
    ("autolink-and-bare", "Go to <https://a.b/x_y> or https://c.d/e_f.", "Go to https://a.b/x_y or https://c.d/e_f."),
    ("angle-brackets-kept", "5 < 10 and 10 > 5", "5 < 10 and 10 > 5"),
    ("html-tags-dropped", "Line<br>break <b>bold</b>", "Line\nbreak bold"),
    ("bullets", "* one\n+ two\n- three\n1. four", "- one\n- two\n- three\n1. four"),
    ("inline-code", "Run `uv sync --all-packages` first", "Run uv sync --all-packages first"),
    ("fenced-code", "```sh\nx = **not bold**\n```\nafter", "x = **not bold**\nafter"),
    ("snake-case-untouched", "Use snake_case_names and 2*3*4", "Use snake_case_names and 2*3*4"),
    ("escapes", r"A literal \* star and \_ underscore", "A literal * star and _ underscore"),
    ("blockquote", "> quoted *word*", "quoted _word_"),
    ("comment-removed", "before <!-- hidden --> after", "before  after"),
    ("nested-in-heading", "# Title with _em_ inside", "*Title with _em_ inside*"),
    (
        "bold-in-heading-unwrapped",
        "# Episode 3: **EPS** bring-up\n# ***Both*** here",
        "*Episode 3: EPS bring-up*\n*_Both_ here*",
    ),
    ("quoted-heading-and-bullet", "> # Heading\n> * item\n> > nested", "*Heading*\n- item\nnested"),
    ("hyphen-adjacent", "pre-**bold**-post and **re**-run", "pre- *bold* -post and *re* -run"),
    ("underscore-wrapping-bold", "_**x**_ and _**bold** words_", "_*x*_ and _*bold* words_"),
    ("angle-brackets-non-html", "Vec<u8> and <placeholder> but <b>x</b>", "Vec<u8> and <placeholder> but x"),
    ("comment-inside-fence-kept", "```\n<!-- keep -->\n```\nx <!-- gone --> y", "<!-- keep -->\nx  y"),
    ("adjacent-spans", "**a**_b_", "*a* _b_"),
]


@pytest.mark.parametrize(("name", "source", "expected"), CASES, ids=[c[0] for c in CASES])
def test_conversion_table(name, source, expected):
    assert convert(source) == expected


def test_trailing_newline_and_crlf_preserved_as_lf():
    assert convert("**a**\r\n**b**\r\n") == "*a*\n*b*\n"


def test_no_placeholder_leaks():
    out = convert("**a** _b_ `c` [d](https://e.f) # not a heading\n# heading with `code`")
    assert "" not in out and "" not in out
    assert out == "*a* _b_ c d: https://e.f # not a heading\n*heading with code*"
