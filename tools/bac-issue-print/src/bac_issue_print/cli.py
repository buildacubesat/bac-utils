# SPDX-License-Identifier: MIT
"""bac-issue-print – print a Codeberg issue with all its comments as Markdown.

The Markdown goes to stdout, so it pipes into a file, a pager or an LLM
session. Everything else – the spinner while fetching, errors – goes to
stderr. Repository keys map to repositories through
``~/.config/bac/bac-issue-print.toml``; without the file, the Build a
CubeSat defaults apply, so the tool works before ``--init`` has run.

Exit codes: 0 printed, 1 the API refused or failed, 2 bad arguments.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.config import default_config_path, load_env, load_toml, write_config
from bac_common.errors import ConfigError, UsageError

from . import __version__
from .api import fetch_json, get_comments, get_issue
from .render import render

TOOL = "bac-issue-print"
TOKEN_ENV = "CODEBERG_TOKEN"

DEFAULT_HOST = "https://codeberg.org"
DEFAULT_OWNER = "buildacubesat-project"
DEFAULT_REPOS = {
    "docs": "bac-docs",
    "software": "bac-software",
    "hardware": "bac-hardware",
    "structure": "bac-structure",
}

CONFIG_TEMPLATE = f"""# {TOOL}.toml
# Build a CubeSat – {TOOL} configuration. Keys under [repos] are what you
# type on the command line; values are repository names under `owner`.
host = "{DEFAULT_HOST}"
owner = "{DEFAULT_OWNER}"

[repos]
""" + "".join(f'{key} = "{repo}"\n' for key, repo in DEFAULT_REPOS.items())


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Print a Codeberg issue with all its comments as Markdown.",
        examples=[
            "bac-issue-print hardware 42 > issue-42.md",
            "bac-issue-print someone/their-repo 7 --env-file ~/.config/bac/.env",
        ],
        list_help="print the repository keys and exit",
        dry_run=False,
    )
    parser.add_argument("repo", nargs="?", metavar="REPO", help="repository key (see -l) or owner/repo")
    parser.add_argument("number", nargs="?", metavar="NUMBER", help="issue number")
    args = parser.parse_args(argv)

    if args.init:
        return _init(args.config)

    load_env(args.env_file)
    config = load_toml(TOOL, args.config)
    host, owner, repos = _settings(config)

    if args.list:
        for key, repo in repos.items():
            print(f"{key:<12} {owner}/{repo}")
        return 0

    if not args.repo or args.number is None:
        parser.error("REPO and NUMBER are required.")
    slug = _resolve(args.repo, owner, repos)
    number = _issue_number(args.number)
    token = os.getenv(TOKEN_ENV) or None

    base = f"{host.rstrip('/')}/api/v1/repos/{slug}/issues/{number}"
    fetch = lambda url: fetch_json(url, token)  # noqa: E731 – binds the token for api.get_*
    with ui.err_console.status(f"[dim]Fetching {slug} #{number}[/]", spinner="dots"):
        issue = get_issue(fetch, base)
        comments = get_comments(fetch, base)

    sys.stdout.write(render(issue, comments, slug))
    return 0


def _init(config_path: str | None) -> int:
    target = Path(config_path).expanduser() if config_path else default_config_path(TOOL)
    if write_config(target, CONFIG_TEMPLATE):
        ui.ok(f"Wrote {ui.path(target)}")
    else:
        ui.warn(f"{ui.path(target)} exists; left unchanged")
    ui.step(f"Edit [repos] there to add repositories. For private ones put {TOKEN_ENV}=… in a .env")
    ui.step("file in your working directory (or above it), or pass one with --env-file.")
    return 0


def _settings(config: dict) -> tuple[str, str, dict[str, str]]:
    host = str(config.get("host") or DEFAULT_HOST)
    owner = str(config.get("owner") or DEFAULT_OWNER)
    repos_raw = config.get("repos", DEFAULT_REPOS)
    if not isinstance(repos_raw, dict) or not all(isinstance(v, str) and v for v in repos_raw.values()):
        raise ConfigError("[repos] must map keys to repository names.", f"See `{TOOL} --init` for the shape.")
    if not host.startswith(("https://", "http://")):
        raise ConfigError(f"host must be a URL, got {host!r}.")
    return host, owner, {str(k): v for k, v in repos_raw.items()}


def _resolve(key: str, owner: str, repos: dict[str, str]) -> str:
    """``owner/repo`` for a configured key, or the key itself when it already has that shape."""
    if "/" in key:
        parts = [p for p in key.split("/") if p]
        if len(parts) != 2 or any(c in key for c in " ?#"):
            raise UsageError(f"Not a repository: {key!r}", "Use a key from -l or owner/repo.")
        return "/".join(parts)
    if key not in repos:
        raise UsageError(f"Unknown repository key: {key!r}", f"Run `{TOOL} -l` to list them, or give owner/repo.")
    return f"{owner}/{repos[key]}"


def _issue_number(value: str) -> int:
    text = value.lstrip("#")
    if not text.isdigit() or int(text) < 1:
        raise UsageError(f"Issue number must be a positive integer, got {value!r}.")
    return int(text)
