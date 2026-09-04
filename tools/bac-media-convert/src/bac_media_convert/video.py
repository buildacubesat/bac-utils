# SPDX-License-Identifier: MIT
"""Constant-frame-rate H.264 export through ffmpeg.

Screen recordings and browser captures come as variable-frame-rate WebM,
which editors handle badly. The recipe is the one the shell loop used –
crop to even dimensions, resample to a fixed rate, ``libx264`` at CRF 18
with ``yuv420p`` for compatibility – expressed as an argument list, never
a shell string. ``-fps_mode cfr`` replaces the deprecated ``-vsync`` and
needs ffmpeg 5.1 or newer.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from bac_common.errors import ExternalToolError

__all__ = [
    "DEFAULT_FPS",
    "DEFAULT_CRF",
    "target_name",
    "is_own_output",
    "cfr_command",
    "require_ffmpeg",
    "run_ffmpeg",
]

DEFAULT_FPS = 25
DEFAULT_CRF = 18
EVEN_CROP = "crop=trunc(iw/2)*2:trunc(ih/2)*2"
_OWN_OUTPUT = re.compile(r".+_\d+fps\.mp4$", re.IGNORECASE)


def target_name(source: Path, fps: int = DEFAULT_FPS) -> str:
    """``clip.webm`` becomes ``clip_25fps.mp4``, the name the shell loop produced."""
    return f"{source.stem}_{fps}fps.mp4"


def is_own_output(path: Path) -> bool:
    """True for ``*_25fps.mp4`` – a folder listing must not re-encode the tool's earlier results."""
    return bool(_OWN_OUTPUT.match(path.name))


def cfr_command(
    source: Path, target: Path, *, fps: int = DEFAULT_FPS, crf: int = DEFAULT_CRF, ffmpeg: str = "ffmpeg"
) -> list[str]:
    """The ffmpeg argv. ``-n`` makes ffmpeg itself refuse to overwrite, as a second guard."""
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-n",
        "-i",
        str(source),
        "-vf",
        EVEN_CROP,
        "-r",
        str(fps),
        "-fps_mode",
        "cfr",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        str(target),
    ]


def require_ffmpeg() -> str:
    """The ffmpeg executable, or a clear error naming it."""
    found = shutil.which("ffmpeg")
    if not found:
        raise ExternalToolError("ffmpeg is not installed or not on PATH.", "Install ffmpeg 5.1 or newer and retry.")
    return found


def run_ffmpeg(command: list[str], label: str = "input") -> None:
    """Run ffmpeg silently; a non-zero exit becomes an error carrying the last lines it printed."""
    try:
        completed = subprocess.run(
            command, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace", check=False
        )
    except OSError as exc:
        raise ExternalToolError("Could not start ffmpeg.", str(exc)) from exc
    if completed.returncode != 0:
        tail = " · ".join(line.strip() for line in completed.stderr.strip().splitlines()[-3:] if line.strip())
        raise ExternalToolError(f"ffmpeg failed (exit {completed.returncode}) for {label}", tail or None)
