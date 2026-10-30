# SPDX-License-Identifier: MIT
"""bac-design-export – export the BAC guides from Markdown to PDF as BAC documents.

Exit codes: 0 every export current (or written), 1 an export is stale under --check, a
document failed or the bac-design checkout cannot be found, 2 bad arguments.
"""

from __future__ import annotations

from pathlib import Path

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.errors import ConfigError, UsageError

from . import __version__
from .document import read
from .fonts import faces
from .render import PAPERS, creator, page, pdf_creator, source_hash, write_pdf

TOOL = "bac-design-export"
FORMATS = ("pdf", "html")
LOGO = "assets/bac-logo-black-v4r1.svg"


def main() -> None:
    bac_cli.run(_main)


def is_design(folder: Path) -> bool:
    return (folder / "guides").is_dir() and (folder / "fonts").is_dir()


def find_design(start: Path) -> Path | None:
    """The bac-design checkout: an ancestor of ``start``, or a ``bac-design`` folder beside one."""
    for folder in (start, *start.parents):
        if is_design(folder):
            return folder
        if is_design(folder / "bac-design"):
            return folder / "bac-design"
    return None


def output_name(stem: str, paper: str, fmt: str) -> str:
    return f"{stem}{'' if paper == 'a4' else '-' + paper}.{fmt}"


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Export the BAC guides from Markdown to PDF as BAC documents.",
        examples=["bac-design-export --check", "bac-design-export bac-identity-guide --format html -o /tmp/preview"],
        list_help="print the guides found and exit",
        init=False,
        env_file=False,
        config=False,
    )
    parser.add_argument("documents", nargs="*", metavar="DOC", help="guide names or Markdown files (default: all)")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if any export is stale")
    parser.add_argument("--paper", choices=PAPERS, default="a4", metavar="SIZE", help="a4 or letter (default: a4)")
    parser.add_argument("--format", choices=FORMATS, default="pdf", metavar="FMT", help="pdf or html (default: pdf)")
    parser.add_argument("--design", metavar="PATH", help="the bac-design checkout (default: found from here)")
    parser.add_argument("-o", "--out-dir", metavar="DIR", help="where to write (default: <design>/exports)")
    args = parser.parse_args(argv)

    design = Path(args.design).resolve() if args.design else find_design(Path.cwd().resolve())
    if design is None or not is_design(design):
        raise ConfigError("No bac-design checkout found.", "Pass --design PATH or run inside or beside the checkout.")
    guides = sorted((design / "guides").glob("*.md"))

    if args.list:
        for path in guides:
            print(path.stem)
        return 0

    sources: list[Path] = []
    for name in args.documents:
        path = Path(name)
        if path.suffix == ".md" and path.is_file():
            sources.append(path.resolve())
        elif (design / "guides" / f"{name}.md").is_file():
            sources.append(design / "guides" / f"{name}.md")
        else:
            raise UsageError(f"No guide named {name}.", f"Run `{TOOL} -l` for the list.")
    sources = sources or guides
    if args.check and args.format != "pdf":
        raise UsageError("--check compares PDF exports only.")

    out = Path(args.out_dir).resolve() if args.out_dir else design / "exports"
    logo = design / LOGO
    ui.opening(TOOL, __version__, f"{len(sources)} document(s) → {out} ({args.paper.upper()}, {args.format.upper()})")
    with ui.spinner("Preparing the fonts"):
        face_list = faces(design / "fonts")

    current = written = stale = failed = 0
    for path in sources:
        doc = read(path)
        target = out / output_name(doc.stem, args.paper, args.format)
        digest = source_hash(doc, face_list, args.paper, logo)
        if args.format == "pdf" and pdf_creator(target) == creator(digest):
            current += 1
            ui.dim(f"{target.name} is current")
            continue
        if args.check:
            stale += 1
            ui.fail(f"Stale: {ui.path(target.name)}")
            continue
        if args.dry_run:
            stale += 1
            ui.step(f"Would write: {ui.path(target.name)}")
            continue
        markup = page(doc, face_list, args.paper, logo, digest)
        try:
            if args.format == "html":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(markup, encoding="utf-8")
            else:
                with ui.spinner(f"Rendering {doc.stem}"):
                    write_pdf(markup, target)
        except Exception as exc:  # noqa: BLE001 – one failed document does not stop the run
            if debug:
                raise
            failed += 1
            ui.fail(f"Failed: {ui.path(target.name)} – {ui.esc(str(exc))}")
            continue
        written += 1
        ui.ok(f"Written: {ui.path(target.name)}")

    label = "Stale" if args.check or args.dry_run else "Written"
    rows = [("Current", current), (label, stale if args.check or args.dry_run else written)]
    if failed:
        rows.append(("Failed", failed))
    ui.summary(rows, dry_run=args.dry_run)
    if args.check and stale:
        ui.error("Exports are out of date with the guides.", f"Run `{TOOL}` and commit the result.")
        return 1
    return 1 if failed else 0
