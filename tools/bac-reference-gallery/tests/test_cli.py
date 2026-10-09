# SPDX-License-Identifier: MIT
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from bac_reference_gallery import __version__, browser, cli
from bac_reference_gallery.render import Rendered
from bac_reference_gallery.site import Board
from gallery_testkit import copy_gallery
from pypdf import PdfReader, PdfWriter

from bac_common.testing import assert_standard_flags, invoke

TOOL = "bac-reference-gallery"
FAKE_BROWSER = browser.Browser(Path("/opt/fake/chrome"), "BAC_CHROMIUM_PATH")


class FakeRenderer:
    """Stands in for the Chromium renderer: writes a tiny PNG and a one-page PDF per board."""

    fail: set[str] = set()
    missing_fonts: list[str] = []
    theme: str | None = None

    def __init__(self, found, theme):
        FakeRenderer.theme = theme

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def render(self, board: Board, png: Path | None, pdf: Path | None) -> Rendered:
        if board.name in self.fail:
            raise RuntimeError("page.goto: net::ERR_FILE_NOT_FOUND\nCall log:\n  - navigating")
        size = (1055, 1491) if board.name == "product-sheet" else (1600, 1000)
        result = Rendered(*size, missing_fonts=list(self.missing_fonts))
        if png is not None:
            png.parent.mkdir(parents=True, exist_ok=True)
            png.write_bytes(b"\x89PNG\r\n\x1a\n")
            result.files.append(png)
        if pdf is not None:
            pdf.parent.mkdir(parents=True, exist_ok=True)
            writer = PdfWriter()
            writer.add_blank_page(width=size[0] * 0.75, height=size[1] * 0.75)
            with pdf.open("wb") as fh:
                writer.write(fh)
            result.files.append(pdf)
        return result


@pytest.fixture
def fake(monkeypatch):
    FakeRenderer.fail = set()
    FakeRenderer.missing_fonts = []
    monkeypatch.setattr(cli, "Renderer", FakeRenderer)
    monkeypatch.setattr(browser, "find", lambda: FAKE_BROWSER)
    return FakeRenderer


def test_standard_flags():
    assert_standard_flags(cli._main, TOOL, __version__)


def test_help_shows_the_tool_flags_and_hides_config():
    r = invoke(cli._main, ["--help"])
    for flag in (
        "--only NAME",
        "--format FMT",
        "--theme MODE",
        "--out-dir DIR",
        "--source DIR",
        "-l, --list",
        "--init",
    ):
        assert flag in r.stdout
    assert "--config" not in r.stdout


def test_list_prints_names_only():
    r = invoke(cli._main, ["-l"])
    assert r.exit_code == 0
    assert r.stdout.splitlines()[0] == "identity-overview"
    assert len(r.stdout.splitlines()) == 7
    assert "Render" not in r.stdout


def test_unknown_board_is_a_usage_error():
    r = invoke(cli._main, ["--only", "nope"])
    assert r.exit_code == 2
    assert "Unknown board: nope" in r.stderr


@pytest.mark.parametrize("argv", [["--format", "jpg"], ["--theme", "sepia"], ["--bogus"]])
def test_bad_options_exit_2(argv):
    assert invoke(cli._main, argv).exit_code == 2


def test_out_dir_must_be_a_folder(tmp_path):
    f = tmp_path / "file"
    f.write_text("")
    r = invoke(cli._main, ["--dry-run", "--out-dir", str(f)])
    assert r.exit_code == 2
    assert "not a folder" in r.stderr


def test_source_must_be_a_gallery(tmp_path):
    r = invoke(cli._main, ["--source", str(tmp_path)])
    assert r.exit_code == 2
    assert "Not a gallery folder" in r.stderr


def test_dry_run_needs_no_browser_and_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(browser, "find", lambda: None)
    r = invoke(cli._main, ["--dry-run", "--only", "product-sheet", "--format", "pdf", "--out-dir", str(tmp_path / "x")])
    assert r.exit_code == 0, r.output
    assert "product-sheet → pdf" in r.stdout
    assert "none found" in r.stdout
    assert "combined" not in r.stdout  # --only: the combined PDF is not touched
    assert "dry run – no changes made" in r.stdout
    assert not (tmp_path / "x").exists()


def test_dry_run_of_the_whole_gallery_names_the_combined_pdf(monkeypatch):
    monkeypatch.setattr(browser, "find", lambda: None)
    r = invoke(cli._main, ["--dry-run", "--theme", "dark"])
    assert r.exit_code == 0, r.output
    assert "combined → pdf/bac-reference-exemplars-dark.pdf" in r.stdout


def test_a_dry_run_reports_a_broken_playwright_and_goes_on(monkeypatch):
    from bac_common.errors import ExternalToolError

    def broken():
        raise ExternalToolError("Playwright is not installed.")

    monkeypatch.setattr(browser, "find", broken)
    r = invoke(cli._main, ["--dry-run", "--only", "product-sheet"])
    assert r.exit_code == 0, r.output
    assert "unavailable – Playwright is not installed." in r.stdout


def test_no_browser_points_at_init_after_the_panel_and_with_a_summary(monkeypatch):
    monkeypatch.setattr(browser, "find", lambda: None)
    r = invoke(cli._main, [])
    assert r.exit_code == 1
    assert "No Chromium found" in r.stderr
    assert "--init" in r.stderr
    assert "Render 7 board(s)" in r.stdout
    assert "Rendered       :  0" in r.stdout


def test_a_playwright_that_does_not_import_is_an_error_not_a_crash(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)  # import raises ImportError
    r = invoke(cli._main, [])
    assert r.exit_code == 1
    assert "Playwright is not installed." in r.stderr
    assert "Unexpected error" not in r.stderr


def test_a_bad_override_is_reported(monkeypatch, tmp_path):
    monkeypatch.setenv(browser.ENV, str(tmp_path / "missing"))
    r = invoke(cli._main, [])
    assert r.exit_code == 1
    assert "BAC_CHROMIUM_PATH names no file" in r.stderr
    assert "Failed         :  0" in r.stdout


def test_full_run_writes_every_board_and_the_combined_pdf(fake, tmp_path):
    out = tmp_path / "exports"
    r = invoke(cli._main, ["--out-dir", str(out)])
    assert r.exit_code == 0, r.output
    assert len(list((out / "png").glob("*.png"))) == 7
    combined = out / "pdf" / "bac-reference-exemplars.pdf"
    assert len(PdfReader(str(combined)).pages) == 7
    assert "✓ product-sheet 1055 × 1491 → png, pdf" in r.stdout
    assert "Combined 7 pages" in r.stdout
    assert "Files written  :  15" in r.stdout
    assert "overwritten" not in r.stdout
    again = invoke(cli._main, ["--out-dir", str(out), "--only", "ops-vs-mission"])
    assert again.exit_code == 0
    assert "(overwritten)" in again.stdout
    assert "Combined" not in again.stdout  # one board: no combined PDF


def test_only_leaves_the_combined_pdf_of_the_whole_gallery_alone(fake, tmp_path):
    out = tmp_path / "exports"
    assert invoke(cli._main, ["--out-dir", str(out)]).exit_code == 0
    combined = out / "pdf" / "bac-reference-exemplars.pdf"
    r = invoke(cli._main, ["--out-dir", str(out), "--only", "ops-vs-mission", "--only", "product-sheet"])
    assert r.exit_code == 0, r.output
    assert "Combined PDF left as it was" in r.stdout
    assert len(PdfReader(str(combined)).pages) == 7


def test_the_default_output_is_exports_in_the_working_directory(fake, tmp_path):
    r = invoke(cli._main, ["--only", "identity-overview", "--format", "png"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "exports" / "png" / "identity-overview.png").is_file()
    assert not (tmp_path / "exports" / "pdf").exists()


def test_dark_renders_carry_the_theme_in_their_names(fake, tmp_path):
    r = invoke(cli._main, ["--theme", "dark", "--format", "pdf"])
    assert r.exit_code == 0, r.output
    assert FakeRenderer.theme == "dark"
    names = {p.name for p in (tmp_path / "exports" / "pdf").iterdir()}
    assert {"bac-reference-exemplars-dark.pdf", "ops-vs-mission-dark.pdf", "product-sheet-dark.pdf"} <= names
    assert not any(p.name.endswith(".png") for p in (tmp_path / "exports").rglob("*"))


def test_one_failed_board_does_not_end_the_run(fake, tmp_path):
    fake.fail = {"document-family"}
    r = invoke(cli._main, [])
    assert r.exit_code == 1
    assert "✗ document-family: page.goto: net::ERR_FILE_NOT_FOUND" in r.stdout
    assert "Call log" not in r.stdout
    assert "✓ product-sheet" in r.stdout
    assert "Combined PDF not written: 1 board(s) failed." in r.stdout
    assert not (tmp_path / "exports" / "pdf" / "bac-reference-exemplars.pdf").exists()
    assert "Failed         :   1" in r.stdout


def test_missing_fonts_are_reported_once(fake):
    fake.missing_fonts = ["Nunito Sans"]
    r = invoke(cli._main, ["--only", "identity-overview", "--only", "ops-vs-mission"])
    assert r.exit_code == 0
    assert r.stdout.count("Fonts missing, fallbacks used: Nunito Sans") == 1


def test_a_renderer_that_does_not_start_still_prints_the_summary(monkeypatch):
    from bac_common.errors import ExternalToolError

    class Broken(FakeRenderer):
        def __enter__(self):
            raise ExternalToolError("Chromium did not start.", "spawn ENOENT")

    monkeypatch.setattr(cli, "Renderer", Broken)
    monkeypatch.setattr(browser, "find", lambda: FAKE_BROWSER)
    r = invoke(cli._main, [])
    assert r.exit_code == 1
    assert "Chromium did not start." in r.stderr
    assert "Rendered       :  0" in r.stdout


def test_a_custom_gallery_renders_through_source(fake, tmp_path):
    gallery = copy_gallery(tmp_path / "mine")
    (gallery / "examples" / "zz-extra.html").write_text("<!doctype html><main class='board'></main>")
    r = invoke(cli._main, ["--source", str(gallery), "-l"])
    assert r.stdout.splitlines()[-1] == "zz-extra"
    r = invoke(cli._main, ["--source", str(gallery), "--only", "zz-extra", "--format", "png"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "exports" / "png" / "zz-extra.png").is_file()


def test_init_with_a_browser(monkeypatch):
    monkeypatch.setattr(browser, "find", lambda: FAKE_BROWSER)
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 0, r.output
    assert "✓ Pages:" in r.stdout and "(7 boards)" in r.stdout
    assert "✓ Browser: /opt/fake/chrome (BAC_CHROMIUM_PATH)" in r.stdout


def test_init_without_a_browser_and_without_a_terminal_prints_the_command(monkeypatch):
    monkeypatch.setattr(browser, "find", lambda: None)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 1
    assert "No Chromium found." in r.stdout
    assert "-m playwright install chromium" in r.stdout


def test_init_downloads_when_asked(monkeypatch):
    found = iter([None, browser.Browser(None, "Playwright")])
    monkeypatch.setattr(browser, "find", lambda: next(found))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli.ui.console, "input", lambda prompt: "y")
    installs = []
    monkeypatch.setattr(browser, "install", lambda: installs.append(1))
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 0, r.output
    assert installs == [1]
    assert "✓ Browser: Playwright's Chromium" in r.stdout


def test_init_counts_end_of_input_as_no(monkeypatch):
    monkeypatch.setattr(browser, "find", lambda: None)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def eof(prompt):
        raise EOFError

    monkeypatch.setattr(cli.ui.console, "input", eof)
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 1
    assert "To download it later" in r.stdout
    assert "Unexpected error" not in r.stderr


def test_init_reports_a_failed_download_and_still_summarises(monkeypatch):
    from bac_common.errors import ExternalToolError

    monkeypatch.setattr(browser, "find", lambda: None)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli.ui.console, "input", lambda prompt: "yes")

    def failing():
        raise ExternalToolError("The Chromium download failed.", "exited with 1")

    monkeypatch.setattr(browser, "install", failing)
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 1
    assert "✗ The Chromium download failed." in r.stdout
    assert "Browser  :  none" in r.stdout


def test_init_with_a_wrong_source_is_a_usage_error(tmp_path):
    r = invoke(cli._main, ["--init", "--source", str(tmp_path)])
    assert r.exit_code == 2
    assert "Not a gallery folder" in r.stderr


def test_init_reports_a_bad_override(monkeypatch, tmp_path):
    monkeypatch.setenv(browser.ENV, str(tmp_path / "missing"))
    r = invoke(cli._main, ["--init"])
    assert r.exit_code == 1
    assert "✗ Browser: BAC_CHROMIUM_PATH names no file." in r.stdout


def test_env_file_sets_the_override(monkeypatch, tmp_path):
    exe = tmp_path / "chrome"
    exe.write_text("")
    env = tmp_path / "custom.env"
    env.write_text(f"BAC_CHROMIUM_PATH={exe}\n")
    monkeypatch.setattr(browser, "managed_path", lambda: None)
    r = invoke(cli._main, ["--env-file", str(env), "--dry-run", "--only", "product-sheet"])
    assert r.exit_code == 0, r.output
    assert "(BAC_CHROMIUM_PATH)" in r.stdout


def test_the_env_file_override_does_not_leak_into_the_next_test():
    import os

    assert "BAC_CHROMIUM_PATH" not in os.environ
