"""`bac-antenna pack design/sensitivity.toml` – build a sensitivity pack for the antenna visualizer.

The axes file defines the sliders: which parameter each one moves (design parameters via `params`, config keys via
`set`), the levels, and where to look for runs. For every level the pack takes the case whose parameters and
config equal the nominal case in every other respect (so runs from any sweep on the same stack qualify, and runs on
another stack are excluded on their own), writes a plan file for the levels that have no run yet, and packs the
small result files of the matched cases into gzipped CSV + JSON – a few MB, readable by pandas anywhere. `--zip`
also writes `<name>-pack.zip` beside the folder, the form to attach to the antenna's release; the visualizer reads
either.

    [sensitivity]
    name = "s-band-cross-patch-2200"
    config = "design/2200.toml"
    design = "design/2200.json"
    nominal = "sim/runs/ref-2200"
    runs = ["sim/runs/freeze", "sim/runs/through_pin", "sim/runs/sensitivity"]
    plan = "design/plans/sensitivity.toml"
    output = "generated/sensitivity"
    source = "https://codeberg.org/buildacubesat-project/bac-hardware"   # provenance shown by the visualizer (optional)
    release = "s-band-cross-patch-v1"                                   # the release the pack zip is attached to (optional)

    ignore = ["geometry.stack.max_height_mm"]   # config keys a case may change without becoming a different antenna

    [[axis]]
    id = "gap"
    label = "Air gap"
    unit = "mm"
    set = "geometry.stack.gap_mm"          # or params = ["arm_x_mm", "arm_y_mm"]
    levels = [4.07, 4.37, 4.67, 4.97, 5.27]
    also = ["geometry.stack.max_height_mm=7.0"]  # extra overrides every run of this axis needs

Pack layout (all paths relative to `output`):
    pack.json       axes, levels -> case ids, nominal, bands and targets, provenance
    cases.csv.gz    one row per case: axis, level, parameters, axis values, band metrics, diagnostics summary
    sweeps.csv.gz   case x frequency: network-input S11 (dB, re, im), per-port S11/S22/S21 (dB)
    samples.csv.gz  case x sample frequency: broadside gain, AR, efficiency
    cuts.csv.gz     case x frequency x phi x theta (pattern cuts)
    sphere.csv.gz   case x theta x phi at band centre
    efield.csv.gz   case x plane x (u, v): |E| in dB on each dumped plane, resampled to `efield_grid_mm` (default 2 mm)
    models.json     geometry primitives per case, for the 3D view without any solver code
    config.toml, design.json   the nominal antenna, so a notebook with the tool installed can rebuild the model live
"""
from __future__ import annotations

import csv
import datetime
import gzip
import json
import math
from pathlib import Path
import tomllib

from .antennas import get_antenna
from .config import load_config
from .core import full_params

TOL = 1e-6
CASE_FILES = ("result.json", "openems_diagnostics.json", "s11_sweep.csv", "sparams.csv", "sparams_complex.csv",
              "farfield_samples.csv", "farfield_cuts.csv", "farfield_sphere.csv")


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = v
    return out


def _resolve_key(raw: dict, dotted: str):
    node = raw
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def effective_state(config_path: Path, design: dict, overrides: list[str]) -> dict:
    """Everything that defines a case: design parameters plus the flattened config (with the case's overrides)."""
    config = load_config(config_path, overrides)
    state = {f"param:{k}": float(v) for k, v in full_params(design, config).items()}
    for k, v in _flatten(config.raw).items():
        if not isinstance(v, (list, dict)):
            state[f"cfg:{k}"] = v
    return state, config


def _same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= TOL * max(1.0, abs(float(a)), abs(float(b)))
    return a == b


def axis_keys(axis: dict) -> list[str]:
    if "params" in axis:
        return [f"param:{p}" for p in axis["params"]]
    return [f"cfg:{axis['set']}"]


def state_matches(state: dict, nominal: dict, axis: dict, level: float, ignore: set[str] = frozenset()) -> bool:
    keys = set(axis_keys(axis))
    for k, v in nominal.items():
        if k in ignore:
            continue
        if k in keys:
            if not _same(state.get(k), level):
                return False
        elif not _same(state.get(k), v):
            return False
    return True


def axis_value(state: dict, axis: dict):
    return state.get(axis_keys(axis)[0])


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _write_gz(path: Path, rows: list[dict], columns: list[str]) -> None:
    with gzip.open(path, "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _serial_model(model) -> list[dict]:
    out = []
    for p in model.primitives:
        d = {"kind": p.kind, "prop": p.prop, "material": p.material, "priority": p.priority}
        if p.kind in ("box", "cylinder"):
            d.update(start=list(p.start), stop=list(p.stop))
            if p.kind == "cylinder":
                d["radius"] = p.radius
        else:
            d.update(points=[list(q) for q in p.points], elevation=p.elevation, length=p.length)
        if p.material != "metal":
            d["epsilon_r"] = p.epsilon_r
        out.append(d)
    return out


def efield_planes(case_dir: Path, diag: dict, cid: str, grid_mm: float) -> list[dict]:
    """|E| of the combined excitation on each dumped plane, resampled to a `grid_mm` grid, in dB relative to the
    plane's maximum. Needs h5py and the per-port dumps; returns [] without them. Columns: plane, axes (e.g. "xy"),
    fixed axis and its coordinate, u, v (mm), e_db."""
    info = diag.get("efield_dump")
    if not info:
        return []
    try:
        import h5py  # noqa: F401
        import numpy as np
        from scipy.interpolate import RegularGridInterpolator

        from .report.charts import read_fd_dump
    except ImportError:
        return []
    weights = [complex(a, b) for a, b in info["weights"]]
    rows = []
    for fname in info["files"]:
        fields, mesh = [], None
        for k, pdir in enumerate(info["port_dirs"]):
            path = case_dir / pdir / fname
            if not path.exists():
                fields = []
                break
            E, mesh = read_fd_dump(path)
            fields.append(weights[k] * E)
        if not fields:
            continue
        mag = np.sqrt(np.sum(np.abs(sum(fields)) ** 2, axis=0))
        axes = {"x": mesh["x"], "y": mesh["y"], "z": mesh["z"]}
        fixed = next((ax for ax in "xyz" if mag.shape["xyz".index(ax)] == 1), None)
        if fixed is None:
            continue
        free = [ax for ax in "xyz" if ax != fixed]
        plane = np.squeeze(mag, axis="xyz".index(fixed))                 # (n_free0, n_free1)
        g0, g1 = axes[free[0]], axes[free[1]]
        u = np.arange(g0[0], g0[-1] + 1e-9, grid_mm); v = np.arange(g1[0], g1[-1] + 1e-9, grid_mm)
        f = RegularGridInterpolator((g0, g1), plane, bounds_error=False, fill_value=0.0)
        U, V = np.meshgrid(u, v, indexing="ij")
        val = f(np.stack([U.ravel(), V.ravel()], axis=1)).reshape(U.shape)
        db = 20 * np.log10(np.maximum(val, 1e-12) / max(float(np.max(val)), 1e-12))
        coord = float(axes[fixed][0])
        name = fname[:-3]
        for i in range(len(u)):
            for j in range(len(v)):
                rows.append({"case": cid, "plane": name, "axes": "".join(free), "fixed": fixed, "coord": coord,
                             "u": f"{u[i]:.2f}", "v": f"{v[j]:.2f}", "e_db": f"{db[i, j]:.1f}"})
    return rows


def _tool_version() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:
        return ""


def build_pack(sens_path: Path, public: Path | None = None, make_zip: bool = False) -> int:
    sens_path = Path(sens_path).resolve()
    root = sens_path.parent.parent if sens_path.parent.name == "design" else sens_path.parent
    spec = tomllib.loads(sens_path.read_text())
    s = spec["sensitivity"]
    axes = spec.get("axis", [])
    config_path = root / s["config"]
    design = json.loads((root / s["design"]).read_text())
    nominal_dir = root / s["nominal"]
    if not (nominal_dir / "result.json").exists():
        print(f"nominal case {s['nominal']} has no result.json")
        return 1
    nom_over = json.loads((nominal_dir / "overrides.json").read_text()) if (nominal_dir / "overrides.json").exists() else []
    nom_design = json.loads((nominal_dir / "parameters.json").read_text()) if (nominal_dir / "parameters.json").exists() else design
    nominal, config = effective_state(config_path, nom_design, nom_over)
    antenna = get_antenna(config)

    # every candidate case with its effective state
    candidates = {}
    for run_dir in [nominal_dir.parent, *(root / r for r in s.get("runs", []))]:
        if not run_dir.is_dir():
            continue
        for case in sorted(p for p in run_dir.iterdir() if p.is_dir() and (p / "result.json").exists()):
            over = json.loads((case / "overrides.json").read_text()) if (case / "overrides.json").exists() else []
            des = json.loads((case / "parameters.json").read_text()) if (case / "parameters.json").exists() else design
            try:
                state, _ = effective_state(config_path, des, over)
            except Exception as exc:                        # a case from a config this tool no longer accepts
                print(f"  skipping {case}: {exc}")
                continue
            candidates[case] = (state, des, over)

    ignore = {f"cfg:{k}" for k in s.get("ignore", [])}     # config keys that may differ without making a case foreign
    matched: dict[str, dict] = {}                          # case id -> record
    missing_plan: list[dict] = []
    axes_out = []
    nominal_id = "nominal"
    matched[nominal_id] = {"dir": nominal_dir, "axis": "", "level": axis_value(nominal, axes[0]) if axes else None, "design": nom_design, "overrides": nom_over}
    for axis in axes:
        levels_out = []
        for level in axis["levels"]:
            level = float(level)
            if state_matches(nominal, nominal, axis, level, ignore):
                levels_out.append({"level": level, "case": nominal_id})
                continue
            hit = next((c for c, (st, _, _) in candidates.items() if state_matches(st, nominal, axis, level, ignore)), None)
            if hit is None:
                levels_out.append({"level": level, "case": None})
                entry = {"name": f"{axis['id']}_{level:g}", "set": list(axis.get("also", []))}
                if "params" in axis:
                    entry["params"] = {p: level for p in axis["params"]}
                else:
                    entry["set"].append(f"{axis['set']}={level:g}")
                missing_plan.append(entry)
            else:
                cid = f"{axis['id']}_{level:g}"
                matched[cid] = {"dir": hit, "axis": axis["id"], "level": level, "design": candidates[hit][1], "overrides": candidates[hit][2]}
                levels_out.append({"level": level, "case": cid})
        axes_out.append({"id": axis["id"], "label": axis.get("label", axis["id"]), "unit": axis.get("unit", ""),
                         "params": axis.get("params"), "set": axis.get("set"), "levels": levels_out,
                         "nominal": axis_value(nominal, axis), "missing": [x["level"] for x in levels_out if x["case"] is None]})

    # plan for the missing levels
    if missing_plan:
        plan_path = root / s.get("plan", "design/plans/sensitivity.toml")
        lines = [f"# Sensitivity cases missing from the pack, written by `bac-antenna pack` on {datetime.date.today().isoformat()}.",
                 f"# Run:  uv run bac-antenna sweep -c $ANT/{s['config']} -p $ANT/{s['design']} --plan $ANT/{s.get('plan', 'design/plans/sensitivity.toml')} --output runs/sensitivity",
                 "# then copy runs/sensitivity into sim/runs/ and rerun `bac-antenna pack`.", ""]
        for e in missing_plan:
            lines.append("[[case]]")
            lines.append(f'name = "{e["name"]}"')
            if e["set"]:
                lines.append("set = [" + ", ".join(f'"{x}"' for x in e["set"]) + "]")
            if "params" in e:
                lines.append("params = { " + ", ".join(f"{k} = {v:g}" for k, v in e["params"].items()) + " }")
            lines.append("")
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text("\n".join(lines))
        print(f"{len(missing_plan)} case(s) without a run – plan written to {plan_path.relative_to(root)}")

    # pack files
    out = root / s.get("output", "generated/sensitivity")
    out.mkdir(parents=True, exist_ok=True)
    band_meta = [{"name": b.name, "low_hz": b.low_hz, "high_hz": b.high_hz, "weight": b.weight, "max_s11_db": b.max_s11_db,
                  "min_gain_dbic": b.min_gain_dbic, "max_ar_db": b.max_ar_db} for b in config.bands]
    cases_rows, sweeps_rows, samples_rows, cuts_rows, sphere_rows, efield_rows, models = [], [], [], [], [], [], {}
    for cid, rec in matched.items():
        d = rec["dir"]
        res = json.loads((d / "result.json").read_text())
        diag = json.loads((d / "openems_diagnostics.json").read_text()) if (d / "openems_diagnostics.json").exists() else {}
        state, cfg_case = effective_state(config_path, rec["design"], rec["overrides"])
        row = {"case": cid, "axis": rec["axis"], "level": rec["level"], "run": str(d.relative_to(root)) if d.is_relative_to(root) else str(d),
               "files": ",".join(f for f in CASE_FILES if (d / f).exists())}
        for k, v in full_params(rec["design"], cfg_case).items():
            row[k] = v
        for ax in axes:
            row[f"axis:{ax['id']}"] = axis_value(state, ax)
        for bname, m in res["metrics"]["bands"].items():
            for k, v in m.items():
                row[f"{bname}_{k}"] = v
        row["resonance_hz"] = res["metrics"].get("resonance_hz")
        row["probe_res_hz"] = diag.get("probe_resonance_hz")
        row["load_fraction"] = diag.get("hybrid_load_fraction_at_primary_centre")
        w = (diag.get("pattern") or {}).get("worst") or {}
        for k in ("gain_co_min_45", "gain_co_min_60", "ar_max_45", "ar_max_60", "front_to_back_db", "back_fraction", "gain_co_broadside"):
            row[k] = w.get(k)
        cases_rows.append(row)
        # frequency tables
        sw = {float(r["frequency_hz"]): r for r in read_csv(d / "s11_sweep.csv")} if (d / "s11_sweep.csv").exists() else {}
        sp = {float(r["frequency_hz"]): r for r in read_csv(d / "sparams.csv")} if (d / "sparams.csv").exists() else {}
        sc = {float(r["frequency_hz"]): r for r in read_csv(d / "sparams_complex.csv")} if (d / "sparams_complex.csv").exists() else {}
        for f in sorted(set(sw) | set(sp) | set(sc)):
            r = {"case": cid, "frequency_hz": f}
            if f in sw:
                r.update(s11_in_db=sw[f].get("s11_db"), s11_in_re=sw[f].get("s11_real"), s11_in_im=sw[f].get("s11_imag"))
            if f in sp:
                r.update({k: sp[f].get(k) for k in ("s11_db", "s22_db", "s21_db", "s12_db") if k in sp[f]})
            if f in sc:
                r.update(s11_re=sc[f].get("s11_re"), s11_im=sc[f].get("s11_im"))
                if "s21_re" in sc[f]:
                    r.update(s21_re=sc[f].get("s21_re"), s21_im=sc[f].get("s21_im"))
            sweeps_rows.append(r)
        efield_rows.extend(efield_planes(d, diag, cid, float(s.get("efield_grid_mm", 2.0))))
        if (d / "farfield_samples.csv").exists():
            for r in read_csv(d / "farfield_samples.csv"):
                samples_rows.append({"case": cid, **r})
        if (d / "farfield_cuts.csv").exists():
            for r in read_csv(d / "farfield_cuts.csv"):
                cuts_rows.append({"case": cid, **r})
        if (d / "farfield_sphere.csv").exists():
            for r in read_csv(d / "farfield_sphere.csv"):
                sphere_rows.append({"case": cid, **r})
        models[cid] = _serial_model(antenna.model(full_params(rec["design"], cfg_case), cfg_case))

    def cols(rows):
        seen = []
        for r in rows:
            for k in r:
                if k not in seen:
                    seen.append(k)
        return seen

    _write_gz(out / "cases.csv.gz", cases_rows, cols(cases_rows))
    _write_gz(out / "sweeps.csv.gz", sweeps_rows, cols(sweeps_rows) or ["case", "frequency_hz"])
    _write_gz(out / "samples.csv.gz", samples_rows, cols(samples_rows) or ["case", "frequency_hz"])
    _write_gz(out / "cuts.csv.gz", cuts_rows, cols(cuts_rows) or ["case", "frequency_hz", "phi_deg", "theta_deg"])
    _write_gz(out / "sphere.csv.gz", sphere_rows, cols(sphere_rows) or ["case", "theta_deg", "phi_deg"])
    _write_gz(out / "efield.csv.gz", efield_rows, cols(efield_rows) or ["case", "plane", "u", "v", "e_db"])
    (out / "models.json").write_text(json.dumps(models, separators=(",", ":")))
    (out / "config.toml").write_text(config_path.read_text())
    (out / "design.json").write_text(json.dumps(nom_design, indent=2) + "\n")
    pack = {"name": s.get("name", out.parent.parent.name), "antenna_type": config.antenna_type, "generated": datetime.date.today().isoformat(),
            "tool": "bac-antenna-optimizer", "tool_version": _tool_version(), "config": s["config"], "design": s["design"], "nominal_case": nominal_id,
            "nominal_run": s["nominal"], "bands": band_meta, "primary_band": config.primary_band.name,
            "parameters": sorted(full_params(nom_design, config)), "axes": axes_out,
            "cases": {cid: {"run": r["run"], "axis": r["axis"], "level": r["level"]} for cid, r in zip(matched, cases_rows)},
            "notes": [n for n in [s.get("notes")] if n],
            "source": s.get("source", ""), "release": s.get("release", "")}
    (out / "pack.json").write_text(json.dumps(pack, indent=1))
    n_missing = sum(len(a["missing"]) for a in axes_out)
    print(f"pack {pack['name']}: {len(matched)} cases, {len(axes_out)} axes, {n_missing} level(s) missing -> {out.relative_to(root)}")
    for a in axes_out:
        have = [f"{x['level']:g}" for x in a["levels"] if x["case"]]
        miss = [f"{x:g}" for x in a["missing"]]
        print(f"  {a['id']:8s} have {', '.join(have) or '-'}" + (f"   missing {', '.join(miss)}" if miss else ""))
    if make_zip:
        import zipfile
        zpath = out.parent / f"{pack['name']}-pack.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(out.iterdir()):
                if f.is_file():
                    z.write(f, f"{pack['name']}/{f.name}")
        print(f"zip written: {zpath.relative_to(root)} ({zpath.stat().st_size / 1e6:.1f} MB) – attach it to the antenna's release")
    if public:
        import shutil
        dest = Path(public) / pack["name"]
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(out, dest)
        print(f"copied to {dest}")
    return 0
