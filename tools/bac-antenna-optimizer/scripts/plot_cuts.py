#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Plot farfield_cuts.csv of one or more case directories: RHCP realized gain and axial ratio versus
signed theta in the four cut planes, one column per frequency. Writes farfield_cuts.png next to the
CSV and prints the off-axis summary from openems_diagnostics.json.

    uv run --with matplotlib scripts/plot_cuts.py runs/freeze/frozen [runs/freeze/gap_4.37 ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bac_antenna.pattern import read_cuts_csv, signed_cut  # noqa: E402

PLANES = (0.0, 90.0, 45.0, 135.0)


def plot_case(case_dir: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cuts = read_cuts_csv(case_dir / "farfield_cuts.csv")
    freqs, theta, phi, metrics = cuts["freqs"], cuts["theta"], cuts["phi"], cuts["metrics"]
    fig, axes = plt.subplots(2, len(freqs), figsize=(4.8 * len(freqs), 7.0), sharex=True, squeeze=False)
    for c, (f, m) in enumerate(zip(freqs, metrics, strict=True)):
        ax_g, ax_ar = axes[0, c], axes[1, c]
        for plane in PLANES:
            xs, g = signed_cut(theta, phi, m["gain_co_dbic"], plane)
            _, gx = signed_cut(theta, phi, m["gain_cross_dbic"], plane)
            _, ar = signed_cut(theta, phi, m["ar_db"], plane)
            (line,) = ax_g.plot(xs, g, label=f"phi = {plane:g} deg")
            ax_g.plot(xs, gx, color=line.get_color(), linestyle=":", linewidth=0.8)
            ax_ar.plot(xs, ar, color=line.get_color())
        ax_g.set_title(f"{f / 1e9:.3f} GHz")
        ax_g.set_ylim(-20, 12)
        ax_g.axvline(-60, color="0.7", linewidth=0.6)
        ax_g.axvline(60, color="0.7", linewidth=0.6)
        ax_g.grid(True, alpha=0.3)
        ax_ar.set_ylim(0, 12)
        ax_ar.axhline(3, color="0.7", linewidth=0.6)
        ax_ar.axvline(-60, color="0.7", linewidth=0.6)
        ax_ar.axvline(60, color="0.7", linewidth=0.6)
        ax_ar.grid(True, alpha=0.3)
        ax_ar.set_xlabel("theta (deg), signed along the plane")
        ax_ar.set_xlim(-180, 180)
        ax_ar.set_xticks(range(-180, 181, 60))
    axes[0, 0].set_ylabel("realized gain (dBic), co solid / cross dotted")
    axes[1, 0].set_ylabel("axial ratio (dB)")
    axes[0, 0].legend(loc="lower center", fontsize=8)
    fig.suptitle(case_dir.name)
    fig.tight_layout()
    out = case_dir / "farfield_cuts.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def print_summary(case_dir: Path) -> None:
    diag = case_dir / "openems_diagnostics.json"
    if not diag.exists():
        return
    pat = json.loads(diag.read_text()).get("pattern")
    if not pat:
        return
    print(f"{case_dir.name}:")
    for key, s in pat["per_frequency"].items():
        print(
            f"  {key:>12s}  G0 {s['gain_co_broadside']:5.2f} dBic  AR0 {s['ar_broadside']:4.2f} dB  "
            f"G45 {s['gain_co_min_45']:5.2f}  AR45 {s['ar_max_45']:4.2f}  G60 {s['gain_co_min_60']:5.2f}  "
            f"AR60 {s['ar_max_60']:4.2f}  F/B {s['front_to_back_db']:4.1f} dB"
        )
    w = pat["worst"]
    print(
        f"  {'worst':>12s}  G60 {w['gain_co_min_60']:5.2f} dBic  AR60 {w['ar_max_60']:4.2f} dB  "
        f"F/B {w['front_to_back_db']:4.1f} dB  rear-hemisphere power {100 * w['back_fraction']:.1f} %"
    )


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for arg in argv:
        case_dir = Path(arg)
        if not (case_dir / "farfield_cuts.csv").exists():
            print(f"{case_dir}: no farfield_cuts.csv (run or reprocess the case first)")
            continue
        print_summary(case_dir)
        print(f"  -> {plot_case(case_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
