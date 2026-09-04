# SPDX-License-Identifier: MIT
"""bac-markdown-to-youtube – a filter: Markdown in, YouTube description out.

Reads a file or stdin and writes to stdout unless ``-o FILE`` is given, so
it composes with pipes and clipboards. It has no persistent settings, hence
no ``--init``, ``--config`` or ``--env-file``.

Exit codes: 0 converted, 1 could not read or write, 2 bad arguments.
"""

from __future__ import annotations

import sys
from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.errors import BacError, UsageError

from . import __version__
from .convert import convert

TOOL = "bac-markdown-to-youtube"


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Convert Markdown into the formatting YouTube renders in video descriptions.",
        examples=[
            "bac-markdown-to-youtube notes.md > description.txt",
            "cat notes.md | bac-markdown-to-youtube -o description.txt",
        ],
        init=False,
        dry_run=False,
        env_file=False,
        config=False,
    )
    parser.add_argument("input", nargs="?", metavar="INPUT", help="Markdown file (default: stdin, also -)")
    parser.add_argument("-o", "--output", metavar="FILE", help="write here instead of stdout")
    args = parser.parse_args(argv)

    if args.input and args.input != "-":
        source = Path(args.input).expanduser()
        if not source.is_file():
            raise UsageError(f"Input file does not exist: {args.input}")
        try:
            markdown = source.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise BacError(f"Input is not UTF-8 text: {args.input}", str(exc)) from exc
        except OSError as exc:
            raise BacError(f"Cannot read {args.input}", exc.strerror or str(exc)) from exc
    else:
        markdown = sys.stdin.read()

    text = convert(markdown)

    if args.output:
        target = Path(args.output).expanduser()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise BacError(f"Cannot write {args.output}", exc.strerror or str(exc)) from exc
        ui.ok(f"Wrote {ui.path(target)} ({len(text.splitlines())} lines)")
    else:
        sys.stdout.write(text)
    return 0
