# SPDX-License-Identifier: MIT
"""bac-kicad-stitch – ground stitching vias where a board needs them.

``stitch`` reads a board's filled ground zones, finds every spot where a
via would be clean on all copper layers, and adds vias until no point of
the ground copper is farther than the pitch from one; the vias already on
the net count, so a board that is dense enough gets nothing. New vias go
into a group named ``bac-stitch``; ``remove`` takes that group out again,
``report`` only measures. Files are edited by span: a diff shows the new
vias and the group, nothing else. Nothing is written without confirmation
(``--yes`` in scripts), a ``.bak`` keeps the previous content unless
``--no-backup``, and ``--dry-run`` only reports.

Exit codes: 0 done (gaps no via can close are reported, not failed), 1 a
file could not be read or written or DRC found violations, 2 bad arguments.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

import typer

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.config import default_config_path, write_config
from bac_common.errors import BacError, UsageError
from bac_common.sexp import parse_file
from bac_kicad_common.files import confirm, write_back

from . import __version__
from .board import Board, read_board
from .config import CONFIG_TEMPLATE, COURTYARD_MODES, GROUP_NAME, TOOL, Settings, load_settings, validate
from .edit import insert_vias, remove_vias
from .preview import write_svg
from .stitch import Result, as_vias, plan

app = typer.Typer(
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    help="Build a CubeSat – ground stitching vias where a board's ground copper is too far from one.",
    epilog=(
        "\b\n"
        "Examples:\n"
        "  bac-kicad-stitch report board.kicad_pcb --pitch 5\n"
        "  bac-kicad-stitch stitch board.kicad_pcb --max-frequency 1e9 --preview plan.svg\n"
        "  bac-kicad-stitch stitch board.kicad_pcb --edge-fence --yes\n"
        "  bac-kicad-stitch remove board.kicad_pcb"
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
# Options shared by report and stitch
# ---------------------------------------------------------------------------

BoardArg = typer.Argument(..., metavar="BOARD", help="A .kicad_pcb with its zones filled.")
Net = typer.Option(None, "--net", metavar="NAME", help="The ground net (GND).")
Pitch = typer.Option(
    None, "--pitch", metavar="MM", help="Target pitch: no ground copper farther than this from a via (10)."
)
MaxFrequency = typer.Option(
    None, "--max-frequency", metavar="HZ", help="Derive the pitch as wavelength / fraction at this frequency."
)
Fraction = typer.Option(None, "--fraction", metavar="N", help="Wavelength fraction for --max-frequency (20).")
EpsilonR = typer.Option(None, "--epsilon-r", metavar="ER", help="Dielectric constant (stackup average, or 4.4).")
ViaSize = typer.Option(None, "--via-size", metavar="MM", help="Via diameter (0.6).")
ViaDrill = typer.Option(None, "--via-drill", metavar="MM", help="Via drill (0.3).")
Clearance = typer.Option(None, "--clearance", metavar="MM", help="Copper clearance to other nets (0.2).")
HoleToHole = typer.Option(None, "--hole-to-hole", metavar="MM", help="Hole-to-hole clearance (0.25).")
EdgeClearance = typer.Option(None, "--edge-clearance", metavar="MM", help="Copper to board edge (0.5).")
Margin = typer.Option(None, "--margin", metavar="MM", help="Extra distance beyond every clearance (0.05).")
MinLayers = typer.Option(None, "--min-layers", metavar="N", help="Ground fill layers a via must sit in (2).")
KeepZones = typer.Option(
    None, "--keep-zones/--refill-zones", help="Treat other nets' zone fills as obstacles (off: they refill)."
)
Courtyards = typer.Option(None, "--courtyards", metavar="MODE", help="allow, avoid, avoid-fine-pitch (default).")
FinePitch = typer.Option(
    None, "--fine-pitch", metavar="MM", help="Pad pitch below which a footprint is fine-pitch (0.65)."
)
FinePitchPads = typer.Option(
    None, "--fine-pitch-pads", metavar="N", help="Pads a fine-pitch footprint has at least (6)."
)
EdgeFence = typer.Option(None, "--edge-fence/--no-edge-fence", help="A row of vias along the board edge.")
EdgeFencePitch = typer.Option(None, "--edge-fence-pitch", metavar="MM", help="Fence pitch (half the pitch).")
Step = typer.Option(None, "--step", metavar="MM", help="Candidate grid step (0.1).")
Preview = typer.Option(None, "--preview", metavar="SVG", help="Write a picture of the plan.")
Json = typer.Option(False, "--json", help="Print a machine-readable report instead.")
DryRun = typer.Option(False, "--dry-run", help="Plan and report; write nothing.")
Yes = typer.Option(False, "--yes", help="Write without asking.")
NoBackup = typer.Option(False, "--no-backup", help="Do not keep a <file>.bak copy.")
Drc = typer.Option(None, "--drc/--no-drc", help="Run kicad-cli pcb drc after writing (on when kicad-cli is found).")


def _settings(ctx: typer.Context, **overrides: object) -> Settings:
    settings = load_settings(ctx.obj.config)
    given = {k: v for k, v in overrides.items() if v is not None}
    if "max_frequency_hz" in given and "pitch" not in given:
        given["pitch"] = None
    if "courtyards" in given and given["courtyards"] not in COURTYARD_MODES:
        raise UsageError(f"--courtyards takes one of {', '.join(COURTYARD_MODES)}.")
    settings = replace(settings, **given)
    try:
        validate(settings)
    except BacError as exc:
        raise UsageError(exc.message, exc.detail) from None
    return settings


@app.command("report")
def report(
    ctx: typer.Context,
    board_path: Path = BoardArg,
    net: str | None = Net,
    pitch: float | None = Pitch,
    max_frequency: float | None = MaxFrequency,
    fraction: float | None = Fraction,
    epsilon_r: float | None = EpsilonR,
    via_size: float | None = ViaSize,
    via_drill: float | None = ViaDrill,
    clearance: float | None = Clearance,
    hole_to_hole: float | None = HoleToHole,
    edge_clearance: float | None = EdgeClearance,
    margin: float | None = Margin,
    min_layers: int | None = MinLayers,
    keep_zones: bool | None = KeepZones,
    courtyards: str | None = Courtyards,
    fine_pitch: float | None = FinePitch,
    fine_pitch_pads: int | None = FinePitchPads,
    edge_fence: bool | None = EdgeFence,
    edge_fence_pitch: float | None = EdgeFencePitch,
    step: float | None = Step,
    preview: Path | None = Preview,
    as_json: bool = Json,
) -> None:
    """Measure the coverage and show what stitch would add; write nothing."""
    settings = _settings(
        ctx,
        net=net,
        pitch=pitch,
        max_frequency_hz=max_frequency,
        fraction=fraction,
        epsilon_r=epsilon_r,
        via_size=via_size,
        via_drill=via_drill,
        clearance=clearance,
        hole_to_hole=hole_to_hole,
        edge_clearance=edge_clearance,
        margin=margin,
        min_layers=min_layers,
        keep_zones=keep_zones,
        courtyards=courtyards,
        fine_pitch=fine_pitch,
        fine_pitch_pads=fine_pitch_pads,
        edge_fence=edge_fence,
        edge_fence_pitch=edge_fence_pitch,
        step=step,
    )
    _opening(as_json, f"Measuring {settings.net} via coverage of {board_path.name}.")
    board, result = _plan(board_path, settings, as_json)
    if preview:
        write_svg(
            preview, board, result, step=settings.step, avoided=result.avoided_footprints, via_size=settings.via_size
        )
        if not as_json:
            ui.ok(f"Wrote {ui.path(preview)}")
    _summary(board_path, board, result, settings, command="report", as_json=as_json, written=False, dry_run=False)


@app.command("stitch")
def stitch(
    ctx: typer.Context,
    board_path: Path = BoardArg,
    net: str | None = Net,
    pitch: float | None = Pitch,
    max_frequency: float | None = MaxFrequency,
    fraction: float | None = Fraction,
    epsilon_r: float | None = EpsilonR,
    via_size: float | None = ViaSize,
    via_drill: float | None = ViaDrill,
    clearance: float | None = Clearance,
    hole_to_hole: float | None = HoleToHole,
    edge_clearance: float | None = EdgeClearance,
    margin: float | None = Margin,
    min_layers: int | None = MinLayers,
    keep_zones: bool | None = KeepZones,
    courtyards: str | None = Courtyards,
    fine_pitch: float | None = FinePitch,
    fine_pitch_pads: int | None = FinePitchPads,
    edge_fence: bool | None = EdgeFence,
    edge_fence_pitch: float | None = EdgeFencePitch,
    step: float | None = Step,
    preview: Path | None = Preview,
    as_json: bool = Json,
    dry_run: bool = DryRun,
    yes: bool = Yes,
    no_backup: bool = NoBackup,
    drc: bool | None = Drc,
) -> None:
    """Add stitching vias to the board, in the bac-stitch group, with a .bak copy."""
    settings = _settings(
        ctx,
        net=net,
        pitch=pitch,
        max_frequency_hz=max_frequency,
        fraction=fraction,
        epsilon_r=epsilon_r,
        via_size=via_size,
        via_drill=via_drill,
        clearance=clearance,
        hole_to_hole=hole_to_hole,
        edge_clearance=edge_clearance,
        margin=margin,
        min_layers=min_layers,
        keep_zones=keep_zones,
        courtyards=courtyards,
        fine_pitch=fine_pitch,
        fine_pitch_pads=fine_pitch_pads,
        edge_fence=edge_fence,
        edge_fence_pitch=edge_fence_pitch,
        step=step,
    )
    _opening(as_json, f"Stitching {settings.net} on {board_path.name}.")
    text, root = parse_file(board_path)
    board, result = _plan(board_path, settings, as_json, parsed=(text, root))
    if preview:
        write_svg(
            preview, board, result, step=settings.step, avoided=result.avoided_footprints, via_size=settings.via_size
        )
        if not as_json:
            ui.ok(f"Wrote {ui.path(preview)}")
    written = False
    drc_result: dict | None = None
    if result.placed and not dry_run:
        if not as_json:
            confirm(f"Add {len(result.placed)} via(s) to {board_path.name}?", yes=yes)
        elif not yes:
            raise UsageError("--json writes only with --yes; there is no prompt in a report.")
        new_text, _ = insert_vias(text, root, as_vias(result, settings))
        with board_path.open(encoding="utf-8", newline="") as f:
            if f.read() != text:
                raise BacError("The file changed after it was planned; run again.")
        saved = write_back(board_path, new_text, backup=not no_backup)
        written = True
        if not as_json:
            note = f" [dim](backup {ui.esc(saved.name)})[/]" if saved else ""
            ui.ok(f"Wrote {ui.path(board_path)}{note}")
        drc_result = _run_drc(board_path, drc, as_json)
    elif not result.placed and not as_json:
        ui.dim("nothing to add")
    _summary(
        board_path,
        board,
        result,
        settings,
        command="stitch",
        as_json=as_json,
        written=written,
        dry_run=dry_run,
        drc=drc_result,
    )
    if drc_result and drc_result.get("violations"):
        raise typer.Exit(1)


@app.command("remove")
def remove(
    ctx: typer.Context,
    board_path: Path = BoardArg,
    as_json: bool = Json,
    dry_run: bool = DryRun,
    yes: bool = Yes,
    no_backup: bool = NoBackup,
) -> None:
    """Take the bac-stitch group and its vias out of the board."""
    _opening(as_json, f"Removing the {GROUP_NAME} group from {board_path.name}.")
    text, root = parse_file(board_path)
    new_text, count = remove_vias(text, root)
    written = False
    if count and not dry_run:
        if not as_json:
            confirm(f"Remove {count} via(s) from {board_path.name}?", yes=yes)
        elif not yes:
            raise UsageError("--json writes only with --yes; there is no prompt in a report.")
        saved = write_back(board_path, new_text, backup=not no_backup)
        written = True
        if not as_json:
            note = f" [dim](backup {ui.esc(saved.name)})[/]" if saved else ""
            ui.ok(f"Wrote {ui.path(board_path)}{note}")
    elif not count and not as_json:
        ui.dim(f"no {GROUP_NAME} group in the board")
    if as_json:
        typer.echo(
            json.dumps(
                {
                    "tool": TOOL,
                    "version": __version__,
                    "command": "remove",
                    "dry_run": dry_run,
                    "vias_removed": count,
                    "written": written,
                },
                indent=2,
            )
        )
        return
    ui.summary([("Vias removed", count), ("Files written", int(written))], dry_run=dry_run)


@app.command("init")
def init(ctx: typer.Context) -> None:
    """Write the config file with the board conventions."""
    target = Path(ctx.obj.config).expanduser() if ctx.obj.config else default_config_path(TOOL)
    if write_config(target, CONFIG_TEMPLATE):
        ui.ok(f"Wrote {ui.path(target)}")
    else:
        ui.warn(f"{ui.path(target)} exists; left unchanged")
    ui.step("Edit the via size, clearances and pitch there; every flag overrides its value for one run.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _opening(as_json: bool, description: str) -> None:
    if not as_json:
        ui.opening(TOOL, __version__, description)


def _plan(path: Path, settings: Settings, as_json: bool, parsed: tuple | None = None) -> tuple[Board, Result]:
    text, root = parsed if parsed else parse_file(path)
    if root.head != "kicad_pcb":
        raise BacError(f"{path}: not a KiCad board file.")
    if as_json:
        board = read_board(root, settings.net, where=str(path))
        result = plan(board, settings)
    else:
        with ui.spinner("Reading copper, holes and outline"):
            board = read_board(root, settings.net, where=str(path))
        with ui.spinner("Finding spots and placing vias"):
            result = plan(board, settings)
        _show(board, result, settings)
    return board, result


def _show(board: Board, result: Result, settings: Settings) -> None:
    ui.fields(
        [
            ("Copper layers", ", ".join(board.copper_layers)),
            (
                "Ground fill on",
                ", ".join(layer for layer in board.copper_layers if not board.ground_fill[layer].is_empty),
            ),
            (
                "Pitch",
                f"{result.pitch:.2f} mm" + (f" (fence {result.fence_pitch:.2f} mm)" if result.fence_pitch else ""),
            ),
            ("Via", f"{settings.via_size} / {settings.via_drill} mm, in {settings.min_layers}+ ground layers"),
            ("Ground copper", f"{result.target_area:.0f} mm², via allowed on {result.valid_area:.0f} mm²"),
        ]
    )
    if result.avoided_footprints:
        refs = ", ".join(result.avoided_footprints[:12])
        more = f" … (+{len(result.avoided_footprints) - 12})" if len(result.avoided_footprints) > 12 else ""
        ui.dim(f"courtyards avoided: {ui.esc(refs + more)}")
    for p in result.placed:
        kind = "fence" if p.fence else "via  "
        ui.step(f"    + {kind} at ({p.x:.2f}, {p.y:.2f})")
    for x, y, d in result.gaps[:10]:
        ui.warn(f"gap at ({x:.1f}, {y:.1f}): nearest via {d:.1f} mm away, no clean spot within the pitch")
    if len(result.gaps) > 10:
        ui.dim(f"… and {len(result.gaps) - 10} more gaps; --preview draws them, --json lists them")


def _summary(
    path: Path,
    board: Board,
    result: Result,
    settings: Settings,
    *,
    command: str,
    as_json: bool,
    written: bool,
    dry_run: bool,
    drc: dict | None = None,
) -> None:
    fence = sum(p.fence for p in result.placed)
    if as_json:
        report = {
            "tool": TOOL,
            "version": __version__,
            "command": command,
            "dry_run": dry_run,
            "path": str(path),
            "net": settings.net,
            "pitch_mm": result.pitch,
            "fence_pitch_mm": result.fence_pitch,
            "existing_vias": result.existing,
            "placed": [{"x": p.x, "y": p.y, "fence": p.fence} for p in result.placed],
            "coverage_before": result.coverage_before,
            "coverage_after": result.coverage_after,
            "ground_area_mm2": result.target_area,
            "allowed_area_mm2": result.valid_area,
            "gaps": [{"x": x, "y": y, "distance_mm": d} for x, y, d in result.gaps],
            "gap_area_mm2": result.gap_area,
            "avoided_footprints": result.avoided_footprints,
            "written": written,
            "drc": drc,
        }
        typer.echo(json.dumps(report, indent=2))
        return
    rows: list[tuple[str, int | str]] = [
        ("Existing ground vias", result.existing),
        ("Vias to add" if not written else "Vias added", len(result.placed) - fence),
    ]
    if result.fence_pitch:
        rows.append(("Fence vias", fence))
    rows += [
        ("Coverage before", f"{result.coverage_before * 100:.1f} %"),
        ("Coverage after", f"{result.coverage_after * 100:.1f} %"),
        ("Gaps", len(result.gaps)),
    ]
    if drc:
        rows.append(("DRC violations", drc.get("violations", "?")))
    ui.summary(rows, dry_run=dry_run)


def _run_drc(path: Path, drc: bool | None, as_json: bool) -> dict | None:
    exe = shutil.which("kicad-cli")
    if drc is False or (drc is None and exe is None):
        return None
    if exe is None:
        raise BacError("kicad-cli not found; pass --no-drc or put it on PATH.")
    report = path.with_name(path.stem + "-drc.json")
    cmd = [
        exe,
        "pcb",
        "drc",
        "--format",
        "json",
        "--severity-error",
        "--exit-code-violations",
        "-o",
        str(report),
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BacError("kicad-cli pcb drc failed to run.", str(exc)) from exc
    violations = None
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
        violations = len(data.get("violations", [])) + len(data.get("unconnected_items", []))
    except (OSError, ValueError):
        pass
    result = {"exit_code": proc.returncode, "violations": violations, "report": str(report)}
    if not as_json:
        if proc.returncode == 0 and violations in (0, None):
            ui.ok(f"DRC clean [dim]({ui.esc(report.name)})[/]")
        else:
            ui.fail(f"DRC reports {violations if violations is not None else 'problems'}; see {ui.path(report)}")
    return result


__all__ = ["app", "main"]
