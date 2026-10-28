# SPDX-License-Identifier: MIT
"""bac-page – create and manage bac.page short URLs.

``bac-page <url> [slug]`` writes a redirect folder into the Pages repository,
commits and pushes; ``list`` shows what is there, ``edit`` changes a slug or
a destination or makes a QR code, ``init`` sets the repository path. The
parser and the error boundary come from ``bac_common.cli``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.config import default_config_path, load_env, load_toml, write_config
from bac_common.errors import ConfigError, ExternalToolError, UserAbort

from . import __version__, prompts
from .qr import FORMATS, LEVELS, QrOptions, qr_path, write_qr
from .redirects import (
    DOMAIN,
    SLUG_MAX,
    create_redirect,
    generate_uid,
    list_redirects,
    short_url,
    slug_exists,
    validate_slug,
    validate_target,
)

TOOL = "bac-page"
REPO_ENV = "BAC_PAGE_REPO"
# read once more in 0.5; gone in 0.6 – put BAC_PAGE_REPO in a .env or run --init
LEGACY_ENV = Path("~/.config/bac-page/.env")
COMMANDS = ("add", "list", "edit", "init")
DESCRIPTION = f"""Create and manage {DOMAIN} short URLs.

commands:
  <url> [slug]   create a redirect (`add`); slug 1–{SLUG_MAX} characters, else random
  list           every redirect, sorted by slug
  edit           change a slug or destination, or make a QR code
  init           set the Pages repository path (same as --init)"""
EXAMPLES = (
    f"{TOOL} https://buildacubesat.space/docs/eps eps-docs --qr",
    f"{TOOL} edit --dry-run",
)
CONFIG_TEMPLATE = """# bac-page.toml
# Build a CubeSat – bac-page configuration

[repo]
path = "{repo}"
"""


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = bac_cli.make_parser(TOOL, __version__, DESCRIPTION, examples=EXAMPLES, list_help="same as `list`")
    parser.usage = f"{TOOL} [options] <url> [slug]\n       {TOOL} [options] {{add,list,edit,init}} ..."
    return parser


def build_add_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=f"{TOOL} add", description="Create a redirect, commit and push it.")
    p.add_argument("url", help="destination URL")
    p.add_argument("slug", nargs="?", help=f"1–{SLUG_MAX} letters, digits and hyphens (default: random)")
    p.add_argument("--qr", action="store_true", help="also write a QR code for the short URL")
    p.add_argument("--format", dest="fmt", choices=FORMATS, default="svg", help="QR format (default: svg)")
    p.add_argument("--invert", action="store_true", help="white on black")
    p.add_argument("--alpha", action="store_true", help="transparent background")
    p.add_argument("--ec", choices=LEVELS, default="M", help="error correction level (default: M)")
    p.add_argument("--size", type=int, default=1000, metavar="PX", help="QR size in pixels (default: 1000)")
    p.add_argument("--output", type=Path, default=None, metavar="DIR", help="QR output directory (default: ~)")
    return p


def build_list_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=f"{TOOL} list", description="List every redirect, sorted by slug.")
    p.add_argument("--plain", action="store_true", help="tab-separated lines, no table (automatic when piped)")
    return p


def build_simple_parser(name: str, description: str) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog=f"{TOOL} {name}", description=description)


def parse(argv: list[str]) -> tuple[str, argparse.Namespace]:
    """The command and its merged namespace; a bare URL is ``add``."""
    parser = build_parser()
    if argv and argv[0] in COMMANDS and {"-h", "--help"} & set(argv[1:]):
        _subparser(argv[0]).parse_args(argv[1:])  # prints the subcommand's help and exits 0
    args, rest = parser.parse_known_args(argv)
    if args.init:
        command = "init"
    elif args.list:
        command = "list"
    elif rest and rest[0] in COMMANDS:
        command = rest.pop(0)
    elif rest and not rest[0].startswith("-"):
        command = "add"
    else:
        parser.print_help(sys.stderr)
        raise SystemExit(2)
    sub_args = _subparser(command).parse_args(rest)
    return command, argparse.Namespace(**vars(args), **vars(sub_args))


def _subparser(command: str) -> argparse.ArgumentParser:
    return {
        "add": build_add_parser,
        "list": build_list_parser,
        "edit": lambda: build_simple_parser("edit", "Change a slug or destination, or make a QR code."),
        "init": lambda: build_simple_parser("init", "Set the Pages repository path."),
    }[command]()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_environment(env_file: str | None) -> None:
    """The nearest ``.env`` (or the given one), then the legacy file with a note."""
    load_env(env_file)
    legacy = LEGACY_ENV.expanduser()
    if env_file is None and legacy.is_file():
        load_dotenv(legacy)
        ui.err_console.print(
            f"[dim]{ui.esc(str(legacy))} is read for the last time in 0.5: "
            f"put {REPO_ENV} in a .env next to your work or run `{TOOL} --init`.[/]"
        )


def repo_path(config_path: str | None) -> Path:
    """The Pages repository: ``BAC_PAGE_REPO``, else ``[repo] path`` of the config."""
    from_env = os.environ.get(REPO_ENV, "")
    if from_env:
        repo = Path(from_env).expanduser().resolve()
        if not repo.is_dir():
            raise ConfigError(
                f"Repository path does not exist: {repo}",
                f"It comes from {REPO_ENV}, which overrides the config file – unset or update it.",
            )
        return repo
    config = load_toml(TOOL, config_path)
    configured = str(config.get("repo", {}).get("path", "") or "")
    if not configured:
        raise ConfigError(
            f"{TOOL} is not set up: no repository path.",
            f"Run `{TOOL} --init` to set it, or export {REPO_ENV}.",
        )
    repo = Path(configured).expanduser().resolve()
    if not repo.is_dir():
        raise ConfigError(f"Repository path does not exist: {repo}", f"Run `{TOOL} --init` to update it.")
    return repo


def _ask(prompt: str, default: str) -> str:
    answer = ui.console.input(f"  {prompt} [dim]\\[{ui.esc(default)}][/]: ").strip()
    return answer or default


def run_init(args: argparse.Namespace) -> int:
    """``--init``: ask for the clone of the Pages repository and write the TOML (re-runs overwrite)."""
    ui.opening(TOOL, __version__, "First-time setup: the local clone of the Pages repository.")
    target = Path(args.config).expanduser() if args.config else default_config_path(TOOL)
    existing = load_toml(TOOL, args.config).get("repo", {}).get("path") if target.exists() else None
    current = str(existing or os.environ.get(REPO_ENV) or Path.home() / "bac" / "bac-page")
    repo = Path(_ask("Path to the bac-page git repository", current)).expanduser().resolve()
    if not repo.is_dir():
        raise ConfigError(f"Directory does not exist: {repo}")
    if not (repo / ".git").exists():
        ui.warn(f"{ui.path(repo)} does not look like a git repository")
    if args.dry_run:
        ui.step(f"would write {ui.path(target)}")
        ui.summary([("Config", str(target)), ("Repository", str(repo))], dry_run=True)
        return 0
    write_config(target, CONFIG_TEMPLATE.format(repo=repo), overwrite=True)
    ui.ok(f"Wrote {ui.path(target)}")
    from_env = os.environ.get(REPO_ENV)
    if from_env and Path(from_env).expanduser().resolve() != repo:
        ui.warn(f"{REPO_ENV} is set to {ui.path(from_env)} and overrides this config – unset or update it")
    ui.summary([("Config", str(target)), ("Repository", str(repo))])
    return 0


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------


def git(repo: Path, *argv: str) -> None:
    try:
        result = subprocess.run(["git", *argv], cwd=repo, capture_output=True, text=True)
    except FileNotFoundError:
        raise ExternalToolError("git is not installed.", "Install git and run again.") from None
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().replace("\n", "\n      ")
        if argv[0] in ("pull", "push"):
            detail += f"\n      The repository at {repo} may hold a local commit that is not pushed."
        raise ExternalToolError(f"git {argv[0]} failed.", detail)


def commit_and_push(repo: Path, message: str, *paths: str) -> None:
    with ui.spinner("Committing and pushing"):
        for p in paths:
            git(repo, "add", "--", p)
        git(repo, "commit", "-m", message)
        git(repo, "pull", "--rebase")
        git(repo, "push")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def emit_qr(url: str, slug: str, options: QrOptions, dry_run: bool) -> Path:
    dest = qr_path(slug, options)
    if dry_run:
        ui.step(f"would write {ui.path(dest)}")
        return dest
    write_qr(url, slug, options)
    ui.ok(f"QR code {ui.path(dest)}")
    return dest


def cmd_add(args: argparse.Namespace) -> int:
    repo = repo_path(args.config)
    validate_target(args.url)
    if args.slug:
        validate_slug(repo, args.slug)
        slug = args.slug
    else:
        slug = generate_uid()
        while slug_exists(repo, slug):
            slug = generate_uid()
    url = short_url(slug)
    options = QrOptions(args.fmt, args.invert, args.alpha, args.ec, args.size, args.output)
    ui.opening(TOOL, __version__, f"Adding a redirect in {ui.esc(str(repo))}.")
    if args.dry_run:
        ui.step(f"would create {ui.path(url)} → {ui.esc(args.url)}")
    else:
        create_redirect(repo, slug, args.url)
        commit_and_push(repo, f"add redirect: /{slug} → {args.url}", slug)
        ui.ok(f"{ui.path(url)} → {ui.esc(args.url)}")
    if args.qr:
        emit_qr(url, slug, options, args.dry_run)
    ui.summary([("Redirect", url), ("QR code", options.fmt if args.qr else "–")], dry_run=args.dry_run)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    repo = repo_path(args.config)
    redirects = list_redirects(repo)
    if not redirects:
        ui.step("No redirects found.")
        return 0
    if args.plain or not ui.console.is_terminal:
        for slug, target in redirects:
            print(f"{short_url(slug)}\t{target}")
        return 0
    ui.table(
        f"{DOMAIN} redirects ({len(redirects)})",
        [("Slug", 0), ("Destination", 1)],
        [(ui.path("/" + slug), ui.esc(target)) for slug, target in redirects],
    )
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    repo = repo_path(args.config)
    redirects = list_redirects(repo)
    if not redirects:
        ui.step("No redirects found.")
        return 0
    ui.opening(TOOL, __version__, f"Editing a redirect in {ui.esc(str(repo))}.")
    slug, target = redirects[prompts.pick_redirect(redirects)]
    url = short_url(slug)
    ui.fields([("Short URL", url), ("Destination", target)])
    action = prompts.pick_action(slug)

    if action == "cancel":
        raise UserAbort("Cancelled.")

    if action == "qr":
        options = prompts.qr_options()
        dest = emit_qr(url, slug, options, args.dry_run)
        ui.summary([("Redirect", url), ("QR code", str(dest))], dry_run=args.dry_run)
        return 0

    if action == "slug":
        new_slug = prompts.ask_text("New slug:", slug)
        if new_slug == slug:
            ui.step("Unchanged.")
            return 0
        validate_slug(repo, new_slug)
        ui.step(f"{ui.path(url)} → {ui.path(short_url(new_slug))}")
        if args.dry_run:
            ui.summary([("Old", url), ("New", short_url(new_slug))], dry_run=True)
            return 0
        if not prompts.confirm("Rename and push?"):
            raise UserAbort()
        with ui.spinner("Committing and pushing"):
            git(repo, "mv", "--", slug, new_slug)
            git(repo, "commit", "-m", f"rename redirect: /{slug} → /{new_slug}")
            git(repo, "pull", "--rebase")
            git(repo, "push")
        ui.ok(f"{ui.path(short_url(new_slug))} → {ui.esc(target)}")
        ui.warn(f"QR codes and links to /{slug} no longer resolve")
        ui.summary([("Old", url), ("New", short_url(new_slug))])
        return 0

    new_target = prompts.ask_text("New destination URL:", target)
    if new_target == target:
        ui.step("Unchanged.")
        return 0
    validate_target(new_target)
    ui.step(f"{ui.path(url)}: {ui.esc(target)} → {ui.esc(new_target)}")
    if args.dry_run:
        ui.summary([("Redirect", url), ("Destination", new_target)], dry_run=True)
        return 0
    if not prompts.confirm("Update and push?"):
        raise UserAbort()
    create_redirect(repo, slug, new_target)
    commit_and_push(repo, f"update redirect: /{slug} → {new_target}", slug)
    ui.ok(f"{ui.path(url)} → {ui.esc(new_target)}")
    ui.summary([("Redirect", url), ("Destination", new_target)])
    return 0


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


def main() -> None:
    """``[project.scripts]`` target."""
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    command, args = parse(argv)
    load_environment(args.env_file)
    if command == "init":
        return run_init(args)
    return {"add": cmd_add, "list": cmd_list, "edit": cmd_edit}[command](args)
