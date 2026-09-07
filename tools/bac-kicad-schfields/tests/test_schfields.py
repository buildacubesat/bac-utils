# SPDX-License-Identifier: MIT
from __future__ import annotations

import re
from pathlib import Path

from bac_kicad_schfields import __version__, cli
from bac_kicad_schfields.schematic import process_sheet, walk_hierarchy

from bac_common import sexp
from bac_common.testing import assert_standard_flags, invoke
from bac_kicad_common.rules import load_rules_dir

TOOL = "bac-kicad-schfields"
EXAMPLE_RULES = Path(__file__).resolve().parents[1] / "examples" / "rules"


def value(stdout: str, label: str) -> str | None:
    m = re.search(rf"{re.escape(label)}\s+:\s+(\S+)", stdout)
    return m.group(1) if m else None


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_walk_hierarchy_counts_reused_sheets(project):
    h = walk_hierarchy(project / "board.kicad_sch")
    assert [(s.path.name, s.instantiations) for s in h.sheets] == [("board.kicad_sch", 1), ("power.kicad_sch", 2)]
    assert h.warnings == []
    (project / "board.kicad_sch").write_text(
        (project / "board.kicad_sch")
        .read_text(encoding="utf-8")
        .replace('"power.kicad_sch"', '"missing.kicad_sch"', 1),
        encoding="utf-8",
    )
    h = walk_hierarchy(project / "board.kicad_sch")
    assert any("sheet not found" in w for w in h.warnings) and len(h.sheets) == 3


def test_process_sheet_fields_and_flags(project):
    rulesets = load_rules_dir(EXAMPLE_RULES, target="schematic")
    path = project / "board.kicad_sch"
    text, root = sexp.parse_file(path)

    new_text, results = process_sheet(path, text, root, rulesets)
    by_ref = {r.reference: r for r in results}
    assert [c.kind for c in by_ref["R1"].changes] == ["fill"] and by_ref["R1"].changes[0].value == "RC0603FR-0710KL"
    assert by_ref["R2"].skipped == [("Manufacturer PN", "would overwrite 'OLD-PN'; needs --allow-overwrite")]
    assert [s[0] for s in by_ref["TP1"].skipped] == ["dnp", "in_bom"] and "needs --allow-flags" in by_ref[
        "TP1"
    ].skipped[0][1]
    assert new_text == text.replace(
        '(property "Manufacturer PN" ""', '(property "Manufacturer PN" "RC0603FR-0710KL"', 1
    )

    new_text, results = process_sheet(path, text, root, rulesets, allow_overwrite=True, allow_flags=True)
    by_ref = {r.reference: r for r in results}
    assert [(c.kind, c.previous, c.value) for c in by_ref["R2"].changes] == [("set", "OLD-PN", "RC0603FR-071KL")]
    assert [(c.kind, c.key, c.previous, c.value) for c in by_ref["TP1"].changes] == [
        ("flag", "dnp", "unset", "yes"),
        ("flag", "in_bom", "unset", "no"),
    ]
    tp = sexp.parse(new_text).children("symbol")[2]
    assert tp.child("dnp").value(1) == "yes" and tp.child("in_bom").value(1) == "no"
    # The flags were inserted right after (unit 1), on their own lines.
    assert "\t\t(unit 1)\n\t\t(dnp yes)\n\t\t(in_bom no)\n\t\t(uuid" in new_text
    # Idempotent.
    again, results = process_sheet(
        path, new_text, sexp.parse(new_text), rulesets, allow_overwrite=True, allow_flags=True
    )
    assert again == new_text and results == []


def test_process_sheet_adds_fields_and_edits_existing_flag(project, tmp_path):
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "10.toml").write_text(
        'target = "schematic"\n[match]\nreference_regex = ["^C"]\n\n'
        '[[field]]\nname = "Checked By"\nvalue = "MI"\nhide = true\n\n'
        '[[flag]]\nname = "dnp"\nvalue = true\n',
        encoding="utf-8",
    )
    rulesets = load_rules_dir(rules, target="schematic")
    path = project / "power.kicad_sch"
    text, root = sexp.parse_file(path)
    new_text, results = process_sheet(path, text, root, rulesets, allow_flags=True)
    assert results[0].reference == "C1" and [c.kind for c in results[0].changes] == ["add", "flag"]
    assert (
        '\t\t(property "Checked By" "MI"\n\t\t\t(at 76.2 63.5 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)\n\t\t\t)\n\t\t)\n\t\t(instances'
        in new_text
    )
    assert "(dnp yes)" in new_text and "(dnp no)" not in new_text
    assert (
        new_text.replace("(dnp yes)", "(dnp no)").replace(
            new_text[new_text.index('\t\t(property "Checked By"') : new_text.index("\t\t(instances")], ""
        )
        == text
    )


def test_cli_dry_run_confirm_write_and_cache(project, monkeypatch):
    board = project / "board.kicad_sch"
    original = board.read_text(encoding="utf-8")
    r = invoke(cli._main, [str(board), "--rules", str(EXAMPLE_RULES), "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "power.kicad_sch is instantiated 2×" in r.stdout and "~ Manufacturer PN = RC0603FR-0710KL" in r.stdout
    assert "· dnp skipped" in r.stdout and value(r.stdout, "Sheets to write") == "1" and "dry run" in r.stdout
    assert board.read_text(encoding="utf-8") == original

    monkeypatch.setattr("bac_common.ui.console.input", lambda prompt: "")
    r = invoke(cli._main, [str(board), "--rules", str(EXAMPLE_RULES)])
    assert r.exit_code == 0 and "Aborted" in r.stdout and board.read_text(encoding="utf-8") == original

    r = invoke(cli._main, [str(board), "--rules", str(EXAMPLE_RULES), "--allow-overwrite", "--allow-flags", "--yes"])
    assert r.exit_code == 0, r.output
    assert "! Manufacturer PN = OLD-PN → RC0603FR-071KL" in r.stdout and "* dnp = unset → yes" in r.stdout
    assert (
        value(r.stdout, "Sheets written") == "1"
        and (project / "board.kicad_sch.bak").read_text(encoding="utf-8") == original
    )
    assert value(r.stdout, "Flags changed") == "2" and value(r.stdout, "Values overwritten") == "1"

    r = invoke(cli._main, [str(board), "--rules", str(EXAMPLE_RULES), "--allow-overwrite", "--allow-flags", "--yes"])
    assert "Nothing to write" in r.stdout and value(r.stdout, "Components matched") == "0"

    r = invoke(cli._main, [str(board), "--rules", str(EXAMPLE_RULES), "--include-cache", "--dry-run"])
    assert r.exit_code == 0 and "cache" not in r.stdout  # the cached bac:R has no reference, so no rule matches it


def test_cli_errors(project, tmp_path):
    r = invoke(cli._main, [str(tmp_path / "nope.kicad_sch"), "--rules", str(EXAMPLE_RULES)])
    assert r.exit_code == 2 and "Schematic not found" in r.stderr
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "a.toml").write_text('target = "symbol"\n', encoding="utf-8")
    r = invoke(cli._main, [str(project / "board.kicad_sch"), "--rules", str(tmp_path / "rules")])
    assert r.exit_code == 2 and 'No rule files with target = "schematic"' in r.stderr
    r = invoke(cli._main, [str(project / "board.kicad_sch")])
    assert r.exit_code == 2 and "--rules" in r.stderr
    (project / "broken.kicad_sch").write_text("(kicad_symbol_lib)", encoding="utf-8")
    r = invoke(cli._main, [str(project / "broken.kicad_sch"), "--rules", str(EXAMPLE_RULES)])
    assert r.exit_code == 1 and "not a kicad_sch file" in r.stderr and "Traceback" not in r.stderr


def test_process_sheet_inserts_into_a_symbol_without_properties(project, tmp_path):
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "10.toml").write_text(
        'target = "schematic"\n[match]\nlib_id_regex = ["^x:Bare$"]\n\n[[field]]\nname = "Checked By"\nvalue = "MI"\n',
        encoding="utf-8",
    )
    rulesets = load_rules_dir(rules, target="schematic")
    path = project / "bare.kicad_sch"
    for text in (
        '(kicad_sch\n\t(version 20250114)\n\t(lib_symbols)\n\t(symbol\n\t\t(lib_id "x:Bare")\n\t\t(unit 1)\n\t)\n)\n',
        '(kicad_sch (version 20250114) (lib_symbols) (symbol (lib_id "x:Bare") (unit 1)))',
    ):
        path.write_text(text, encoding="utf-8")
        text, root = sexp.parse_file(path)
        new_text, results = process_sheet(path, text, root, rulesets)
        assert [c.kind for c in results[0].changes] == ["add"]
        new_root = sexp.parse(new_text)
        assert new_root.children("property") == []
        placed = new_root.children("symbol")[0]
        assert placed.child("property").value(1) == "Checked By" and placed.child("unit") is not None


def test_failed_write_exits_one(project, monkeypatch):
    from bac_common.errors import BacError

    def refuse(path, text, *, backup=True):
        raise BacError(f"Cannot write {path}", "Read-only file system")

    monkeypatch.setattr(cli, "write_back", refuse)
    r = invoke(cli._main, [str(project / "board.kicad_sch"), "--rules", str(EXAMPLE_RULES), "--yes"])
    assert (
        r.exit_code == 1 and "✗" in r.stdout and "Cannot write" in r.stdout and value(r.stdout, "Sheets written") == "0"
    )


def test_help_fits_eighty_columns(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    assert_standard_flags(cli._main, TOOL, __version__)
