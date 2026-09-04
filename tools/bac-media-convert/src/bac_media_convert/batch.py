# SPDX-License-Identifier: MIT
"""Input collection and output planning shared by every subcommand.

Inputs are files, taken as given, or directories, listed one level deep for
the extensions the subcommand handles. Paths are de-duplicated by their
resolved form, so a case-insensitive file system that matches ``a.JPG``
twice yields one job. Outputs are planned before any work starts: two
inputs that would write the same file (``a.jpg`` and ``a.png`` both become
``a.webp``) are an error, and an output that already exists is skipped
unless ``--force`` is given.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from bac_common.errors import UsageError

__all__ = ["IMAGE_EXTENSIONS", "VIDEO_EXTENSIONS", "Job", "collect", "plan", "mark_existing"]

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff"})
VIDEO_EXTENSIONS = frozenset({".webm", ".mkv", ".mov", ".mp4", ".m4v", ".avi"})


@dataclass(slots=True)
class Job:
    source: Path
    target: Path
    status: str = "pending"  # pending | done | skipped | failed
    note: str = ""
    extras: dict[str, object] = field(default_factory=dict)


def collect(
    paths: Sequence[Path], extensions: Iterable[str], *, skip: Callable[[Path], bool] | None = None
) -> list[Path]:
    """Files as given, directories listed for ``extensions`` (lowercased suffixes), sorted and de-duplicated.

    ``skip`` drops files from a directory listing – used to leave this
    tool's own earlier outputs alone. A file named explicitly is never skipped.
    """
    wanted = {e.lower() for e in extensions}
    seen: dict[Path, Path] = {}
    for given in paths:
        path = given.expanduser()
        if path.is_dir():
            candidates = sorted(
                p for p in path.iterdir() if p.is_file() and p.suffix.lower() in wanted and not (skip and skip(p))
            )
        elif path.is_file():
            candidates = [path]
        else:
            raise UsageError(f"No such file or directory: {given}")
        for candidate in candidates:
            seen.setdefault(candidate.resolve(), candidate)
    return [seen[key] for key in sorted(seen, key=lambda p: (str(p.parent).lower(), p.name.lower()))]


def plan(inputs: Sequence[Path], out_dir: Path | None, target_name: Callable[[Path], str]) -> list[Job]:
    """One job per input. Raises when two inputs would write the same output."""
    jobs: list[Job] = []
    owners: dict[Path, Path] = {}
    collisions: list[str] = []
    for source in inputs:
        directory = out_dir.expanduser() if out_dir else source.parent
        target = directory / target_name(source)
        key = target.resolve()
        if key in owners:
            collisions.append(f"{owners[key].name} and {source.name} → {target.name}")
        else:
            owners[key] = source
            jobs.append(Job(source, target))
    if collisions:
        raise UsageError(
            "Two inputs would write the same output file.",
            "; ".join(collisions) + ". Rename one, or convert them into different --out-dir folders.",
        )
    return jobs


def mark_existing(jobs: Iterable[Job], *, force: bool) -> None:
    """Skip jobs whose output exists unless ``force``. A source that is its own target is always skipped."""
    for job in jobs:
        if job.source.resolve() == job.target.resolve():
            job.status, job.note = "skipped", "would overwrite its own input"
        elif job.target.exists() and not force:
            job.status, job.note = "skipped", "exists"
