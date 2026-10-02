"""`bac-antenna report antenna.toml` – regenerate everything derived in an antenna folder.

The manifest names the bands (config + design + reference run), the output tree and the templates. For each band the
command draws the boards, writes the charts from the reference run, generates the KiCad files, collects the numbers,
and then renders the templates (README.md, docs/simulation.md) with `{{ key }}` placeholders. `generated/STATUS.md`
records what was produced and, for anything missing, the exact commands that produce it.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import re
import tomllib

import numpy as np

from ..pattern import read_cuts_csv, signed_cut
from ..antennas import get_antenna
from ..config import load_config
from .charts import make_charts

DASH = "—"


# --- templates ------------------------------------------------------------------------------
def resolve(context: dict, key: str):
    cur = context
    for part in key.strip().split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def render(template: str, context: dict, missing: list[str] | None = None) -> str:
    def sub(m):
        val = resolve(context, m.group(1))
        if val is None:
            if missing is not None:
                missing.append(m.group(1).strip())
            return DASH
        return str(val)
    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", sub, template)


# --- values ------------------------------------------------------------------------------------
def fmt(x, nd=1, unit=""):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return DASH
    return f"{x:.{nd}f}{unit}"


def pick_reference(root: Path, b: dict) -> str:
    """`reference_run` may be a path or a list of candidate paths; the first existing directory wins."""
    cands = b.get("reference_run", [])
    if isinstance(cands, str):
        cands = [cands]
    for c in cands:
        if (root / c).is_dir():
            return c
    return cands[0] if cands else ""


def band_values(root: Path, band_id: str, b: dict, options: dict | None = None) -> dict:
    """Generic per-band values (band, reference case, metrics) plus whatever the antenna type contributes."""
    options = options or {}
    b = dict(b, reference_run=pick_reference(root, b))
    config = load_config(root / b["config"])
    des = json.loads((root / b["design"]).read_text())
    primary = config.primary_band
    v = {
        "id": band_id, "label": b.get("label", band_id),
        "low_mhz": f"{primary.low_hz / 1e6:.0f}", "high_mhz": f"{primary.high_hz / 1e6:.0f}", "centre_mhz": f"{primary.centre_hz / 1e6:.0f}",
        "band_name": primary.name, "config": b["config"], "design": b["design"], "antenna_type": config.antenna_type,
        "ref_run": b.get("reference_run", ""), "ref_case": Path(b.get("reference_run", "")).name, "charts": f"generated/charts/{band_id}",
        "available": "no",
    }
    v.update({k: str(x) for k, x in des.items()})            # raw design parameters, e.g. {{ 2200.arm_x_mm }}
    v.update(get_antenna(config).report_values(config, des, options))
    ref = root / b["reference_run"] if b.get("reference_run") else None
    if not ref or not ref.is_dir():
        return v
    res = None
    if (ref / "result.json").exists():
        res = json.loads((ref / "result.json").read_text())
    elif (ref.parent / "sweep_summary.csv").exists():
        # a sweep case whose result.json was not copied: rebuild the band metrics from its summary row
        with (ref.parent / "sweep_summary.csv").open(newline="") as fh:
            rows = [r for r in csv.DictReader(fh) if r.get("case") == ref.name]
        if rows:
            r = rows[-1]
            names = sorted({k[:-4] for k in r if k.endswith("_s11") and not k.endswith("probe_s11")})
            res = {"metrics": {"bands": {n: {"s11_worst_db": float(r[f"{n}_s11"]), "gain_min_dbic": float(r[f"{n}_gain"]),
                                             "ar_worst_db": float(r[f"{n}_ar"]), "efficiency_percent": float(r[f"{n}_eff"]),
                                             "hand": r.get(f"{n}_hand", "")} for n in names if r.get(f"{n}_s11")}}}
    if res is None:
        return v
    diag = json.loads((ref / "openems_diagnostics.json").read_text()) if (ref / "openems_diagnostics.json").exists() else {}
    pb = res["metrics"]["bands"].get(primary.name, {})
    v.update({"available": "yes",
              "s11_worst": fmt(pb.get("s11_worst_db")), "gain_min": fmt(pb.get("gain_min_dbic"), 2), "ar_max": fmt(pb.get("ar_worst_db"), 2),
              "eff_pct": fmt(pb.get("efficiency_percent")), "hand": str(pb.get("hand", "")).upper()})
    if pb.get("efficiency_percent"):
        v["eff_db"] = fmt(10 * math.log10(pb["efficiency_percent"] / 100), 2)
    if pb.get("s11_worst_db") is not None:
        v["rl_min"] = fmt(-pb["s11_worst_db"])
    for name, other in res["metrics"]["bands"].items():
        if name != primary.name:
            v[f"other_{name}_gain"] = fmt(other.get("gain_min_dbic"))
    if "probe_resonance_hz" in diag:
        v["probe_res_ghz"] = f"{diag['probe_resonance_hz'] / 1e9:.4f}"
    if "hybrid_load_fraction_at_primary_centre" in diag:
        lf = diag["hybrid_load_fraction_at_primary_centre"]
        v["load_pct"] = fmt(100 * lf); v["load_db"] = fmt(-10 * math.log10(1 - lf), 2); v["load_mw_2w"] = f"{2000 * lf:.0f}"
    pp = diag.get("per_port_at_primary_centre", {})
    if "s11_db" in pp:
        v["probe_rl"] = fmt(-pp["s11_db"], 0)
    w = (diag.get("pattern") or {}).get("worst") or {}
    if w:
        v.update({"g45": fmt(w["gain_co_min_45"]), "g60": fmt(w["gain_co_min_60"]), "ar45": fmt(w["ar_max_45"]), "ar60": fmt(w["ar_max_60"]),
                  "fb": fmt(w["front_to_back_db"]), "back_pct": fmt(100 * w["back_fraction"], 0),
                  "gain_centre": fmt(w.get("gain_co_broadside"))})
    per = (diag.get("pattern") or {}).get("per_frequency") or {}
    if per:
        centre_key = sorted(per)[len(per) // 2]
        v["gain_centre"] = fmt(per[centre_key]["gain_co_broadside"])
    cuts = ref / "farfield_cuts.csv"
    if cuts.exists():
        c = read_cuts_csv(cuts)
        m = c["metrics"][1 if len(c["freqs"]) >= 3 else 0]
        g0 = float(np.mean(m["gain_co_dbic"][0]))
        bws, g30s = [], []
        for plane in (0.0, 45.0, 90.0, 135.0):
            xs, g = signed_cut(c["theta"], c["phi"], m["gain_co_dbic"], plane)
            inside = xs[g >= g0 - 3]
            bws.append(float(inside.max() - inside.min()))
            g30s += [float(np.interp(30.0, xs, g)), float(np.interp(-30.0, xs, g))]
        v["bw3"] = f"{min(bws):.0f}"; v["half_bw3"] = f"{min(bws) / 2:.0f}"; v["g30"] = fmt(min(g30s))
        ar_ok = 0.0
        for plane in (0.0, 45.0, 90.0, 135.0):
            xs, ar = signed_cut(c["theta"], c["phi"], m["ar_db"], plane)
            inner = xs[(np.abs(xs) <= 90) & (ar > 3)]
            lim = float(np.min(np.abs(inner))) if len(inner) else 90.0
            ar_ok = lim if ar_ok == 0.0 else min(ar_ok, lim)
        v["ar3_angle"] = f"{ar_ok:.0f}"
    return v


def global_values(root: Path, man: dict, bands: dict) -> dict:
    """Manifest facts plus the antenna type's shared values (from the first band's config)."""
    first = next(iter(bands.values()))
    config = load_config(root / man["bands"][first["id"]]["config"])
    a = man.get("antenna", {})
    options = man.get("boards", {})
    extra = {k: str(v) for k, v in a.items()}     # any [antenna] key is available to the templates
    out = {**extra,
           "name": a.get("name", "antenna"), "tool": a.get("tool", "bac-antenna-optimizer"), "tool_tag": a.get("tool_tag", ""),
           "tool_project": a.get("tool_project", "../bac-antenna-optimizer"), "date": a.get("date", ""),
           "antenna_type": config.antenna_type, "band_ids": ", ".join(bands), "n_bands": str(len(bands))}
    out.update(get_antenna(config).report_globals(config, options))
    return out


# --- pipeline ----------------------------------------------------------------------------------
def run_report(manifest_path: Path, skip: set[str] = frozenset(), allow_missing: bool = False) -> int:
    manifest_path = Path(manifest_path).resolve()
    root = manifest_path.parent
    man = tomllib.loads(manifest_path.read_text())
    out = root / man.get("output", {}).get("generated", "generated")
    out.mkdir(parents=True, exist_ok=True)
    boards_cfg = man.get("boards", {})
    status: list[str] = []
    missing_cmds: list[str] = []
    bands: dict[str, dict] = {}
    wanted_exporters = man.get("exporters")          # None = every exporter the antenna type offers
    for band_id, b in man["bands"].items():
        b = dict(b); b["id"] = band_id; b["reference_run"] = pick_reference(root, b)
        b["config_path"], b["design_path"] = root / b["config"], root / b["design"]
        bands[band_id] = b
    antenna = get_antenna(load_config(next(iter(bands.values()))["config_path"]))
    exporters = {k: v for k, v in antenna.exporters.items() if (wanted_exporters is None or k in wanted_exporters) and k not in skip}
    for band_id, b in bands.items():
        title = f"{b.get('label', band_id)} – {man.get('antenna', {}).get('date', '')}"
        ctx = {"root": root, "band": band_id, "config_path": b["config_path"], "design_path": b["design_path"], "out": out,
               "title": title, "options": boards_cfg, "bands": bands}
        for name, (scope, fn) in exporters.items():
            if scope == "band":
                files = fn(ctx)
                status.append(f"- {name}/{band_id}: {len(files)} files")
        ref = root / b["reference_run"] if b.get("reference_run") else None
        if "charts" not in skip:
            inputs = ("result.json", "openems_diagnostics.json", "farfield_cuts.csv", "s11_sweep.csv", "sparams.csv",
                      "sparams_complex.csv", "farfield_samples.csv", "farfield_sphere.csv")
            present = [n for n in inputs if ref and (ref / n).exists()] if ref else []
            if present:
                files = make_charts(ref, out / "charts" / band_id, label=b.get("label", band_id))
                status.append(f"- charts/{band_id} from `{b['reference_run']}`: " + ", ".join(files))
                absent = [n for n in inputs if n not in present]
                if absent:
                    status.append(f"  - case files missing, charts skipped accordingly: " + ", ".join(absent))
                if not any(f.startswith("efield") for f in files):
                    status.append(f"  - no E-field images: the run has no field dumps (`simulate --set dump.efield=true`)")
            else:
                status.append(f"- charts/{band_id}: reference run `{b.get('reference_run', '?')}` not found – charts and numbers missing")
            complete = present and all(n in present for n in ("result.json", "openems_diagnostics.json", "farfield_cuts.csv", "sparams_complex.csv"))
            if not complete or not any((ref / d / "E_gap.h5").exists() for d in ("simulation_port1",) if ref):
                missing_cmds.append(
                    f"uv run bac-antenna simulate -c $ANT/{b['config']} -p $ANT/{b['design']} --set dump.efield=true --output runs/ref-{band_id}"
                    f"   # copy to $ANT/sim/runs/ref-{band_id} and set reference_run = \"sim/runs/ref-{band_id}\" for band {band_id}")
    # A checkout without sim/runs (the runs are not tracked) must not overwrite documents that were generated
    # with them: that turns a complete datasheet into one full of dashes. Stop here unless told otherwise.
    unavailable = [bid for bid, b in bands.items()
                   if not (b.get("reference_run") and (root / b["reference_run"] / "result.json").exists())]
    if unavailable and not allow_missing:
        print(f"reference run(s) missing for band(s) {', '.join(unavailable)} – documents, values.json and boards left as they are.")
        print("Restore sim/runs from the release archive or the tool's runs/ folder, or pass --allow-missing to regenerate anyway.")
        return 1
    for name, (scope, fn) in exporters.items():
        if scope == "once":
            ctx = {"root": root, "out": out, "options": boards_cfg, "bands": bands, "title": man.get("antenna", {}).get("name", "")}
            files = fn(ctx)
            status.append(f"- {name}: " + ", ".join(files))
    # values and documents
    context = global_values(root, man, bands)
    for band_id, b in bands.items():
        context[band_id] = band_values(root, band_id, b, boards_cfg)
    context["generated"] = man.get("output", {}).get("generated", "generated")
    (out / "values.json").write_text(json.dumps(context, indent=2) + "\n")
    if "docs" not in skip:
        for entry in man.get("documents", []):
            tpl = root / entry["template"]
            target = root / entry["output"]
            unresolved: list[str] = []
            text = render(tpl.read_text(), context, unresolved)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            status.append(f"- {entry['output']} from {entry['template']}" + (f" ({len(set(unresolved))} placeholders unresolved: "
                          + ", ".join(sorted(set(unresolved))[:8]) + ("…" if len(set(unresolved)) > 8 else "") + ")" if unresolved else ""))
    # status note
    import datetime
    today = datetime.date.today().isoformat()
    lines = [f"# Generated {today} with {context['tool']} {context['tool_tag']} (design date {man.get('antenna', {}).get('date', '?')})", "",
             "Everything in this tree is produced by `bac-antenna report antenna.toml`; edit `design/`, `templates/` or `sim/runs/` and rerun.", "",
             "## What was produced", *status, ""]
    if missing_cmds:
        lines += ["## Missing – run on the simulation machine, from the tool checkout, with `ANT` = this folder", "", "```bash",
                  *missing_cmds, "```", ""]
    lines += ["## To update", "", "```bash", f"# 1. new or changed runs: copy the run directories into sim/runs/ (the .gitignore drops the field data)",
              f"# 2. regenerate, from this folder:",
              f"uv run --project {context['tool_project']} --extra report bac-antenna report antenna.toml", "```", ""]
    (out / "STATUS.md").write_text("\n".join(lines))
    print("\n".join(lines))
    return 0
