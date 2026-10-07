# SPDX-License-Identifier: MIT
"""bac-suite – serves the operations suite: the index and every installed engine's notebook.

Settings come from the suite config (``bac-db --init`` writes it); the
notebooks resolve the backend themselves through the same config and
``BAC_DB_DSN``. The shell binds to localhost by default because marimo has
no authentication of its own.

Exit codes: 0 server stopped normally, 1 setup or server failure, 2 bad arguments.
"""

from __future__ import annotations

import os

from bac_common import cli as bac_cli
from bac_common import ui
from bac_suite_db import config as suite_config
from bac_suite_db.cli import run_init
from bac_suite_db.dsn import describe

from . import __version__
from .app import create_app, discover_tools

TOOL = "bac-suite"


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Serve the Build a CubeSat operations suite: an index and every notebook.",
        examples=["bac-suite", "bac-suite --port 2720 --dry-run"],
        list_help="list the registered notebooks and exit",
        config=False,
    )
    parser.add_argument(
        "--config", metavar="PATH", default=None, help="suite config (default: ~/.config/bac/bac-suite.toml)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=2718, help="port (default: 2718)")
    args = parser.parse_args(argv)

    if args.init:
        run_init(args.config, args.env_file)
        return 0
    tools = discover_tools()
    if args.list:
        for tool in tools:
            print(f"{tool.label}\t{tool.route}")
        return 0

    settings = suite_config.load_settings(args.config, args.env_file)
    suite_config.require_setup(settings)
    ui.opening(TOOL, __version__, "Orchestrated mode: every engine on the same store.")
    rows: list[tuple[str, object]] = [("Backend", settings.backend), ("Data directory", settings.data_dir)]
    if settings.uses_db:
        rows.append(("Database", describe(suite_config.require_dsn(settings))))
    ui.fields(rows)
    for tool in tools:
        ui.step(f"{tool.label:<12} http://{args.host}:{args.port}{tool.route}")
    if not tools:
        ui.warn("No engines installed; the index will be empty.")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        ui.warn(
            f"Binding to {args.host}: marimo has no authentication; anyone who reaches this port can edit and save."
        )
    if args.dry_run:
        ui.summary([("Engines", len(tools))], dry_run=True)
        return 0

    os.environ[suite_config.CONFIG_ENV] = str(settings.config_path)
    if settings.dsn:
        os.environ[suite_config.DSN_ENV] = settings.dsn
    import uvicorn

    ui.step(f"serving on http://{args.host}:{args.port} – Ctrl-C stops it")
    uvicorn.run(create_app(tools), host=args.host, port=args.port, log_level="warning")
    ui.summary([("Engines", len(tools))])
    return 0
