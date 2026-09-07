# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

from bac_kicad_symfields.config import Settings
from bac_kicad_symfields.lint import duplicate_uuids, fix_file, lint_file

from bac_common import sexp

FIXTURES = Path(__file__).parent / "fixtures"
SETTINGS = Settings()


def test_lint_bac_r_flags_the_ten_hidden_properties():
    path = FIXTURES / "bac-r.kicad_sym"
    _, root = sexp.parse_file(path)
    findings = lint_file(path, root, SETTINGS)
    assert len(findings) == 10 and {f.kind for f in findings} == {"size"} and all(f.fixable for f in findings)
    assert {f.found for f in findings} == {"0.635"} and findings[0].expected == "1.27 or 0.762"
    assert [f.where for f in findings][:3] == ["property Footprint", "property Datasheet", "property Tolerance"]


def test_lint_clean_files_and_duplicate_uuids():
    _, root = sexp.parse_file(FIXTURES / "ti-tpsm5d1806rdbr.kicad_sym")
    assert lint_file(FIXTURES / "ti-tpsm5d1806rdbr.kicad_sym", root, SETTINGS) == []
    _, root = sexp.parse_file(FIXTURES / "R-0603-100k.kicad_mod")
    assert lint_file(FIXTURES / "R-0603-100k.kicad_mod", root, SETTINGS) == []
    _, root = sexp.parse_file(FIXTURES / "TI-TPSM5D1806RDBR.kicad_mod")
    findings = lint_file(FIXTURES / "TI-TPSM5D1806RDBR.kicad_mod", root, SETTINGS)
    assert [f.kind for f in findings] == ["uuid"] * 4 and all("×2" in f.found for f in findings)
    assert len(duplicate_uuids(root)) == 4 and not any(f.fixable for f in findings)


def test_lint_footprint_prefix_and_pin_sizes(tmp_path):
    path = tmp_path / "x.kicad_sym"
    text = (FIXTURES / "bac-r.kicad_sym").read_text(encoding="utf-8")
    text = text.replace('"bac KiCad Library Footprints v1:R-0603"', '"Resistor_SMD:R_0603"', 1)
    text = text.replace("(size 1.27 1.27)", "(size 1.524 1.524)", 1)  # the Reference property
    text = text.replace(
        '(number "1"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)',
        '(number "1"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1 1)',
    )
    path.write_text(text, encoding="utf-8")
    _, root = sexp.parse_file(path)
    findings = {(f.where, f.kind): f for f in lint_file(path, root, SETTINGS)}
    assert findings[("property Footprint", "prefix")].found == "Resistor_SMD:R_0603"
    assert findings[("property Reference", "size")].found == "1.524"
    assert findings[("pin 1 number", "size")].expected == "1.27"
    assert len(findings) == 13


def test_fix_symbol_sizes_is_minimal_and_idempotent(tmp_path):
    path = FIXTURES / "bac-r.kicad_sym"
    text, root = sexp.parse_file(path)
    new_text, fixed = fix_file(path, text, root, SETTINGS)
    assert len(fixed) == 10 and {f.expected for f in fixed} == {"0.762"}
    assert new_text == text.replace("(size 0.635 0.635)", "(size 0.762 0.762)")  # those ten nodes and nothing else
    root2 = sexp.parse(new_text)
    assert lint_file(path, root2, SETTINGS) == []
    again, fixed_again = fix_file(path, new_text, root2, SETTINGS)
    assert again == new_text and fixed_again == []


def test_fix_footprint_fonts_including_missing_thickness(tmp_path):
    path = tmp_path / "R.kicad_mod"
    text = (FIXTURES / "R-0603-100k.kicad_mod").read_text(encoding="utf-8")
    text = text.replace(
        "(size 0.8 0.8)\n\t\t\t\t(thickness 0.1)", "(size 1 1)\n\t\t\t\t(thickness 0.15)", 1
    )  # Reference
    text = text.replace("(size 0.8 0.8)\n\t\t\t\t(thickness 0.1)", "(size 0.8 0.8)", 1)  # Value: thickness dropped
    path.write_text(text, encoding="utf-8")
    _, root = sexp.parse_file(path)
    findings = lint_file(path, root, SETTINGS)
    assert [(f.where, f.kind, f.found) for f in findings] == [
        ("property Reference", "size", "1"),
        ("property Reference", "thickness", "0.15"),
        ("property Value", "thickness", "none"),
    ]
    new_text, fixed = fix_file(path, text, root, SETTINGS)
    assert len(fixed) == 3
    assert new_text == (FIXTURES / "R-0603-100k.kicad_mod").read_text(encoding="utf-8")
    assert lint_file(path, sexp.parse(new_text), SETTINGS) == []


def test_settings_drive_the_lint():
    strict = Settings(property_sizes=(1.27,), property_fix_size=1.27)
    path = FIXTURES / "bac-r.kicad_sym"
    text, root = sexp.parse_file(path)
    assert len(lint_file(path, root, strict)) == 13  # 0.762 on Value, Package and Rating now count too
    new_text, fixed = fix_file(path, text, root, strict)
    assert len(fixed) == 13 and "(size 0.762" not in new_text and "(size 0.635" not in new_text
    lenient = Settings(property_sizes=(1.27, 0.762, 0.635))
    assert lint_file(path, root, lenient) == []


def test_fields_insert_inside_an_item_without_properties(tmp_path):
    """Multi-line and one-line symbols with no properties get the block inside the symbol, right after its name."""
    from bac_kicad_symfields.items import process_file

    from bac_kicad_common.rules import load_rules_dir

    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "10.toml").write_text(
        'target = "symbol"\n[match]\nname_regex = ["^R"]\n\n[[field]]\nname = "Package"\nvalue = "0603"\n',
        encoding="utf-8",
    )
    rulesets = load_rules_dir(rules, target="symbol")
    lib = tmp_path / "x.kicad_symdir"
    lib.mkdir()
    multi = lib / "r.kicad_sym"
    multi.write_text(
        '(kicad_symbol_lib\n\t(version 20251024)\n\t(symbol "R"\n\t\t(pin_numbers\n\t\t\t(hide yes)\n\t\t)\n\t)\n)\n',
        encoding="utf-8",
    )
    text, root = sexp.parse_file(multi)
    new_text, results = process_file(multi, text, root, rulesets)
    assert [c.kind for c in results[0].changes] == ["add"]
    new_root = sexp.parse(new_text)
    symbol = new_root.children("symbol")[0]
    assert [n.head for n in symbol.children()][:2] == ["property", "pin_numbers"]
    assert symbol.child("property").value(1) == "Package" and symbol.child("property").value(2) == "0603"
    assert new_root.children("property") == []

    one_line = lib / "one.kicad_sym"
    one_line.write_text(
        '(kicad_symbol_lib (version 20251024) (symbol "R2" (pin_numbers (hide yes))))', encoding="utf-8"
    )
    text, root = sexp.parse_file(one_line)
    new_text, results = process_file(one_line, text, root, rulesets)
    new_root = sexp.parse(new_text)
    symbol = new_root.children("symbol")[0]
    assert symbol.value(1) == "R2" and [n.head for n in symbol.children()] == ["property", "pin_numbers"]
    assert new_root.children("property") == [] and new_text.endswith(")))")
