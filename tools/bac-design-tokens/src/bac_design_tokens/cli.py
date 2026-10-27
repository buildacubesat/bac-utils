# SPDX-License-Identifier: MIT
"""bac-design-tokens – write every copy of the BAC design tokens from tokens.json.

Exit codes: 0 every copy current (or written), 1 a copy is stale under --check or a
target cannot be updated, 2 bad arguments.
"""

from __future__ import annotations

from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import ui

from . import __version__
from .build import find_root, targets

TOOL = "bac-design-tokens"


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Write tokens.css, the Rich colours and the notebook style cells from tokens.json.",
        examples=["bac-design-tokens", "bac-design-tokens --check"],
        init=False,
        dry_run=False,
        env_file=False,
        config=False,
    )
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if any copy is stale")
    parser.add_argument("--root", metavar="PATH", help="the bac-utils checkout (default: found from here)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else find_root(Path.cwd().resolve())
    stale = written = current = 0
    for target in targets(root):
        rel = target.path.relative_to(root)
        old = target.path.read_text(encoding="utf-8") if target.path.exists() else None
        new = target.wanted()
        if old == new:
            current += 1
            ui.dim(f"{rel} is current")
        elif args.check:
            stale += 1
            ui.fail(f"Stale: {ui.path(rel)}")
        else:
            target.path.write_text(new, encoding="utf-8")
            written += 1
            ui.ok(f"Written: {ui.path(rel)}")
    rows = [("Current", current), ("Stale" if args.check else "Written", stale if args.check else written)]
    ui.summary(rows)
    if stale:
        ui.error("Copies are out of date with tokens.json.", f"Run `{TOOL}` and commit the result.")
        return 1
    return 0
