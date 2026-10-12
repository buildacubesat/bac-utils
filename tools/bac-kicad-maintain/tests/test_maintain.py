# SPDX-License-Identifier: MIT
"""The operations on texts: what changes, what stays, and that a second pass changes nothing."""

from __future__ import annotations

from dataclasses import replace

import pytest
from bac_kicad_maintain.config import DEFAULTS, load_settings
from bac_kicad_maintain.maintain import LABEL_HEADS, MaintainError, inspect_stats
from maintain_testkit import BOARD, LABELS, SCHEMATIC, run

from bac_common.errors import ConfigError
from bac_common.sexp import parse


def test_text_scope_and_preservation():
    out = run(selected={"text"})
    assert out.counts == {"text items": 6}
    assert "unlocked" not in out.text
    for kept in (
        "(at 10 20 135)",
        "(at 40 50 90)",
        "(angle 90)",
        "mirror",
        "bold italic",
        '(property "metadata" "leave me unchanged")',
        "(size 5 5)",
        "(thickness 0.5)",
        "(justify left)",
        '(members "board-text")',
        "(stroke (width 0.15) (type solid))",
        '(segment (start 1 1) (end 2 2) (width 0.3) (layer "F.Cu") (net 2))',
        '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net 2 "SIGNAL"))',
        r'"a (label) \"quoted\""',
    ):
        assert kept in out.text
    assert out.text.count("(size 0.8 0.8)") == 6
    assert out.text.count("(thickness 0.1)") == 6


def test_courtyards_legacy_and_modern():
    out = run(selected={"courtyards"})
    assert out.counts == {"courtyard lines": 2}
    assert '(layer "F.CrtYd") (width 0.05)' in out.text
    assert "(stroke (width 0.05) (type solid))" in out.text
    assert '(layer "F.SilkS") (width 0.15)' in out.text
    assert "(font (size 1 2) (thickness 0.2)" in out.text


def test_vias_numbered_named_and_exclusions():
    out = run(selected={"vias"})
    assert out.counts == {"vias kept, preserved net": 1, "vias": 1, "vias skipped, unconnected": 1}
    assert "(at 1 1) (size 0.6) (drill 0.3)" in out.text
    assert "(at 2 2) (size 0.5) (drill 0.2)" in out.text
    assert "(at 3 3) (size 0.6) (drill 0.3)" in out.text
    named = """(kicad_pcb
      (via (at 1 1) (size 0.6) (drill 0.3) (net "GND"))
      (via (at 2 2) (size 0.6) (drill 0.3) (net "SIGNAL"))
      (via micro (at 3 3) (size 0.1) (drill 0.05) (net "SIGNAL"))
      (via (at 4 4) (size 0.6) (drill 0.3) (net 99)))"""
    out = run(named, {"vias"})
    assert out.counts["vias"] == 1
    assert out.counts["vias skipped, unknown net"] == 1
    assert out.counts["vias skipped, type or padstack"] == 1
    assert "(size 0.1) (drill 0.05)" in out.text


def test_via_types_and_preserve_patterns_from_settings():
    named = """(kicad_pcb
      (via micro (at 3 3) (size 0.1) (drill 0.05) (net "SIGNAL"))
      (via (at 1 1) (size 0.6) (drill 0.3) (net "Power/GND")))"""
    settings = replace(DEFAULTS, via_types=("through", "micro"), preserve_nets=("GND", "*/GND"))
    out = run(named, {"vias"}, settings)
    assert out.counts == {"vias": 1, "vias kept, preserved net": 1}
    assert '(size 0.5) (drill 0.2) (net "SIGNAL")' in out.text


@pytest.mark.parametrize("source", [BOARD, "﻿" + BOARD.replace("\n", "\r\n")])
def test_idempotent_and_line_endings(source):
    out = run(source, {"text", "courtyards", "vias"})
    assert run(out.text, {"text", "courtyards", "vias"}).text == out.text
    if source.startswith("﻿"):
        assert out.text.startswith("﻿")
        assert out.text.count("\r\n") == source.count("\r\n")


def test_missing_font_values_and_render_cache():
    source = """(kicad_pcb
      (footprint "x" (layer "F.Cu")
        (property "Reference" "REF**" (effects (font (size 1 1))))
        (fp_text user "x" (effects (font (face "Font") (size 1 1)))
          (render_cache "x" 0 (polygon (pts (xy 0 0)))))
        (fp_text value "x" (effects (justify left)))))"""
    out = run(source, {"text"})
    assert out.counts == {"text items": 3}
    assert "render_cache" not in out.text
    assert out.text.count("(thickness 0.1)") == 3
    assert run(out.text, {"text"}).text == out.text


def test_text_layers_restrict_the_operation():
    settings = replace(DEFAULTS, text_layers=("F.SilkS",))
    out = run(selected={"text"}, settings=settings)
    assert out.counts == {"text items": 3}  # the board text box, the reference and the custom fp_text
    assert "(font (size 1 2) (thickness 0.2) bold italic)" in out.text  # B.SilkS board text untouched


def test_text_without_centring_keeps_justification():
    settings = replace(DEFAULTS, text_center=False, text_keep_upright=False)
    out = run(selected={"text"}, settings=settings)
    assert "(justify left bottom mirror)" in out.text
    assert "(unlocked yes)" in out.text


def test_only_boards_are_board_input():
    footprint = '(footprint "x" (layer "F.Cu") (fp_text user "x" (effects (font (size 1 1)))))'
    with pytest.raises(MaintainError, match="Not a board"):
        run(footprint, {"text"})
    with pytest.raises(MaintainError, match="needs --labels"):
        run(LABELS, {"text"})


def test_library_rename_exact_and_cached_identifiers():
    out = run(SCHEMATIC, set(), command="rename-library", old="bac Library v1", new="bac Library Symbols v1")
    assert out.counts == {"cached symbols": 1, "symbol references": 1}
    assert '(symbol "bac Library Symbols v1:C"' in out.text
    assert '(lib_id "bac Library Symbols v1:C")' in out.text
    assert '(lib_id "bac Library v10:C")' in out.text
    assert '(property "Value" "bac Library v1:C")' in out.text
    assert '(text "bac Library v1:C"' in out.text
    again = run(out.text, set(), command="rename-library", old="bac Library v1", new="bac Library Symbols v1")
    assert again.text == out.text


def test_library_rename_collision_is_refused():
    source = '(kicad_sch (lib_symbols (symbol "old:C") (symbol "new:C")))'
    with pytest.raises(MaintainError, match="new:C"):
        run(source, set(), command="rename-library", old="old", new="new")


def test_schematic_label_sizes_only():
    out = run(LABELS, {"labels"})
    assert out.counts == {"labels": 3}
    assert out.text.count("(size 1.27 1.27)") == 3
    for item in parse(LABELS).children():
        if item.head not in LABEL_HEADS:
            assert LABELS[item.start : item.end] in out.text
    for unchanged in (
        "(thickness 0.08)",
        "(justify left bottom) hide",
        "(at 1 2 90)",
        '(face "Font")',
        "bold italic",
        '(property "Intersheetrefs" "${INTERSHEET_REFS}"\n      (effects (font (size 2 2))))',
    ):
        assert unchanged in out.text
    assert run(out.text, {"labels"}).text == out.text


def test_label_missing_font_and_custom_size():
    source = '(kicad_sch (label "a") (global_label "b" (effects (justify right))))'
    out = run(source, {"labels"})
    assert out.counts == {"labels": 2}
    assert out.text.count("(size 1.27 1.27)") == 2
    assert "(justify right)" in out.text
    assert run(out.text, {"labels"}).text == out.text
    out = run(source, {"labels"}, replace(DEFAULTS, label_size_mil=60))
    assert out.text.count("(size 1.524 1.524)") == 2


def test_stats_for_board_and_schematic():
    board = inspect_stats(parse(BOARD))
    assert sum(board["text"].values()) == 6
    assert sum(board["vias"].values()) == 3
    assert "0.6/0.3 mm, through, net GND" in board["vias"]
    assert "B.SilkS: 1 × 2 mm / 0.2 mm" in board["text"]
    sheet = inspect_stats(parse(LABELS))
    assert sheet == {
        "labels": {"global_label: 1 × 1 mm": 1, "hierarchical_label: 0.7 × 0.7 mm": 1, "label: 0.9 × 1.1 mm": 1}
    }


def test_nothing_to_change_is_byte_identical():
    out = run(selected={"text", "courtyards", "vias"})
    assert run(out.text, {"text", "courtyards", "vias"}).text == out.text
    assert run("(kicad_pcb (version 1))", {"text", "courtyards", "vias"}).text == "(kicad_pcb (version 1))"


def test_config_file_values_and_errors(tmp_path):
    config = tmp_path / "rules.toml"
    config.write_text('[text]\nwidth = 0.9\nheight = 0.7\n[files]\nexclude = ["ignore.kicad_pcb"]\n', encoding="utf-8")
    settings = load_settings(str(config))
    assert (settings.text_width, settings.text_height, settings.exclude) == (0.9, 0.7, ("ignore.kicad_pcb",))
    assert settings.enabled() == {"text", "courtyards"}
    for bad in (
        '[text]\nwidth = "wrong"\n',
        "[text]\nwidht = 0.8\n",
        "[vias]\ndrill = 0.5\ndiameter = 0.4\n",
        '[vias]\ntypes = ["buried"]\n',
        "[labels]\nsize_mil = 0.001\n",
        "[other]\nx = 1\n",
    ):
        config.write_text(bad, encoding="utf-8")
        with pytest.raises(ConfigError):
            load_settings(str(config))
    assert load_settings(None) == DEFAULTS  # no file: the defaults


KICAD10 = (
    "(kicad_pcb\r\n"
    "\t(version 20250114)\r\n"
    '\t(footprint "A:B"\r\n'
    '\t\t(layer "F.Cu")\r\n'
    '\t\t(property "Reference" "U1"\r\n'
    "\t\t\t(at 0 0 90)\r\n"
    "\t\t\t(unlocked yes)\r\n"
    '\t\t\t(layer "F.SilkS")\r\n'
    "\t\t\t(effects\r\n"
    "\t\t\t\t(font\r\n"
    "\t\t\t\t\t(size 1.27 1.27)\r\n"
    "\t\t\t\t)\r\n"
    "\t\t\t\t(justify left top mirror)\r\n"
    "\t\t\t)\r\n"
    "\t\t)\r\n"
    '\t\t(property "Value" "IC"\r\n'
    "\t\t\t(effects\r\n"
    "\t\t\t\t(font\r\n"
    "\t\t\t\t\t(size 0.8 0.8)\r\n"
    "\t\t\t\t\t(thickness 0.1)\r\n"
    "\t\t\t\t)\r\n"
    "\t\t\t\t(justify left)\r\n"
    "\t\t\t)\r\n"
    "\t\t)\r\n"
    "\t)\r\n"
    ")\r\n"
)


def test_kicad10_layout_edits_whole_lines():
    """KiCad 10 writes one child per line: a removed list takes its line, an added one gets its own."""
    out = run(KICAD10, {"text"})
    assert out.counts == {"text items": 2}
    assert "(unlocked yes)" not in out.text
    assert "\t\t\t\t\t(size 0.8 0.8)\r\n\t\t\t\t\t(thickness 0.1)\r\n\t\t\t\t)\r\n" in out.text
    assert "\t\t\t\t(justify mirror)\r\n" in out.text
    assert "(justify left)" not in out.text and "(justify)" not in out.text
    assert out.text.count("\r\n") == KICAD10.count("\r\n") - 1  # unlocked and justify left out, thickness in
    assert "\r\n\r\n" not in out.text and " \r\n" not in out.text
    assert run(out.text, {"text"}).text == out.text


VERTICAL = (
    "(kicad_pcb\n"
    "\t(version 20250114)\n"
    '\t(gr_text "note"\n'
    '\t\t(layer "F.SilkS")\n'
    "\t\t(effects\n"
    "\t\t\t(justify left)\n"
    "\t\t)\n"
    '\t\t(render_cache "note" 0\n'
    "\t\t\t(polygon\n"
    "\t\t\t\t(pts\n"
    "\t\t\t\t\t(xy 0 0)\n"
    "\t\t\t\t)\n"
    "\t\t\t)\n"
    "\t\t)\n"
    "\t)\n"
    "\t(via\n"
    "\t\t(at 1 1)\n"
    "\t\t(size 0.6)\n"
    "\t\t(drill 0.3)\n"
    "\t\t(net 0)\n"
    "\t)\n"
    ")\n"
)


def test_vertical_layout_without_font_and_with_render_cache():
    """An effects without font gets one; a multi-line render_cache goes with all its lines."""
    out = run(VERTICAL, {"text", "vias"})
    assert out.counts == {"text items": 1, "vias skipped, unconnected": 1}
    assert "render_cache" not in out.text and "polygon" not in out.text
    assert "\t\t(effects\n\t\t\t(font (size 0.8 0.8) (thickness 0.1))\n\t\t)\n\t)\n\t(via\n" in out.text
    assert "(justify left)" not in out.text
    assert run(out.text, {"text", "vias"}).text == out.text
