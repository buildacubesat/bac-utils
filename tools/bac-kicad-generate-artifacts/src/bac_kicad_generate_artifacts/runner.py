# SPDX-License-Identifier: MIT
"""External programs: discovery and a subprocess wrapper with dry run and timeout.

Every stage calls kicad-cli, cwebp or an SVG rasteriser through :class:`Runner`
so that ``--dry-run`` records the commands instead of running them and a
failing program becomes one :class:`ExternalToolError` with the tail of its
stderr as the detail line. Tests pass a fake runner that writes the files a
stage expects.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bac_common.errors import ExternalToolError

__all__ = ["Tools", "Runner", "find_tools", "TARGET_KICAD"]

TARGET_KICAD = "kicad-cli 10.x (tested with 10.0.3)"
"""The command set the stages are written against. Help text is never probed."""

Which = Callable[[str], str | None]


@dataclass(frozen=True)
class Tools:
    kicad_cli: str
    svg_raster: str  # inkscape or rsvg-convert

    @property
    def raster_is_inkscape(self) -> bool:
        return Path(self.svg_raster).name.startswith("inkscape")


def find_tools(which: Which | None = None) -> Tools:
    """Locate the programs every run needs, or raise one error naming all that are missing."""
    which = which or shutil.which  # looked up at call time, so tests can replace shutil.which
    kicad_cli = which("kicad-cli")
    raster = which("inkscape") or which("rsvg-convert")
    missing = [name for name, found in (("kicad-cli", kicad_cli), ("inkscape or rsvg-convert", raster)) if not found]
    if missing:
        raise ExternalToolError(
            "Missing programs: " + ", ".join(missing) + ".",
            "Install KiCad 10 (kicad-cli) and inkscape or librsvg (rsvg-convert).",
        )
    assert kicad_cli and raster
    return Tools(kicad_cli, raster)


@dataclass
class Runner:
    """Runs a command list; in dry-run mode it only records it.

    ``commands`` collects every command seen, dry or not, for ``--debug``
    output and for tests.
    """

    dry_run: bool = False
    timeout: float = 600.0
    commands: list[list[str]] = field(default_factory=list)

    def __call__(
        self, cmd: list[str], *, cwd: Path | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(cmd))
        if self.dry_run:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        try:
            result = subprocess.run(
                cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=self.timeout, check=False
            )
        except FileNotFoundError as exc:
            raise ExternalToolError(f"Program not found: {cmd[0]}", str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            raise ExternalToolError(
                f"{Path(cmd[0]).name} did not finish within {self.timeout:.0f} s.", _short(cmd)
            ) from exc
        if check and result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip().splitlines()
            detail = tail[-1] if tail else "no output"
            raise ExternalToolError(f"{Path(cmd[0]).name} failed (exit {result.returncode}): {detail}", _short(cmd))
        return result

    def ok(self, cmd: list[str]) -> bool:
        """True when ``cmd`` exits 0. Never raises for a non-zero exit; a missing program is False too."""
        try:
            return self(cmd, check=False).returncode == 0
        except ExternalToolError:
            return False


def _short(cmd: list[str]) -> str:
    """The command for an error detail line: program name plus subcommand words, paths shortened."""
    parts = [Path(cmd[0]).name] + [Path(c).name if "/" in c else c for c in cmd[1:]]
    text = " ".join(parts)
    return text if len(text) <= 110 else text[:107] + "..."
