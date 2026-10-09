# SPDX-License-Identifier: MIT
"""bac-reference-gallery – the reference boards to PNG and PDF, or in a browser.

Renders every board of the gallery (or the ones named with ``--only``) into
``png/`` and ``pdf/`` below the output folder, plus one combined PDF after a
complete run of the whole gallery. Renders are meant to be regenerated, so an
existing file is overwritten and the ✓ line says so. ``--serve`` shows the
pages in a browser over http://127.0.0.1 until Ctrl-C. ``--init`` checks the
pages and the browser and offers to download Playwright's Chromium.

Exit codes: 0 every board rendered (or the server stopped with Ctrl-C), 1 at
least one board failed, no browser was found or the server did not start,
2 bad arguments.
"""

from __future__ import annotations

import contextlib
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.config import load_env
from bac_common.errors import BacError, ConfigError, ExternalToolError, UsageError

from . import TOOL_NAME, __version__, browser, serve, site
from .render import Renderer, merge_pdfs, short_error

DESCRIPTION = "Render the BAC reference gallery's boards to PNG and PDF, or serve them."
FORMATS = ("png", "pdf", "both")
THEMES = ("light", "dark")
COMBINED = "bac-reference-exemplars"


def main() -> None:
    bac_cli.run(_main)


def build_parser():
    p = bac_cli.make_parser(
        TOOL_NAME,
        __version__,
        DESCRIPTION,
        examples=[
            f"{TOOL_NAME} --only ops-vs-mission --format png",
            f"{TOOL_NAME} --theme dark --out-dir ~/Desktop/gallery",
            f"{TOOL_NAME} --serve",
        ],
        list_help="list the boards and exit",
        config=False,
    )
    p.usage = f"{TOOL_NAME} [options]"
    p.add_argument("--only", metavar="NAME", action="append", help="render this board only (repeatable)")
    p.add_argument("--format", metavar="FMT", choices=FORMATS, help="png, pdf or both (default both)")
    p.add_argument("--theme", metavar="MODE", choices=THEMES, help="light or dark (default light)")
    p.add_argument("--out-dir", metavar="DIR", help="folder for png/ and pdf/ (default ./exports)")
    p.add_argument("--source", metavar="DIR", help="gallery folder (default: the installed pages)")
    p.add_argument("--serve", action="store_true", help="show the pages in a browser (local HTTP server)")
    return p


def outputs(board: site.Board, out_dir: Path, fmt: str, theme: str) -> tuple[Path | None, Path | None]:
    """Where one board's PNG and PDF go; a dark render carries ``-dark`` in its name."""
    stem = board.name if theme == "light" else f"{board.name}-{theme}"
    png = out_dir / "png" / f"{stem}.png" if fmt in ("png", "both") else None
    pdf = out_dir / "pdf" / f"{stem}.pdf" if fmt in ("pdf", "both") else None
    return png, pdf


def combined_path(out_dir: Path, theme: str) -> Path:
    stem = COMBINED if theme == "light" else f"{COMBINED}-{theme}"
    return out_dir / "pdf" / f"{stem}.pdf"


def _kinds(paths: tuple[Path | None, Path | None]) -> str:
    """``png, pdf`` – the formats a board is written in; the names follow from the board."""
    return ", ".join(p.suffix.lstrip(".") for p in paths if p is not None)


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _main(argv: list[str], debug: bool) -> int:
    args = build_parser().parse_args(argv)
    load_env(args.env_file)
    source = Path(args.source) if args.source else None
    if args.init:
        if source is not None:
            site.find_site(source)  # a wrong --source is a usage error, before any panel
        return run_init(source)

    if args.serve and not args.list:
        given = [
            flag
            for flag, value in (
                ("--only", args.only),
                ("--format", args.format),
                ("--theme", args.theme),
                ("--out-dir", args.out_dir),
            )
            if value
        ]
        if given:
            raise UsageError(f"--serve takes no render options: {', '.join(given)}", "Render without --serve.")

    folder = site.find_site(source)
    every = site.boards(folder)
    if args.list:
        for board in every:
            print(board.name)
        return 0
    if args.serve:
        return run_serve(folder, args.dry_run)
    fmt = args.format or "both"
    theme = args.theme or "light"
    chosen = site.select(every, args.only)
    if not chosen:
        raise ConfigError("The gallery has no boards.", f"{folder / 'examples'} holds no .html page.")
    out_dir = (Path(args.out_dir).expanduser() if args.out_dir else Path.cwd() / "exports").resolve()
    if out_dir.exists() and not out_dir.is_dir():
        raise UsageError(f"--out-dir {args.out_dir} is not a folder.")
    whole_gallery = len(chosen) == len(every)

    what = {"png": "PNG", "pdf": "PDF", "both": "PNG and PDF"}[fmt]
    ui.opening(TOOL_NAME, __version__, f"Render {len(chosen)} board(s) as {what}, {theme} mode.")

    rendered = failed = written = 0
    pdfs: list[Path] = []
    try:
        if args.dry_run:
            try:
                browser_text = browser.describe(browser.find())
            except BacError as exc:  # a dry run reports the problem and goes on
                browser_text = f"unavailable – {exc.message}"
            ui.fields([("Pages", folder), ("Output", out_dir), ("Browser", browser_text)])
            for board in chosen:
                ui.step(f"{ui.path(board.name)} → {_kinds(outputs(board, out_dir, fmt, theme))}")
                rendered += 1
            if fmt != "png" and whole_gallery and len(chosen) > 1:
                ui.step(f"combined → {ui.esc(_rel(combined_path(out_dir, theme), out_dir))}")
            return 0
        found = browser.require(browser.find(), TOOL_NAME)
        ui.fields([("Pages", folder), ("Output", out_dir), ("Browser", browser.describe(found))])
        with contextlib.ExitStack() as stack:
            with ui.spinner("Starting Chromium"):
                renderer = stack.enter_context(Renderer(found, theme))
            fonts_reported = False
            for board in chosen:
                png, pdf = outputs(board, out_dir, fmt, theme)
                targets = [p for p in (png, pdf) if p is not None]
                existed = any(p.exists() for p in targets)
                try:
                    with ui.spinner(f"Rendering {ui.esc(board.name)}"):
                        result = renderer.render(board, png, pdf)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:  # noqa: BLE001 – one broken page must not end the batch
                    ui.fail(f"{ui.path(board.name)}: {ui.esc(short_error(exc))}")
                    if debug:
                        ui.err_console.print(traceback.format_exc(), highlight=False, markup=False)
                    failed += 1
                    continue
                if result.missing_fonts and not fonts_reported:
                    ui.warn(f"Fonts missing, fallbacks used: {ui.esc(', '.join(result.missing_fonts))}")
                    ui.dim("The pages load them from Google Fonts – render online or install them locally.")
                    fonts_reported = True
                over = " [dim](overwritten)[/dim]" if existed else ""
                ui.ok(f"{ui.path(board.name)} {result.width} × {result.height} → {_kinds((png, pdf))}{over}")
                rendered += 1
                written += len(result.files)
                if pdf is not None:
                    pdfs.append(pdf)
        if len(pdfs) > 1 and not whole_gallery:
            ui.dim("Combined PDF left as it was: --only renders part of the gallery.")
        elif len(pdfs) > 1 and failed:
            ui.warn(f"Combined PDF not written: {failed} board(s) failed.")
        elif len(pdfs) > 1:
            target = combined_path(out_dir, theme)
            existed = target.exists()
            merge_pdfs(pdfs, target)
            over = " [dim](overwritten)[/dim]" if existed else ""
            ui.ok(f"Combined {len(pdfs)} pages → {ui.path(_rel(target, out_dir))}{over}")
            written += 1
    finally:
        ui.summary(
            [
                ("Boards", len(chosen)),
                ("Planned" if args.dry_run else "Rendered", rendered),
                ("Failed", failed),
                ("Files written", written),
            ],
            dry_run=args.dry_run,
        )
    return 1 if failed else 0


def run_serve(folder: Path, dry_run: bool) -> int:
    """Serve the gallery folder on 127.0.0.1 and open it in the default browser; Ctrl-C stops.

    The server answers before the browser is asked to open the page: some
    browser commands (a ``BROWSER`` setting, a text browser without a display)
    return only once they exit, so they must find the server running.
    """
    ui.opening(TOOL_NAME, __version__, "Show the gallery in a browser, served from this computer.")
    server: serve.GalleryServer | None = None
    thread: threading.Thread | None = None
    planned = f"http://{serve.HOST}:{serve.PORT}/ (a free port if that one is taken)"
    try:
        if dry_run:
            ui.fields([("Pages", folder), ("Address", planned)])
            return 0
        try:
            server = serve.make_server(folder)
        except OSError as exc:
            raise ExternalToolError("The local web server did not start.", str(exc)) from exc
        ui.fields([("Pages", folder), ("Address", server.url)])
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
        thread.start()
        try:
            if _open_browser(server.url):
                ui.step("Opening it in the default browser.")
            else:
                ui.warn("No browser could be started – open the address yourself.")
            ui.dim("Serving until Ctrl-C.")
            while thread.is_alive():
                thread.join(0.5)
        except KeyboardInterrupt:
            ui.console.print()  # the ^C keeps its own line
    finally:
        if thread is not None and server is not None:
            server.shutdown()
            thread.join(5)
        if server is not None:
            server.server_close()
        ui.summary(
            [("Address", server.url if server else planned), ("Requests", server.requests if server else 0)],
            dry_run=dry_run,
        )
    return 0


def _open_browser(url: str) -> bool:
    """Ask the system for its browser; a broken browser setting is reported, not fatal."""
    try:
        return bool(webbrowser.open(url))
    except Exception:  # noqa: BLE001 – webbrowser raises whatever the launcher raised
        return False


def run_init(source: Path | None) -> int:
    """Check the pages and the browser; offer Playwright's Chromium when there is none."""
    ui.opening(TOOL_NAME, __version__, "Check the gallery pages and the browser the renderer uses.")
    problems = 0
    count = 0
    found: browser.Browser | None = None
    try:
        try:
            folder = site.find_site(source)
            count = len(site.boards(folder))
            ui.ok(f"Pages: {ui.path(folder)} ({count} boards)")
        except BacError as exc:
            ui.fail(f"Pages: {ui.esc(exc.message)}")
            problems += 1
        try:
            found = browser.find()
        except BacError as exc:
            ui.fail(f"Browser: {ui.esc(exc.message)} {ui.esc(exc.detail or '')}")
            problems += 1
            return 1
        if found is None:
            ui.warn("No Chromium found.")
            if sys.stdin.isatty() and _ask("  Download Playwright's Chromium (about 150 MB) now? [y/N] "):
                ui.step("Downloading – Playwright reports its own progress.")
                try:
                    browser.install()
                    found = browser.find()
                except BacError as exc:
                    ui.fail(f"{ui.esc(exc.message)} {ui.esc(exc.detail or '')}")
        if found is not None:
            ui.ok(f"Browser: {ui.esc(browser.describe(found))}")
        else:
            ui.dim(f"To download it later: {ui.esc(' '.join(browser.INSTALL_COMMAND))}")
            ui.dim(f"Or point {browser.ENV} at a Chromium or Chrome in a .env file.")
            problems += 1
    finally:
        ui.summary([("Boards", count), ("Browser", found.source if found else "none")])
    return 1 if problems else 0


def _ask(prompt: str) -> bool:
    """A [y/N] answer; end of input counts as no."""
    try:
        return ui.console.input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False
