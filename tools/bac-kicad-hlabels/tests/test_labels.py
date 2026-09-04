# SPDX-License-Identifier: MIT
from __future__ import annotations

import re

import pytest
from bac_kicad_hlabels.labels import LabelStyle, escape, fmt, make_label, parse_names, render

EXPECTED_BLOCK = """(hierarchical_label "A_CAN_1_P"
\t(shape passive)
\t(at 0 2.54 0)
\t(effects
\t\t(font
\t\t\t(size 1.27 1.27)
\t\t)
\t\t(justify right)
\t)
\t(uuid "00000000-0000-4000-8000-000000000001")
)"""


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (0, "0"),
        (0.0, "0"),
        (2.54, "2.54"),
        (7.62, "7.62"),
        (2.54 * 3, "7.62"),
        (1.27, "1.27"),
        (0.635, "0.635"),
        (100, "100"),
        (-2.5, "-2.5"),
        (1.00005, "1.0001"),
        (0.00001, "0"),
    ],
)
def test_fmt(value, text):
    assert fmt(value) == text


def test_escape():
    assert escape('A"B\\C') == 'A\\"B\\\\C'


def test_make_label_matches_kicad_shape():
    block = make_label("A_CAN_1_P", 0, 2.54, LabelStyle(), uid="00000000-0000-4000-8000-000000000001")
    assert block == EXPECTED_BLOCK


def test_make_label_style_and_random_uuid():
    style = LabelStyle(shape="input", justify="left", rotation=90, font_size=1.0)
    block = make_label("VBAT", 12.7, -3.81, style)
    assert "(shape input)" in block and "(at 12.7 -3.81 90)" in block
    assert "(size 1 1)" in block and "(justify left)" in block
    assert re.search(r'\(uuid "[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"\)', block)


def test_parse_names_drops_or_keeps_blanks(example_text):
    names = parse_names(example_text)
    assert len(names) == 38 and None not in names
    assert names[:3] == ["A_CAN_1_P", "3V3_AUX", "A_CAN_1_N"]

    slots = parse_names(example_text, gap_on_blank=True)
    assert len(slots) == 47
    assert slots[3:7] == [None] * 4 and slots[7] == "VBAT"
    assert slots[-1] == "A_3V3_MAIN"  # trailing blank lines never add slots

    assert parse_names("  a  \n\n\n b \n\n") == ["a", "b"]
    assert parse_names("a\n\n\nb\n\n", gap_on_blank=True) == ["a", None, None, "b"]


def test_render_positions_and_gaps():
    uids = iter(f"u{i}" for i in range(10))
    out = render(["A", None, "B"], x=1, y_start=10, step=2.54, uuid_factory=lambda: next(uids))
    blocks = out.split("\n\n")
    assert len(blocks) == 2 and out.endswith(")\n")
    assert "(at 1 10 0)" in blocks[0] and '(uuid "u0")' in blocks[0]
    assert "(at 1 15.08 0)" in blocks[1] and '(uuid "u1")' in blocks[1]
    assert render([]) == ""


def test_render_forty_labels_have_exact_positions():
    out = render([f"N{i}" for i in range(40)], step=2.54)
    ys = re.findall(r"\(at 0 (\S+) 0\)", out)
    assert ys[0] == "0" and ys[1] == "2.54" and ys[3] == "7.62" and ys[39] == "99.06"
