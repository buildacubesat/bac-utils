from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
import signal
import sys

from . import __version__
from .config import load_config
from .core import MockBackend, optimise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bac-antenna", description="Optimise a camera-through S-band patch antenna")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-l", "--list", action="store_true", help="list ranked candidates in an existing output directory")
    parser.add_argument("--output", type=Path, default=None, help="output directory")
    sub = parser.add_subparsers(dest="command")
    opt = sub.add_parser("optimize", help="run the adaptive optimiser")
    opt.add_argument("-c", "--config", type=Path, required=True)
    opt.add_argument("--backend", choices=("mock", "cavity", "coarse", "openems"), default="cavity")
    opt.add_argument("--runs", type=int)
    opt.add_argument("--output", dest="command_output", type=Path)
    opt.add_argument("--set", dest="overrides", action="append", default=[], metavar="SECTION.KEY=VALUE",
                     help="override a config value, e.g. --set feed.mode='\"dual\"' (repeatable)")
    sim = sub.add_parser("simulate", help="evaluate one design (a parameters.json) with one backend")
    sim.add_argument("-c", "--config", type=Path, required=True)
    sim.add_argument("-p", "--params", type=Path, required=True, help="JSON file with the topology parameters")
    sim.add_argument("--backend", choices=("cavity", "coarse", "openems"), default="openems")
    sim.add_argument("--geometry-only", action="store_true", help="openems: write geometry.xml and the mesh, skip the FDTD run")
    sim.add_argument("--reuse", action="store_true", help="openems: reprocess existing simulation data in --output")
    sim.add_argument("--output", dest="command_output", type=Path)
    sim.add_argument("--set", dest="overrides", action="append", default=[], metavar="SECTION.KEY=VALUE")
    sw = sub.add_parser("sweep", help="run every case of a plan file (resumable); see plans/")
    sw.add_argument("-c", "--config", type=Path, required=True)
    sw.add_argument("-p", "--params", type=Path, required=True, help="base design JSON")
    sw.add_argument("--plan", type=Path, required=True)
    sw.add_argument("--backend", choices=("cavity", "coarse", "openems"), default="openems")
    sw.add_argument("--dry-run", action="store_true")
    sw.add_argument("--reprocess", action="store_true",
                    help="openems: re-evaluate every case from its existing field data (no FDTD) and replace its summary row")
    sw.add_argument("--output", dest="command_output", type=Path)
    sw.add_argument("--set", dest="overrides", action="append", default=[], metavar="SECTION.KEY=VALUE")
    chk = sub.add_parser("check", help="tune a nominal design with the cavity model and print its mode spectrum")
    chk.add_argument("-c", "--config", type=Path, required=True)
    chk.add_argument("--set", dest="overrides", action="append", default=[], metavar="SECTION.KEY=VALUE")
    mg = sub.add_parser("migrate", help="rewrite 0.5 configs and plans to the 0.6 layout ([antenna] type, [geometry.*], geometry.* overrides)")
    mg.add_argument("paths", nargs="+", type=Path, help="config .toml files and/or plan .toml files (plans are detected by their [[case]] tables)")
    pk = sub.add_parser("pack", help="build a sensitivity pack for the antenna visualizer from design/sensitivity.toml")
    pk.add_argument("axes", type=Path, help="the sensitivity TOML (axes, nominal case, run directories)")
    pk.add_argument("--zip", action="store_true", help="also write <name>-pack.zip beside the pack folder (for the antenna's release)")
    pk.add_argument("--public", type=Path, help="also copy the pack folder into this directory")
    rp = sub.add_parser("report", help="regenerate an antenna folder (drawings, charts, boards, docs) from its antenna.toml")
    rp.add_argument("manifest", type=Path)
    rp.add_argument("--skip", default="", help="comma-separated: drawings,charts,boards,docs")
    rp.add_argument("--allow-missing", action="store_true", help="regenerate documents even when a band's reference run is absent")
    return parser


def _list_results(output: Path) -> int:
    summary = output / "summary.csv"
    if not summary.exists():
        print(f"No summary found at {summary}", file=sys.stderr)
        return 2
    with summary.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    bands = sorted({k.rsplit("_s11_worst_db", 1)[0] for k in rows[0] if k.endswith("_s11_worst_db")}) if rows else []
    print("rank cand    score  f_res_GHz  " + "  ".join(f"{b}: S11 / G / AR / hand" for b in bands))
    for row in rows[:20]:
        cells = "  ".join(f"{float(row[b + '_s11_worst_db']):6.1f} {float(row[b + '_gain_min_dbic']):5.1f} "
                          f"{float(row[b + '_ar_worst_db']):5.1f} {row[b + '_hand']:>5s}" for b in bands)
        print(f"{int(row['rank']):4d} {int(row['index']):4d} {float(row['score']):8.3f} {float(row['resonance_hz']) / 1e9:10.4f}  {cells}")
    return 0


def _check(config_path: Path, overrides: list[str]) -> int:
    from scipy.optimize import brentq

    from .cavity import C0, Cavity, bore_isolation_db_per_mm, eps_eff
    from .topologies import get_topology

    config = load_config(config_path, overrides)
    topo = get_topology(config)
    if not topo.has_estimator():
        print(f"{topo.name}: no cavity model for this antenna type. Use `simulate --backend coarse` for a fast estimate.")
        return 1
    band = config.primary_band
    s, o = config.stack, config.outline
    print(f"{config.project.get('name', config.antenna_type)}  [{topo.name}, feed {config.feed['mode']}]")
    print(f"  stack {config.stack_height_mm():.2f} mm (limit {s.get('max_height_mm', '–')}), patch height {config.patch_height_mm():.2f} mm, "
          f"eps_eq {config.epsilon_eq():.3f}, tan_d_eq {config.loss_tangent_eq():.4f}")
    bore = float(o["bore_diameter_mm"])
    att = bore_isolation_db_per_mm(bore, band.centre_hz)
    print(f"  bore {bore:.1f} mm: {att:.2f} dB/mm below TE11 cutoff -> {att * float(o['sleeve_length_mm']):.0f} dB over the "
          f"{float(o['sleeve_length_mm']):.0f} mm sleeve; {'shorted to the patch' if o['bore_short'] else 'open hole in the patch'}")

    mid = {n: (r.low + r.high) / 2 for n, r in config.search.items()}
    if "arm_width_mm" in mid:
        mid["arm_width_mm"] = config.search["arm_width_mm"].high      # widest arms: lowest Q, shortest resonant arms
    mid.update(config.fixed)
    tune = ("arm_x_mm", "arm_y_mm") if topo.name == "cross_patch" else ("outer_radius_mm",)
    lo, hi = config.search[tune[0]].low, config.search[tune[0]].high

    def broadside_f(x: float) -> float:
        p = dict(mid, **{t: x for t in tune})
        cav = Cavity.build(topo.shape(p, config), config, grid_mm=0.5)
        table = cav.mode_table(2 * math.pi * band.centre_hz / C0)
        return next(m["f_hz"] for m in table if m["kind"].startswith("broadside"))

    try:
        x = brentq(lambda v: broadside_f(v) - band.centre_hz, lo, hi, xtol=0.05)
    except ValueError:
        print(f"  WARNING: no {'/'.join(tune)} within [{lo}, {hi}] puts the broadside mode at {band.centre_hz / 1e9:.3f} GHz")
        return 1
    p = dict(mid, **{t: x for t in tune})
    cav = Cavity.build(topo.shape(p, config), config).with_pad(p.get("pad_radius_mm", 2.0), config)
    print(f"  nominal: {', '.join(f'{k}={v:.2f}' for k, v in sorted(p.items()))}")
    print(f"  edge extension {cav.extension_mm:.2f} mm, eps_eff {cav.ee:.3f}; valid in search space: {topo.valid(p, config)}")
    print("  cavity modes:")
    for m in cav.mode_table(2 * math.pi * band.centre_hz / C0)[:7]:
        if m["f_hz"] > 1e6:
            q = m["q_rad"]
            bw = f"~{100 / (math.sqrt(2) * q):.1f} % VSWR-2 BW" if m["kind"].startswith("broadside") and math.isfinite(q) else ""
            print(f"    {m['f_hz'] / 1e9:6.3f} GHz  Q_rad {q:6.1f}  {m['kind']:32s} {bw}")
    for b in config.bands:
        print(f"  band {b.name:6s} {b.low_hz / 1e9:.3f}–{b.high_hz / 1e9:.3f} GHz ({100 * (b.high_hz - b.low_hz) / b.centre_hz:.1f} %), weight {b.weight}")
    return 0


def _simulate(args, output: Path) -> int:
    import json

    from .cavity import CavityBackend
    from .core import full_params, score
    from .geometry import check_model
    from .topologies import get_topology
    from .vtk import write_geometry_vtp

    config = load_config(args.config, args.overrides)
    topo = get_topology(config)
    params = full_params(json.loads(args.params.read_text()), config)
    missing = set(topo.params) - set(params)
    if missing:
        print(f"{args.params} lacks: {', '.join(sorted(missing))}", file=sys.stderr)
        return 2
    if not topo.valid(params, config):
        print("warning: design violates the configured constraints", file=sys.stderr)
    output.mkdir(parents=True, exist_ok=True)
    (output / "parameters.json").write_text(json.dumps(params, indent=2) + "\n")
    model = topo.model(params, config)
    problems = check_model(model)
    if problems:
        print("; ".join(problems), file=sys.stderr)
        return 2
    write_geometry_vtp(output / "geometry.vtp", model)
    reference = CavityBackend().evaluate(params, config, output) if topo.has_estimator() else None
    if args.backend == "cavity":
        if reference is None:
            print(f"{topo.name}: no cavity model for this antenna type; use --backend coarse or openems")
            return 1
        metrics = reference
    else:
        from .openems_backend import CoarseBackend, OpenEMSBackend

        backend = CoarseBackend() if args.backend == "coarse" else OpenEMSBackend()
        metrics = backend.evaluate(params, config, output, geometry_only=args.geometry_only, reuse=args.reuse)
        if metrics is None:
            print(f"geometry written: {output / 'geometry.xml'}  (inspect with AppCSXCAD)")
            return 0
    result = {"score": score(metrics, config), "backend": args.backend, "metrics": metrics.as_dict(),
              "cavity_reference": reference.as_dict() if reference else None}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"{'band':8s} {'':10s} {'S11 worst':>10s} {'G min dBic':>11s} {'AR worst':>9s} {'eff %':>6s}  hand")
    for b in config.bands:
        for label, m in [(args.backend, metrics)] + ([("cavity", reference)] if reference else []):
            bm = m.bands[b.name]
            print(f"{b.name:8s} {label:10s} {bm.s11_worst_db:10.1f} {bm.gain_min_dbic:11.1f} {bm.ar_worst_db:9.1f} "
                  f"{bm.efficiency_percent:6.1f}  {bm.hand}")
    print(f"S11 minimum: {args.backend} {metrics.resonance_hz / 1e9:.4f} GHz" + (f", cavity {reference.resonance_hz / 1e9:.4f} GHz" if reference else ""))
    diag_path = output / "openems_diagnostics.json"
    if args.backend == "openems" and diag_path.exists():
        diag = json.loads(diag_path.read_text())
        if "probe_resonance_hz" in diag:
            print(f"per-probe S11 minimum: {diag['probe_resonance_hz'] / 1e9:.4f} GHz"
                  + (f", hybrid load fraction {100 * diag['hybrid_load_fraction_at_primary_centre']:.1f} %"
                     if "hybrid_load_fraction_at_primary_centre" in diag else ""))
        w = (diag.get("pattern") or {}).get("worst")
        if w:
            print(f"pattern (worst over {config.primary_band.name} band and planes): G45 {w['gain_co_min_45']:.2f} dBic, "
                  f"AR45 {w['ar_max_45']:.2f} dB, G60 {w['gain_co_min_60']:.2f} dBic, AR60 {w['ar_max_60']:.2f} dB, "
                  f"F/B {w['front_to_back_db']:.1f} dB, rear hemisphere {100 * w['back_fraction']:.1f} %  -> farfield_cuts.csv")
    return 0


def main(argv: list[str] | None = None) -> int:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    args = _parser().parse_args(argv)
    output = (getattr(args, "command_output", None) or args.output or Path("runs")).resolve()
    if args.list:
        return _list_results(output)
    if args.command == "pack":
        from .pack import build_pack

        return build_pack(args.axes, args.public, make_zip=args.zip)
    if args.command == "migrate":
        from .migrate import migrate_files

        return migrate_files(args.paths)
    if args.command == "report":
        from .report.manifest import run_report

        return run_report(args.manifest, skip={x.strip() for x in args.skip.split(",") if x.strip()}, allow_missing=args.allow_missing)
    if args.command == "check":
        return _check(args.config, args.overrides)
    if args.command == "simulate":
        return _simulate(args, output)
    if args.command == "sweep":
        from .sweep import run_sweep

        return run_sweep(args.config, args.params, args.plan, output, args.backend, args.overrides, args.dry_run,
                         reprocess=args.reprocess)
    if args.command != "optimize":
        _parser().print_help()
        return 2
    config = load_config(args.config, args.overrides)
    if args.backend == "mock":
        backend = MockBackend()
    elif args.backend == "cavity":
        from .cavity import CavityBackend

        backend = CavityBackend()
    elif args.backend == "coarse":
        from .openems_backend import CoarseBackend

        backend = CoarseBackend()
    else:
        from .openems_backend import OpenEMSBackend

        backend = OpenEMSBackend()
    ranked = optimise(config, backend, output, args.runs)
    print(f"Best: candidate_{ranked[0].index:04d}, score={ranked[0].score:.4f}")
    return 0
