# SPDX-License-Identifier: MIT
"""The command line: flags, discovery, confirmation, backups, exit codes, the reports."""

from __future__ import annotations

import json
import re
from pathlib import Path

from bac_kicad_maintain import __version__, cli
from maintain_testkit import BOARD, LABELS, SCHEMATIC

from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-kicad-maintain"


def call(*argv: str):
    return invoke(cli._main, list(argv))


def value(stdout: str, label: str) -> str | None:
    m = re.search(rf"{re.escape(label)}\s+:\s+(\S+)", stdout)
    return m.group(1) if m else None


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return path


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_no_command_prints_help():
    r = call()
    assert r.exit_code == 0 and "Commands:" in r.stdout


def test_check_apply_backup_and_second_run(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", BOARD.replace("\n", "\r\n"))
    original = board.read_bytes()

    r = call("check", str(board))
    assert r.exit_code == 1, r.output
    assert "text items: 6" in r.stdout and "courtyard lines: 2" in r.stdout
    assert board.read_bytes() == original

    r = call("apply", str(board), "--dry-run")
    assert r.exit_code == 0 and "dry run" in r.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["board.kicad_pcb"]

    r = call("apply", str(board), "--yes")
    assert r.exit_code == 0, r.output
    assert "Wrote" in r.stdout and value(r.stdout, "Files written") == "1"
    backup = tmp_path / "board.kicad_pcb.bak"
    assert backup.read_bytes() == original
    maintained = board.read_bytes()
    assert maintained != original and b"\r\n" in maintained and b"(size 0.8 0.8)" in maintained

    assert call("check", str(board)).exit_code == 0
    r = call("apply", str(board), "--yes")
    assert r.exit_code == 0 and "nothing to change" in r.stdout
    assert board.read_bytes() == maintained


def test_apply_asks_before_writing(tmp_path, monkeypatch):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    monkeypatch.setattr("bac_common.ui.console.input", lambda prompt: "n")
    r = call("apply", str(board))
    assert r.exit_code == 0 and "Aborted" in r.stdout
    assert board.read_text(encoding="utf-8") == BOARD
    monkeypatch.setattr("bac_common.ui.console.input", lambda prompt: "y")
    r = call("apply", str(board), "--no-backup")
    assert r.exit_code == 0 and "Wrote" in r.stdout
    assert not (tmp_path / "board.kicad_pcb.bak").exists()


def test_malformed_file_stops_the_batch(tmp_path):
    good = write(tmp_path / "a.kicad_pcb", BOARD)
    write(tmp_path / "z.kicad_pcb", '(kicad_pcb (gr_text "unterminated)')
    r = call("apply", str(tmp_path), "--yes")
    assert r.exit_code == 1, r.output
    assert "unterminated string" in r.stderr
    assert good.read_text(encoding="utf-8") == BOARD
    assert len(list(tmp_path.iterdir())) == 2


def test_recursive_discovery_selectors_and_config(tmp_path):
    board = write(tmp_path / "nested" / "board.kicad_pcb", BOARD)
    write(tmp_path / ".git" / "invalid.kicad_pcb", "invalid")
    write(tmp_path / "old-backups" / "invalid.kicad_pcb", "invalid")
    write(tmp_path / "ignore.kicad_pcb", "invalid")
    write(tmp_path / "board.kicad_pcb.bak", "invalid")
    write(tmp_path / "part.kicad_mod", "(footprint)")
    config = write(
        tmp_path / "rules.toml", '[text]\nwidth = 0.9\nheight = 0.7\n[files]\nexclude = ["ignore.kicad_pcb"]\n'
    )
    r = call("--config", str(config), "apply", str(tmp_path), "--text", "--json", "--yes")
    assert r.exit_code == 0, r.output
    report = json.loads(r.stdout)
    assert [Path(f["path"]).name for f in report["files"]] == ["board.kicad_pcb"]
    assert report["files"][0]["written"] is True and report["written_files"] == 1
    text = board.read_text(encoding="utf-8")
    assert "(size 0.7 0.9)" in text
    assert '(layer "F.CrtYd") (width 0.15)' in text  # --text alone leaves the courtyards
    assert "(at 2 2) (size 0.6) (drill 0.3)" in text


def test_exclude_flag_and_footprint_file_refused(tmp_path):
    write(tmp_path / "vendor" / "x.kicad_pcb", BOARD)
    write(tmp_path / "board.kicad_pcb", BOARD)
    r = call("check", str(tmp_path), "--exclude", "vendor/*", "--json")
    assert r.exit_code == 1 and len(json.loads(r.stdout)["files"]) == 1
    part = write(tmp_path / "part.kicad_mod", "(footprint)")
    r = call("check", str(part))
    assert r.exit_code == 2 and "Not a file this command works on" in r.stderr


def test_via_options_need_vias_and_are_validated(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    r = call("apply", str(board), "--via-diameter", "0.5", "--yes")
    assert r.exit_code == 2 and "need --vias" in r.stderr
    r = call("apply", str(board), "--vias", "--via-diameter", "0.1", "--via-drill", "0.2", "--yes")
    assert r.exit_code == 2 and "smaller than its diameter" in r.stderr
    r = call("apply", str(board), "--vias", "--via-types", "buried", "--yes")
    assert r.exit_code == 2 and "Unknown via type" in r.stderr
    assert board.read_text(encoding="utf-8") == BOARD
    r = call("apply", str(board), "--vias", "--via-diameter", "0.7", "--via-drill", "0.35", "--yes")
    assert r.exit_code == 0 and "(at 2 2) (size 0.7) (drill 0.35)" in board.read_text(encoding="utf-8")


def test_invalid_config_file(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    config = write(tmp_path / "bad.toml", '[text]\nwidth = "wrong"\n')
    r = call("--config", str(config), "apply", str(board), "--yes")
    assert r.exit_code == 1 and "width must be a number" in r.stderr
    assert board.read_text(encoding="utf-8") == BOARD


def test_stats_text_and_json(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    r = call("stats", str(board))
    assert r.exit_code == 0 and "B.SilkS: 1 × 2 mm / 0.2 mm" in r.stdout and "net GND" in r.stdout
    r = call("stats", str(board), "--json")
    stats = json.loads(r.stdout)["files"][0]["stats"]
    assert sum(stats["text"].values()) == 6 and sum(stats["vias"].values()) == 3


def test_concurrent_change_is_refused(tmp_path, monkeypatch):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    real_confirm = cli.confirm

    def confirm_and_edit(question, *, yes=False):
        board.write_text(BOARD + "\n", encoding="utf-8")
        real_confirm(question, yes=yes)

    monkeypatch.setattr(cli, "confirm", confirm_and_edit)
    r = call("apply", str(board), "--yes")
    assert r.exit_code == 1 and "changed after it was planned" in r.stdout
    assert board.read_text(encoding="utf-8") == BOARD + "\n"
    assert not (tmp_path / "board.kicad_pcb.bak").exists()


def test_labels_cli_discovery_backups_and_stats(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", "ignored invalid PCB")
    original = '(kicad_sch (label "L" (effects (font (size 1 1))))\n(text "note" (effects (font (size 3 3)))))'
    sheet = write(tmp_path / "sub" / "sheet.kicad_sch", original)
    assert call("check", str(tmp_path), "--labels").exit_code == 1
    assert call("apply", str(tmp_path), "--labels", "--dry-run").exit_code == 0
    assert sheet.read_text(encoding="utf-8") == original
    assert call("apply", str(tmp_path), "--labels", "--yes").exit_code == 0
    text = sheet.read_text(encoding="utf-8")
    assert "(size 1.27 1.27)" in text and '(text "note" (effects (font (size 3 3))))' in text
    assert board.read_text(encoding="utf-8") == "ignored invalid PCB"
    assert (tmp_path / "sub" / "sheet.kicad_sch.bak").read_text(encoding="utf-8") == original
    assert call("check", str(tmp_path), "--labels").exit_code == 0
    r = call("stats", str(tmp_path), "--labels", "--json")
    assert r.exit_code == 0
    assert json.loads(r.stdout)["files"][0]["stats"] == {"labels": {"label: 1.27 × 1.27 mm": 1}}


def test_label_size_from_config(tmp_path):
    sheet = write(tmp_path / "sheet.kicad_sch", '(kicad_sch (label "a") (global_label "b" (effects (justify right))))')
    config = write(tmp_path / "config.toml", "[labels]\nsize_mil = 60\n")
    r = call("--config", str(config), "apply", str(sheet), "--labels", "--yes")
    assert r.exit_code == 0, r.output
    assert sheet.read_text(encoding="utf-8").count("(size 1.524 1.524)") == 2


def test_a_schematic_without_labels_selected_is_an_error(tmp_path):
    sheet = write(tmp_path / "sheet.kicad_sch", LABELS)
    r = call("check", str(sheet))
    assert r.exit_code == 2 and "Not a file this command works on" in r.stderr


def test_rename_library_dry_run_diff_and_write(tmp_path):
    sheet = write(tmp_path / "power.kicad_sch", SCHEMATIC)
    r = call(
        "rename-library",
        str(tmp_path),
        "--from",
        "bac Library v1",
        "--to",
        "bac Library Symbols v1",
        "--dry-run",
        "--diff",
    )
    assert r.exit_code == 0, r.output
    assert "cached symbols: 1" in r.stdout and "symbol references: 1" in r.stdout
    assert '+  (symbol (lib_id "bac Library Symbols v1:C")' in r.stdout
    assert sheet.read_text(encoding="utf-8") == SCHEMATIC
    r = call("rename-library", str(tmp_path), "--from", "bac Library v1", "--to", "bac Library Symbols v1", "--yes")
    assert r.exit_code == 0, r.output
    assert '(lib_id "bac Library Symbols v1:C")' in sheet.read_text(encoding="utf-8")
    assert (tmp_path / "power.kicad_sch.bak").read_text(encoding="utf-8") == SCHEMATIC
    for bad in (["--from", "a:b", "--to", "c"], ["--from", "same", "--to", "same"], ["--from", "", "--to", "c"]):
        assert call("rename-library", str(tmp_path), *bad).exit_code == 2


def test_rename_library_collision_writes_nothing(tmp_path):
    sheet = write(tmp_path / "s.kicad_sch", '(kicad_sch (lib_symbols (symbol "old:C") (symbol "new:C")))')
    r = call("rename-library", str(sheet), "--from", "old", "--to", "new", "--yes")
    assert r.exit_code == 1 and "new:C" in r.stderr
    assert not (tmp_path / "s.kicad_sch.bak").exists()


def test_init_writes_the_config(tmp_path):
    r = call("init")
    assert r.exit_code == 0 and "Wrote" in r.stdout
    target = tmp_path / "home" / ".config" / "bac" / "bac-kicad-maintain.toml"
    assert target.is_file() and "[courtyards]" in target.read_text(encoding="utf-8")
    assert "left unchanged" in call("init").stdout
    r = call("--config", str(tmp_path / "other.toml"), "init")
    assert r.exit_code == 0 and (tmp_path / "other.toml").is_file()


def test_via_types_repeatable_or_comma_separated(tmp_path):
    source = """(kicad_pcb
      (via micro (at 3 3) (size 0.1) (drill 0.05) (net "SIGNAL"))
      (via blind (at 4 4) (size 0.4) (drill 0.2) (net "SIGNAL"))
      (via (at 1 1) (size 0.6) (drill 0.3) (net "Power/GND")))"""
    board = write(tmp_path / "board.kicad_pcb", source)
    r = call("check", str(board), "--vias", "--via-types", "through", "--via-types", "micro", "--json")
    assert r.exit_code == 1 and json.loads(r.stdout)["files"][0]["counts"]["vias"] == 2
    r = call("check", str(board), "--vias", "--via-types", "micro, blind,", "--json")
    assert r.exit_code == 1 and json.loads(r.stdout)["files"][0]["counts"]["vias"] == 2
    r = call("check", str(board), "--vias", "--via-types", "", "--json")
    assert r.exit_code == 2 and "at least one via type" in r.stderr
    r = call("check", str(board), "--vias", "--preserve-net", "SIGNAL", "--preserve-net", "*/GND", "--json")
    assert json.loads(r.stdout)["files"][0]["counts"] == {"vias kept, preserved net": 3}


def test_via_sizes_on_the_command_line_keep_six_decimals(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    r = call("check", str(board), "--vias", "--via-diameter", "0.1234567", "--via-drill", "0.0000001")
    assert r.exit_code == 2 and "at most six decimals" in r.stderr
    r = call("check", str(board), "--vias", "--via-drill", "0", "--via-diameter", "0.5")
    assert r.exit_code == 2 and "must be positive" in r.stderr


def test_no_matching_file_is_an_error(tmp_path):
    (tmp_path / "empty").mkdir()
    r = call("check", str(tmp_path / "empty"))
    assert r.exit_code == 2 and "No .kicad_pcb files found" in r.stderr
    write(tmp_path / "board.kicad_pcb", BOARD)
    r = call("check", str(tmp_path), "--labels")
    assert r.exit_code == 2 and "No .kicad_sch files found" in r.stderr
    r = call("check", str(tmp_path), "--exclude", "*.kicad_pcb")
    assert r.exit_code == 2


def test_json_and_diff_do_not_combine(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    r = call("check", str(board), "--json", "--diff")
    assert r.exit_code == 2 and "--json and --diff" in r.stderr
    r = call("apply", str(board), "--json")
    assert r.exit_code == 2 and "--yes" in r.stderr


def test_a_failed_write_keeps_the_backup_and_exits_1(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    board.chmod(0o444)
    try:
        r = call("apply", str(board), "--yes")
    finally:
        board.chmod(0o644)
    if r.exit_code == 0:  # running as root: the write succeeds regardless of the mode
        return
    assert r.exit_code == 1 and "Cannot write" in r.stdout
    assert board.read_text(encoding="utf-8") == BOARD
    assert (tmp_path / "board.kicad_pcb.bak").read_text(encoding="utf-8") == BOARD


def test_second_apply_replaces_the_backup(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    assert call("apply", str(board), "--text", "--yes").exit_code == 0
    first = board.read_text(encoding="utf-8")
    assert call("apply", str(board), "--courtyards", "--yes").exit_code == 0
    assert (tmp_path / "board.kicad_pcb.bak").read_text(encoding="utf-8") == first


def test_non_numeric_size_in_a_file(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", '(kicad_pcb (gr_text "x" (effects (font (size a b)))))')
    r = call("check", str(board))
    assert r.exit_code == 1 and "holds a non-number: (size a b)" in r.stderr


def test_subcommand_help_fits(tmp_path):
    for command in ("check", "apply", "stats", "rename-library", "init"):
        r = call(command, "--help")
        assert r.exit_code == 0
        lines = r.stdout.rstrip("\n").splitlines()
        assert len(lines) <= 24 and all(len(line) <= 80 for line in lines), (command, lines)
