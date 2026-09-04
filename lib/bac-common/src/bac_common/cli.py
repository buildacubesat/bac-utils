# SPDX-License-Identifier: MIT
"""Command-line scaffolding: the standard flags and the error boundary.

A minimal BAC tool looks like this::

    from bac_common import cli, ui
    from bac_common.errors import BacError

    TOOL, VERSION = "bac-example", "0.1.0"

    def main(argv: list[str], debug: bool) -> int:
        parser = cli.make_parser(TOOL, VERSION, "Does one thing.", examples=["bac-example input.txt"])
        parser.add_argument("input")
        args = parser.parse_args(argv)
        ui.opening(TOOL, VERSION, "Processing one file.")
        ...
        ui.summary([("Processed", 1)], dry_run=args.dry_run)
        return 0

    def entry() -> None:
        cli.run(main)

``entry`` is the ``[project.scripts]`` target. :func:`run` strips ``--debug``
from anywhere in the argument list, calls ``main``, and maps every
:class:`~bac_common.errors.BacError` to a formatted stderr line and the
right exit code. Tools built on Typer use :func:`run` the same way and call
``app(args=argv)`` inside ``main``.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from collections.abc import Callable, Sequence
from typing import NoReturn

from . import ui
from .errors import BacError, UserAbort

__all__ = [
    "version_string",
    "make_parser",
    "add_standard_flags",
    "strip_debug",
    "run",
    "help_text",
]

MainFn = Callable[[list[str], bool], int | None]


def version_string(tool: str, version: str) -> str:
    """``bac-toolname v0.1.0`` – the ``-v`` output."""
    return f"{tool} {ui.display_version(version)}"


class _Formatter(argparse.RawDescriptionHelpFormatter):
    """Keeps the Examples block verbatim. Defaults are written into help strings where they matter."""


def make_parser(
    tool: str,
    version: str,
    description: str,
    *,
    examples: Sequence[str] = (),
    list_help: str | None = None,
    init: bool = True,
    dry_run: bool = True,
    env_file: bool = True,
    config: bool = True,
) -> argparse.ArgumentParser:
    """An ``ArgumentParser`` with the guide's standard flags and help layout.

    ``description`` should be one sentence. ``examples`` become the
    ``Examples:`` block at the end of ``--help``; give two or three.
    """
    epilog = None
    if examples:
        epilog = "Examples:\n" + "\n".join(f"  {e}" for e in examples)
    parser = argparse.ArgumentParser(
        prog=tool,
        description=description,
        epilog=epilog,
        formatter_class=_Formatter,
        allow_abbrev=False,
    )
    add_standard_flags(
        parser,
        tool=tool,
        version=version,
        list_help=list_help,
        init=init,
        dry_run=dry_run,
        env_file=env_file,
        config=config,
    )
    return parser


def add_standard_flags(
    parser: argparse.ArgumentParser,
    *,
    tool: str,
    version: str,
    list_help: str | None = None,
    init: bool = True,
    dry_run: bool = True,
    env_file: bool = True,
    config: bool = True,
) -> None:
    """Add the BAC Project & Tooling Guide §3.3 flags to an existing parser.

    ``-v`` is always added. ``-l/--list`` is added only when ``list_help`` is
    given, because it only makes sense for tools that operate on a named set.
    ``--debug`` is hidden from ``--help`` and is normally consumed by
    :func:`run` before the parser sees it; it is registered here too so that
    a tool calling ``parse_args`` directly does not reject it.
    """
    parser.add_argument(
        "-v", "--version", action="version", version=version_string(tool, version), help="print version and exit"
    )
    if list_help:
        parser.add_argument("-l", "--list", action="store_true", help=list_help)
    if env_file:
        parser.add_argument(
            "--env-file", metavar="PATH", default=None, help=".env file to load (default: nearest .env)"
        )
    if config:
        parser.add_argument(
            "--config", metavar="PATH", default=None, help=f"TOML config (default: ~/.config/bac/{tool}.toml)"
        )
    if dry_run:
        parser.add_argument("--dry-run", action="store_true", help="plan and validate; change nothing")
    if init:
        parser.add_argument("--init", action="store_true", help="first-time setup (safe to re-run)")
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)


def strip_debug(argv: Sequence[str]) -> tuple[list[str], bool]:
    """Remove ``--debug`` wherever it appears and report whether it was present."""
    debug = "--debug" in argv
    return [a for a in argv if a != "--debug"], debug


def run(main: MainFn, argv: Sequence[str] | None = None) -> NoReturn:
    """The error boundary every BAC tool runs inside.

    Calls ``main(argv, debug)`` and exits with its return value (``None`` is
    0). Expected errors print as ``ERROR message`` on stderr with their exit
    code; unexpected ones are summarised in one line unless ``--debug`` is
    set, in which case the traceback is shown. Ctrl-C exits 1 after a short
    note, and ``SystemExit`` from argparse passes through unchanged.
    """
    args, debug = strip_debug(sys.argv[1:] if argv is None else argv)
    try:
        code = main(args, debug)
    except UserAbort as exc:
        ui.step(exc.message)
        raise SystemExit(exc.exit_code) from None
    except BacError as exc:
        ui.error(ui.esc(exc.message), ui.esc(exc.detail) if exc.detail else None)
        if debug:
            ui.err_console.print(traceback.format_exc(), highlight=False, markup=False)
        raise SystemExit(exc.exit_code) from None
    except KeyboardInterrupt:
        ui.step("Interrupted.")
        raise SystemExit(1) from None
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 – the whole point of the boundary
        if debug:
            raise
        ui.error(f"Unexpected error: {ui.esc(str(exc))}", "Re-run with --debug for the full traceback.")
        raise SystemExit(1) from None
    raise SystemExit(0 if code is None else int(code))


def help_text(parser: argparse.ArgumentParser, width: int = 80) -> str:
    """The ``--help`` output at a fixed width, for tests asserting the ≤24-line rule."""
    parser.formatter_class = lambda prog: _Formatter(prog, width=width)  # type: ignore[assignment]
    return parser.format_help()
