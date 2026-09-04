# SPDX-License-Identifier: MIT
from __future__ import annotations

import io
import re
from pathlib import Path

from bac_kicad_hlabels import __version__, cli

from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-kicad-hlabels"
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "nets.txt"


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_example_to_stdout():
    r = invoke(cli._main, [str(EXAMPLE)])
    assert r.exit_code == 0, r.output
    assert r.stdout.count("(hierarchical_label ") == 38
    assert r.stderr == ""
    assert r.stdout.startswith('(hierarchical_label "A_CAN_1_P"\n\t(shape passive)\n\t(at 0 0 0)\n')
    # Without --gap-on-blank the fourth label follows directly.
    assert '(hierarchical_label "VBAT"\n\t(shape passive)\n\t(at 0 7.62 0)' in r.stdout


def test_gap_on_blank_and_geometry_flags():
    argv = [
        str(EXAMPLE),
        "--gap-on-blank",
        "--at",
        "10",
        "20",
        "--step",
        "5",
        "--rotation",
        "180",
        "--font-size",
        "1",
        "--shape",
        "input",
        "--justify",
        "left",
    ]
    r = invoke(cli._main, argv)
    assert r.exit_code == 0, r.output
    assert r.stdout.count("(hierarchical_label ") == 38
    assert '(hierarchical_label "VBAT"\n\t(shape input)\n\t(at 10 55 180)' in r.stdout  # slot 7
    assert "(size 1 1)" in r.stdout and "(justify left)" in r.stdout
    assert len(set(re.findall(r'\(uuid "([^"]+)"\)', r.stdout))) == 38


def test_stdin_to_file(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("SDA\nSCL\n"))
    out = tmp_path / "snippet" / "labels.kicad_snippet"
    r = invoke(cli._main, ["-o", str(out)])
    assert r.exit_code == 0, r.output
    assert out.read_text(encoding="utf-8").count("(hierarchical_label ") == 2
    assert "✓ Wrote 2 label(s)" in r.stdout


def test_errors():
    for argv, code, text in (
        ([str(EXAMPLE), "--shape", "round"], 2, "Unknown shape"),
        ([str(EXAMPLE), "--justify", "middle"], 2, "Unknown justification"),
        ([str(EXAMPLE), "--rotation", "45"], 2, "Rotation must be"),
        ([str(EXAMPLE), "--step", "0"], 2, "must be positive"),
        (["/nonexistent/nets.txt"], 2, "does not exist"),
    ):
        r = invoke(cli._main, argv)
        assert r.exit_code == code, argv
        assert text in r.stderr and "Traceback" not in r.stderr


def test_empty_input(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("\n\n"))
    r = invoke(cli._main, [])
    assert r.exit_code == 1 and "No net names" in r.stderr
