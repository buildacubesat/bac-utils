# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

from bac_common import sexp

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_FILES = sorted(FIXTURES.iterdir())

SAMPLE = '(symbol "bac R"\n\t(property "Value" "R"\n\t\t(at -1.27 -1.778 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 0.762 0.762)\n\t\t\t)\n\t\t)\n\t)\n\t(pin passive line (at 2.54 0 180) (name "" (effects (font (size 1.27 1.27)))))\n)\n'


def test_parse_records_spans_and_values():
    root = sexp.parse(SAMPLE)
    assert root.head == "symbol" and root.start == 0 and root.end == len(SAMPLE) - 1
    assert SAMPLE[root.start : root.end].startswith("(symbol") and SAMPLE[root.end - 1] == ")"
    prop = root.child("property")
    assert prop is not None and prop.value(1) == "Value" and prop.value(2) == "R"
    name_atom = prop.atoms()[1]
    assert name_atom.quoted and name_atom.raw(SAMPLE) == '"Value"'
    size = prop.child("effects").child("font").child("size")
    assert [a.number() for a in size.atoms()[1:]] == [0.762, 0.762]
    assert size.atoms()[0].number() is None
    assert [n.head for n in root.find_all("size")] == ["size", "size"]
    assert len(list(root.walk())) == 12


def test_helpers_on_missing_children():
    root = sexp.parse("(kicad_symbol_lib (version 20251024) (generator x))")
    assert root.child("nothing") is None
    assert root.value(5) == ""
    assert sexp.format_version(root) == 20251024
    assert sexp.format_version(sexp.parse("(footprint x)")) == 0


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=[p.name for p in FIXTURE_FILES])
def test_fixtures_round_trip_byte_for_byte(path):
    text, root = sexp.parse_file(path)
    assert root.head in ("kicad_symbol_lib", "footprint")
    assert text[root.start : root.end] == text.rstrip("\n")
    # Every recorded span points at what it claims.
    for node in root.walk():
        assert text[node.start] == "(" and text[node.end - 1] == ")"
        for atom in node.atoms():
            raw = atom.raw(text)
            assert (raw.startswith('"') and raw.endswith('"')) is atom.quoted
            assert sexp.unescape(raw[1:-1]) == atom.value if atom.quoted else raw == atom.value
    assert sexp.apply_edits(text, []) == text


def test_strings_with_escapes_and_write_back():
    text = '(property "Description" "Line one\\nsays \\"hi\\" \\\\ tab\\there")'
    root = sexp.parse(text)
    value = root.value(2)
    assert value == 'Line one\nsays "hi" \\ tab\there'
    assert sexp.quoted(value) == '"Line one\\nsays \\"hi\\" \\\\ tab\\there"'
    atom = root.atoms()[2]
    edited = sexp.apply_edits(text, [(atom.start, atom.end, sexp.quoted(value))])
    assert edited == text  # a value written back unchanged is byte-identical
    assert sexp.parse(edited).value(2) == value


def test_apply_edits_orders_and_rejects_overlaps():
    text = "0123456789"
    assert sexp.apply_edits(text, [(2, 4, "AB"), (7, 8, "C"), (0, 0, ">")]) == ">01AB456C89"
    assert sexp.apply_edits(text, [(5, 5, "x"), (5, 5, "y")]) == "01234xy56789"
    with pytest.raises(sexp.SexpError, match="Overlapping"):
        sexp.apply_edits(text, [(2, 5, "a"), (4, 6, "b")])
    with pytest.raises(sexp.SexpError):
        sexp.apply_edits(text, [(5, 4, "a")])


def test_parse_errors_name_the_file():
    with pytest.raises(sexp.SexpError, match="lib.kicad_sym: unbalanced"):
        sexp.parse(")", where="lib.kicad_sym")
    with pytest.raises(sexp.SexpError, match="unterminated string"):
        sexp.parse('(a "b')
    with pytest.raises(sexp.SexpError, match="no complete"):
        sexp.parse("(a (b)")
    with pytest.raises(sexp.SexpError, match="no complete"):
        sexp.parse("   ")


def test_parse_file_errors(tmp_path):
    bad = tmp_path / "x.kicad_sym"
    bad.write_bytes(b"\xff\xfe(a)")
    with pytest.raises(sexp.SexpError, match="not UTF-8"):
        sexp.parse_file(bad)
    with pytest.raises(sexp.SexpError, match="Cannot read"):
        sexp.parse_file(tmp_path / "missing.kicad_sym")


def test_fmt_number_and_indent_helpers():
    assert sexp.fmt_number(0.762) == "0.762"
    assert sexp.fmt_number(1.27) == "1.27"
    assert sexp.fmt_number(0.0) == "0"
    assert sexp.fmt_number(-3.624001) == "-3.624001"
    assert sexp.fmt_number(2.5, places=2) == "2.5"
    text = "(a\n\t\t(b 1)\n  (c)\n"
    assert sexp.line_indent(text, text.index("(b")) == "\t\t"
    assert sexp.line_indent(text, text.index("(c")) == "  "
    assert sexp.line_indent(text, 0) == ""
    assert sexp.indent_unit("\t\t") == "\t" and sexp.indent_unit("    ") == "  "
