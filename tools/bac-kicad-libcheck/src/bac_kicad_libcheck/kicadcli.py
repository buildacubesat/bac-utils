# SPDX-License-Identifier: MIT
"""Delegate the stale-library check to KiCad's own ERC and DRC.

KiCad already knows whether a placed symbol or footprint still matches its
library copy – ERC raises a symbol mismatch, DRC a footprint mismatch.
Running those and filtering the JSON report keeps the definition of
"current" as KiCad's rather than a reimplementation that drifts with the
file format.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Violation", "CliResult", "run_erc", "run_drc", "extract"]

TIMEOUT_S = 600


@dataclass(slots=True)
class Violation:
    kind: str  # erc | drc
    type: str
    severity: str
    description: str
    items: list[str]


@dataclass
class CliResult:
    available: bool
    violations: list[Violation] = field(default_factory=list)
    all_types: set[str] = field(default_factory=set)
    error: str = ""


def extract(payload: dict, kind: str, wanted: list[str]) -> tuple[list[Violation], set[str]]:
    """The wanted violations and every type seen. ERC nests violations under sheets; DRC keeps them at the top."""
    buckets: list[dict] = []
    if isinstance(payload.get("violations"), list):
        buckets.extend(payload["violations"])
    for sheet in payload.get("sheets") or []:
        buckets.extend(sheet.get("violations") or [])
    for key in ("unconnected_items", "schematic_parity"):
        buckets.extend(payload.get(key) or [])

    violations: list[Violation] = []
    seen: set[str] = set()
    for v in buckets:
        if not isinstance(v, dict):
            continue
        vtype = str(v.get("type", ""))
        seen.add(vtype)
        if vtype not in wanted:
            continue
        items = [str(i.get("description") or i.get("uuid") or "") for i in v.get("items") or [] if isinstance(i, dict)]
        violations.append(
            Violation(kind, vtype, str(v.get("severity", "")), str(v.get("description", "")), [i for i in items if i])
        )
    return violations, seen


def _run(cli: str, args: list[str], kind: str, wanted: list[str]) -> CliResult:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"{kind}.json"
        cmd = [cli, *args, "--format", "json", "-o", str(out)]
        try:
            proc = subprocess.run(
                cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace", timeout=TIMEOUT_S
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CliResult(False, error=f"{kind.upper()}: {exc}")
        if not out.exists():
            lines = (proc.stderr or proc.stdout or "").strip().splitlines()
            return CliResult(
                False, error=f"{kind.upper()}: no report produced – {lines[-1] if lines else f'exit {proc.returncode}'}"
            )
        try:
            payload = json.loads(out.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return CliResult(False, error=f"{kind.upper()}: unreadable report – {exc}")
    if not isinstance(payload, dict):
        return CliResult(False, error=f"{kind.upper()}: unexpected report shape")
    violations, seen = extract(payload, kind, wanted)
    return CliResult(True, violations, seen)


def run_erc(cli: str, schematic: Path, wanted: list[str]) -> CliResult:
    if shutil.which(cli) is None:
        return CliResult(False, error=f"{cli} not found on PATH")
    return _run(cli, ["sch", "erc", str(schematic)], "erc", wanted)


def run_drc(cli: str, board: Path, wanted: list[str]) -> CliResult:
    if shutil.which(cli) is None:
        return CliResult(False, error=f"{cli} not found on PATH")
    return _run(cli, ["pcb", "drc", str(board)], "drc", wanted)
