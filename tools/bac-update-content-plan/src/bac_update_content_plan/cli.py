# SPDX-License-Identifier: MIT
"""bac-update-content-plan – the content plan sheet rendered into the docs repository.

Fetch the configured Google Sheets range through a service account, render
it as one Markdown table, write it into the docs repository, and on request
commit and push. The repository is validated and switched to the configured
branch before the sheet is fetched, so nothing is written when git is not
ready. ``--dry-run`` fetches and renders, compares against the file on disk
and reports what would change.

Exit codes: 0 done (also when nothing changed), 1 the sheet, the key, the
config or git refused, 2 bad arguments.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import gsheets, ui
from bac_common.config import default_config_path, load_env, load_toml, write_config
from bac_common.errors import ConfigError

from . import __version__
from .gitops import Repo
from .render import Rendered, diff_stats, render
from .settings import DEFAULTS, TOOL, Settings, config_text, load_settings

__all__ = ["TOOL", "main", "run_init"]

DEFAULT_MESSAGE = "Update content plan"
Ask = Callable[[str, str], str]
"""``ask(question, default) -> answer`` – injectable so ``--init`` is testable."""


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Render the content plan from its sheet into the docs repo; commit and push.",
        examples=[
            "bac-update-content-plan --dry-run",
            "bac-update-content-plan --push -m 'Content plan: week 41'",
        ],
    )
    parser.add_argument("--commit", action="store_true", help="commit the file on the configured branch")
    parser.add_argument("--push", action="store_true", help="push after committing (implies --commit)")
    parser.add_argument("-m", "--message", metavar="TEXT", default=DEFAULT_MESSAGE, help="commit message")
    parser.add_argument("-y", "--yes", action="store_true", help="push without asking")
    args = parser.parse_args(argv)

    if args.init:
        return run_init(args.config)

    load_env(args.env_file)
    settings = load_settings(load_toml(TOOL, args.config))
    commit = args.commit or args.push
    key_path, key_source = gsheets.credentials_source(
        settings.credentials_file or None, configured_as="[credentials] file"
    )

    ui.opening(TOOL, __version__, "Content plan from the sheet into the docs repository.")
    ui.fields(
        [
            ("Sheet", settings.sheet_url),
            ("Range", settings.a1_range),
            ("Target", settings.target),
            ("Key", f"{key_path} ({key_source})"),
            ("Branch", f"{settings.branch} ({settings.remote})" if commit else "not committing"),
        ]
    )

    repo = Repo(settings.repo)
    repo.check()  # a typo in output.repo must not become a fresh directory tree
    on_branch = _prepare_branch(repo, settings, dry_run=args.dry_run) if commit else True

    with ui.spinner("Fetching the sheet"):
        client = gsheets.SheetsClient.from_service_account(key_path)
        values = client.read_range(settings.sheet_id, settings.a1_range)
    rendered = render(values, title=settings.title, status_column=settings.status_column, sheet_url=settings.sheet_url)
    _report_rows(rendered, settings.status_column)

    if on_branch:
        old = settings.target.read_text(encoding="utf-8") if settings.target.is_file() else None
    else:  # dry run while another branch is checked out: compare against the configured branch's file
        old = repo.show(settings.branch, settings.file)
    added, removed = diff_stats(old, rendered.text)
    changed = old != rendered.text
    rows: list[tuple[str, int | str]] = [
        ("Rows in sheet", rendered.rows_total),
        ("Rows written", rendered.rows_kept),
        ("Lines changed", f"+{added} −{removed}" if changed else "none"),
    ]

    if args.dry_run:
        verb = "Would write" if changed else "No change for"
        ui.step(f"{verb} {ui.path(settings.target)}")
        if commit and changed:
            ui.step(f"Would commit on {settings.branch}" + (" and push" if args.push else ""))
        ui.summary(rows, dry_run=True)
        return 0

    settings.target.parent.mkdir(parents=True, exist_ok=True)
    settings.target.write_text(rendered.text, encoding="utf-8")
    ui.ok(f"Wrote {ui.path(settings.target)}" + ("" if changed else " (unchanged)"))

    committed = pushed = "no"
    if commit:
        branch, remote = ui.esc(settings.branch), ui.esc(settings.remote)
        try:
            repo.add(settings.file)
            if repo.has_staged(settings.file):
                committed = repo.commit(args.message, settings.file)
                ui.ok(f"Committed {committed}: {ui.esc(args.message)}")
            else:
                ui.step("Nothing to commit.")
            if args.push:
                if args.yes or _confirm(f"Push {branch} to {remote}?"):
                    pushed = "failed"
                    with ui.spinner("Pushing"):
                        repo.push(settings.remote, settings.branch)
                    ui.ok(f"Pushed {remote}/{branch}")
                    pushed = "yes"
                else:
                    ui.step("Push skipped.")
        finally:
            ui.summary(rows + [("Committed", committed), ("Pushed", pushed)])
        return 0

    ui.summary(rows)
    return 0


def _prepare_branch(repo: Repo, settings: Settings, *, dry_run: bool) -> bool:
    """Put the work tree on the configured branch before anything is fetched or written.

    Returns whether the work tree is on that branch afterwards (a dry run only says what it would do).
    """
    if not repo.has_branch(settings.branch):
        raise ConfigError(f"Branch {settings.branch!r} does not exist in {repo.path}", "Check [output] branch.")
    current = repo.current_branch()
    if current == settings.branch:
        return True
    branch, was = ui.esc(settings.branch), ui.esc(current or "detached")
    if dry_run:
        ui.step(f"Would check out {branch} (currently {was})")
        return False
    repo.checkout(settings.branch)
    ui.step(f"Checked out {branch} (was {was})")
    return True


def _report_rows(rendered: Rendered, status_column: str) -> None:
    dropped = rendered.rows_total - rendered.rows_kept
    column = ui.esc(repr(status_column))
    if status_column and not rendered.filtered:
        ui.warn(f"No {column} column in the header; every row is kept")
    elif dropped:
        noun = "row" if dropped == 1 else "rows"
        ui.dim(f"{dropped} {noun} without a {column} value left out")


def _confirm(question: str) -> bool:
    if not sys.stdin.isatty():
        ui.warn("No terminal to ask on; pass -y to push without asking")
        return False
    answer = ui.console.input(f"{question} [y/N] ").strip().lower()
    return answer in ("y", "yes")


def _ask_default(question: str, default: str) -> str:
    if not sys.stdin.isatty():
        return default
    shown = f" [{default}]" if default else ""
    return ui.console.input(f"{question}{shown}: ").strip() or default


def run_init(config_path: str | None, ask: Ask = _ask_default) -> int:
    """``--init``: ask for the sheet and the repository, write the TOML, say where the key goes.

    Re-running leaves an existing file alone. Without a terminal the
    placeholders are written for editing by hand.
    """
    target = Path(config_path).expanduser() if config_path else default_config_path(TOOL)
    if target.exists():
        ui.warn(f"{ui.path(target)} exists; left unchanged")
    else:
        sheet = ask("Spreadsheet id or URL", "")
        sheet_id = gsheets.spreadsheet_id(sheet) if sheet else ""
        repo = ask("Docs repository (git work tree)", "~/bac/bac-docs")
        file = ask("File inside the repository", DEFAULTS["file"])
        branch = ask("Branch", DEFAULTS["branch"])
        write_config(target, config_text(sheet_id, repo, file, branch))
        ui.ok(f"Wrote {ui.path(target)}")
        if not sheet_id:
            ui.warn(f"No sheet given; fill in {ui.esc('[sheet]')} id before the first run")
    ui.step(f"Put {gsheets.CREDENTIALS_ENV}=/path/to/key.json in a .env file in your working directory")
    ui.step("(or above it), or pass one with --env-file. Share the sheet with the key's client_email.")
    return 0
