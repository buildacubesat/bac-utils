# SPDX-License-Identifier: MIT
"""The command line: flags, confirmation, backups, the reports, remove, init."""

from __future__ import annotations

import json
import re
from pathlib import Path

from bac_kicad_stitch import __version__, cli
from stitch_testkit import BOARD

from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-kicad-stitch"


def call(*argv: str):
    return invoke(cli._main, list(argv))


def value(stdout: str, label: str) -> str | None:
    m = re.search(rf"{re.escape(label)}\s+:\s+(\S+)", stdout)
    return m.group(1) if m else None


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8", newline="")
    return path


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_no_command_prints_help():
    r = call()
    assert r.exit_code == 0 and "Commands:" in r.stdout


def test_report_writes_nothing_and_draws(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    r = call("report", str(board), "--pitch", "6", "--fine-pitch-pads", "4", "--preview", "plan.svg")
    assert r.exit_code == 0, r.output
    assert value(r.stdout, "Existing ground vias") == "1"
    assert int(value(r.stdout, "Vias to add")) > 0
    assert "courtyards avoided: U1" in r.stdout
    assert board.read_text(encoding="utf-8") == BOARD
    assert (tmp_path / "plan.svg").read_text(encoding="utf-8").startswith("<svg")


def test_stitch_dry_run_confirm_backup_and_second_run(tmp_path, monkeypatch):
    board = write(tmp_path / "board.kicad_pcb", BOARD.replace("\n", "\r\n"))
    original = board.read_bytes()

    r = call("stitch", str(board), "--pitch", "6", "--dry-run")
    assert r.exit_code == 0 and "dry run" in r.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["board.kicad_pcb"]

    monkeypatch.setattr("bac_common.ui.console.input", lambda prompt: "n")
    r = call("stitch", str(board), "--pitch", "6")
    assert r.exit_code == 0 and "Aborted" in r.stdout
    assert board.read_bytes() == original

    r = call("stitch", str(board), "--pitch", "6", "--yes", "--no-drc")
    assert r.exit_code == 0, r.output
    assert "Wrote" in r.stdout
    added = int(value(r.stdout, "Vias added"))
    assert added > 0
    assert (tmp_path / "board.kicad_pcb.bak").read_bytes() == original
    stitched = board.read_bytes()
    assert b"\n" not in stitched.replace(b"\r\n", b"")  # line endings kept
    assert stitched.count(b"\t(via\r\n") == 1 + added

    r = call("stitch", str(board), "--pitch", "6", "--yes", "--no-drc")
    assert r.exit_code == 0 and "nothing to add" in r.stdout
    assert board.read_bytes() == stitched

    r = call("remove", str(board), "--yes", "--no-backup")
    assert r.exit_code == 0 and value(r.stdout, "Vias removed") == str(added)
    assert board.read_bytes() == original


def test_json_report(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    r = call("report", str(board), "--pitch", "6", "--json")
    assert r.exit_code == 0, r.output
    data = json.loads(r.stdout)
    assert data["tool"] == TOOL and data["pitch_mm"] == 6 and data["existing_vias"] == 1
    assert data["placed"] and data["coverage_after"] >= data["coverage_before"]

    r = call("stitch", str(board), "--pitch", "6", "--json")
    assert r.exit_code == 2 and "--yes" in r.output


def test_frequency_and_bad_arguments(tmp_path):
    board = write(tmp_path / "board.kicad_pcb", BOARD)
    r = call("report", str(board), "--max-frequency", "1e9", "--json")
    assert r.exit_code == 0, r.output
    assert abs(json.loads(r.stdout)["pitch_mm"] - 299.792458 / 2 / 20) < 1e-9
    r = call("report", str(board), "--via-drill", "0.8")
    assert r.exit_code == 2 and "drill" in r.output
    r = call("report", str(board), "--courtyards", "never")
    assert r.exit_code == 2
    r = call("report", str(tmp_path / "missing.kicad_pcb"))
    assert r.exit_code == 1 and "Cannot read" in r.output


def test_init_writes_config(tmp_path):
    r = call("init")
    assert r.exit_code == 0 and "Wrote" in r.stdout
    config = tmp_path / "home" / ".config" / "bac" / f"{TOOL}.toml"
    assert config.exists() and "[placement]" in config.read_text(encoding="utf-8")
    r = call("init")
    assert "exists" in r.stdout

    board = write(tmp_path / "board.kicad_pcb", BOARD)
    config.write_text("[placement]\npitch = 4\nfine_pitch_pads = 4\n", encoding="utf-8")
    r = call("report", str(board), "--json")
    assert json.loads(r.stdout)["pitch_mm"] == 4
    config.write_text("[placement]\nbogus = 1\n", encoding="utf-8")
    r = call("report", str(board))
    assert r.exit_code == 1 and "bogus" in r.output
