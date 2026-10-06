# SPDX-License-Identifier: MIT
"""Shared helpers of the visualizer tests: a synthetic sensitivity pack built with the optimizer itself."""

import gzip
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


def build_synthetic_pack(root: Path) -> Path:
    """An antenna folder with cavity-backend cases on two axes, packed by the tool, plus synthetic 3D data."""
    from bac_antenna.pack import build_pack
    from bac_antenna.sweep import run_sweep

    tool = Path(__import__("bac_antenna").__file__).resolve().parents[2]
    (root / "design" / "plans").mkdir(parents=True)
    (root / "sim" / "runs").mkdir(parents=True)
    shutil.copy(tool / "config" / "cross_2200_dual_v2.toml", root / "design" / "2200.toml")
    shutil.copy(tool / "designs" / "cross_2200_dual_v2.json", root / "design" / "2200.json")
    (root / "plan.toml").write_text(
        '[[case]]\nname = "ref-2200"\n'
        '[[case]]\nname = "gap_4.37"\nset = ["geometry.stack.gap_mm=4.37"]\n'
        '[[case]]\nname = "gap_4.97"\nset = ["geometry.stack.gap_mm=4.97", "geometry.stack.max_height_mm=7.0"]\n'
        '[[case]]\nname = "arms_60.2"\nparams = { arm_x_mm = 60.2, arm_y_mm = 60.2 }\n'
        '[[case]]\nname = "arms_61.2"\nparams = { arm_x_mm = 61.2, arm_y_mm = 61.2 }\n'
    )
    run_sweep(
        root / "design" / "2200.toml",
        root / "design" / "2200.json",
        root / "plan.toml",
        root / "sim" / "runs",
        "cavity",
        [],
        False,
    )
    (root / "design" / "sensitivity.toml").write_text(
        '[sensitivity]\nname = "synthetic-2200"\nconfig = "design/2200.toml"\ndesign = "design/2200.json"\n'
        'nominal = "sim/runs/ref-2200"\nruns = ["sim/runs"]\nignore = ["geometry.stack.max_height_mm"]\n'
        'source = "test"\nrelease = "none"\n'
        '[[axis]]\nid = "gap"\nlabel = "Air gap"\nunit = "mm"\nset = "geometry.stack.gap_mm"\nlevels = [4.37, 4.67, 4.97]\n'
        '[[axis]]\nid = "arms"\nlabel = "Arm length"\nunit = "mm"\nparams = ["arm_x_mm", "arm_y_mm"]\nlevels = [60.2, 60.7, 61.2]\n'
    )
    assert build_pack(root / "design" / "sensitivity.toml") == 0
    pack = root / "generated" / "sensitivity"
    meta = json.loads((pack / "pack.json").read_text())
    nominal = meta["nominal_case"]
    cases = list(meta["cases"])
    # sphere: a cos^4 lobe with a small back lobe, every case
    th = np.arange(0, 181, 5.0)
    ph = np.arange(0, 360, 10.0)
    rows = []
    for k, c in enumerate(cases):
        for t in th:
            for p in ph:
                g = (
                    10 * np.log10(max(1e-3, np.cos(np.radians(t)) ** 4)) + 10.5 - 0.3 * k
                    if t <= 90
                    else -12 - 0.05 * (t - 90)
                )
                rows.append(
                    {
                        "case": c,
                        "theta_deg": t,
                        "phi_deg": p,
                        "gain_total_dbi": g,
                        "gain_co_dbic": g,
                        "gain_cross_dbic": g - 20,
                        "ar_db": 0.6 + t / 60,
                    }
                )
    with gzip.open(pack / "sphere.csv.gz", "wt", newline="") as fh:
        pd.DataFrame(rows).to_csv(fh, index=False)
    # field planes: a gaussian on two planes, nominal only
    rows = []
    u = np.arange(-40, 41, 4.0)
    for plane, axes, fixed, coord in (("E_gap", "xy", "z", 2.33), ("E_xz", "xz", "y", 0.0)):
        for a in u:
            for b in u:
                rows.append(
                    {
                        "case": nominal,
                        "plane": plane,
                        "axes": axes,
                        "fixed": fixed,
                        "coord": coord,
                        "u": a,
                        "v": b,
                        "e_db": -(a**2 + b**2) / 100,
                    }
                )
    with gzip.open(pack / "efield.csv.gz", "wt", newline="") as fh:
        pd.DataFrame(rows).to_csv(fh, index=False)
    # sweeps: the cavity backend writes no S-parameter files, so make a loop per case
    f = np.linspace(1.6e9, 2.9e9, 131)
    ang = (f - 2.245e9) / 0.3e9 * np.pi
    sw = pd.concat(
        [
            pd.DataFrame(
                {
                    "case": c,
                    "frequency_hz": f,
                    "s11_in_db": -20 - 5 * np.cos(ang),
                    "s11_db": -10 - 5 * np.cos(ang),
                    "s21_db": -30.0,
                    "s11_re": 0.3 * np.cos(ang) + 0.1,
                    "s11_im": 0.3 * np.sin(ang),
                }
            )
            for c in cases
        ]
    )
    with gzip.open(pack / "sweeps.csv.gz", "wt", newline="") as fh:
        sw.to_csv(fh, index=False)
    return pack
