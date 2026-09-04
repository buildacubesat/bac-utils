# SPDX-License-Identifier: MIT
from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

from rich.progress import BarColumn, SpinnerColumn, TextColumn

from bac_common import ui


def capture(fn, *args, **kwargs) -> tuple[str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        fn(*args, **kwargs)
    return out.getvalue(), err.getvalue()


def test_step_glyphs():
    assert capture(ui.ok, "done")[0] == "  ✓ done\n"
    assert capture(ui.fail, "broken")[0] == "  ✗ broken\n"
    assert capture(ui.warn, "careful")[0] == "  ! careful\n"
    assert capture(ui.step, "plain")[0] == "  plain\n"
    assert capture(ui.dim, "quiet")[0] == "  quiet\n"


def test_path_escapes_markup():
    out, _ = capture(ui.step, ui.path("weird [/] name.pdf"))
    assert "weird [/] name.pdf" in out


def test_fields_aligns_and_escapes():
    out, _ = capture(ui.fields, [("Title", "A [bold]b[/]"), ("Year", 2026), ("Note", None)])
    lines = out.splitlines()
    assert lines[0] == "    Title  A [bold]b[/]"
    assert lines[1] == "    Year   2026"
    assert lines[2] == "    Note   "


def test_error_goes_to_stderr_with_detail():
    out, err = capture(ui.error, "It failed.", "Try again.")
    assert out == ""
    assert err.splitlines() == ["ERROR It failed.", "      Try again."]


def test_display_version_and_header():
    assert ui.display_version("0.4.0") == "v0.4.0"
    assert ui.display_version("v0.4.0") == "v0.4.0"
    assert ui.header("bac-page", "0.4.0") == "Build a CubeSat – bac-page v0.4.0"


def test_opening_panel_contains_tool_and_version():
    out, _ = capture(ui.opening, "bac-x", "1.0.0", "Doing the thing.")
    assert "bac-x" in out and "v1.0.0" in out and "Doing the thing." in out


def test_summary_right_aligns_values_and_labels_dry_run():
    out, _ = capture(ui.summary, [("Processed", 3), ("Uploaded", 12), ("Errors", 0)], dry_run=True)
    lines = [line.strip() for line in out.splitlines() if ":" in line or "dry run" in line]
    assert lines[0] == "Processed  :   3"
    assert lines[1] == "Uploaded   :  12"
    assert lines[2] == "Errors     :   0"
    assert lines[3] == "(dry run – no changes made)"


def test_summary_without_rows_still_prints_dry_run_label():
    out, _ = capture(ui.summary, [], dry_run=True)
    assert "(dry run – no changes made)" in out


def test_table_right_justifies_numeric_column():
    out, _ = capture(
        ui.table,
        "Ingest plan",
        [("Source", 2), ("Conf.", 0, "right")],
        [["report.pdf", "0.91"], ["a-much-longer-name.pdf", "1.00"]],
    )
    assert "Ingest plan" in out
    rows = [line for line in out.splitlines() if ".pdf" in line]
    assert all(line.rstrip().endswith(("0.91", "1.00")) for line in rows)


def test_progress_has_name_bar_and_one_status_only():
    for status in ("count", "percent", "elapsed"):
        progress = ui.make_progress(status)  # type: ignore[arg-type]
        columns = progress.columns
        assert len(columns) == 3
        assert isinstance(columns[0], TextColumn)
        assert isinstance(columns[1], BarColumn)
        assert not any(isinstance(c, SpinnerColumn) for c in columns)


def test_spinner_is_a_context_manager():
    with ui.spinner("Working"):
        pass
