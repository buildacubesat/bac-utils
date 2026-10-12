# SPDX-License-Identifier: MIT
"""bac-kicad-maintain – keep KiCad boards and schematics on the project conventions.

``check`` and ``apply`` normalise text (size, stroke, centring, keep
upright), courtyard line widths and, when asked, via sizes on boards, and
label sizes on schematics; ``stats`` lists the sizes a file uses;
``rename-library`` moves a schematic's symbols to another library
nickname, cached copies included. Files are edited by span, so a diff shows
only the intended tokens. Nothing is written without confirmation (``--yes``
in scripts), a ``.bak`` keeps the previous content unless ``--no-backup``,
and ``--dry-run`` only reports.

Exit codes: 0 done (``check``: nothing to change), 1 ``check`` found
changes, a file could not be read or a write failed, 2 bad arguments.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, replace
from pathlib import Path

import typer

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.config import default_config_path, write_config
from bac_common.errors import BacError, UsageError
from bac_common.sexp import parse_file
from bac_kicad_common.files import confirm, write_back
from bac_kicad_common.report import print_item

from . import __version__
from .config import CONFIG_TEMPLATE, OPERATIONS, TOOL, Settings, load_settings, number, validate
from .maintain import Outcome, discover, suffixes_for, transform

app = typer.Typer(
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    help=(
        "Build a CubeSat – text, courtyard, via and label sizes on KiCad boards and "
        "schematics, and symbol-library renames, editing files by span."
    ),
    epilog=(
        "\b\n"
        "Examples:\n"
        "  bac-kicad-maintain check boards/ --diff\n"
        "  bac-kicad-maintain apply board.kicad_pcb --vias --yes\n"
        "  bac-kicad-maintain rename-library . --from 'bac Library v1' --to 'bac v2'"
    ),
)


@dataclass(slots=True)
class Global:
    config: str | None


@dataclass(slots=True)
class Plan:
    path: Path
    original: str
    outcome: Outcome
    written: bool = False

    @property
    def changed(self) -> bool:
        return self.outcome.text != self.original


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

PathsArg = typer.Argument(..., metavar="PATH...", help="Board or schematic files, or folders (recursive).")
Exclude = typer.Option(None, "--exclude", metavar="GLOB", help="Skip paths matching GLOB; repeatable.")
Diff = typer.Option(False, "--diff", help="Show a unified diff per changed file.")
Json = typer.Option(False, "--json", help="Print a machine-readable report instead.")
DryRun = typer.Option(False, "--dry-run", help="Report what would change; write nothing.")
Yes = typer.Option(False, "--yes", help="Write without asking.")
NoBackup = typer.Option(False, "--no-backup", help="Do not keep <file>.bak copies.")
Text = typer.Option(False, "--text", help="Select text normalisation on boards.")
Courtyards = typer.Option(False, "--courtyards", help="Select courtyard line widths on boards.")
Vias = typer.Option(False, "--vias", help="Select via resizing on boards (off unless selected).")
Labels = typer.Option(False, "--labels", help="Select label sizes on schematics.")
ViaDiameter = typer.Option(None, "--via-diameter", metavar="MM", help="Via diameter; needs --vias.")
ViaDrill = typer.Option(None, "--via-drill", metavar="MM", help="Via drill; needs --vias.")
PreserveNet = typer.Option(None, "--preserve-net", metavar="GLOB", help="Nets whose vias keep their size; repeatable.")
ViaTypes = typer.Option(None, "--via-types", metavar="TYPE", help="through, blind, micro; repeatable or commas.")


@app.command("check")
def check(
    ctx: typer.Context,
    paths: list[Path] = PathsArg,
    text: bool = Text,
    courtyards: bool = Courtyards,
    vias: bool = Vias,
    labels: bool = Labels,
    via_diameter: float | None = ViaDiameter,
    via_drill: float | None = ViaDrill,
    preserve_net: list[str] | None = PreserveNet,
    via_types: list[str] | None = ViaTypes,
    exclude: list[str] | None = Exclude,
    diff: bool = Diff,
    as_json: bool = Json,
) -> None:
    """Report what apply would change; exit 1 if it would."""
    settings, selected = _settings(
        ctx, text, courtyards, vias, labels, via_diameter, via_drill, preserve_net, via_types
    )
    files = discover(paths, suffixes_for("check", selected), (*settings.exclude, *(exclude or [])))
    _opening(as_json, f"Checking {len(files)} file(s): {', '.join(sorted(selected))}.")
    plans = _plan(files, settings, "check", selected)
    _show(plans, diff=diff, as_json=as_json)
    _summary(plans, command="check", as_json=as_json)
    if any(p.changed for p in plans):
        raise typer.Exit(1)


@app.command("apply")
def apply(
    ctx: typer.Context,
    paths: list[Path] = PathsArg,
    text: bool = Text,
    courtyards: bool = Courtyards,
    vias: bool = Vias,
    labels: bool = Labels,
    via_diameter: float | None = ViaDiameter,
    via_drill: float | None = ViaDrill,
    preserve_net: list[str] | None = PreserveNet,
    via_types: list[str] | None = ViaTypes,
    exclude: list[str] | None = Exclude,
    diff: bool = Diff,
    as_json: bool = Json,
    dry_run: bool = DryRun,
    yes: bool = Yes,
    no_backup: bool = NoBackup,
) -> None:
    """Normalise the selected sizes in place, with .bak copies."""
    settings, selected = _settings(
        ctx, text, courtyards, vias, labels, via_diameter, via_drill, preserve_net, via_types
    )
    files = discover(paths, suffixes_for("apply", selected), (*settings.exclude, *(exclude or [])))
    _opening(as_json, f"Applying {', '.join(sorted(selected))} to {len(files)} file(s).")
    plans = _plan(files, settings, "apply", selected)
    _show(plans, diff=diff, as_json=as_json)
    written = _write_all(plans, dry_run=dry_run, yes=yes, backup=not no_backup, as_json=as_json)
    _summary(plans, command="apply", as_json=as_json, dry_run=dry_run)
    if not dry_run and written < sum(p.changed for p in plans):
        raise typer.Exit(1)


@app.command("stats")
def stats(
    ctx: typer.Context,
    paths: list[Path] = PathsArg,
    labels: bool = Labels,
    exclude: list[str] | None = Exclude,
    as_json: bool = Json,
) -> None:
    """List text and via sizes of boards, label sizes of sheets."""
    settings = load_settings(ctx.obj.config)
    selected = {"labels"} if labels else {"text", "vias"}
    files = discover(paths, suffixes_for("stats", selected), (*settings.exclude, *(exclude or [])))
    _opening(as_json, f"Reading {len(files)} file(s).")
    plans = _plan(files, settings, "stats", selected)
    if as_json:
        rows = [{"path": str(p.path), "stats": p.outcome.stats} for p in plans]
        typer.echo(json.dumps({"tool": TOOL, "version": __version__, "files": rows}, indent=2))
        return
    for plan in plans:
        print_item(_kind(plan.path), plan.path.name)
        for kind, sizes in plan.outcome.stats.items():
            if not sizes:
                ui.dim(f"no {kind}")
                continue
            ui.table(
                None,
                [(kind.capitalize(), 1), ("Count", 0, "right")],
                [[ui.esc(description), str(count)] for description, count in sizes.items()],
                secondary=True,
            )
    ui.summary([("Files", len(plans))])


@app.command("rename-library")
def rename_library(
    ctx: typer.Context,
    paths: list[Path] = PathsArg,
    old: str = typer.Option(..., "--from", metavar="NAME", help="The library nickname to replace."),
    new: str = typer.Option(..., "--to", metavar="NAME", help="The nickname to use instead."),
    exclude: list[str] | None = Exclude,
    diff: bool = Diff,
    as_json: bool = Json,
    dry_run: bool = DryRun,
    yes: bool = Yes,
    no_backup: bool = NoBackup,
) -> None:
    """Move symbols to another library nickname, cache included."""
    for value in (old, new):
        if not value or ":" in value or any(ord(c) < 32 for c in value):
            raise UsageError("A library nickname is not empty and has no colon or control character.")
    if old == new:
        raise UsageError("--from and --to name the same library.")
    settings = load_settings(ctx.obj.config)
    files = discover(paths, suffixes_for("rename-library", set()), (*settings.exclude, *(exclude or [])))
    _opening(as_json, f"Renaming library {old!r} to {new!r} in {len(files)} schematic(s).")
    plans = _plan(files, settings, "rename-library", set(), old=old, new=new)
    _show(plans, diff=diff, as_json=as_json)
    written = _write_all(plans, dry_run=dry_run, yes=yes, backup=not no_backup, as_json=as_json)
    _summary(plans, command="rename-library", as_json=as_json, dry_run=dry_run)
    if not dry_run and written < sum(p.changed for p in plans):
        raise typer.Exit(1)


@app.command("init")
def init(ctx: typer.Context) -> None:
    """Write the config file with the board conventions."""
    target = Path(ctx.obj.config).expanduser() if ctx.obj.config else default_config_path(TOOL)
    if write_config(target, CONFIG_TEMPLATE):
        ui.ok(f"Wrote {ui.path(target)}")
    else:
        ui.warn(f"{ui.path(target)} exists; left unchanged")
    ui.step("Edit the sizes there, or turn an operation on with `enabled = true` so it runs without a flag.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(
    ctx: typer.Context,
    text: bool,
    courtyards: bool,
    vias: bool,
    labels: bool,
    via_diameter: float | None,
    via_drill: float | None,
    preserve_net: list[str] | None,
    via_types: list[str] | None,
) -> tuple[Settings, set[str]]:
    """The config with the command-line overrides, and the operations this run performs."""
    settings = load_settings(ctx.obj.config)
    flags = {"text": text, "courtyards": courtyards, "vias": vias, "labels": labels}
    selected = {name for name in OPERATIONS if flags[name]} or settings.enabled()
    if not selected:
        raise UsageError(
            "No operation selected.", "Pass --text, --courtyards, --vias or --labels, or enable one in the config."
        )
    overrides: dict[str, object] = {}
    if via_diameter is not None:
        overrides["via_diameter"] = _positive(via_diameter, "--via-diameter")
    if via_drill is not None:
        overrides["via_drill"] = _positive(via_drill, "--via-drill")
    if preserve_net is not None:
        overrides["preserve_nets"] = tuple(preserve_net)
    if via_types is not None:
        overrides["via_types"] = tuple(t.strip() for value in via_types for t in value.split(",") if t.strip())
    if overrides and "vias" not in selected:
        raise UsageError("The via options need --vias (or vias.enabled = true in the config).")
    if overrides:
        settings = replace(settings, **overrides)
        try:
            validate(settings)
        except BacError as exc:
            raise UsageError(exc.message, exc.detail) from None
    return settings, selected


def _positive(value: float, flag: str) -> float:
    n = number(value)
    if n <= 0 or n.as_tuple().exponent < -6:
        raise UsageError(f"{flag} must be positive with at most six decimals, got {value}.")
    return value


def _kind(path: Path) -> str:
    return "sch" if path.suffix.lower() == ".kicad_sch" else "pcb"


def _opening(as_json: bool, description: str) -> None:
    if not as_json:
        ui.opening(TOOL, __version__, description)


def _plan(
    files: list[Path],
    settings: Settings,
    command: str,
    selected: set[str],
    *,
    old: str | None = None,
    new: str | None = None,
) -> list[Plan]:
    """Parse and plan every file before anything is written: one bad file stops the batch."""
    plans: list[Plan] = []
    for path in files:
        text, root = parse_file(path)
        try:
            outcome = transform(text, root, settings, command, selected, old=old, new=new, where=str(path))
        except BacError as exc:
            raise BacError(f"{path}: {exc.message}", exc.detail) from None
        plans.append(Plan(path, text, outcome))
    return plans


def _write_all(plans: list[Plan], *, dry_run: bool, yes: bool, backup: bool, as_json: bool) -> int:
    """Confirm once, then write every changed file. Returns how many were written."""
    pending = [p for p in plans if p.changed]
    if not pending or dry_run:
        return 0
    if not as_json:
        confirm(f"Write {len(pending)} file(s)?", yes=yes)
    elif not yes:
        raise UsageError("--json writes only with --yes; there is no prompt in a report.")
    written = 0
    for plan in pending:
        try:
            with plan.path.open(encoding="utf-8", newline="") as f:
                if f.read() != plan.original:
                    raise BacError("The file changed after it was planned; run again.")
            saved = write_back(plan.path, plan.outcome.text, backup=backup)
        except BacError as exc:
            if not as_json:
                ui.fail(f"{ui.path(plan.path)}: {ui.esc(exc.message)}")
            continue
        written += 1
        plan.written = True
        if not as_json:
            note = f" [dim](backup {ui.esc(saved.name)})[/]" if saved else ""
            ui.ok(f"Wrote {ui.path(plan.path)}{note}")
    return written


def _show(plans: list[Plan], *, diff: bool, as_json: bool) -> None:
    """One block per file: the counts of what changes, and the diff when asked."""
    if as_json:
        if diff:
            raise UsageError("--json and --diff do not combine; the report has no place for a diff.")
        return
    for plan in plans:
        if not plan.changed:
            ui.dim(f"{ui.esc(plan.path.name)}: nothing to change")
            continue
        print_item(_kind(plan.path), plan.path.name)
        for key, value in plan.outcome.counts.items():
            ui.step(f"    ~ {ui.esc(key)}: {value}")
        if diff:
            lines = difflib.unified_diff(
                plan.original.splitlines(keepends=True),
                plan.outcome.text.splitlines(keepends=True),
                fromfile=str(plan.path),
                tofile=f"{plan.path} (maintained)",
            )
            ui.console.print("".join(lines).rstrip("\n"), markup=False, highlight=False, soft_wrap=True)


def _summary(plans: list[Plan], *, command: str, as_json: bool, dry_run: bool = False) -> None:
    changed = [p for p in plans if p.changed]
    written = sum(p.written for p in plans)
    totals: dict[str, int] = {}
    for plan in plans:
        for key, value in plan.outcome.counts.items():
            totals[key] = totals.get(key, 0) + value
    if as_json:
        rows = [
            {"path": str(p.path), "changed": p.changed, "written": p.written, "counts": p.outcome.counts} for p in plans
        ]
        report = {
            "tool": TOOL,
            "version": __version__,
            "command": command,
            "dry_run": dry_run,
            "files": rows,
            "changed_files": len(changed),
            "written_files": written,
        }
        typer.echo(json.dumps(report, indent=2))
        return
    rows_out: list[tuple[str, int | str]] = [("Files scanned", len(plans))]
    rows_out += [(key[0].upper() + key[1:], value) for key, value in totals.items()]
    if command == "check" or dry_run:
        rows_out.append(("Files to change", len(changed)))
    else:
        rows_out.append(("Files written", written))
    ui.summary(rows_out, dry_run=dry_run)


__all__ = ["app", "main"]
