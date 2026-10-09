# SPDX-License-Identifier: MIT
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from bac_reference_gallery import browser

from bac_common.errors import ConfigError, ExternalToolError


def test_the_override_wins(monkeypatch, tmp_path):
    exe = tmp_path / "chrome"
    exe.write_text("")
    monkeypatch.setenv(browser.ENV, str(exe))
    found = browser.find(which=lambda name: "/usr/bin/chromium", managed=lambda: Path("/x"))
    assert found == browser.Browser(exe, browser.ENV)


def test_an_override_naming_no_file_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv(browser.ENV, str(tmp_path / "missing"))
    with pytest.raises(ConfigError, match="names no file"):
        browser.find(which=lambda name: None, managed=lambda: None)


def test_playwrights_build_comes_before_the_system_one():
    found = browser.find(which=lambda name: "/usr/bin/chromium", managed=lambda: Path("/cache/chrome"))
    assert found == browser.Browser(None, "Playwright")
    assert browser.describe(found) == "Playwright's Chromium"


def test_a_system_browser_is_found_by_name():
    seen = []

    def which(name):
        seen.append(name)
        return "/usr/bin/google-chrome" if name == "google-chrome" else None

    found = browser.find(which=which, managed=lambda: None)
    assert found == browser.Browser(Path("/usr/bin/google-chrome"), "system")
    assert seen == ["chromium", "chromium-browser", "google-chrome"]
    assert browser.describe(found) == "/usr/bin/google-chrome (system)"


def test_none_found_and_require():
    assert browser.find(which=lambda name: None, managed=lambda: None) is None
    assert browser.describe(None) == "none found"
    with pytest.raises(ConfigError, match="No Chromium") as err:
        browser.require(None, "bac-reference-gallery")
    assert "--init" in err.value.detail


def test_install_runs_playwright_with_this_interpreter():
    calls = []

    def run(cmd, check):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    browser.install(run=run)
    assert calls == [browser.INSTALL_COMMAND]
    assert browser.INSTALL_COMMAND[1:] == ["-m", "playwright", "install", "chromium"]


def test_install_failures_are_external_errors():
    with pytest.raises(ExternalToolError, match="download failed"):
        browser.install(run=lambda cmd, check: subprocess.CompletedProcess(cmd, 3))

    def broken(cmd, check):
        raise OSError("no such interpreter")

    with pytest.raises(ExternalToolError, match="could not start"):
        browser.install(run=broken)
