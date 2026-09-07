# SPDX-License-Identifier: MIT
"""bac-kicad-symfields – fields, lint and fix for KiCad symbol and footprint libraries.

``fields`` applies TOML rules (add missing properties, fill empty ones,
overwrite when both the rule and the run allow it); ``lint`` reports text
sizes, footprint prefixes and duplicate UUIDs that drift from the library
conventions, and – with ``--rules`` – the field changes ``fields`` would
make; ``fix`` corrects the sizes. Files are edited by splicing byte ranges
into the original text, so a diff shows only the intended change. Nothing
is written without confirmation (``--yes`` in scripts), a ``.bak`` keeps the
previous content unless ``--no-backup``, and ``--dry-run`` only reports.

Exit codes: 0 done (``lint``: clean), 1 findings or a failure, 2 bad
arguments or rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.config import default_config_path, write_config
from bac_common.errors import BacError, UsageError
from bac_common.sexp import parse_file
from bac_kicad_common.files import confirm, write_back
from bac_kicad_common.library import find_files
from bac_kicad_common.report import print_changes, print_item
from bac_kicad_common.rules import load_rules_dir

from . import __version__
from .config import CONFIG_TEMPLATE, TOOL, Settings, load_settings
from .items import ItemResult, process_file
from .lint import Finding, fix_file, lint_file

app = typer.Typer(
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    help=(
        "Build a CubeSat – unify property fields and text sizes across KiCad symbol and footprint "
        "libraries, from TOML rules, editing files by span.\n\n"
        "\b\n"
        "Examples:\n"
        "  bac-kicad-symfields lint libs/ --rules rules/\n"
        "  bac-kicad-symfields fields libs/BAC_Passives.kicad_symdir --rules rules/ --dry-run\n"
        "  bac-kicad-symfields fix libs/ --yes"
    ),
)


@dataclass(slots=True)
class Global:
    config: str | None


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    return bac_cli.run_typer(app, argv, TOOL)


def _version(value: bool) -> None:
    if value:
        typer.echo(bac_cli.version_string(TOOL, __version__))
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "-v", "--version", callback=_version, is_eager=True, help="Print version."),
    config: str | None = typer.Option(
        None, "--config", metavar="PATH", help=f"TOML config (~/.config/bac/{TOOL}.toml)."
    ),
) -> None:
    ctx.obj = Global(config=config)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

PathsArg = typer.Argument(..., metavar="PATH...", help="Library files, .kicad_symdir/.pretty or parent folders.")
RulesOpt = typer.Option(None, "--rules", metavar="DIR", help="TOML rule files (default from config).")
DryRun = typer.Option(False, "--dry-run", help="Report what would change; write nothing.")
Yes = typer.Option(False, "--yes", help="Write without asking.")
NoBackup = typer.Option(False, "--no-backup", help="Do not keep <file>.bak copies.")


@app.command("fields")
def fields(
    ctx: typer.Context,
    paths: list[Path] = PathsArg,
    rules: Path | None = RulesOpt,
    dry_run: bool = DryRun,
    yes: bool = Yes,
    no_backup: bool = NoBackup,
    no_fill_empty: bool = typer.Option(False, "--no-fill-empty", help="Leave empty existing fields alone."),
    allow_overwrite: bool = typer.Option(False, "--allow-overwrite", help="Let overwrite = true rules replace values."),
) -> None:
    """Add, fill or overwrite property fields from the rule files."""
    settings = load_settings(ctx.obj.config)
    rulesets = load_rules_dir(_rules_dir(rules, settings))
    files = find_files(paths)
    ui.opening(TOOL, __version__, f"Applying {len(rulesets)} rule file(s) to {len(files)} library file(s).")

    pending: list[tuple[Path, str]] = []
    counts = {"symbol": 0, "footprint": 0, "add": 0, "fill": 0, "set": 0, "skipped": 0}
    for path in files:
        text, root = parse_file(path)
        new_text, results = process_file(
            path, text, root, rulesets, fill_empty=not no_fill_empty, allow_overwrite=allow_overwrite
        )
        _print_results(path, results, counts)
        if new_text != text:
            pending.append((path, new_text))

    written = _write_all(pending, dry_run=dry_run, yes=yes, backup=not no_backup)
    ui.summary(
        [
            ("Files scanned", len(files)),
            ("Symbols matched", counts["symbol"]),
            ("Footprints matched", counts["footprint"]),
            ("Fields added", counts["add"]),
            ("Fields filled", counts["fill"]),
            ("Values overwritten", counts["set"]),
            ("Rules skipped", counts["skipped"]),
            ("Files to write" if dry_run else "Files written", len(pending) if dry_run else written),
        ],
        dry_run=dry_run,
    )
    if not dry_run and written < len(pending):
        raise typer.Exit(1)


@app.command("lint")
def lint(
    ctx: typer.Context,
    paths: list[Path] = PathsArg,
    rules: Path | None = typer.Option(None, "--rules", metavar="DIR", help="Also report field changes the rules want."),
) -> None:
    """Report sizes, footprint prefixes, duplicate UUIDs and (with --rules) missing fields. Exit 1 on findings."""
    settings = load_settings(ctx.obj.config)
    rulesets = load_rules_dir(_rules_dir(rules, settings)) if rules or settings.rules_dir else []
    files = find_files(paths)
    ui.opening(TOOL, __version__, f"Linting {len(files)} library file(s) against the library conventions.")

    rows: list[list[str]] = []
    clean = 0
    for path in files:
        text, root = parse_file(path)
        findings = lint_file(path, root, settings)
        if rulesets:
            _, results = process_file(path, text, root, rulesets)
            for r in results:
                for c in r.changes:
                    findings.append(
                        Finding(
                            r.name,
                            f"field {c.key}",
                            "field",
                            "missing" if c.kind == "add" else c.kind,
                            c.value or "(placeholder)",
                        )
                    )
        if findings:
            ui.fail(f"{ui.path(path.name)}: {len(findings)} finding(s)")
            rows.extend([path.name, f.item, f.where, f.found, f.expected] for f in findings)
        else:
            clean += 1
            ui.ok(f"{ui.path(path.name)}")
    if rows:
        ui.table(
            "Findings",
            [("File", 2), ("Item", 2), ("Where", 3), ("Found", 0, "right"), ("Expected", 0)],
            [[ui.esc(c) for c in r] for r in rows],
        )
    ui.summary([("Files", len(files)), ("Clean", clean), ("Findings", len(rows))])
    if rows:
        raise typer.Exit(1)


@app.command("fix")
def fix(
    ctx: typer.Context,
    paths: list[Path] = PathsArg,
    dry_run: bool = DryRun,
    yes: bool = Yes,
    no_backup: bool = NoBackup,
) -> None:
    """Set non-conforming text sizes and thicknesses to the library values, in place."""
    settings = load_settings(ctx.obj.config)
    files = find_files(paths)
    ui.opening(TOOL, __version__, f"Fixing text sizes in {len(files)} library file(s).")

    pending: list[tuple[Path, str]] = []
    total = 0
    for path in files:
        text, root = parse_file(path)
        new_text, fixed = fix_file(path, text, root, settings)
        if not fixed:
            ui.dim(f"{ui.esc(path.name)}: nothing to fix")
            continue
        total += len(fixed)
        print_item("file", path.name, f"{len(fixed)} change(s)")
        for f in fixed:
            ui.step(f"    ~ {ui.esc(f.item)} · {ui.esc(f.where)}: {ui.esc(f.found)} → {ui.esc(f.expected)}")
        pending.append((path, new_text))

    written = _write_all(pending, dry_run=dry_run, yes=yes, backup=not no_backup)
    ui.summary(
        [
            ("Files scanned", len(files)),
            ("Sizes corrected", total),
            ("Files to write" if dry_run else "Files written", len(pending) if dry_run else written),
        ],
        dry_run=dry_run,
    )
    if not dry_run and written < len(pending):
        raise typer.Exit(1)


@app.command("init")
def init(ctx: typer.Context) -> None:
    """Write the config file with the library conventions as defaults."""
    target = Path(ctx.obj.config).expanduser() if ctx.obj.config else default_config_path(TOOL)
    if write_config(target, CONFIG_TEMPLATE):
        ui.ok(f"Wrote {ui.path(target)}")
    else:
        ui.warn(f"{ui.path(target)} exists; left unchanged")
    ui.step("Set `rules` there to the directory of your TOML rule files, or pass --rules on each run.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rules_dir(given: Path | None, settings: Settings) -> Path:
    if given is not None:
        return given
    if settings.rules_dir is not None:
        return settings.rules_dir
    raise UsageError("No rules directory.", f"Pass --rules DIR, or set `rules` in the config (`{TOOL} init`).")


def _print_results(path: Path, results: list[ItemResult], counts: dict[str, int]) -> None:
    for r in results:
        counts[r.target] += 1
        kind = "sym" if r.target == "symbol" else "fp"
        ident = f"{r.library}:{r.name}" if r.library else r.name
        print_item(kind, ident, f"[{r.prefix}]" if r.prefix else "")
        print_changes(r.changes, r.skipped)
        for c in r.changes:
            counts[c.kind] += 1
        counts["skipped"] += len(r.skipped)


def _write_all(pending: list[tuple[Path, str]], *, dry_run: bool, yes: bool, backup: bool) -> int:
    """Confirm once, then write every changed file. Returns how many were written."""
    if not pending:
        if not dry_run:
            ui.step("Nothing to write.")
        return 0
    if dry_run:
        for path, _ in pending:
            ui.step(f"Would write {ui.path(path)}")
        return 0
    confirm(f"Write {len(pending)} file(s)?", yes=yes)
    written = 0
    for path, text in pending:
        try:
            saved = write_back(path, text, backup=backup)
        except BacError as exc:
            ui.fail(f"{ui.path(path)}: {ui.esc(exc.message)}")
            continue
        written += 1
        note = f" [dim](backup {ui.esc(saved.name)})[/]" if saved else ""
        ui.ok(f"Wrote {ui.path(path)}{note}")
    return written
