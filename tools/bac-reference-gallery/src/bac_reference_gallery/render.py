# SPDX-License-Identifier: MIT
"""Board pages to PNG and PDF through a headless Chromium.

Each board is opened from its file URL, exactly as a browser shows it, in
the requested colour scheme. The board element's own box sets the output
size, so a portrait board needs no special case. Playwright is imported
when a run starts rendering (and by ``browser.managed_path`` to find its
Chromium), never at import time, so ``-v``, ``--help`` and ``-l`` stay fast.

The pages load their fonts from Google Fonts. Those requests go through a
route with a short timeout: a font host that does not answer costs one
timeout per run, after which the fonts are skipped and the system fallbacks
render, instead of every board waiting for the page's load event.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any

from bac_common.errors import ExternalToolError

from .browser import Browser
from .site import Board

FONT_FAMILIES = ("Nunito", "Nunito Sans", "IBM Plex Mono")
FONT_HOSTS = ("**://fonts.googleapis.com/**", "**://fonts.gstatic.com/**")
FONT_TIMEOUT_MS = 8_000
TIMEOUT_MS = 30_000
DEFAULT_VIEWPORT = {"width": 1600, "height": 1000}

_BOARD_SIZE_JS = """() => {
  const el = document.querySelector('.board') || document.documentElement;
  const r = el.getBoundingClientRect();
  return [Math.ceil(r.width), Math.ceil(r.height)];
}"""

# A family is missing when text set in it measures exactly like each generic fallback.
_MISSING_FONTS_JS = """(families) => {
  const ctx = document.createElement('canvas').getContext('2d');
  const sample = 'mmmmmmmmmmlli1WQ@#';
  return families.filter((family) => ['monospace', 'serif', 'sans-serif'].every((generic) => {
    ctx.font = `72px ${generic}`;
    const fallback = ctx.measureText(sample).width;
    ctx.font = `72px "${family}", ${generic}`;
    return ctx.measureText(sample).width === fallback;
  }));
}"""


@dataclass
class Rendered:
    width: int
    height: int
    files: list[Path] = field(default_factory=list)
    missing_fonts: list[str] = field(default_factory=list)


def short_error(exc: BaseException) -> str:
    """The first line of an exception, for a ✗ line; Playwright appends a call log below it."""
    text = str(exc).strip().splitlines()
    first = text[0] if text else type(exc).__name__
    return first if len(first) <= 160 else first[:157] + "..."


class FontGate:
    """Route handler for the font hosts: fetch with a timeout, and give up on them after the first failure."""

    def __init__(self, timeout_ms: int = FONT_TIMEOUT_MS) -> None:
        self.timeout_ms = timeout_ms
        self.unreachable = False

    def __call__(self, route: Any) -> None:
        if self.unreachable:
            route.abort()
            return
        try:
            response = route.fetch(timeout=self.timeout_ms)
        except Exception:  # noqa: BLE001 – any failure means the fonts are not coming
            self.unreachable = True
            route.abort()
            return
        route.fulfill(response=response)


class Renderer:
    """One browser for a whole run: ``with Renderer(browser, "light") as r: r.render(board, png, pdf)``."""

    def __init__(self, browser: Browser, theme: str) -> None:
        self.browser = browser
        self.theme = theme
        self.fonts = FontGate()
        self._pw: Any = None
        self._chromium: Any = None
        self._context: Any = None
        self._interrupted = False

    def __enter__(self) -> Renderer:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ExternalToolError("Playwright is not installed.", f"Reinstall the tool: {exc}") from exc

        try:
            self._pw = sync_playwright().start()
        except PlaywrightError as exc:
            raise ExternalToolError("Playwright's driver did not start.", short_error(exc)) from exc
        try:
            kwargs: dict[str, Any] = {"headless": True}
            if self.browser.path is not None:
                kwargs["executable_path"] = str(self.browser.path)
            self._chromium = self._pw.chromium.launch(**kwargs)
            self._context = self._chromium.new_context(
                viewport=DEFAULT_VIEWPORT,
                device_scale_factor=1,
                color_scheme=self.theme,
                reduced_motion="reduce",
            )
            for pattern in FONT_HOSTS:
                self._context.route(pattern, self.fonts)
        except PlaywrightError as exc:
            self._close()
            raise ExternalToolError("Chromium did not start.", short_error(exc)) from exc
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        # Ctrl-C reaches the whole process group: Playwright's driver and the
        # browser are gone, and a close() on them would wait for ever. The
        # call that was cut off leaves an asyncio task behind, which asyncio
        # would report at exit; that report is noise after "Interrupted.".
        if self._interrupted or (exc_type is not None and issubclass(exc_type, KeyboardInterrupt)):
            logging.getLogger("asyncio").setLevel(logging.CRITICAL)
            return
        if exc_type is None:
            self._close(strict=True)
        else:
            self._close()  # a failing close must not hide the error that ended the run

    def _close(self, strict: bool = False) -> None:
        errors: list[BaseException] = []
        for step in (getattr(self._chromium, "close", None), getattr(self._pw, "stop", None)):
            if step is None:
                continue
            try:
                step()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
        if strict and errors:
            raise ExternalToolError("Chromium did not close cleanly.", short_error(errors[0]))

    def render(self, board: Board, png: Path | None, pdf: Path | None) -> Rendered:
        page = self._context.new_page()
        try:
            page.goto(board.path.as_uri(), wait_until="load", timeout=TIMEOUT_MS)
            page.evaluate("document.fonts.ready.then(() => true)")
            width, height = page.evaluate(_BOARD_SIZE_JS)
            page.set_viewport_size({"width": width, "height": height})
            result = Rendered(width, height, missing_fonts=page.evaluate(_MISSING_FONTS_JS, list(FONT_FAMILIES)))
            if png is not None:
                png.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": width, "height": height})
                result.files.append(png)
            if pdf is not None:
                pdf.parent.mkdir(parents=True, exist_ok=True)
                page.emulate_media(media="screen")
                page.add_style_tag(content=f"@page {{ size: {width}px {height}px; margin: 0; }}")
                page.pdf(
                    path=str(pdf),
                    width=f"{width}px",
                    height=f"{height}px",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                    prefer_css_page_size=True,
                )
                result.files.append(pdf)
            return result
        except KeyboardInterrupt:
            self._interrupted = True
            raise
        finally:
            if not self._interrupted:
                with contextlib.suppress(Exception):
                    page.close()


def merge_pdfs(paths: list[Path], output: Path) -> None:
    """One PDF with every board as a page, in the given order; written beside the parts."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for path in paths:
        for page in PdfReader(str(path)).pages:
            writer.add_page(page)
    tmp = output.with_name(output.name + ".part")
    with tmp.open("wb") as fh:
        writer.write(fh)
    tmp.replace(output)
