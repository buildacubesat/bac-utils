# SPDX-License-Identifier: MIT
from __future__ import annotations

import io

from bac_markdown_to_youtube import __version__, cli

from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-markdown-to-youtube"


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_file_to_stdout(tmp_path):
    src = tmp_path / "notes.md"
    src.write_text("# Title\n\nSome **bold** text.\n", encoding="utf-8")
    r = invoke(cli._main, [str(src)])
    assert r.exit_code == 0, r.output
    assert r.stdout == "*Title*\n\nSome *bold* text.\n"
    assert r.stderr == ""


def test_stdin_to_file(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("_italic_ here\n"))
    out = tmp_path / "out" / "description.txt"
    r = invoke(cli._main, ["-o", str(out)])
    assert r.exit_code == 0, r.output
    assert out.read_text(encoding="utf-8") == "_italic_ here\n"
    assert "✓ Wrote" in r.stdout and "description.txt" in r.stdout


def test_missing_input_is_a_usage_error(tmp_path):
    r = invoke(cli._main, [str(tmp_path / "nope.md")])
    assert r.exit_code == 2
    assert "ERROR Input file does not exist" in r.stderr
    assert "Traceback" not in r.stderr
