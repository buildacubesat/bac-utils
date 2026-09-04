# SPDX-License-Identifier: MIT
"""bac-kicad-hlabels – hierarchical labels for a list of net names.

Reads names from a file or stdin, writes the blocks to stdout or ``-o FILE``.
No persistent settings, so no ``--init``, ``--config`` or ``--env-file``;
every geometry and font value is a flag with the defaults that suit a
2.54 mm grid.

Exit codes: 0 written, 1 no names or unwritable output, 2 bad arguments.
"""

from __future__ import annotations

import sys
from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.errors import BacError, UsageError

from . import __version__
from .labels import JUSTIFY, ROTATIONS, SHAPES, LabelStyle, parse_names, render

TOOL = "bac-kicad-hlabels"


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Emit KiCad hierarchical-label blocks for a list of net names, one per line.",
        examples=[
            "bac-kicad-hlabels nets.txt > labels.kicad_snippet",
            "bac-kicad-hlabels nets.txt --gap-on-blank --shape input --at 0 25.4",
        ],
        init=False,
        dry_run=False,
        env_file=False,
        config=False,
    )
    parser.usage = (
        "bac-kicad-hlabels [INPUT] [-o FILE] [--at X Y] [--step MM] [--rotation DEG]\n"
        "                         [--font-size MM] [--shape S] [--justify J] [--gap-on-blank]"
    )
    parser.add_argument("input", nargs="?", metavar="INPUT", help="net names, one per line (default: stdin)")
    parser.add_argument("-o", "--output", metavar="FILE", help="write here instead of stdout")
    parser.add_argument("--at", nargs=2, type=float, metavar=("X", "Y"), default=(0.0, 0.0), help="mm (default 0 0)")
    parser.add_argument("--step", type=float, metavar="MM", default=2.54, help="Y distance between labels")
    parser.add_argument("--rotation", type=int, metavar="DEG", default=0, help="0, 90, 180 or 270")
    parser.add_argument("--font-size", type=float, metavar="MM", default=1.27, help="font size (default 1.27)")
    parser.add_argument("--shape", metavar="S", default="passive", help=", ".join(SHAPES))
    parser.add_argument("--justify", metavar="J", default="right", help="left or right")
    parser.add_argument("--gap-on-blank", action="store_true", help="a blank input line leaves one slot empty")
    args = parser.parse_args(argv)

    if args.shape not in SHAPES:
        raise UsageError(f"Unknown shape {args.shape!r}.", "One of: " + ", ".join(SHAPES))
    if args.justify not in JUSTIFY:
        raise UsageError(f"Unknown justification {args.justify!r}.", "left or right")
    if args.rotation not in ROTATIONS:
        raise UsageError(f"Rotation must be one of {', '.join(str(r) for r in ROTATIONS)}.")
    if args.step <= 0 or args.font_size <= 0:
        raise UsageError("--step and --font-size must be positive.")
    style = LabelStyle(shape=args.shape, justify=args.justify, rotation=args.rotation, font_size=args.font_size)

    if args.input and args.input != "-":
        source = Path(args.input).expanduser()
        if not source.is_file():
            raise UsageError(f"Input file does not exist: {args.input}")
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise BacError(f"Input is not UTF-8 text: {args.input}", str(exc)) from exc
        except OSError as exc:
            raise BacError(f"Cannot read {args.input}", exc.strerror or str(exc)) from exc
    else:
        text = sys.stdin.read()

    names = parse_names(text, gap_on_blank=args.gap_on_blank)
    count = sum(1 for n in names if n is not None)
    if not count:
        raise BacError("No net names in the input.", "One name per line; blank lines are ignored.")

    output = render(names, x=args.at[0], y_start=args.at[1], step=args.step, style=style)
    if args.output:
        target = Path(args.output).expanduser()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(output, encoding="utf-8")
        except OSError as exc:
            raise BacError(f"Cannot write {args.output}", exc.strerror or str(exc)) from exc
        ui.ok(f"Wrote {count} label(s) to {ui.path(target)}")
    else:
        sys.stdout.write(output)
    return 0
