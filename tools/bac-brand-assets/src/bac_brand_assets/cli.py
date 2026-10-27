# SPDX-License-Identifier: MIT
"""bac-brand-assets – write the BAC symbol, wordmark and logo SVGs into bac-design/assets.

Exit codes: 0 every asset current (or written), 1 an asset is stale under --check or the
bac-design checkout cannot be found, 2 bad arguments.
"""

from __future__ import annotations

from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.errors import ConfigError

from . import __version__
from .assets import VERSION, assets, find_design
from .wordmark import FONT_FILE

TOOL = "bac-brand-assets"


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        f"Write the Build a CubeSat symbol, wordmark and logo ({VERSION}) as SVG.",
        examples=[
            "bac-brand-assets",
            "bac-brand-assets --check",
            "bac-brand-assets --design ~/bac/bac-design -o /tmp/assets",
        ],
        list_help="print the asset file names and exit",
        init=False,
        env_file=False,
        config=False,
    )
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if any asset is stale")
    parser.add_argument("--design", metavar="PATH", help="the bac-design checkout (default: found from here)")
    parser.add_argument("-o", "--out-dir", metavar="DIR", help="where to write (default: <design>/assets)")
    args = parser.parse_args(argv)

    if args.list:
        for asset in assets():
            print(asset.name)
        return 0

    design = Path(args.design).resolve() if args.design else find_design(Path.cwd().resolve())
    if design is None:
        raise ConfigError("No bac-design checkout found.", "Pass --design PATH or run inside the checkout.")
    fonts = design / "fonts"
    if not (fonts / FONT_FILE).is_file():
        raise ConfigError(f"{FONT_FILE} is missing.", f"Expected it in {fonts}.")
    out = Path(args.out_dir).resolve() if args.out_dir else design / "assets"

    stale = written = current = 0
    for asset in assets():
        target = out / asset.name
        old = target.read_text(encoding="utf-8") if target.exists() else None
        new = asset.render(fonts)
        if old == new:
            current += 1
            ui.dim(f"{asset.name} is current")
        elif args.check:
            stale += 1
            ui.fail(f"Stale: {ui.path(asset.name)}")
        elif args.dry_run:
            stale += 1
            ui.step(f"Would write: {ui.path(asset.name)}")
        else:
            out.mkdir(parents=True, exist_ok=True)
            target.write_text(new, encoding="utf-8")
            written += 1
            ui.ok(f"Written: {ui.path(asset.name)}")
    label = "Stale" if args.check or args.dry_run else "Written"
    ui.summary([("Current", current), (label, stale or written)], dry_run=args.dry_run)
    if args.check and stale:
        ui.error("Assets are out of date with their construction.", f"Run `{TOOL}` and commit the result.")
        return 1
    return 0
