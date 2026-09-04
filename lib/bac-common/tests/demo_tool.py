# SPDX-License-Identifier: MIT
"""A minimal tool built on bac-common, used by the tests as the reference shape."""

from __future__ import annotations

from pathlib import Path

from bac_common import cli, ui
from bac_common.config import default_config_path, load_env, load_toml, require_setup, write_config
from bac_common.errors import BacError, ConfigError, UserAbort

TOOL = "bac-demo"
VERSION = "0.2.0"

ITEMS = ["alpha", "beta", "gamma"]


def main(argv: list[str], debug: bool) -> int:
    parser = cli.make_parser(
        TOOL,
        VERSION,
        "Counts the files in a directory.",
        examples=["bac-demo ./docs", "bac-demo ./docs --dry-run", "bac-demo -l"],
        list_help="print the known item names and exit",
    )
    parser.add_argument("directory", nargs="?", help="directory to count")
    parser.add_argument("--boom", choices=["config", "abort", "crash", "interrupt"], help="fail in a chosen way")
    args = parser.parse_args(argv)

    if args.list:
        for item in ITEMS:
            print(item)
        return 0

    if args.init:
        # Setup runs before any config is loaded: the file may not exist yet.
        target = Path(args.config) if args.config else default_config_path(TOOL)
        write_config(target, '[paths]\ntarget = "/tmp/demo"\n', overwrite=True)
        ui.ok(f"Wrote {ui.path(target)}")
        return 0

    load_env(args.env_file)
    config = load_toml(TOOL, args.config)
    require_setup(TOOL, config, "paths.target")

    if args.boom == "config":
        raise ConfigError("Something is not configured.", "Set it and retry.")
    if args.boom == "abort":
        raise UserAbort()
    if args.boom == "crash":
        raise ValueError("unexpected [red]markup[/] in message")
    if args.boom == "interrupt":
        raise KeyboardInterrupt

    if not args.directory:
        raise BacError("A directory is required.")
    ui.opening(TOOL, VERSION, "Counting files.")
    count = sum(1 for p in Path(args.directory).iterdir() if p.is_file())
    ui.ok(f"Counted {count} file(s) in {ui.path(args.directory)}")
    ui.summary([("Files", count), ("Errors", 0)], dry_run=args.dry_run)
    return 0 if count else 3


def entry() -> None:
    cli.run(main)
