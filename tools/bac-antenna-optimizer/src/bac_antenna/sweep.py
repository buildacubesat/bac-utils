# SPDX-License-Identifier: MIT
"""Unattended parameter sweeps over a plan file.

Plan (TOML):

    [[case]]
    name = "gap_4.1"
    set = ["stack.gap_mm=4.1"]        # config overrides, same syntax as --set
    params = { feed_offset_mm = 15.0 } # design-parameter overrides

Cases with an existing result.json are skipped, so a sweep can be stopped and resumed.
Each finished case appends one row to sweep_summary.csv. With reprocess=True every case is
re-evaluated from its existing field data (no FDTD) and its summary row replaced – use it after a
post-processing change to refresh an old sweep.
"""

from __future__ import annotations

import csv
import json
import time
import tomllib
from pathlib import Path

from .config import load_config
from .core import full_params, score
from .geometry import check_model
from .metrics import Metrics
from .topologies import get_topology
from .vtk import write_geometry_vtp


def _row(name: str, params: dict, metrics: Metrics, s: float, diag: dict, seconds: float, config) -> dict:
    row = {
        "case": name,
        "score": f"{s:.4f}",
        "resonance_hz": f"{metrics.resonance_hz:.5e}",
        "seconds": f"{seconds:.0f}",
    }
    row.update({k: f"{v:.3f}" for k, v in sorted(params.items())})
    for b in config.bands:
        m = metrics.bands[b.name]
        row.update(
            {
                f"{b.name}_s11": f"{m.s11_worst_db:.2f}",
                f"{b.name}_gain": f"{m.gain_min_dbic:.2f}",
                f"{b.name}_ar": f"{m.ar_worst_db:.2f}",
                f"{b.name}_eff": f"{m.efficiency_percent:.1f}",
                f"{b.name}_hand": m.hand,
            }
        )
    pb = diag.get("power_cross_check_primary_centre") or {}
    row["p_rad_over_p_acc"] = f"{pb.get('p_rad_over_p_acc', float('nan')):.3f}"
    row["hybrid_load_fraction"] = f"{diag.get('hybrid_load_fraction_at_primary_centre', float('nan')):.3f}"
    row["probe_res_hz"] = f"{diag.get('probe_resonance_hz', float('nan')):.5e}"
    w = (diag.get("pattern") or {}).get("worst") or {}
    p = config.primary_band.name
    row[f"{p}_gain_45"] = f"{w.get('gain_co_min_45', float('nan')):.2f}"
    row[f"{p}_ar_45"] = f"{w.get('ar_max_45', float('nan')):.2f}"
    row[f"{p}_gain_60"] = f"{w.get('gain_co_min_60', float('nan')):.2f}"
    row[f"{p}_ar_60"] = f"{w.get('ar_max_60', float('nan')):.2f}"
    row["fb_db"] = f"{w.get('front_to_back_db', float('nan')):.1f}"
    row["back_fraction"] = f"{w.get('back_fraction', float('nan')):.3f}"
    return row


def read_summary(summary: Path) -> tuple[list[str], list[dict]]:
    if not summary.exists():
        return [], []
    with summary.open(newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def write_summary(summary: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with summary.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def append_row(summary: Path, row: dict) -> None:
    """Append under the file's existing header; new columns are only added when the file is new."""
    fields, _ = read_summary(summary)
    if not fields:
        write_summary(summary, list(row), [row])
        return
    with summary.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow({k: row.get(k, "") for k in fields})


def merged_fields(existing: list[str], row: dict) -> list[str]:
    return existing + [k for k in row if k not in existing]


def run_sweep(
    config_path: Path,
    design_path: Path,
    plan_path: Path,
    output: Path,
    backend_name: str,
    base_overrides: list[str],
    dry_run: bool = False,
    reuse: bool = True,
    reprocess: bool = False,
) -> int:
    plan = tomllib.load(plan_path.open("rb"))
    cases = plan.get("case", [])
    base_design = json.loads(design_path.read_text())
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = output / "sweep_summary.csv"
    fields, rows = read_summary(summary)
    done = {r["case"] for r in rows}
    print(f"{len(cases)} cases, {len(done)} already in {summary.name}" + (" (reprocessing)" if reprocess else ""))
    if backend_name == "openems" and not dry_run:
        try:
            import CSXCAD  # noqa: F401
            import h5py  # noqa: F401
            import openEMS  # noqa: F401
        except ImportError as exc:
            print(
                f"openEMS backend unavailable in this environment ({exc.name}). Install the bindings into this venv:\n"
                "  uv sync --extra simulation\n"
                "  CSXCAD_INSTALL_PATH=<openEMS install> OPENEMS_INSTALL_PATH=<openEMS install> "
                "uv pip install <openEMS-Project>/CSXCAD/python <openEMS-Project>/openEMS/python\n"
                "then use `uv run` or `uv sync --inexact`; a plain `uv sync` removes them again (HANDOFF §7)."
            )
            return 2
    failures: list[tuple[str, str]] = []
    for i, case in enumerate(cases, start=1):
        name = str(case["name"])
        overrides = base_overrides + [str(x) for x in case.get("set", [])]
        params_over = {k: float(v) for k, v in case.get("params", {}).items()}
        tag = f"[{i}/{len(cases)}] {name}"
        if name in done and not reprocess:
            print(f"{tag}: done, skipping")
            continue
        if dry_run:
            print(f"{tag}: set={overrides} params={params_over}")
            continue
        try:
            config = load_config(config_path, overrides)
        except ValueError as exc:
            print(f"{tag}: SKIPPED – {exc}", flush=True)
            failures.append((name, str(exc)))
            continue
        topo = get_topology(config)
        params = full_params({**base_design, **params_over}, config)
        if not topo.valid(params, config):
            print(f"{tag}: WARNING design violates constraints, running anyway")
        case_dir = output / name
        case_dir.mkdir(exist_ok=True)
        has_fields = (case_dir / "simulation_port1" / "port_ut_1").exists()
        if reprocess and not has_fields and backend_name != "cavity":
            print(f"{tag}: no field data to reprocess, skipping")
            continue
        (case_dir / "parameters.json").write_text(json.dumps(params, indent=2) + "\n")
        (case_dir / "overrides.json").write_text(json.dumps(overrides, indent=2) + "\n")
        model = topo.model(params, config)
        problems = check_model(model)
        if problems:
            print(f"{tag}: SKIPPED – {'; '.join(problems)}")
            continue
        write_geometry_vtp(case_dir / "geometry.vtp", model)
        t0 = time.time()
        print(f"{tag}: {'reprocessing' if reprocess else 'running'} ({backend_name}) ...", flush=True)
        try:
            if backend_name == "cavity":
                from .cavity import CavityBackend

                metrics = CavityBackend().evaluate(params, config, case_dir)
                diag = {}
            else:
                from .openems_backend import OpenEMSBackend

                metrics = OpenEMSBackend().evaluate(params, config, case_dir, reuse=(reuse or reprocess) and has_fields)
                diag = json.loads((case_dir / "openems_diagnostics.json").read_text())
        except Exception as exc:  # one bad case must not end an unattended sweep
            import traceback

            print(f"{tag}: FAILED after {time.time() - t0:.0f} s – {exc}", flush=True)
            (case_dir / "error.txt").write_text(traceback.format_exc())
            failures.append((name, str(exc)))
            continue
        (case_dir / "error.txt").unlink(missing_ok=True)
        s = score(metrics, config)
        (case_dir / "result.json").write_text(
            json.dumps({"score": s, "backend": backend_name, "metrics": metrics.as_dict()}, indent=2) + "\n"
        )
        seconds = time.time() - t0
        if reprocess and name in done:
            old = next(r for r in rows if r["case"] == name)
            seconds = float(old.get("seconds") or seconds)  # keep the FDTD time, not the reprocessing time
        row = _row(name, params, metrics, s, diag, seconds, config)
        if reprocess:
            rows = [r for r in rows if r["case"] != name] + [row]
            fields = merged_fields(fields, row)
            write_summary(summary, fields, rows)  # rewritten after every case: a crash loses nothing
        else:
            append_row(summary, row)
        done.add(name)
        pm = metrics.bands[config.primary_band.name]
        w = (diag.get("pattern") or {}).get("worst") or {}
        extra = (
            f", G60 {w['gain_co_min_60']:.1f} dBic, AR60 {w['ar_max_60']:.1f} dB, F/B {w['front_to_back_db']:.0f} dB"
            if w
            else ""
        )
        print(
            f"{tag}: f_res {metrics.resonance_hz / 1e9:.4f} GHz  {config.primary_band.name}: S11 {pm.s11_worst_db:.1f} "
            f"dB, "
            f"G {pm.gain_min_dbic:.1f} dBic, AR {pm.ar_worst_db:.1f} dB, {pm.hand}{extra}  ({time.time() - t0:.0f} s)",
            flush=True,
        )
    if failures:
        print(f"{len(failures)} case(s) failed: " + ", ".join(n for n, _ in failures))
        return 1
    return 0
