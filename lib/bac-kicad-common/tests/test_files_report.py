# SPDX-License-Identifier: MIT
from __future__ import annotations

import io
from contextlib import redirect_stdout

import pytest

from bac_common.errors import BacError, UserAbort
from bac_kicad_common import files, report
from bac_kicad_common.props import Change


def test_write_back_makes_a_backup_first(tmp_path):
    target = tmp_path / "lib.kicad_sym"
    target.write_text("old", encoding="utf-8")
    saved = files.write_back(target, "new")
    assert saved == tmp_path / "lib.kicad_sym.bak" and saved.read_text(encoding="utf-8") == "old"
    assert target.read_text(encoding="utf-8") == "new"
    assert files.write_back(target, "newer", backup=False) is None
    assert saved.read_text(encoding="utf-8") == "old" and target.read_text(encoding="utf-8") == "newer"
    with pytest.raises(BacError, match="Cannot write"):
        files.write_back(tmp_path / "missing" / "x.kicad_sym", "x", backup=False)


def test_confirm(monkeypatch):
    files.confirm("Write?", yes=True)
    monkeypatch.setattr("bac_common.ui.console.input", lambda prompt: "y")
    files.confirm("Write?")
    monkeypatch.setattr("bac_common.ui.console.input", lambda prompt: "")
    with pytest.raises(UserAbort):
        files.confirm("Write?")

    def eof(prompt):
        raise EOFError

    monkeypatch.setattr("bac_common.ui.console.input", eof)
    with pytest.raises(UserAbort):
        files.confirm("Write?")


def test_report_lines():
    out = io.StringIO()
    with redirect_stdout(out):
        report.print_item("sym", "bac:R [x]", "R")
        report.print_changes(
            [
                Change("add", "MPN", "", "00.toml"),
                Change("set", "Tol", "1%", "10.toml", previous="5%"),
                Change("flag", "dnp", "yes", "60.toml"),
            ],
            [("URL", "requires MPN")],
        )
    text = out.getvalue()
    assert "sym  bac:R [x] R" in text.replace("  ", " ") or "bac:R" in text
    assert "+ MPN = (empty placeholder)" in text and "(00.toml)" in text
    assert "! Tol = 5% → 1%" in text and "* dnp = unset → yes" in text
    assert "· URL skipped: requires MPN" in text


def test_write_back_keeps_crlf_line_endings(tmp_path):
    from bac_common import sexp

    target = tmp_path / "lib.kicad_sym"
    target.write_bytes(b'(kicad_symbol_lib\r\n\t(version 20251024)\r\n\t(symbol "R"\r\n\t)\r\n)\r\n')
    text, root = sexp.parse_file(target)
    assert "\r\n" in text and root.children("symbol")[0].value(1) == "R"
    files.write_back(target, text.replace('"R"', '"R2"'), backup=False)
    assert target.read_bytes() == b'(kicad_symbol_lib\r\n\t(version 20251024)\r\n\t(symbol "R2"\r\n\t)\r\n)\r\n'
