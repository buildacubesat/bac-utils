# SPDX-License-Identifier: MIT
"""bac-kicad-schfields – bulk-edit symbol fields across a schematic hierarchy.

Roughly what KiCad's symbol fields table does interactively, but from TOML
rules: deterministic, reviewable, repeatable. The root sheet is given and
the hierarchy is walked from there. Files are edited by span, so a diff
shows only the intended change; nothing is written without confirmation
(``--yes`` for scripts), a ``.bak`` keeps the previous content unless
``--no-backup``, and ``--dry-run`` only reports. The rules live with the
project, so there is no config file and ``--rules`` is required.

Exit codes: 0 done, 1 a failure, 2 bad arguments or rules.
"""

from __future__ import annotations

from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.errors import BacError, UsageError
from bac_common.sexp import parse_file
from bac_kicad_common.files import confirm, write_back
from bac_kicad_common.report import print_changes, print_item
from bac_kicad_common.rules import load_rules_dir

from . import __version__
from .schematic import process_sheet, walk_hierarchy

TOOL = "bac-kicad-schfields"


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Bulk-edit symbol fields and flags across a KiCad schematic hierarchy from TOML rules.",
        examples=[
            "bac-kicad-schfields Board.kicad_sch --rules rules/ --dry-run",
            "bac-kicad-schfields Board.kicad_sch --rules rules/ --allow-flags --yes",
        ],
        init=False,
        env_file=False,
        config=False,
    )
    parser.usage = (
        "bac-kicad-schfields SCHEMATIC --rules DIR [--dry-run] [--yes] [--no-backup]\n"
        "                           [--allow-overwrite] [--allow-flags] [--include-cache] [--no-fill-empty]"
    )
    parser.add_argument("schematic", metavar="SCHEMATIC", help="root .kicad_sch of the project")
    parser.add_argument("--rules", metavar="DIR", required=True, help='TOML rule files (target = "schematic")')
    parser.add_argument("--yes", action="store_true", help="write without asking")
    parser.add_argument("--no-backup", action="store_true", help="do not keep <file>.bak copies")
    parser.add_argument("--allow-overwrite", action="store_true", help="let overwrite = true rules replace values")
    parser.add_argument("--allow-flags", action="store_true", help="let [[flag]] rules change dnp and friends")
    parser.add_argument("--include-cache", action="store_true", help="also edit the lib_symbols cache")
    parser.add_argument("--no-fill-empty", action="store_true", help="leave empty existing fields alone")
    args = parser.parse_args(argv)

    root_sheet = Path(args.schematic).expanduser()
    if not root_sheet.is_file():
        raise UsageError(f"Schematic not found: {args.schematic}")
    rulesets = load_rules_dir(Path(args.rules), target="schematic")
    if not rulesets:
        raise UsageError(f'No rule files with target = "schematic" in {args.rules}.')

    hierarchy = walk_hierarchy(root_sheet)
    ui.opening(TOOL, __version__, f"Applying {len(rulesets)} rule file(s) to {len(hierarchy.sheets)} sheet(s).")
    for warning in hierarchy.warnings:
        ui.warn(ui.esc(warning))
    for sheet in hierarchy.sheets:
        if sheet.instantiations > 1:
            ui.warn(
                f"{ui.path(sheet.path.name)} is instantiated {sheet.instantiations}×; one edit affects every instance"
            )

    pending: list[tuple[Path, str]] = []
    counts = {"add": 0, "fill": 0, "set": 0, "flag": 0, "skipped": 0, "components": 0}
    for sheet in hierarchy.sheets:
        if not sheet.readable:
            continue
        text, root = parse_file(sheet.path)
        new_text, results = process_sheet(
            sheet.path,
            text,
            root,
            rulesets,
            fill_empty=not args.no_fill_empty,
            allow_overwrite=args.allow_overwrite,
            allow_flags=args.allow_flags,
            include_cache=args.include_cache,
        )
        if results:
            print_item("file", sheet.path.name)
        for r in results:
            counts["components"] += 1
            units = f"({r.units} units)" if r.units > 1 else ""
            print_item("cache" if r.cached else "sym", f"{r.reference}  {r.lib_id}" if r.reference else r.lib_id, units)
            print_changes(r.changes, r.skipped)
            for c in r.changes:
                counts[c.kind] += 1
            counts["skipped"] += len(r.skipped)
        if new_text != text:
            pending.append((sheet.path, new_text))

    written = 0
    if not pending:
        if not args.dry_run:
            ui.step("Nothing to write.")
    elif args.dry_run:
        for path, _ in pending:
            ui.step(f"Would write {ui.path(path)}")
    else:
        confirm(f"Write {len(pending)} sheet(s)?", yes=args.yes)
        for path, new_text in pending:
            try:
                saved = write_back(path, new_text, backup=not args.no_backup)
            except BacError as exc:
                ui.fail(f"{ui.path(path)}: {ui.esc(exc.message)}")
                continue
            written += 1
            ui.ok(f"Wrote {ui.path(path)}" + (f" [dim](backup {ui.esc(saved.name)})[/]" if saved else ""))

    ui.summary(
        [
            ("Sheets", len(hierarchy.sheets)),
            ("Components matched", counts["components"]),
            ("Fields added", counts["add"]),
            ("Fields filled", counts["fill"]),
            ("Values overwritten", counts["set"]),
            ("Flags changed", counts["flag"]),
            ("Rules skipped", counts["skipped"]),
            ("Sheets to write" if args.dry_run else "Sheets written", len(pending) if args.dry_run else written),
        ],
        dry_run=args.dry_run,
    )
    return 1 if not args.dry_run and written < len(pending) else 0
