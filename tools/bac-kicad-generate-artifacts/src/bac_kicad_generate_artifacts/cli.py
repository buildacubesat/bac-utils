# SPDX-License-Identifier: MIT
"""bac-kicad-generate-artifacts – the release bundle of a KiCad project from one command.

For every project folder given (the one holding the ``.kicad_pro``), the tool
creates ``<root>/<prefix>-<subsystem>-<name>-<vXrY>/`` on the desktop (or ``--desktop``) and runs
the stages in order: an optional QR code on a copy of the board, the 3D
render, the schematic PDF, the pinout plot, the CSV BOM, the optional
interactive BOM, Gerbers, drills, the centroid file, the STEP model, and
the manufacturing ZIP with Gerbers, drills and centroid renamed to the
``<prefix>-<subsystem>-<name>-<vXrY>-<layer>`` scheme.

A folder without a schematic is a panel: the schematic-derived stages are
skipped, ``User.Comments`` (V-cut lines) joins the Gerber layers, and the
zone fills are exported exactly as the panelizer saved them.

Exit codes: 0 every project done, 1 at least one project or stage failed or
the config file is invalid, 2 bad arguments.
"""

from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import config as bac_config
from bac_common import ui
from bac_common.errors import BacError, UsageError

from . import TOOL_NAME, __version__
from .config import Settings, config_template, desktop_dir, find_ibom_script, load_settings
from .project import discover, make_plan
from .runner import Runner, Tools, find_tools
from .stages import STAGE_NAMES, Context, select_stages

DESCRIPTION = "Generate the release artifacts of a KiCad project, from render to ZIP."


def main() -> None:
    bac_cli.run(_main)


def build_parser():
    p = bac_cli.make_parser(
        TOOL_NAME,
        __version__,
        DESCRIPTION,
        examples=[
            f"{TOOL_NAME} ~/bac-hardware/inhibit/deployment-switch/kicad10",
            f"{TOOL_NAME} --ibom --qr https://bac.page/dsw-v1 dsw/kicad10",
        ],
        env_file=False,
    )
    p.usage = f"{TOOL_NAME} [options] KICAD_DIR [KICAD_DIR ...]"
    p._option_string_actions["--config"].help = "TOML config (default: ~/.config/bac/<tool>.toml)"  # noqa: SLF001
    p.add_argument("kicad_dirs", nargs="*", metavar="KICAD_DIR", help="KiCad project folders, processed in turn")
    p.add_argument("--desktop", metavar="DIR", help="output root (default: the desktop, or root in the config)")
    p.add_argument("--only", metavar="STAGES", help="run only these stages, comma-separated")
    p.add_argument("--skip", metavar="STAGES", help="skip these stages")
    p.add_argument("--ibom", action="store_true", help="also build the interactive HTML BOM (plugin from --init)")
    p.add_argument("--qr", metavar="TEXT", help="replace QR_MARKER text boxes with a QR code of TEXT")
    p.add_argument("--patch", metavar="N", type=int, help="patch revision on the tags (v1r2 → v1r2.N)")
    p.add_argument("--open", action="store_true", help="open the output folder and GerbView when done")
    return p


def parse_stage_list(value: str | None) -> set[str]:
    if not value:
        return set()
    names = {s.strip() for s in value.split(",") if s.strip()}
    unknown = sorted(names - set(STAGE_NAMES))
    if unknown:
        raise UsageError(f"Unknown stage: {', '.join(unknown)}.", "Stages: " + ", ".join(STAGE_NAMES))
    return names


def do_init(config_path: str | None) -> int:
    path = Path(config_path).expanduser() if config_path else bac_config.default_config_path(TOOL_NAME)
    script = find_ibom_script()
    if bac_config.write_config(path, config_template(script)):
        ui.ok(f"Wrote {ui.path(path)}")
    else:
        ui.dim(f"{ui.path(path)} exists – left as it is")
    if script:
        ui.step(f"iBOM plugin: {ui.path(script)}")
    else:
        ui.step(ui.esc("iBOM plugin: not found – set script in [ibom] once InteractiveHtmlBom is installed"))
    ui.step(ui.esc("Set author and organization in [metadata]; they go into the STEP file header."))
    return 0


@dataclass(frozen=True)
class Run:
    """What one invocation decided once, shared by every project it processes."""

    settings: Settings
    tools: Tools
    runner: Runner
    root: Path
    only: set[str]
    skip: set[str]
    qr_text: str
    ibom: bool
    patch: int | None
    open: bool
    dry_run: bool
    debug: bool


def open_outputs(out_dir: Path, zip_path: Path | None) -> None:
    """Best effort: the output folder in the file manager and the ZIP in GerbView."""
    try:
        system = platform.system().lower()
        if system == "darwin":
            opener = shutil.which("open")
        elif system == "windows":
            os.startfile(str(out_dir))  # type: ignore[attr-defined]  # noqa: S606
            opener = None
        else:
            opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, str(out_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        gerbview = shutil.which("gerbview")
        if gerbview and zip_path and zip_path.is_file():
            subprocess.Popen([gerbview, str(zip_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        ui.warn(f"Could not open the output: {ui.esc(str(exc))}")


def process(kicad_dir: Path, run: Run) -> bool:
    """One project folder; returns True when every stage succeeded."""
    settings, runner, debug = run.settings, run.runner, run.debug
    ui.rule(kicad_dir.parent.name if kicad_dir.name.startswith("kicad") else kicad_dir.name)
    try:
        project = discover(kicad_dir)
        plan = make_plan(
            project,
            run.root,
            prefix=settings.prefix,
            hardware_root=settings.hardware_root,
            pcb_patch=run.patch,
            sch_patch=run.patch,
        )
    except BacError as exc:
        ui.fail(f"{ui.path(kicad_dir)}: {ui.esc(exc.message)}" + (f" – {ui.esc(exc.detail)}" if exc.detail else ""))
        return False

    rows = [
        ("Board", project.pcb_file.name),
        ("Title", project.pcb_title.title or "–"),
        ("Revision", f"{project.pcb_title.rev or '–'} → {plan.pcb_tag}"),
        ("Schematic", project.sch_file.name if project.sch_file else "none – panel"),
        ("Output", str(plan.out_dir)),
    ]
    if project.sch_file and plan.sch_tag != plan.pcb_tag:
        rows.insert(4, ("Sch. tag", plan.sch_tag))
    ui.fields(rows)
    if project.panel:
        ui.warn("No schematic – a panel: schematic, pinout, BOM and iBOM are skipped, User.Comments joins the Gerbers.")

    stages = select_stages(run.only, run.skip, ibom=run.ibom, qr=bool(run.qr_text))
    if not stages:
        ui.warn("No stages selected.")
        return True
    ctx = Context(
        runner,
        run.tools,
        settings,
        plan,
        ibom=run.ibom,
        qr_text=run.qr_text,
        open=run.open,
        debug=debug,
        spinner=ui.spinner,
    )
    if not run.dry_run:
        plan.out_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(plan.work_dir, ignore_errors=True)  # a copy a --debug run kept must not feed this run
    ok = True
    try:
        for stage in stages:
            if stage.needs_schematic and project.panel:
                ui.dim(f"· {stage.label} – skipped (panel)")
                continue
            shown = ui.path(stage.output(plan))
            seen = len(runner.commands)
            t0 = time.perf_counter()
            ctx.shown = None
            try:
                note = stage.run(ctx)
            except KeyboardInterrupt:
                raise
            except BacError as exc:
                ui.fail(
                    f"{stage.label} → {shown}: {ui.esc(exc.message)}"
                    + (f" – {ui.esc(exc.detail)}" if exc.detail else "")
                )
                ctx.failed.add(stage.name)
                ok = False
            except Exception as exc:  # noqa: BLE001 – one stage must not end the run
                ui.fail(f"{stage.label} → {shown}: {ui.esc(f'{type(exc).__name__}: {exc}')}")
                if debug:
                    ui.err_console.print(traceback.format_exc(), highlight=False, markup=False)
                ctx.failed.add(stage.name)
                ok = False
            else:
                if run.dry_run:
                    ui.step(f"· {stage.label} → {shown}" + (f" ({ui.esc(note)})" if note else ""))
                else:
                    detail = ", ".join(x for x in (note, f"{time.perf_counter() - t0:.1f} s") if x)
                    ui.ok(f"{stage.label} → {ui.path(ctx.shown) if ctx.shown else shown} ({ui.esc(detail)})")
            if debug:
                for cmd in runner.commands[seen:]:
                    ui.dim("$ " + ui.esc(shlex.join(cmd)))
    finally:
        if not debug and not run.dry_run and plan.work_dir.exists():
            shutil.rmtree(plan.work_dir, ignore_errors=True)
    if run.open and not run.dry_run:
        zips = sorted(plan.out_dir.glob(f"{plan.base}-*.zip"))
        open_outputs(plan.out_dir, zips[-1] if zips else None)
    return ok


def _main(argv: list[str], debug: bool) -> int:
    args = build_parser().parse_args(argv)
    if args.init:
        return do_init(args.config)
    if not args.kicad_dirs:
        raise UsageError("Give at least one KiCad project folder.", f"See `{TOOL_NAME} --help`.")
    only, skip = parse_stage_list(args.only), parse_stage_list(args.skip)
    settings = load_settings(args.config)
    # Absolute: the iBOM plugin resolves a relative --dest-dir against the board's folder, not the cwd.
    root = (Path(args.desktop).expanduser() if args.desktop else (settings.output_root or desktop_dir())).resolve()
    run = Run(
        settings=settings,
        tools=find_tools(),
        runner=Runner(dry_run=args.dry_run, timeout=settings.timeout),
        root=root,
        only=only,
        skip=skip,
        qr_text=args.qr if args.qr is not None else settings.qr_text,
        ibom=args.ibom,
        patch=args.patch,
        open=args.open,
        dry_run=args.dry_run,
        debug=debug,
    )

    ui.opening(TOOL_NAME, __version__, DESCRIPTION)
    if settings.source:
        ui.dim(f"config {ui.path(settings.source)}")
    if not args.dry_run:
        root.mkdir(parents=True, exist_ok=True)
    done = failed = 0
    for d in args.kicad_dirs:
        if process(Path(d).expanduser().resolve(), run):
            done += 1
        else:
            failed += 1
    ui.summary(
        [("Projects", done + failed), ("Planned" if args.dry_run else "Done", done), ("Failed", failed)],
        dry_run=args.dry_run,
    )
    return 1 if failed else 0
