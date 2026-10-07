# SPDX-License-Identifier: MIT
"""bac-store-product-cropper – crop product photos by hand, export WebP under a size target.

Takes files or folders, plans one ``.webp`` per image (in ``out_webp/``
beside the source unless ``--out-dir``), refuses two inputs that would
write the same file, skips outputs that exist unless ``--force``, and then
opens one Tk window where each image is framed by hand. No persistent
settings, so no ``--init``, ``--config`` or ``--env-file``.

Exit codes: 0 finished or quit early (the summary says what remains),
1 at least one image could not be read or written, or Tk is missing,
2 bad arguments.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bac_media_convert.batch import IMAGE_EXTENSIONS, Job, collect, mark_existing, plan

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.errors import UsageError

from . import __version__, gui
from .export import ExportOptions

__all__ = ["TOOL", "DEFAULT_SUBDIR", "main", "plan_jobs"]

TOOL = "bac-store-product-cropper"
DEFAULT_SUBDIR = "out_webp"
"""Where the WebP files go when ``--out-dir`` is not given: this folder beside each source."""


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    parser = bac_cli.make_parser(
        TOOL,
        __version__,
        "Crop product photos by hand and export WebP under a size target.",
        examples=[
            "bac-store-product-cropper photos/",
            "bac-store-product-cropper photos/ --aspect 4/3 --out-dir web/",
        ],
        init=False,
        env_file=False,
        config=False,
    )
    parser.usage = "bac-store-product-cropper [options] PATH..."
    parser.add_argument("paths", nargs="+", metavar="PATH", type=Path, help="image files or folders (one level)")
    parser.add_argument(
        "--out-dir", metavar="DIR", type=Path, help=f"output folder (default: {DEFAULT_SUBDIR}/ beside each source)"
    )
    parser.add_argument(
        "--aspect", metavar="RATIO", type=aspect_ratio, default=1.0, help="width/height: 1, 4/3, 0.5, 2"
    )
    parser.add_argument("--max-width", metavar="PX", type=int, default=3840, help="longest output width (default 3840)")
    parser.add_argument("--target-kb", metavar="KB", type=int, default=200, help="size target (default 200; 0 = once)")
    parser.add_argument("--start-q", metavar="Q", type=int, default=30, help="first WebP quality tried (default 30)")
    parser.add_argument("--min-q", metavar="Q", type=int, default=10, help="lowest quality tried (default 10)")
    parser.add_argument("--force", action="store_true", help="redo outputs that already exist")
    args = parser.parse_args(argv)

    options = ExportOptions(
        aspect=args.aspect,
        max_width=args.max_width,
        target_kb=args.target_kb,
        start_quality=args.start_q,
        min_quality=args.min_q,
    )
    try:
        options.validate()
    except ValueError as exc:
        raise UsageError(f"{exc}.", "Check --aspect, --max-width, --target-kb, --start-q and --min-q.") from exc
    if args.out_dir is not None and args.out_dir.exists() and not args.out_dir.is_dir():
        raise UsageError(f"--out-dir is not a directory: {args.out_dir}")

    jobs = plan_jobs(args.paths, args.out_dir, force=args.force)
    if not jobs:
        raise UsageError("No images found.", f"Looked for {', '.join(sorted(IMAGE_EXTENSIONS))} in the given paths.")

    ui.opening(TOOL, __version__, "Crop product photos by hand; export WebP under a size target.")
    ui.fields(
        [
            ("Images", len(jobs)),
            ("Aspect", f"{options.aspect:g}"),
            ("Output", args.out_dir or f"{DEFAULT_SUBDIR}/ beside each source"),
            (
                "Target",
                f"≤ {options.target_kb} kB, q{options.start_quality} → q{options.min_quality}"
                if options.target_kb
                else f"q{options.start_quality}, no size target",
            ),
        ]
    )
    skipped_existing = 0
    for job in jobs:
        if job.status == "skipped":
            skipped_existing += 1
            ui.warn(f"{ui.path(job.target)} {job.note} – use --force to redo")

    pending = [job for job in jobs if job.status == "pending"]
    if args.dry_run:
        for job in pending:
            ui.dim(f"{ui.esc(str(job.source))} → {ui.esc(str(job.target))}")
        ui.summary([("Images", len(jobs)), ("To crop", len(pending)), ("Existing", skipped_existing)], dry_run=True)
        return 0

    def report(kind: str, job: Job, note: str) -> None:
        if kind == "done":
            ui.ok(f"{ui.path(job.target)} {note}")
        elif kind == "skipped":
            ui.dim(f"{ui.esc(job.source.name)} skipped")
        else:
            ui.fail(f"{ui.esc(job.source.name)}: {ui.esc(note)}")

    counts = gui.run(jobs, options, report=report)
    ui.summary(
        [
            ("Saved", counts.saved),
            ("Skipped", counts.skipped + skipped_existing),
            ("Failed", counts.failed),
            ("Remaining", counts.remaining),
        ]
    )
    return 1 if counts.failed else 0


def aspect_ratio(text: str) -> float:
    """``--aspect`` accepts a decimal (``1.3333``) or a fraction (``4/3``)."""
    try:
        if "/" in text:
            num, den = text.split("/", 1)
            return float(num) / float(den)
        return float(text)
    except (ValueError, ZeroDivisionError):
        raise argparse.ArgumentTypeError(f"not a ratio: {text!r} (use 1, 4/3, 0.5 or 2)") from None


def plan_jobs(paths: list[Path], out_dir: Path | None, *, force: bool) -> list[Job]:
    """Collect the images, plan the targets, mark the ones that exist. Collisions raise before any work."""
    inputs = collect(paths, IMAGE_EXTENSIONS)
    if out_dir is None:
        jobs = plan(inputs, None, lambda source: f"{DEFAULT_SUBDIR}/{source.stem}.webp")
    else:
        jobs = plan(inputs, out_dir, lambda source: f"{source.stem}.webp")
    mark_existing(jobs, force=force)
    return jobs
