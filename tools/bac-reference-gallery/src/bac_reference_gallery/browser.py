# SPDX-License-Identifier: MIT
"""Which Chromium renders the boards.

``BAC_CHROMIUM_PATH`` wins when set. Otherwise Playwright's own Chromium is
used if it has been downloaded (``--init`` offers that), then a system
Chromium or Chrome on ``PATH``. Playwright's build comes first because a
packaged system browser can be confined: Ubuntu's snap Chromium cannot read
hidden folders such as ``~/.local``, where an installed tool keeps its pages.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bac_common.errors import ConfigError, ExternalToolError

ENV = "BAC_CHROMIUM_PATH"
SYSTEM_NAMES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
INSTALL_COMMAND = [sys.executable, "-m", "playwright", "install", "chromium"]


@dataclass(frozen=True)
class Browser:
    path: Path | None  # None: let Playwright launch the build it manages
    source: str  # BAC_CHROMIUM_PATH, Playwright, system


def managed_path() -> Path | None:
    """Where Playwright's Chromium is, if it has been downloaded.

    Asking starts Playwright's driver for a moment; a Playwright that cannot
    be imported or whose driver does not start is an :class:`ExternalToolError`.
    """
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ExternalToolError("Playwright is not installed.", f"Reinstall the tool: {exc}") from exc
    try:
        with sync_playwright() as pw:
            path = Path(pw.chromium.executable_path)
    except PlaywrightError as exc:
        raise ExternalToolError("Playwright's driver did not start.", str(exc).splitlines()[0]) from exc
    return path if path.is_file() else None


def find(
    *, which: Callable[[str], str | None] = shutil.which, managed: Callable[[], Path | None] | None = None
) -> Browser | None:
    """The browser to use, or ``None`` when there is none."""
    override = os.getenv(ENV)
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise ConfigError(f"{ENV} names no file.", f"{path} – fix the variable or unset it.")
        return Browser(path, ENV)
    if (managed or managed_path)() is not None:
        return Browser(None, "Playwright")
    for name in SYSTEM_NAMES:
        found = which(name)
        if found:
            return Browser(Path(found), "system")
    return None


def require(browser: Browser | None, tool: str) -> Browser:
    if browser is None:
        raise ConfigError(
            "No Chromium found to render with.",
            f"Run {tool} --init, or set {ENV}.",
        )
    return browser


def describe(browser: Browser | None) -> str:
    if browser is None:
        return "none found"
    if browser.path is None:
        return "Playwright's Chromium"
    return f"{browser.path} ({browser.source})"


def install(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None:
    """Download Playwright's Chromium with this interpreter's Playwright, output passed through."""
    try:
        result = run(INSTALL_COMMAND, check=False)
    except OSError as exc:
        raise ExternalToolError("The Chromium download could not start.", str(exc)) from exc
    if result.returncode != 0:
        raise ExternalToolError(
            "The Chromium download failed.",
            f"{' '.join(INSTALL_COMMAND)} exited with {result.returncode}.",
        )
