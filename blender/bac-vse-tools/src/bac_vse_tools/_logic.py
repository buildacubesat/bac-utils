# SPDX-License-Identifier: MIT
"""The parts of bac-vse-tools that do not need Blender: file lists, frame maths, the proxy wait, the trim plan.

Everything in here is a plain function or a small class over plain values,
so it is tested with pytest on any Python. The Blender modules call these
and keep only the ``bpy`` plumbing for themselves.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "VIDEO_EXTENSIONS",
    "AUDIO_EXTENSIONS",
    "media_kind",
    "natural_key",
    "list_media",
    "min_frames",
    "fps_settings",
    "autosave_name",
    "proxy_artifact",
    "ProxyWait",
    "TrimAction",
    "trim_plan",
    "count_actions",
]

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mxf", ".mkv", ".avi", ".mpg", ".mpeg", ".m4v", ".webm", ".wmv"})
AUDIO_EXTENSIONS = frozenset({".wav", ".mp3", ".aac", ".flac", ".aiff", ".aif", ".ogg", ".m4a", ".opus"})


# -- bulk import ----------------------------------------------------------------


def media_kind(path: Path) -> str | None:
    """``"video"``, ``"audio"`` or ``None`` by extension, case-insensitive."""
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    return None


def natural_key(name: str) -> tuple:
    """Sort key that orders ``clip2`` before ``clip10``, case-insensitively."""
    return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)) + (name,)


def list_media(folder: Path) -> list[Path]:
    """The video and audio files of ``folder`` (one level) in natural name order (``clip2`` before ``clip10``).

    Hidden files are left out, as are files whose extension is not in the two sets.
    """
    files = [p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".") and media_kind(p)]
    return sorted(files, key=lambda p: natural_key(p.name))


def min_frames(seconds: float, fps: float) -> int:
    """The shortest strip length kept, in frames; ``0`` when the filter is off."""
    if seconds <= 0:
        return 0
    return max(1, round(seconds * fps))


def fps_settings(clip_fps: float) -> tuple[int, float]:
    """Blender's ``(render.fps, render.fps_base)`` pair for a clip's frame rate.

    Blender stores a rate as an integer over a base: 25 → (25, 1.0),
    29.97 → (30, 1.001), 23.976 → (24, 1.001).
    """
    if clip_fps <= 0:
        raise ValueError("frame rate must be positive")
    whole = max(1, round(clip_fps))
    base = whole / clip_fps
    if abs(base - 1.0) < 1e-6:
        base = 1.0
    return whole, round(base, 6)


def autosave_name(blend_path: str, index: int, total: int) -> str:
    """``<blend stem>_import_0007_of_0120.blend``; an unsaved file is called ``unsaved``."""
    stem = Path(blend_path).stem if blend_path else "unsaved"
    return f"{stem}_import_{index:04d}_of_{total:04d}.blend"


# -- sequential proxies ---------------------------------------------------------


def proxy_artifact(
    source_path: str,
    size: int,
    *,
    storage: str = "PER_STRIP",
    project_dir: str = "",
    custom_dir: str = "",
    use_custom_dir: bool = False,
) -> Path:
    """Where Blender writes the proxy movie for ``source_path`` at ``size`` percent.

    Blender names the folder after the source *file* (``clip.mp4``), not the
    strip: ``<dir>/BL_proxy/clip.mp4/proxy_25.avi`` beside the source by
    default, ``<custom dir>/clip.mp4/proxy_25.avi`` for a strip with its own
    proxy directory, and ``<project proxy dir>/clip.mp4/proxy_25.avi`` when
    the sequencer keeps every proxy in one place – with ``project_dir`` the
    caller's resolution of the sequencer's directory, ``//BL_proxy`` beside
    the ``.blend`` when that setting is empty, as Blender resolves it. All
    paths are expected absolute already (``bpy.path.abspath`` is the
    caller's job).
    """
    source = Path(source_path)
    if storage == "PROJECT":
        if not project_dir:
            raise ValueError("project storage needs the resolved project proxy directory")
        root = Path(project_dir)
    elif use_custom_dir and custom_dir:
        root = Path(custom_dir)
    else:
        root = source.parent / "BL_proxy"
    return root / source.name / f"proxy_{int(size)}.avi"


@dataclass(slots=True)
class ProxyWait:
    """The wait for one proxy build, driven by the file's modification time.

    Blender exposes no status for the proxy job to Python, so the file is
    watched: the build counts as done once the proxy exists, has changed
    since the build was triggered (a proxy left over from an earlier build
    does not count), and has then stayed unchanged for ``stable_time``
    seconds – a margin only, since Blender writes ``proxy_25_part.avi`` and
    renames it when complete. ``timeout`` applies to the whole wait, whether
    the file has appeared or not, and ``started`` is the moment the build
    was triggered.
    """

    started: float
    before_mtime: float | None
    stable_time: float
    timeout: float
    last_mtime: float | None = None
    stable_since: float | None = None

    def observe(self, now: float, mtime: float | None) -> str:
        """``"waiting"``, ``"done"`` or ``"timeout"`` for the proxy file's state at ``now``."""
        if now - self.started > self.timeout:
            return "timeout"
        if mtime is None or mtime == self.before_mtime:
            return "waiting"
        if mtime != self.last_mtime:
            self.last_mtime = mtime
            self.stable_since = now
            return "waiting"
        if self.stable_since is not None and now - self.stable_since >= self.stable_time:
            return "done"
        return "waiting"


# -- separate meta --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TrimAction:
    name: str
    action: str
    """``keep`` (inside the meta's range already), ``clip`` (one or both ends move) or ``remove`` (entirely outside)."""
    start: int
    end: int


def trim_plan(meta_start: int, meta_end: int, children: Iterable[tuple[str, int, int]]) -> list[TrimAction]:
    """What separating a meta trimmed to ``[meta_start, meta_end)`` means for each child ``(name, start, end)``.

    Ends are exclusive, as Blender's ``frame_final_end`` is. A child that
    lies entirely outside the range is removed; one that straddles an edge is
    clipped to it; the rest stay as they are.
    """
    plan: list[TrimAction] = []
    for name, start, end in children:
        if end <= meta_start or start >= meta_end:
            plan.append(TrimAction(name, "remove", start, end))
            continue
        new_start, new_end = max(start, meta_start), min(end, meta_end)
        action = "clip" if (new_start, new_end) != (start, end) else "keep"
        plan.append(TrimAction(name, action, new_start, new_end))
    return plan


def count_actions(plans: Sequence[TrimAction]) -> dict[str, int]:
    counts = {"keep": 0, "clip": 0, "remove": 0}
    for item in plans:
        counts[item.action] += 1
    return counts
