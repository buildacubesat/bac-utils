# SPDX-License-Identifier: MIT
"""bac-kicad-libcheck – verify a KiCad library project.

A library project is the schematic and board that place every symbol and
footprint of a library exactly once, so that the library can be reviewed
as a whole. This tool checks that invariant, that every footprint's 3D
model resolves to a file, and – through KiCad's own ERC and DRC – that the
placed copies still match the library. It changes nothing.

Exit codes: 0 all checks passed, 1 a failure (a warning with ``--strict``,
or an unusable config), 2 bad arguments.
"""

from __future__ import annotations

from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.config import write_config

from . import __version__
from .config import CONFIG_NAME, CONFIG_TEMPLATE, TOOL, Config, load_config
from .kicadcli import CliResult, run_drc, run_erc
from .scan import Scan, Usage, build_scan, counts


class Report:
    """Counts what the section printers report; the summary reads it."""

    def __init__(self) -> None:
        self.failures = 0
        self.warnings = 0

    def ok(self, message: str) -> None:
        ui.ok(message)

    def fail(self, message: str) -> None:
        self.failures += 1
        ui.fail(message)

    def warn(self, message: str) -> None:
        self.warnings += 1
        ui.warn(message)

    def detail(self, message: str) -> None:
        ui.dim(f"  {message}")


def _refs(usages: list[Usage]) -> str:
    return ", ".join(ui.esc(u.reference or "?") for u in usages)


def check_placement(report: Report, kind: str, inventory: set[str], usage: list[Usage]) -> None:
    """Every library item placed exactly once; nothing placed from outside the declared libraries."""
    used = counts(usage)
    ui.rule(f"{kind} placement")
    noun = kind.lower()
    if not inventory:
        report.warn(f"no {noun}s found in the declared libraries")
        return

    missing = sorted(inventory - set(used))
    duplicated = sorted(k for k, v in used.items() if len(v) > 1)
    foreign = sorted(set(used) - inventory)

    for lib_id in missing:
        report.fail(f"{ui.path(lib_id)} – in library, never placed")
    for lib_id in duplicated:
        report.fail(f"{ui.path(lib_id)} – placed {len(used[lib_id])}× ({_refs(used[lib_id])})")
    for lib_id in foreign:
        report.fail(f"{ui.path(lib_id)} – placed ({_refs(used[lib_id])}) but not in a declared library")

    if not (missing or duplicated or foreign):
        report.ok(f"all {len(inventory)} {noun}(s) placed exactly once")
    else:
        once = len(inventory) - len(missing) - len([k for k in duplicated if k in inventory])
        report.detail(f"{once}/{len(inventory)} placed exactly once")


def check_models(report: Report, scan: Scan) -> None:
    """Every ``(model …)`` reference resolves to an existing file."""
    ui.rule("3D models")
    broken = [m for m in scan.models if not m.exists]
    for m in broken:
        report.fail(f"{ui.path(m.lib_id)} – {ui.esc(m.raw)}")
        if m.note:
            report.detail(ui.esc(m.note))
        elif m.resolved:
            report.detail(f"resolved to {ui.path(m.resolved)}")
    for lib_id in scan.footprints_without_model:
        report.warn(f"{ui.path(lib_id)} – no 3D model attached")
    if not broken:
        report.ok(f"all {len(scan.models)} model reference(s) resolve to existing files")


def _sync_result(report: Report, label: str, result: CliResult, wanted: list[str]) -> None:
    if not result.available:
        report.warn(f"{label} not run – {ui.esc(result.error)}")
        return
    if result.violations:
        for v in result.violations:
            report.fail(f"{label} {ui.esc(v.type)}: {ui.esc(v.description)}")
            for item in v.items[:4]:
                report.detail(ui.esc(item))
        return
    report.ok(f"{label} reports no library mismatches")
    unknown = [t for t in wanted if t not in result.all_types]
    if unknown and result.all_types:
        report.detail(
            f"note: violation type(s) {ui.esc(', '.join(unknown))} never appeared in the report – "
            "verify the type names against your KiCad version if this looks wrong"
        )


def check_library_sync(report: Report, cfg: Config) -> None:
    """Placed copies still match the library, as judged by KiCad's ERC and DRC."""
    ui.rule("Library sync (kicad-cli)")
    with ui.spinner(f"Running {cfg.kicad_cli} sch erc"):
        erc = run_erc(cfg.kicad_cli, cfg.schematic, cfg.erc_types)
    _sync_result(report, "ERC", erc, cfg.erc_types)
    with ui.spinner(f"Running {cfg.kicad_cli} pcb drc"):
        drc = run_drc(cfg.kicad_cli, cfg.board, cfg.drc_types)
    _sync_result(report, "DRC", drc, cfg.drc_types)


def _init(config_path: Path) -> int:
    ui.opening(TOOL, __version__, "First-time setup: writing a project config to edit.")
    if write_config(config_path, CONFIG_TEMPLATE):
        ui.ok(f"Wrote {ui.path(config_path)}")
    else:
        ui.step(f"{ui.path(config_path)} exists; left unchanged")
    ui.step("Edit the schematic, board and library paths, then run the tool from the project directory.")
    return 0


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Verify a KiCad library project: every item placed once, in sync with its library, 3D models present.",
        examples=[
            "bac-kicad-libcheck",
            f"bac-kicad-libcheck --config libs/{CONFIG_NAME} --strict",
            "bac-kicad-libcheck --skip-sync",
        ],
        dry_run=False,
        env_file=False,
        config=False,
    )
    parser.add_argument(
        "--config", metavar="PATH", default=CONFIG_NAME, help=f"project config (default: ./{CONFIG_NAME})"
    )
    parser.add_argument("--skip-sync", action="store_true", help="do not run kicad-cli ERC/DRC")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser()
    if args.init:
        return _init(config_path)

    cfg = load_config(config_path)
    ui.opening(TOOL, __version__, f"Checking {ui.path(cfg.schematic.name)} and {ui.path(cfg.board.name)}.")
    ui.dim(f"project {ui.path(cfg.root)}")

    with ui.spinner("Scanning libraries and project"):
        scan = build_scan(cfg)
    report = Report()
    if scan.warnings:
        ui.rule("Scan")
        for w in scan.warnings:
            report.warn(ui.esc(w))

    check_placement(report, "Symbol", scan.symbol_inventory, scan.symbol_usage)
    check_placement(report, "Footprint", scan.footprint_inventory, scan.footprint_usage)
    check_models(report, scan)
    if args.skip_sync:
        ui.rule("Library sync (kicad-cli)")
        report.detail("skipped (--skip-sync)")
    else:
        check_library_sync(report, cfg)

    ui.summary(
        [
            ("Symbols in library", len(scan.symbol_inventory)),
            ("Footprints in library", len(scan.footprint_inventory)),
            ("Model references", len(scan.models)),
            ("Failures", report.failures),
            ("Warnings", report.warnings),
        ]
    )
    if report.failures or (args.strict and report.warnings):
        ui.fail("Checks failed." if report.failures else "Warnings treated as failures (--strict).")
        return 1
    ui.ok("All checks passed.")
    return 0
