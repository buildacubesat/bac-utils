# SPDX-License-Identifier: MIT
from __future__ import annotations

import re
from pathlib import Path

import pytest
from bac_kicad_libcheck import __version__, cli
from bac_kicad_libcheck.config import CONFIG_NAME, load_config
from bac_kicad_libcheck.kicadcli import extract
from bac_kicad_libcheck.scan import build_scan, resolve_model_path

from bac_common.errors import ConfigError
from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-kicad-libcheck"


def value(stdout: str, label: str) -> str | None:
    m = re.search(rf"{re.escape(label)}\s+:\s+(\S+)", stdout)
    return m.group(1) if m else None


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


# --- config -----------------------------------------------------------------


def test_load_config_resolves_paths_relative_to_file(project):
    cfg = load_config(project / CONFIG_NAME)
    assert cfg.root == project.resolve()
    assert cfg.schematic == project.resolve() / "library.kicad_sch"
    assert [(e.nickname, e.path.name) for e in cfg.symbol_libraries] == [("bac", "bac.kicad_symdir")]
    assert cfg.model_vars == {"BAC_LIB_DIR": "."}
    assert cfg.erc_types == ["lib_symbol_mismatch", "lib_symbol_issues"]


def test_load_config_errors_point_at_init(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path / CONFIG_NAME)
    assert "--init" in (exc.value.detail or "")
    bad = tmp_path / CONFIG_NAME
    bad.write_text('[project]\nschematic = "a.kicad_sch"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="missing 'board'"):
        load_config(bad)
    bad.write_text('[project]\nschematic = "a.kicad_sch"\nboard = "a.kicad_pcb"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="at least one"):
        load_config(bad)


def test_init_writes_template_once(tmp_path):
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 0, r.output
    written = tmp_path / CONFIG_NAME
    assert written.is_file() and "[[symbol_library]]" in written.read_text(encoding="utf-8")
    written.write_text("# mine\n", encoding="utf-8")
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 0 and "left unchanged" in r.stdout
    assert written.read_text(encoding="utf-8") == "# mine\n"


# --- scan -------------------------------------------------------------------


def test_scan_finds_inventory_usage_and_models(project):
    scan = build_scan(load_config(project / CONFIG_NAME))
    assert scan.symbol_inventory == {"bac:bac R", "bac:TI TPSM5D1806RDBR"}
    assert scan.footprint_inventory == {"bac:R-0603-100k", "bac:TI-TPSM5D1806RDBR"}
    assert [(u.lib_id, u.reference) for u in scan.symbol_usage] == [
        ("bac:bac R", "R1"),
        ("bac:bac R", "R2"),
        ("other:Widget", "U9"),
    ]
    assert [(u.lib_id, u.reference) for u in scan.footprint_usage] == [
        ("bac:TI-TPSM5D1806RDBR", "U1"),
        ("bac:TI-TPSM5D1806RDBR", "U2"),
    ]
    by_id = {m.lib_id: m for m in scan.models}
    assert not by_id["bac:R-0603-100k"].exists and "KICAD8_3DMODEL_DIR" in by_id["bac:R-0603-100k"].note
    assert by_id["bac:TI-TPSM5D1806RDBR"].exists
    assert by_id["bac:TI-TPSM5D1806RDBR"].resolved == project.resolve() / "3d" / "TI-TPSM5D1806RDBR.step"
    assert scan.footprints_without_model == []
    assert scan.warnings == []


def test_scan_warns_about_missing_inputs(project):
    cfg = load_config(project / CONFIG_NAME)
    (project / "library.kicad_pcb").unlink()
    scan = build_scan(cfg)
    assert scan.footprint_usage == [] and any("board not found" in w for w in scan.warnings)


def test_resolve_model_path_variants(project, monkeypatch):
    cfg = load_config(project / CONFIG_NAME)
    assert resolve_model_path("${KIPRJMOD}/3d/x.step", cfg) == (cfg.root / "3d" / "x.step", "")
    monkeypatch.setenv("SOME_3D_DIR", str(project / "3d"))
    p, note = resolve_model_path("${SOME_3D_DIR}/x.step", cfg)
    assert p == project / "3d" / "x.step" and note == ""
    p, note = resolve_model_path("${NOPE}/x.step", cfg)
    assert p is None and note == "unresolved path variable ${NOPE}"
    p, note = resolve_model_path("3d\\x.step", cfg)
    assert p == cfg.root / "3d" / "x.step"


def test_extract_reads_erc_sheets_and_drc_top_level():
    erc = {
        "sheets": [
            {
                "violations": [
                    {
                        "type": "lib_symbol_mismatch",
                        "severity": "warning",
                        "description": "d",
                        "items": [{"description": "Symbol R1"}],
                    }
                ]
            }
        ]
    }
    violations, seen = extract(erc, "erc", ["lib_symbol_mismatch"])
    assert [(v.kind, v.type, v.items) for v in violations] == [("erc", "lib_symbol_mismatch", ["Symbol R1"])]
    assert seen == {"lib_symbol_mismatch"}
    drc = {"violations": [{"type": "clearance", "severity": "error", "description": "x", "items": []}]}
    violations, seen = extract(drc, "drc", ["lib_footprint_mismatch"])
    assert violations == [] and seen == {"clearance"}


# --- cli --------------------------------------------------------------------


def test_run_reports_placement_and_model_failures(project, no_kicad_cli):
    r = invoke(cli._main, [])
    assert r.exit_code == 1, r.output
    out = r.stdout
    assert "bac:TI TPSM5D1806RDBR – in library, never placed" in out
    assert "bac:bac R – placed 2× (R1, R2)" in out
    assert "other:Widget – placed (U9) but not in a declared library" in out
    assert "bac:R-0603-100k – in library, never placed" in out
    assert "bac:TI-TPSM5D1806RDBR – placed 2× (U1, U2)" in out
    assert "unresolved path variable ${KICAD8_3DMODEL_DIR}" in out
    assert "ERC not run – kicad-cli not found on PATH" in out
    assert "DRC not run – kicad-cli not found on PATH" in out
    assert value(out, "Failures") == "6" and value(out, "Warnings") == "2"


def test_skip_sync_and_strict(project, no_kicad_cli):
    r = invoke(cli._main, ["--skip-sync"])
    assert "skipped (--skip-sync)" in r.stdout and "ERC not run" not in r.stdout
    assert value(r.stdout, "Warnings") == "0"


def test_clean_project_passes(project, fake_kicad_cli):
    """Place everything once and give R-0603 a real model: no failures, exit 0."""
    for name in ("library.kicad_sch", "library.kicad_pcb"):
        (project / name).write_text(_place_everything(project / name), encoding="utf-8")
    mod = project / "libs" / "bac.pretty" / "R-0603-100k.kicad_mod"
    mod.write_text(
        mod.read_text(encoding="utf-8").replace(
            "${KICAD8_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_1608Metric.wrl",
            "${BAC_LIB_DIR}/3d/TI-TPSM5D1806RDBR.step",
        ),
        encoding="utf-8",
    )
    fake_kicad_cli(
        erc={
            "sheets": [
                {"violations": [{"type": "pin_not_connected", "severity": "error", "description": "x", "items": []}]}
            ]
        },
        drc={"violations": []},
    )
    r = invoke(cli._main, [])
    assert r.exit_code == 0, r.output
    assert "all 2 symbol(s) placed exactly once" in r.stdout
    assert "all 2 footprint(s) placed exactly once" in r.stdout
    assert "all 2 model reference(s) resolve" in r.stdout
    assert "ERC reports no library mismatches" in r.stdout and "never appeared in the report" in r.stdout
    assert "DRC reports no library mismatches" in r.stdout
    assert value(r.stdout, "Failures") == "0"
    assert [c[1:3] for c in fake_kicad_cli.calls] == [["sch", "erc"], ["pcb", "drc"]]
    assert all("--format" in c and "json" in c for c in fake_kicad_cli.calls)


def test_sync_violations_fail_the_run(project, fake_kicad_cli):
    fake_kicad_cli(
        erc={
            "sheets": [
                {
                    "violations": [
                        {
                            "type": "lib_symbol_mismatch",
                            "severity": "warning",
                            "description": "Symbol differs",
                            "items": [{"description": "Symbol R1 [bac R]"}],
                        }
                    ]
                }
            ]
        },
        drc={
            "violations": [
                {
                    "type": "lib_footprint_mismatch",
                    "severity": "warning",
                    "description": "Footprint differs",
                    "items": [{"description": "Footprint U1"}],
                }
            ]
        },
    )
    r = invoke(cli._main, ["--config", str(project / CONFIG_NAME)])
    assert r.exit_code == 1
    assert "ERC lib_symbol_mismatch: Symbol differs" in r.stdout and "Symbol R1 [bac R]" in r.stdout
    assert "DRC lib_footprint_mismatch: Footprint differs" in r.stdout


def test_strict_turns_warnings_into_failure(project, fake_kicad_cli):
    """A fully placed project whose only finding is a footprint without a model."""
    mod = project / "libs" / "bac.pretty" / "R-0603-100k.kicad_mod"
    text = mod.read_text(encoding="utf-8")
    mod.write_text(_drop_list(text, text.index("\t(model ")), encoding="utf-8")
    for name in ("library.kicad_sch", "library.kicad_pcb"):
        (project / name).write_text(_place_everything(project / name), encoding="utf-8")
    r = invoke(cli._main, [])
    assert r.exit_code == 0, r.output
    assert "bac:R-0603-100k – no 3D model attached" in r.stdout
    r = invoke(cli._main, ["--strict"])
    assert r.exit_code == 1 and "Warnings treated as failures" in r.stdout


def _drop_list(text: str, start: int) -> str:
    """Remove the s-expression list that opens at ``start`` (fixture text has no parens inside strings)."""
    depth, i = 0, text.index("(", start)
    while True:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
        if depth == 0:
            break
    return text[:start] + text[i:].lstrip("\n")


def _place_everything(path: Path) -> str:
    """The fixture with every library item placed exactly once and the foreign symbol removed."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".kicad_sch":
        text = text.replace('(lib_id "bac:bac R")\n', '(lib_id "bac:TI TPSM5D1806RDBR")\n', 1)
        return _drop_list(text, text.rfind("\t(symbol\n", 0, text.index("other:Widget")))
    return text.replace('(footprint "bac:TI-TPSM5D1806RDBR"', '(footprint "bac:R-0603-100k"', 1)


def test_missing_config_is_a_config_error(tmp_path):
    r = invoke(cli._main, [])
    assert r.exit_code == 1
    assert "Config file not found" in r.stderr and "--init" in r.stderr


def test_model_with_wrong_extension_names_the_sibling(project):
    mod = project / "libs" / "bac.pretty" / "TI-TPSM5D1806RDBR.kicad_mod"
    mod.write_text(
        mod.read_text(encoding="utf-8").replace("TI-TPSM5D1806RDBR.step", "TI-TPSM5D1806RDBR.wrl"), encoding="utf-8"
    )
    scan = build_scan(load_config(project / CONFIG_NAME))
    ref = next(m for m in scan.models if m.lib_id == "bac:TI-TPSM5D1806RDBR")
    assert not ref.exists and ref.note == "but TI-TPSM5D1806RDBR.step exists"


def test_help_fits_eighty_columns(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    assert_standard_flags(cli._main, TOOL, __version__)


def test_kicad_cli_failure_modes(monkeypatch, tmp_path):
    import subprocess

    from bac_kicad_libcheck import kicadcli
    from bac_kicad_libcheck.kicadcli import run_erc

    monkeypatch.setattr(kicadcli.shutil, "which", lambda name: "/usr/bin/kicad-cli")
    monkeypatch.setattr(
        kicadcli.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 3, "", "Error: cannot open\n")
    )
    result = run_erc("kicad-cli", tmp_path / "x.kicad_sch", ["lib_symbol_mismatch"])
    assert not result.available and result.error == "ERC: no report produced – Error: cannot open"

    def garbage(cmd, **kw):
        Path(cmd[cmd.index("-o") + 1]).write_text("{not json", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(kicadcli.subprocess, "run", garbage)
    result = run_erc("kicad-cli", tmp_path / "x.kicad_sch", ["lib_symbol_mismatch"])
    assert not result.available and result.error.startswith("ERC: unreadable report")

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))

    monkeypatch.setattr(kicadcli.subprocess, "run", slow)
    result = run_erc("kicad-cli", tmp_path / "x.kicad_sch", ["lib_symbol_mismatch"])
    assert not result.available and result.error.startswith("ERC: Command")
