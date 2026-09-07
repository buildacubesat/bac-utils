# SPDX-License-Identifier: MIT
from __future__ import annotations

import re
from pathlib import Path

from bac_kicad_symfields import __version__, cli

from bac_common.testing import invoke

TOOL = "bac-kicad-symfields"
EXAMPLE_RULES = Path(__file__).resolve().parents[1] / "examples" / "rules"


def value(stdout: str, label: str) -> str | None:
    """The value of a summary row, whatever the alignment padding."""
    m = re.search(rf"{re.escape(label)}\s+:\s+(\S+)", stdout)
    return m.group(1) if m else None


def snapshot(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _help_lines(*argv: str) -> list[str]:
    r = invoke(cli._main, [*argv, "--help"])
    assert r.exit_code == 0, r.output
    assert "--debug" not in r.stdout
    return r.stdout.rstrip().splitlines()


def test_version_and_help_lengths():
    r = invoke(cli._main, ["-v"])
    assert r.exit_code == 0 and r.stdout.strip() == f"{TOOL} v{__version__}"
    for argv in ((), ("fields",), ("lint",), ("fix",), ("init",)):
        assert len(_help_lines(*argv)) <= 24, argv
    assert "Build a CubeSat" in "\n".join(_help_lines())
    assert invoke(cli._main, []).exit_code == 0


def test_lint_reports_and_exits_one(library):
    r = invoke(cli._main, ["lint", str(library)])
    assert r.exit_code == 1, r.output
    assert "✗ bac-r.kicad_sym: 10 finding(s)" in r.stdout and "✓ ti-tpsm5d1806rdbr.kicad_sym" in r.stdout
    assert "✗ TI-TPSM5D1806RDBR.kicad_mod: 4 finding(s)" in r.stdout
    assert "Findings" in r.stdout and "1.27 or 0.762" in r.stdout and "unique" in r.stdout
    r = invoke(cli._main, ["lint", str(library / "bac.kicad_symdir" / "ti-tpsm5d1806rdbr.kicad_sym")])
    assert r.exit_code == 0 and value(r.stdout, "Findings") == "0"


def test_lint_with_rules_reports_missing_fields(library):
    r = invoke(
        cli._main,
        ["lint", str(library / "bac.kicad_symdir" / "ti-tpsm5d1806rdbr.kicad_sym"), "--rules", str(EXAMPLE_RULES)],
    )
    assert r.exit_code == 1
    assert "field Manufacturer PN" in r.stdout and "missing" in r.stdout and "(placeholder)" in r.stdout


def test_fields_dry_run_writes_nothing(library):
    before = snapshot(library)
    r = invoke(cli._main, ["fields", str(library), "--rules", str(EXAMPLE_RULES), "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "+ Manufacturer PN = (empty placeholder)" in r.stdout and "~ Max Height = 0.55 mm" in r.stdout
    assert "+ Land Pattern = IPC-7351 nominal" in r.stdout and "Would write" in r.stdout
    assert "dry run – no changes made" in r.stdout and value(r.stdout, "Files to write") == "3"
    assert snapshot(library) == before


def test_fields_asks_then_writes_with_backups_and_is_idempotent(library, monkeypatch):
    ti = library / "bac.kicad_symdir" / "ti-tpsm5d1806rdbr.kicad_sym"
    original = ti.read_text(encoding="utf-8")
    monkeypatch.setattr("bac_common.ui.console.input", lambda prompt: "n")
    r = invoke(cli._main, ["fields", str(library), "--rules", str(EXAMPLE_RULES)])
    assert r.exit_code == 0 and "Aborted" in r.stdout and ti.read_text(encoding="utf-8") == original

    monkeypatch.setattr("bac_common.ui.console.input", lambda prompt: "y")
    r = invoke(cli._main, ["fields", str(library), "--rules", str(EXAMPLE_RULES)])
    assert r.exit_code == 0, r.output
    assert (
        value(r.stdout, "Files written") == "3"
        and (library / "bac.kicad_symdir" / "ti-tpsm5d1806rdbr.kicad_sym.bak").read_text(encoding="utf-8") == original
    )
    edited = ti.read_text(encoding="utf-8")
    assert (
        '(property "Manufacturer PN" ""\n\t\t\t(at 0 0 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(hide yes)'
        in edited
    )
    # Only insertions: removing the added blocks gives the original back.
    start = edited.index('\t\t(property "Manufacturer" ""')
    end = edited.index('\t\t(symbol "TI TPSM5D1806RDBR_0_1"')
    assert edited[: start - 1] + edited[end - 1 :] == original

    r = invoke(cli._main, ["fields", str(library), "--rules", str(EXAMPLE_RULES), "--yes", "--no-backup"])
    assert r.exit_code == 0 and "Nothing to write" in r.stdout and value(r.stdout, "Fields added") == "0"
    assert ti.read_text(encoding="utf-8") == edited


def test_fields_overwrite_gate(library, tmp_path):
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "00.toml").write_text(
        'target = "symbol"\n[[field]]\nname = "Tolerance"\nvalue = "5%"\noverwrite = true\n', encoding="utf-8"
    )
    r = invoke(
        cli._main, ["fields", str(library / "bac.kicad_symdir" / "bac-r.kicad_sym"), "--rules", str(rules), "--dry-run"]
    )
    assert "would overwrite '1%'; needs --allow-overwrite" in r.stdout and value(r.stdout, "Rules skipped") == "1"
    r = invoke(
        cli._main,
        [
            "fields",
            str(library / "bac.kicad_symdir" / "bac-r.kicad_sym"),
            "--rules",
            str(rules),
            "--allow-overwrite",
            "--yes",
        ],
    )
    assert r.exit_code == 0 and "! Tolerance = 1% → 5%" in r.stdout
    assert '(property "Tolerance" "5%"' in (library / "bac.kicad_symdir" / "bac-r.kicad_sym").read_text(
        encoding="utf-8"
    )


def test_fix_then_lint_clean(library):
    r = invoke(cli._main, ["fix", str(library), "--dry-run"])
    assert r.exit_code == 0 and value(r.stdout, "Sizes corrected") == "10" and "Would write" in r.stdout
    r = invoke(cli._main, ["fix", str(library), "--yes"])
    assert r.exit_code == 0 and value(r.stdout, "Files written") == "1"
    assert (library / "bac.kicad_symdir" / "bac-r.kicad_sym.bak").exists()
    r = invoke(cli._main, ["lint", str(library / "bac.kicad_symdir")])
    assert r.exit_code == 0, r.output
    r = invoke(cli._main, ["fix", str(library), "--yes"])
    assert "nothing to fix" in r.stdout and value(r.stdout, "Files written") == "0"


def test_init_and_config_change_the_lint(library, tmp_path):
    r = invoke(cli._main, ["init"])
    path = tmp_path / "config" / "bac" / "bac-kicad-symfields.toml"
    assert r.exit_code == 0 and path.exists() and "✓ Wrote" in r.stdout
    assert "exists; left" in invoke(cli._main, ["init"]).stdout
    path.write_text(f'rules = "{EXAMPLE_RULES}"\n[symbol]\nproperty_sizes = [1.27, 0.762, 0.635]\n', encoding="utf-8")
    r = invoke(cli._main, ["lint", str(library / "bac.kicad_symdir" / "bac-r.kicad_sym")])
    assert r.exit_code == 1 and "field" in r.stdout and "0.635" not in r.stdout  # rules from config, sizes accepted
    r = invoke(cli._main, ["fields", str(library / "bac.kicad_symdir"), "--dry-run"])
    assert r.exit_code == 0 and "Applying 4 rule file(s)" in r.stdout
    path.write_text('[symbol]\nproperty_sizes = "big"\n', encoding="utf-8")
    r = invoke(cli._main, ["lint", str(library)])
    assert r.exit_code == 1 and "ERROR [symbol] property_sizes" in r.stderr


def test_usage_errors(library, tmp_path):
    r = invoke(cli._main, ["fields", str(library)])
    assert r.exit_code == 2 and "No rules directory" in r.stderr and "init" in r.stderr
    r = invoke(cli._main, ["fields", str(library), "--rules", str(tmp_path / "nope")])
    assert r.exit_code == 2 and "Rules directory not found" in r.stderr
    r = invoke(cli._main, ["lint", str(tmp_path / "missing")])
    assert r.exit_code == 2 and "No such file" in r.stderr
    (tmp_path / "broken.kicad_sym").write_text("(kicad_symbol_lib (symbol", encoding="utf-8")
    r = invoke(cli._main, ["lint", str(tmp_path / "broken.kicad_sym")])
    assert r.exit_code == 1 and "no complete top-level expression" in r.stderr and "Traceback" not in r.stderr


def test_failed_write_exits_one(library, monkeypatch):
    from bac_common.errors import BacError

    def refuse(path, text, *, backup=True):
        raise BacError(f"Cannot write {path}", "Read-only file system")

    monkeypatch.setattr(cli, "write_back", refuse)
    r = invoke(cli._main, ["fix", str(library), "--yes"])
    assert r.exit_code == 1 and "Cannot write" in r.stdout and value(r.stdout, "Files written") == "0"
    r = invoke(cli._main, ["fields", str(library), "--rules", str(EXAMPLE_RULES), "--yes"])
    assert r.exit_code == 1 and value(r.stdout, "Files written") == "0"


def test_help_fits_eighty_columns(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    for argv in ([], ["fields"], ["lint"], ["fix"]):
        assert len(_help_lines(*argv)) <= 24
