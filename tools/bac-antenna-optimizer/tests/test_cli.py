# SPDX-License-Identifier: MIT
"""The command line on bac-common: the standard flags, the error boundary, `-l`."""

from __future__ import annotations

import csv

from bac_antenna import __version__, cli

from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-antenna"


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_help_fits_the_screen_and_names_every_command():
    r = invoke(cli._main, ["--help"])
    assert r.exit_code == 0
    lines = r.stdout.rstrip().splitlines()
    assert len(lines) <= 24 and max(len(line) for line in lines) <= 80
    for command in ("optimize", "simulate", "sweep", "check", "migrate", "pack", "report"):
        assert f"    {command} " in r.stdout
    assert "Examples:" in r.stdout and "--debug" not in r.stdout


def test_no_command_is_a_usage_error():
    r = invoke(cli._main, [])
    assert r.exit_code == 2 and "usage: bac-antenna" in r.stderr and r.stdout == ""


def test_list_without_a_summary_is_a_usage_error_without_traceback(tmp_path):
    r = invoke(cli._main, ["-l", "--output", str(tmp_path / "nope")])
    assert r.exit_code == 2
    assert "ERROR No summary found" in r.stderr and "--output" in r.stderr and "Traceback" not in r.stderr


def test_list_prints_the_ranked_candidates(tmp_path):
    rows = [
        {
            "rank": 1,
            "index": 7,
            "score": 0.123,
            "resonance_hz": 2.2e9,
            "s_s11_worst_db": -12.5,
            "s_gain_min_dbic": 4.1,
            "s_ar_worst_db": 2.0,
            "s_hand": "RHCP",
        }
    ]
    with (tmp_path / "summary.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    r = invoke(cli._main, ["-l", "--output", str(tmp_path)])
    assert r.exit_code == 0
    assert "rank cand" in r.stdout and "s: S11 / G / AR / hand" in r.stdout
    assert "   1    7    0.123     2.2000   -12.5   4.1   2.0  RHCP" in r.stdout


def test_unexpected_errors_are_one_line(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("the backend fell over")

    monkeypatch.setattr(cli, "_list_results", boom)
    r = invoke(cli._main, ["-l"])
    assert r.exit_code == 1 and "Unexpected error: the backend fell over" in r.stderr and "Traceback" not in r.stderr
