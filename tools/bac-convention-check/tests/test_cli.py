# SPDX-License-Identifier: MIT
from __future__ import annotations

from bac_convention_check import __version__, cli

from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-convention-check"


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_list_rules():
    r = invoke(cli._main, ["-l"])
    assert r.exit_code == 0
    lines = r.stdout.splitlines()
    assert lines[0].startswith("A1   blocking")
    assert any(line.startswith("R1   blocking") for line in lines)
    r = invoke(cli._main, ["-l", "--rules", "firmware"])
    assert r.stdout.splitlines()[0].startswith("B9")


def test_report_format_and_exit_codes(dirty, clean):
    r = invoke(cli._main, [str(dirty), "--format", "report"])
    assert r.exit_code == 1
    assert r.stdout.startswith("=== Build a CubeSat – bac-convention-check v")
    assert "--- CHECK A1 | blocking |" in r.stdout
    assert "README.md:3:Intro with an em dash — here." in r.stdout
    assert "verdict:" in r.stdout and "blocking finding(s)" in r.stdout
    assert r.stdout.rstrip().endswith("=== END")

    r = invoke(cli._main, [str(clean), "--format", "report"])
    assert r.exit_code == 0, r.output
    assert "verdict: clean, no blocking findings" in r.stdout


def test_tsv_format(dirty):
    r = invoke(cli._main, [str(dirty), "--format", "tsv", "--only", "A1,R1"])
    rows = [line.split("\t") for line in r.stdout.splitlines()]
    assert ["A1", "blocking", "README.md", "3", "Intro with an em dash — here."] in rows
    assert any(row[:4] == ["R1", "blocking", "README.md", "0"] for row in rows)


def test_terminal_format(dirty):
    r = invoke(cli._main, [str(dirty), "--format", "terminal", "--only", "A1,A2,H2"])
    assert r.exit_code == 1
    assert "bac-convention-check" in r.stdout and "v" + __version__ in r.stdout
    assert "✗ A1" in r.stdout and "! H2" in r.stdout
    assert "blocking finding(s)" in r.stdout and "Blocking" in r.stdout


def test_severity_filter_and_only(dirty):
    r = invoke(cli._main, [str(dirty), "--format", "report", "--severity", "blocking"])
    assert "--- CHECK A5" not in r.stdout and "--- CHECK A4" in r.stdout
    r = invoke(cli._main, [str(dirty), "--format", "report", "--only", "A5"])
    assert r.exit_code == 0  # advisory only
    assert "--- CHECK A1" not in r.stdout


def test_bad_arguments(tmp_path):
    r = invoke(cli._main, [str(tmp_path / "missing")])
    assert r.exit_code == 2 and "Not a directory" in r.stderr
    r = invoke(cli._main, [str(tmp_path), "--only", "A1,ZZ9"])
    assert r.exit_code == 2 and "Unknown rule id(s): ZZ9" in r.stderr and "bac-convention-check -l" in r.stderr
    r = invoke(cli._main, [str(tmp_path), "--max-hits", "-1"])
    assert r.exit_code == 2
    r = invoke(cli._main, [str(tmp_path), "--severity", "loud"])
    assert r.exit_code == 2 and "usage:" in r.stderr


def test_truncation_note_keeps_full_count(tmp_path):
    (tmp_path / "a.md").write_text("\n".join(f"{i} — x" for i in range(10)) + "\n")
    r = invoke(cli._main, [str(tmp_path), "--format", "report", "--only", "A1", "--max-hits", "3"])
    assert "hits: 10" in r.stdout
    assert "note: output truncated at 3 hits (7 more)" in r.stdout
    assert r.stdout.count("a.md:") == 3


def test_project_config_rules_and_excludes(dirty):
    (dirty / "bac-convention-check.toml").write_text(
        'rules = ["guide"]\nmax_hits = 1\n\n[exclude]\nA1 = ["README.md"]\n"*" = ["no-license/**"]\n'
    )
    r = invoke(cli._main, [str(dirty), "--format", "report", "--only", "A1,L2"])
    assert r.exit_code == 0, r.stdout
    assert "hits: 0" in r.stdout


def test_explicit_config_path_and_relative_rule_set(dirty, tmp_path):
    custom = tmp_path / "rules" / "mine.toml"
    custom.parent.mkdir()
    custom.write_text(
        '[[rules]]\nid = "M1"\ntitle = "No word demo"\nseverity = "advisory"\nkind = "regex"\npattern = "demo"\n'
    )
    cfg = tmp_path / "rules" / "cfg.toml"
    cfg.write_text('rules = ["mine.toml"]\n')
    r = invoke(cli._main, [str(dirty), "--config", str(cfg), "--format", "report"])
    assert r.exit_code == 0
    assert "--- CHECK M1 | advisory | No word demo" in r.stdout and "--- CHECK A1" not in r.stdout
    r = invoke(cli._main, [str(dirty), "--config", str(tmp_path / "nope.toml")])
    assert r.exit_code == 1 and "does not exist" in r.stderr


def test_help_is_within_the_guide_limit():
    r = invoke(cli._main, ["--help"])
    assert len(r.stdout.rstrip().splitlines()) <= 24, r.stdout
