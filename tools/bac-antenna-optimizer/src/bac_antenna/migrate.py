"""`bac-antenna migrate`: rewrite 0.5 config and plan files to the 0.6 layout, preserving comments.

Config:  `[stack]`, `[outline]`, `[feed]`, `[cavity]` -> `[geometry.stack]` …; `[project] topology = "x"` gains an
         `[antenna] type = "x"` table (the [project] table stays for its name); `[polarization] hybrid_*` are left
         alone (still honoured) but a `[feed_network]` block is added when they are present.
Plans:   `set = ["stack.gap_mm=…"]` -> `geometry.stack.gap_mm=…` for the four geometry sections.
Both layouts keep loading; migration only makes the files say what the tool now means.
"""
from __future__ import annotations

from pathlib import Path
import re
import tomllib

GEOMETRY_SECTIONS = ("stack", "outline", "feed", "cavity")


def migrate_config_text(text: str) -> str:
    out = text
    for sec in GEOMETRY_SECTIONS:
        out = re.sub(rf"^\[{sec}\]", f"[geometry.{sec}]", out, flags=re.M)
    raw = tomllib.loads(text)
    if "antenna" not in raw and "project" in raw and "topology" in raw["project"]:
        topo = raw["project"]["topology"]
        out = re.sub(r"^\[project\]", f'[antenna]\ntype = "{topo}"\n\n[project]', out, count=1, flags=re.M)
        out = re.sub(r'^topology\s*=.*\n', "", out, count=1, flags=re.M)
    pol = raw.get("polarization", {})
    if "feed_network" not in raw and ("hybrid_phase_deg" in pol or "hybrid_amplitude_db" in pol):
        phase_err = float(pol.get("hybrid_phase_deg", 90.0)) - 90.0
        amp_err = float(pol.get("hybrid_amplitude_db", 0.0))
        block = ("\n[feed_network]\n# how the ports are driven together; quadrature = 90 deg hybrid (the legacy [polarization] hybrid_* keys still work)\n"
                 f"mode = \"quadrature\"\nphase_error_deg = {phase_err:g}\namplitude_error_db = {amp_err:g}\n")
        out = re.sub(r"^\[geometry\.stack\]", block.lstrip("\n") + "\n[geometry.stack]", out, count=1, flags=re.M)
    return out


def migrate_plan_text(text: str) -> str:
    out = text
    for sec in GEOMETRY_SECTIONS:
        out = re.sub(rf'(["\'])\s*{sec}\.', rf"\1geometry.{sec}.", out)
    return out


def migrate_files(paths: list[Path]) -> int:
    for path in paths:
        text = path.read_text()
        raw = tomllib.loads(text)
        if "case" in raw:
            new = migrate_plan_text(text)
            kind = "plan"
        elif any(k in raw for k in ("band", "search", "mesh")):
            new = migrate_config_text(text)
            kind = "config"
        else:
            print(f"{path}: not a config or plan, skipped")
            continue
        if new == text:
            print(f"{path}: {kind}, already migrated")
            continue
        tomllib.loads(new)       # must still parse
        path.write_text(new)
        print(f"{path}: {kind}, migrated")
    return 0
