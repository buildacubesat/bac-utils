# SPDX-License-Identifier: MIT
"""bac-convention-check – scan a repository for drift from the BAC conventions.

Read-only by nature, so it has no ``--dry-run`` and no ``--init``; the only
persistent settings are per repository, in ``<root>/bac-convention-check.toml``::

    # bac-convention-check.toml
    # Build a CubeSat – bac-convention-check configuration for this repository
    rules = ["guide"]          # bundled set names or paths relative to this file
    max_hits = 40

    [exclude]                  # paths a rule must skip; "*" applies to all rules
    "*" = ["docs/legacy/**"]
    A1 = ["src/parser.py"]     # the parser tolerates em dashes on purpose

Exit codes: 0 clean, 1 blocking findings or rule errors, 2 bad arguments.
"""

from __future__ import annotations

import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from bac_common import cli as bac_cli
from bac_common.errors import ConfigError, UsageError

from . import __version__
from .builtins import BUILTINS
from .engine import FileIndex, enumerate_files, run_rules
from .report import RunMeta, blocking_count, error_count, render_report, render_terminal, render_tsv
from .rules import BUNDLED_SETS, load_rules

TOOL = "bac-convention-check"
CONFIG_NAME = "bac-convention-check.toml"
FORMATS = ("terminal", "report", "tsv")
SEVERITIES = ("all", "blocking")


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Scan a repository for drift from the Build a CubeSat conventions.",
        examples=[
            "bac-convention-check ~/repos/bac-software --rules guide --rules firmware",
            "bac-convention-check --severity blocking --format report > scan.txt",
        ],
        list_help="list the selected rules and exit",
        init=False,
        dry_run=False,
        env_file=False,
        config=False,
    )
    parser.add_argument("root", nargs="?", default=".", help="repository root to scan (default: .)")
    parser.add_argument("--config", metavar="PATH", help=f"config TOML (default: ROOT/{CONFIG_NAME})")
    parser.add_argument("--rules", metavar="SET", action="append", help="guide, firmware, or a path; repeatable")
    parser.add_argument("--only", metavar="IDS", help="comma-separated rule ids, e.g. A1,L2,P1")
    parser.add_argument("--severity", metavar="LEVEL", choices=SEVERITIES, default="all", help="all or blocking")
    parser.add_argument("--max-hits", metavar="N", type=int, default=None, help="findings shown per rule (default: 40)")
    parser.add_argument("--format", metavar="FMT", choices=FORMATS, default=None, help="terminal, report or tsv")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser()
    if not root.is_dir():
        raise UsageError(f"Not a directory: {args.root}")
    root = root.resolve()

    config = _load_config(root, args.config)
    rule_specs = args.rules or config.get("rules") or ["guide"]
    max_hits = args.max_hits if args.max_hits is not None else int(config.get("max_hits", 40))
    if max_hits < 0:
        raise UsageError("--max-hits must be 0 (unlimited) or a positive number.")
    excludes = _excludes(config)

    config_dir = Path(args.config).expanduser().parent if args.config else root
    rules = load_rules([str(s) for s in rule_specs], relative_to=config_dir)

    if args.list:
        for r in rules:
            print(f"{r.id:<4} {r.severity:<9} {r.title}")
        return 0

    if args.only:
        wanted = [s.strip() for s in args.only.split(",") if s.strip()]
        known = {r.id for r in rules}
        unknown = [w for w in wanted if w not in known]
        if unknown:
            raise UsageError(f"Unknown rule id(s): {', '.join(unknown)}", f"Run `{TOOL} -l` to list them.")
        rules = [r for r in rules if r.id in wanted]
    if args.severity == "blocking":
        rules = [r for r in rules if r.severity == "blocking"]
    if not rules:
        raise UsageError("No rules selected.")

    files, source = enumerate_files(root)
    index = FileIndex(root, files)
    results = run_rules(rules, index, excludes=excludes, builtins=BUILTINS)

    meta = RunMeta(
        tool=TOOL,
        version=__version__,
        run_utc=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        root=str(root),
        files=len(files),
        source=source,
        rule_sets=[str(s) for s in rule_specs],
    )
    fmt = args.format or ("terminal" if sys.stdout.isatty() else "report")
    if fmt == "terminal":
        render_terminal(results, meta, max_hits)
    elif fmt == "report":
        sys.stdout.write(render_report(results, meta, max_hits))
    else:
        sys.stdout.write(render_tsv(results, max_hits))

    return 1 if blocking_count(results) or error_count(results) else 0


def _load_config(root: Path, explicit: str | None) -> dict:
    """``--config PATH`` or ``<root>/bac-convention-check.toml``; absent is fine."""
    path = Path(explicit).expanduser() if explicit else root / CONFIG_NAME
    if not path.exists():
        if explicit:
            raise ConfigError(f"Config file does not exist: {path}")
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config file is not valid TOML: {path}", str(exc)) from exc


def _excludes(config: dict) -> dict[str, list[str]]:
    raw = config.get("exclude", {})
    if not isinstance(raw, dict):
        raise ConfigError("[exclude] must be a table of rule id → list of path globs.")
    out: dict[str, list[str]] = {}
    for rule_id, globs in raw.items():
        if isinstance(globs, str):
            globs = [globs]
        if not isinstance(globs, list) or not all(isinstance(g, str) for g in globs):
            raise ConfigError(f"[exclude] {rule_id} must be a list of path globs.")
        out[str(rule_id)] = list(globs)
    return out


__all__ = ["main", "TOOL", "BUNDLED_SETS"]
