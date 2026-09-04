# SPDX-License-Identifier: MIT
"""bac-media-convert – batch conversions with one subcommand per recipe.

``webp-square`` centre-crops images to squares and writes WebP for the
shop; ``cfr`` turns variable-frame-rate video into constant-rate H.264 MP4
for editing. Both take files or folders, plan every output before
starting, skip outputs that exist unless ``--force``, and show a progress
bar with a ✓ line per file. No persistent settings, so no ``--init``,
``--config`` or ``--env-file``.

Exit codes: 0 all converted (skips included), 1 at least one file failed
or a required program is missing, 2 bad arguments.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path

import typer

from bac_common import cli as bac_cli
from bac_common import ui
from bac_common.errors import BacError, UsageError

from . import __version__, video, webp
from .batch import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, Job, collect, mark_existing, plan

TOOL = "bac-media-convert"

app = typer.Typer(
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    help=(
        "Build a CubeSat – batch media conversions: square WebP for the shop, "
        "constant-frame-rate MP4 from variable-rate video.\n\n"
        "\b\n"
        "Examples:\n"
        "  bac-media-convert webp-square photos/ --out-dir photos/webp\n"
        "  bac-media-convert cfr capture.webm --fps 30"
    ),
)


def main() -> None:
    bac_cli.run(_main)


def _main(argv: list[str], debug: bool) -> int:
    return bac_cli.run_typer(app, argv, TOOL)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(bac_cli.version_string(TOOL, __version__))
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "-v", "--version", callback=_version_callback, is_eager=True, help="Print version and exit."
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


@app.command("webp-square")
def webp_square(
    paths: list[Path] = typer.Argument(..., metavar="PATH...", help="Image files, or folders of jpg/png/tif."),
    out_dir: Path | None = typer.Option(None, "--out-dir", metavar="DIR", help="Write here (default: beside)."),
    max_side: int = typer.Option(webp.DEFAULT_MAX_SIDE, "--max-side", metavar="PX", help="Downscale limit."),
    quality: int = typer.Option(webp.DEFAULT_QUALITY, "--quality", metavar="Q", help="WebP quality 1–100."),
    force: bool = typer.Option(False, "--force", help="Overwrite outputs that exist."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan and validate; write nothing."),
) -> None:
    """Square WebP from images: centre crop, downscale, <name>.webp.

    Quality 90, encoder method 6, EXIF orientation applied, alpha kept.
    """
    if not 1 <= quality <= 100:
        raise UsageError("--quality must be between 1 and 100.")
    if max_side < 1:
        raise UsageError("--max-side must be positive.")
    inputs = collect(paths, IMAGE_EXTENSIONS)
    jobs = plan(inputs, out_dir, lambda p: f"{p.stem}.webp")

    def work(job: Job, tmp: Path) -> str:
        width, height, size = webp.convert_square_webp(job.source, tmp, max_side=max_side, quality=quality)
        return f"{width}×{height}, {_human_size(size)}"

    _run(jobs, work, force=force, dry_run=dry_run, description="Centre-cropping images to square WebP.")


@app.command("cfr")
def cfr(
    paths: list[Path] = typer.Argument(..., metavar="PATH...", help="Video files, or folders of webm/mkv/mov/mp4."),
    out_dir: Path | None = typer.Option(None, "--out-dir", metavar="DIR", help="Write here (default: beside)."),
    fps: int = typer.Option(video.DEFAULT_FPS, "--fps", metavar="N", help="Output frame rate."),
    crf: int = typer.Option(video.DEFAULT_CRF, "--crf", metavar="N", help="x264 quality, lower is better."),
    force: bool = typer.Option(False, "--force", help="Overwrite outputs that exist."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan and validate; write nothing."),
) -> None:
    """Constant-frame-rate H.264 MP4 from video, <name>_25fps.mp4.

    libx264, preset veryfast, yuv420p, even dimensions; needs ffmpeg 5.1+.
    """
    if fps < 1:
        raise UsageError("--fps must be positive.")
    if not 0 <= crf <= 51:
        raise UsageError("--crf must be between 0 and 51.")
    inputs = collect(paths, VIDEO_EXTENSIONS, skip=video.is_own_output)
    jobs = plan(inputs, out_dir, lambda p: video.target_name(p, fps))
    ffmpeg = "ffmpeg"
    try:
        ffmpeg = video.require_ffmpeg()
    except BacError:
        if not dry_run:
            raise
        ui.warn("ffmpeg is not installed or not on PATH; the run itself would stop here.")

    def work(job: Job, tmp: Path) -> str:
        video.run_ffmpeg(video.cfr_command(job.source, tmp, fps=fps, crf=crf, ffmpeg=ffmpeg), job.source.name)
        return _human_size(tmp.stat().st_size)

    _run(jobs, work, force=force, dry_run=dry_run, description=f"Re-encoding video to {fps} fps H.264 MP4.")


# ---------------------------------------------------------------------------
# Shared run loop
# ---------------------------------------------------------------------------


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    return f"{size / 1024:.0f} KiB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MiB"


def _part_path(target: Path) -> Path:
    """``clip_25fps.mp4`` is written as ``clip_25fps.part.mp4`` and renamed when complete."""
    return target.with_name(f"{target.stem}.part{target.suffix}")


def _run(
    jobs: Sequence[Job], work: Callable[[Job, Path], str], *, force: bool, dry_run: bool, description: str
) -> None:
    """Skip, plan or convert every job, then print the summary. ``work(job, tmp)`` writes to ``tmp``.

    Outputs are written to a ``.part`` file and renamed into place only when
    the conversion finished, so an interrupted run leaves no half-written
    file that the next run would skip as done.
    """
    ui.opening(TOOL, __version__, description)
    if not jobs:
        raise BacError("No input files found.", "Give files, or folders containing files with a supported extension.")
    mark_existing(jobs, force=force)
    pending = [j for j in jobs if j.status == "pending"]

    for job in jobs:
        if job.status == "skipped":
            hint = "; --force to redo" if job.note == "exists" else ""
            ui.warn(f"Skipped {ui.path(job.target)} ({job.note}{hint})")

    if dry_run:
        for job in pending:
            ui.step(f"Would write {ui.path(job.target)} from {ui.path(job.source.name)}")
    else:
        for job in pending:
            job.target.parent.mkdir(parents=True, exist_ok=True)
        with ui.make_progress("count") as progress:
            task = progress.add_task("Converting", total=len(pending))
            for job in pending:
                progress.update(task, description=ui.esc(job.source.name))
                tmp = _part_path(job.target)
                try:
                    tmp.unlink(missing_ok=True)
                    note = work(job, tmp)
                    os.replace(tmp, job.target)
                except BacError as exc:
                    tmp.unlink(missing_ok=True)
                    job.status, job.note = "failed", exc.message
                    ui.fail(f"{ui.path(job.source.name)}: {ui.esc(exc.message)}")
                    if exc.detail:
                        ui.dim(f"    {ui.esc(exc.detail)}")
                except BaseException:  # Ctrl-C or a crash: never leave a half-written output behind
                    tmp.unlink(missing_ok=True)
                    raise
                else:
                    job.status = "done"
                    ui.ok(f"{ui.path(job.source.name)} → {ui.path(job.target.name)} ({ui.esc(note)})")
                progress.advance(task)

    counts = {s: sum(1 for j in jobs if j.status == s) for s in ("done", "skipped", "failed")}
    ui.summary(
        [
            ("Inputs", len(jobs)),
            ("Converted" if not dry_run else "Would convert", len(pending) if dry_run else counts["done"]),
            ("Skipped", counts["skipped"]),
            ("Failed", counts["failed"]),
        ],
        dry_run=dry_run,
    )
    if counts["failed"]:
        raise typer.Exit(1)
