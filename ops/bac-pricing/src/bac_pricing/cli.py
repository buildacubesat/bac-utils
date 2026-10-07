# SPDX-License-Identifier: MIT
"""bac-pricing – opens the pricing notebook with the suite's settings resolved.

The notebook is a file inside this package; ``bac-pricing`` finds it,
resolves the backend, data directory and DSN the way every suite tool does
(``~/.config/bac/bac-suite.toml`` and ``BAC_DB_DSN`` in ``.env``), fails
early with a clear message when something is missing, and starts marimo on
it. ``--app`` serves it as an app (code hidden, controls live) instead of the editor.

Exit codes: 0 marimo exited normally, 1 setup or marimo failure, 2 bad arguments.
"""

from __future__ import annotations

import os
import subprocess
import sys

from bac_common import cli as bac_cli
from bac_common import ui
from bac_suite_db import config as suite_config
from bac_suite_db.cli import run_init
from bac_suite_db.dsn import describe

from . import NOTEBOOK, __version__

TOOL = "bac-pricing"


def main() -> None:
    bac_cli.run(_main)


def build_command(mode: str, host: str, port: int, headless: bool) -> list[str]:
    cmd = [sys.executable, "-m", "marimo", mode, str(NOTEBOOK), "--host", host, "--port", str(port)]
    if headless:
        cmd.append("--headless")
    return cmd


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Open the Build a CubeSat pricing notebook on the configured backend.",
        examples=["bac-pricing", "bac-pricing --app --port 2719"],
        config=False,
    )
    parser.add_argument(
        "--config", metavar="PATH", default=None, help="suite config (default: ~/.config/bac/bac-suite.toml)"
    )
    parser.add_argument("--app", action="store_true", help="serve as an app (marimo run, code hidden) instead of edit")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=2718, help="port (default: 2718)")
    parser.add_argument("--headless", action="store_true", help="do not open a browser")
    args = parser.parse_args(argv)

    if args.init:
        run_init(args.config, args.env_file)
        return 0

    settings = suite_config.load_settings(args.config, args.env_file)
    suite_config.require_setup(settings)
    mode = "run" if args.app else "edit"
    ui.opening(TOOL, __version__, "Assembly cost rollup and price derivation.")
    rows: list[tuple[str, object]] = [("Backend", settings.backend), ("Data directory", settings.data_dir)]
    if settings.uses_db:
        rows.append(("Database", describe(suite_config.require_dsn(settings))))
    rows.append(("Notebook", NOTEBOOK))
    ui.fields(rows)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        ui.warn(
            f"Binding to {args.host}: marimo has no authentication; anyone who reaches this port can edit and save."
        )

    cmd = build_command(mode, args.host, args.port, args.headless)
    if args.dry_run:
        ui.step("would run " + ui.esc(" ".join(cmd)))
        ui.summary([("Mode", mode)], dry_run=True)
        return 0
    env = dict(os.environ)
    env[suite_config.CONFIG_ENV] = str(settings.config_path)
    if settings.dsn:
        env[suite_config.DSN_ENV] = settings.dsn
    ui.step(f"marimo {mode} on http://{args.host}:{args.port} – Ctrl-C stops it")
    try:
        result = subprocess.run(cmd, env=env, check=False)
    except FileNotFoundError:
        ui.error("Python could not be started for marimo.", f"Interpreter: {sys.executable}")
        return 1
    ui.summary([("Mode", mode), ("Exit", result.returncode)])
    return 0 if result.returncode == 0 else 1
