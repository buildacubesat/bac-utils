"""openEMS backend. Unvalidated until HANDOFF §8 has been worked through.

One FDTD run per port; multi-port excitations (the dual-feed hybrid) are formed by
superposition of the per-port runs, both for S-parameters and far fields.
"""
from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path

from .config import Config
from .geometry import Model, check_model
from .metrics import BandMetrics, Metrics
from .pattern import CUT_PHI_DEG, angular_metrics, back_fraction, cut_summary, write_cuts_csv
from .rf import axial_ratio_db, circular_components, rotation_sense

ETA0 = 376.730313668


EPS0 = 8.8541878128e-12


def _xy(points):
    """CSXCAD wants [xs, ys], not a list of pairs."""
    return [[q[0] for q in points], [q[1] for q in points]]


def merge_lines(fixed, grid, tol: float):
    """Fixed lines are authoritative; grid lines closer than `tol` to a fixed line are dropped, and
    fixed lines closer than `tol` to each other are averaged. Prevents the near-coincident lines
    (e.g. a pad edge at 2.51 mm next to a grid line at 2.50 mm) that otherwise set the time step."""
    import numpy as np
    # never round: a zero-thickness polygon needs a mesh line at exactly its elevation
    fixed = np.sort(np.asarray(fixed, dtype=float))
    keep = [fixed[0]]
    for v in fixed[1:]:
        if v - keep[-1] < tol:
            keep[-1] = (keep[-1] + v) / 2
        else:
            keep.append(v)
    fixed = np.array(keep)
    grid = np.asarray(grid, dtype=float)
    grid = grid[np.min(np.abs(grid[:, None] - fixed[None, :]), axis=1) >= tol]
    return np.unique(np.concatenate([fixed, grid]))


def build_lines(model: Model, mesh_cfg: dict, dom: dict) -> dict:
    """Mesh lines before smoothing: domain edges and the model's fixed lines are authoritative; the fine grid
    around the origin (model.refine) and the model's own grid lines fill in, dropped where they crowd a fixed line."""
    import numpy as np
    ext, cell = model.refine
    cell = float(mesh_cfg.get("refine_cell_mm", cell))
    tol = float(mesh_cfg.get("merge_tolerance_mm", 0.05))
    fine = np.arange(-ext, ext + cell / 2, cell) if ext > 0 and cell > 0 else np.array([])
    out = {}
    for ax in "xyz":
        grid = np.concatenate([fine if ax != "z" else np.array([]), np.asarray(model.grid_lines.get(ax, ()), dtype=float)])
        out[ax] = merge_lines([dom[ax][0], dom[ax][1], *model.fixed_lines[ax]], grid, tol)
    return out


def apply_model(csx, fdtd, model: Model, excite: int, f_ref_hz: float):
    """Loss tangents become conductivities at f_ref_hz."""
    props, ports = {}, []
    for p in model.primitives:
        if p.material == "metal":
            prop = csx.AddMetal(p.prop)
        else:
            kappa = 2 * math.pi * f_ref_hz * EPS0 * p.epsilon_r * p.loss_tangent
            prop = csx.AddMaterial(p.prop, epsilon=p.epsilon_r, kappa=kappa)
        props[p.prop] = prop
        if p.kind == "box":
            prop.AddBox(start=list(p.start), stop=list(p.stop), priority=p.priority)
        elif p.kind == "cylinder":
            prop.AddCylinder(start=list(p.start), stop=list(p.stop), radius=p.radius, priority=p.priority)
        elif p.kind == "polygon":
            prop.AddPolygon(points=_xy(p.points), norm_dir="z", elevation=p.elevation, priority=p.priority)
        elif p.kind == "linpoly":
            prop.AddLinPoly(points=_xy(p.points), norm_dir="z", elevation=p.elevation, length=p.length, priority=p.priority)
        else:
            raise ValueError(p.kind)
    for i, port in enumerate(model.ports):
        ports.append(fdtd.AddLumpedPort(i + 1, port.impedance_ohm, list(port.start), list(port.stop), port.direction,
                                        1.0 if i == excite else 0.0, priority=port.priority, edges2grid="xy"))
    return props, ports


class OpenEMSBackend:
    name = "openems"

    def evaluate(self, params: dict, config: Config, directory: Path, geometry_only: bool = False,
                 reuse: bool = False) -> Metrics | None:
        try:
            import numpy as np
            from CSXCAD import ContinuousStructure
            from openEMS import openEMS
            from openEMS.physical_constants import C0
        except ImportError as exc:
            raise RuntimeError("openEMS Python bindings are unavailable. Install openEMS/CSXCAD and expose them to this uv environment.") from exc
        from .antennas import get_antenna
        from .feednetwork import describe, weight_options

        directory = directory.resolve()      # openEMS.Run() chdirs into the sim folder
        model = get_antenna(config).model(params, config)
        problems = check_model(model)
        if problems:
            raise RuntimeError("; ".join(problems))
        m = config.mesh
        unit = 1e-3
        f_lo, f_hi = float(m["excitation_low_hz"]), float(m["excitation_high_hz"])
        f0, fc = (f_lo + f_hi) / 2, (f_hi - f_lo) / 2
        freqs = np.linspace(f_lo, f_hi, int(m["frequency_points"]))
        f_ref = config.primary_band.centre_hz
        z0s = {float(q.impedance_ohm) for q in model.ports}
        if len(z0s) != 1:
            raise RuntimeError("all ports must share one reference impedance")
        z0 = z0s.pop()
        margin = float(m["air_margin_mm"])
        res_max = C0 / f_hi / unit / float(m["cells_per_wavelength"])
        bc = str(m["boundary"])
        if bc.startswith("PML_"):
            # the PML occupies the outer n cells; keep it clear of the near field (>= lambda/8 of air before it)
            needed = int(bc.split("_")[1]) * res_max + C0 / f_hi / unit / 8
            if margin < needed:
                print(f"air margin {margin:.0f} mm is inside the {bc} layer at this resolution; using {needed:.0f} mm")
                margin = needed
        xmin, xmax, ymin, ymax, zmin, zmax = model.extent()
        dom = {"x": (xmin - margin, xmax + margin), "y": (ymin - margin, ymax + margin), "z": (zmin - margin, zmax + margin)}

        runs = []
        for k in range(len(model.ports)):
            fdtd = openEMS(NrTS=int(m["timesteps"]), EndCriteria=float(m["end_criteria"]))
            fdtd.SetGaussExcite(f0, fc)
            fdtd.SetBoundaryCond([str(m["boundary"])] * 6)
            csx = ContinuousStructure()
            fdtd.SetCSX(csx)
            mesh = csx.GetGrid()
            mesh.SetDeltaUnit(unit)
            res = C0 / f_hi / unit / float(m["cells_per_wavelength"])
            lines = build_lines(model, m, dom)
            for d in "xyz":
                mesh.AddLine(d, lines[d])
            props, ports = apply_model(csx, fdtd, model, k, f_ref)
            for name in model.edge_props:
                if name in props:
                    fdtd.AddEdges2Grid(dirs="xy", properties=props[name], metal_edge_res=res / 2)
            mesh.SmoothMeshLines("all", res, float(m["mesh_growth"]))
            nf2ff = fdtd.CreateNF2FFBox()
            # every zero-thickness sheet must lie exactly on a mesh line, or openEMS silently drops it
            zl = np.asarray(mesh.GetLines(2))
            for prim in model.primitives:
                if prim.kind == "polygon" and not np.any(zl == prim.elevation):
                    raise RuntimeError(f"{prim.prop}: no mesh line at z = {prim.elevation!r} – the primitive would be ignored")
            if k == 0:
                csx.Write2XML(str(directory / "geometry.xml"))
                counts = [len(mesh.GetLines(d)) for d in range(3)]
                min_cell = min(float(np.min(np.diff(np.sort(mesh.GetLines(d))))) for d in range(3))
                print(f"mesh {counts[0]} x {counts[1]} x {counts[2]} = {counts[0] * counts[1] * counts[2] / 1e6:.2f} M cells, "
                      f"smallest cell {min_cell * 1e3:.0f} um")
            if geometry_only:
                return None
            sim = directory / f"simulation_port{k + 1}"
            dump_cfg = config.raw.get("dump", {})
            if bool(dump_cfg.get("efield", False)):
                # frequency-domain E-field on the planes the antenna type suggests, at the primary band centre,
                # HDF5; a plane's fixed coordinate snaps to the nearest mesh line, the others clamp to the domain.
                # Combined per port by report.charts with the feed weights stored in the diagnostics.
                for fp in model.field_planes:
                    start, stop = list(fp.start), list(fp.stop)
                    for d, ax in enumerate("xyz"):
                        if start[d] == stop[d]:
                            ls = np.asarray(mesh.GetLines(d))
                            start[d] = stop[d] = float(ls[int(np.argmin(np.abs(ls - start[d])))])
                        else:
                            start[d], stop[d] = max(start[d], dom[ax][0]), min(stop[d], dom[ax][1])
                    d_ = csx.AddDump(fp.name, dump_type=10, dump_mode=1, file_type=1, frequency=[config.primary_band.centre_hz])
                    d_.AddBox(start, stop)
            if reuse and (sim / "port_ut_1").exists():
                print(f"reusing {sim}")
            else:
                cwd = os.getcwd()
                try:
                    fdtd.Run(str(sim), cleanup=True)
                finally:
                    os.chdir(cwd)
            for port in ports:
                port.CalcPort(str(sim), freqs, ref_impedance=z0)
            runs.append((sim, nf2ff, ports))

        n = len(model.ports)
        for k in range(n):
            inc = np.abs(runs[k][2][k].uf_inc)
            if not np.all(np.isfinite(inc)) or np.max(inc) <= 0:
                raise RuntimeError(f"port {k + 1} recorded no incident wave – the excitation did not couple into the mesh "
                                   f"(check for zero-width cells: see 'smallest cell' above)")
        # S[j, k, f] = b_j / a_k with run k exciting port k
        S = np.array([[runs[k][2][j].uf_ref / runs[k][2][k].uf_inc for k in range(n)] for j in range(n)])
        weights_options = weight_options(config, n)

        theta = np.arange(0.0, 181.0, 5.0)
        phi = np.arange(0.0, 360.0, 10.0)
        sample_f = sorted({f for b in config.bands for f in (b.low_hz, b.centre_hz, b.high_hz,
                                                              b.centre_hz - b.cp_span_hz / 2, b.centre_hz + b.cp_span_hz / 2)})
        ff = [runs[k][1].CalcNF2FF(str(runs[k][0]), sample_f, theta, phi, center=list(model.phase_centre)) for k in range(n)]
        sense = int(config.polarization.get("openems_rhcp_sense", 0))
        wanted = config.polarization["hand"].lower()

        def combine(a, fi: int):
            f = sample_f[fi]
            idx = int(np.argmin(abs(freqs - f)))
            # scale each run so that its incident wave equals a_k
            w = [a[k] / runs[k][2][k].uf_inc[idx] for k in range(n)]
            et = sum(w[k] * np.asarray(ff[k].E_theta[fi]) for k in range(n))
            ep = sum(w[k] * np.asarray(ff[k].E_phi[fi]) for k in range(n))
            u = (abs(et) ** 2 + abs(ep) ** 2) / (2 * ETA0)
            th = np.radians(theta)[:, None]
            p_rad = float(np.sum(u * np.sin(th)) * np.radians(5.0) * np.radians(10.0))
            p_inc = 0.5 * float(np.sum(np.abs(a) ** 2)) / z0
            b = S[:, :, idx] @ a
            p_acc = p_inc - 0.5 * float(np.sum(np.abs(b) ** 2)) / z0
            ex, ey = complex(et[0, 0]), complex(ep[0, 0])
            g = 4 * math.pi * float(u[0, 0]) / p_inc
            er, el = circular_components(ex, ey)
            tot = abs(er) ** 2 + abs(el) ** 2
            s_ = rotation_sense(ex, ey) * sense
            hand = "unverified" if sense == 0 else ("rhcp" if s_ > 0 else "lhcp" if s_ < 0 else "linear")
            g_r, g_l = g * abs(er) ** 2 / tot, g * abs(el) ** 2 / tot
            if sense < 0:
                g_r, g_l = g_l, g_r
            co = max(g_r, g_l) if sense == 0 else (g_r if wanted == "rhcp" else g_l)
            gamma = complex(np.dot(a, b)) if n > 1 else complex(b[0] / a[0])
            if fi == centre_probe[0]:
                # power balance: far-field P_rad vs port P_acc (P_rad > P_acc means the far field is wrong)
                centre_probe.append({"p_rad_w": p_rad, "p_acc_w": p_acc, "p_inc_w": p_inc,
                                     "p_rad_over_p_acc": p_rad / p_acc if p_acc > 0 else None})
            return {"g_co": co, "ar": axial_ratio_db(ex, ey), "hand": hand, "eff": p_rad / p_acc if p_acc > 0 else 0.0,
                    "gamma": gamma, "p_rad": p_rad}

        centre_i = sample_f.index(config.primary_band.centre_hz)
        centre_probe = [centre_i]
        a = max(weights_options, key=lambda x: combine(x, centre_i)["g_co"])
        gam = np.array([complex(np.dot(a, S[:, :, i] @ a)) if n > 1 else S[0, 0, i] for i in range(len(freqs))])
        s11_db = 20 * np.log10(np.maximum(np.abs(gam), 1e-15))
        with (directory / "s11_sweep.csv").open("w", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["frequency_hz", "s11_db", "s11_real", "s11_imag"])
            for f, d, c in zip(freqs, s11_db, gam):
                wr.writerow([f"{f:.6e}", f"{d:.4f}", f"{c.real:.6e}", f"{c.imag:.6e}"])

        diag = {}
        with (directory / "sparams_complex.csv").open("w", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["frequency_hz"] + [f"s{j + 1}{k + 1}_{c}" for j in range(n) for k in range(n) for c in ("re", "im")])
            for i, f in enumerate(freqs):
                wr.writerow([f"{f:.6e}"] + [f"{v:.6e}" for j in range(n) for k in range(n) for v in (S[j, k, i].real, S[j, k, i].imag)])
        # per-port S-parameters (the sweep above is the hybrid-input reflection for dual feeds)
        if n > 1:
            with (directory / "sparams.csv").open("w", newline="") as fh:
                wr = csv.writer(fh)
                wr.writerow(["frequency_hz"] + [f"s{j + 1}{k + 1}_db" for j in range(n) for k in range(n)])
                for i, f in enumerate(freqs):
                    wr.writerow([f"{f:.6e}"] + [f"{20 * math.log10(max(1e-15, abs(S[j, k, i]))):.2f}" for j in range(n) for k in range(n)])
            i0 = int(np.argmin(abs(freqs - f_ref)))
            diag["per_port_at_primary_centre"] = {f"s{j + 1}{k + 1}_db": round(20 * math.log10(max(1e-15, abs(S[j, k, i0]))), 2)
                                                  for j in range(n) for k in range(n)}
            b0 = S[:, :, i0] @ a
            diag["hybrid_load_fraction_at_primary_centre"] = float(np.sum(np.abs(b0) ** 2) / np.sum(np.abs(a) ** 2))
        # where each probe's own match is centred; for a dual feed this, not the hybrid-input minimum,
        # sets the load fraction across the band
        # searched within the primary band +/-200 MHz: near the excitation edges the port spectra are noise
        pb0 = config.primary_band
        win = (freqs >= pb0.low_hz - 200e6) & (freqs <= pb0.high_hz + 200e6)
        fw = freqs[win]
        diag["probe_resonance_hz"] = float(np.mean([fw[int(np.argmin(np.abs(S[k, k, win])))] for k in range(n)]))

        # far field over angle for the primary band: gain and AR versus theta in four planes, front-to-back
        pat = config.raw.get("pattern", {})
        pb = config.primary_band
        cut_f = [pb.low_hz, pb.centre_hz, pb.high_hz]
        cut_theta = np.arange(0.0, 180.0 + 1e-9, float(pat.get("cut_step_deg", 1.0)))
        cut_phi = np.array([float(x) for x in pat.get("cut_phi_deg", CUT_PHI_DEG)])
        angles = tuple(float(x) for x in pat.get("angles_deg", (45.0, 60.0)))
        ffc = [runs[k][1].CalcNF2FF(str(runs[k][0]), cut_f, cut_theta, cut_phi, center=list(model.phase_centre),
                                    outfile="nf2ff_cuts.h5") for k in range(n)]
        p_inc = 0.5 * float(np.sum(np.abs(a) ** 2)) / z0
        per_f, summaries = [], {}
        for fi, f in enumerate(cut_f):
            idx = int(np.argmin(abs(freqs - f)))
            w = [a[k] / runs[k][2][k].uf_inc[idx] for k in range(n)]
            et = sum(w[k] * np.asarray(ffc[k].E_theta[fi]) for k in range(n))
            ep = sum(w[k] * np.asarray(ffc[k].E_phi[fi]) for k in range(n))
            m_ = angular_metrics(et, ep, p_inc, sense, wanted)
            per_f.append(m_)
            summaries[f"{f / 1e9:.4f}_ghz"] = cut_summary(cut_theta, m_, angles)
        write_cuts_csv(directory / "farfield_cuts.csv", cut_f, cut_theta, cut_phi, per_f)
        worst = {k: (min if k.startswith("gain") or k.startswith("front") else max)(s[k] for s in summaries.values())
                 for k in next(iter(summaries.values())) if k != "theta_180_reached"}
        # rear-hemisphere share from the full-sphere grid at band centre
        idx_c = int(np.argmin(abs(freqs - pb.centre_hz)))
        wc = [a[k] / runs[k][2][k].uf_inc[idx_c] for k in range(n)]
        et_c = sum(wc[k] * np.asarray(ff[k].E_theta[centre_i]) for k in range(n))
        ep_c = sum(wc[k] * np.asarray(ff[k].E_phi[centre_i]) for k in range(n))
        worst["back_fraction"] = back_fraction(et_c, ep_c, theta, phi)
        sphere = angular_metrics(et_c, ep_c, p_inc, sense, wanted)
        with (directory / "farfield_sphere.csv").open("w", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["theta_deg", "phi_deg", "gain_total_dbi", "gain_co_dbic", "gain_cross_dbic", "ar_db"])
            for i, th in enumerate(theta):
                for j, ph in enumerate(phi):
                    wr.writerow([f"{th:.1f}", f"{ph:.1f}", f"{sphere['gain_total_dbi'][i, j]:.2f}", f"{sphere['gain_co_dbic'][i, j]:.2f}",
                                 f"{sphere['gain_cross_dbic'][i, j]:.2f}", f"{sphere['ar_db'][i, j]:.2f}"])
        if bool(config.raw.get("dump", {}).get("efield", False)):
            diag["efield_dump"] = {"frequency_hz": pb.centre_hz, "files": [f"{fp.name}.h5" for fp in model.field_planes],
                                   "port_dirs": [f"simulation_port{k + 1}" for k in range(n)],
                                   "weights": [[float(wc[k].real), float(wc[k].imag)] for k in range(n)],
                                   "p_inc_w": p_inc, "layout": "NZYX (component, z, y, x); mesh in /Mesh/x,y,z"}
        diag["pattern"] = {"frequencies_hz": cut_f, "theta_step_deg": float(cut_theta[1] - cut_theta[0]),
                           "phi_deg": [float(x) for x in cut_phi], "per_frequency": summaries, "worst": worst}
        # per-frequency far-field summary for the sampled points (band edges, centres, CP span)
        with (directory / "farfield_samples.csv").open("w", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["frequency_hz", "gain_co_dbic", "ar_db", "hand", "efficiency", "s11_db"])
            for i, f in enumerate(sample_f):
                r = combine(a, i)
                wr.writerow([f"{f:.6e}", f"{10 * math.log10(max(1e-9, r['g_co'])):.2f}", f"{r['ar']:.2f}", r["hand"],
                             f"{r['eff']:.4f}", f"{20 * math.log10(max(1e-15, abs(r['gamma']))):.2f}"])
        out = {}
        for band in config.bands:
            sel = (freqs >= band.low_hz) & (freqs <= band.high_hz)
            pts = [sample_f.index(f) for f in (band.low_hz, band.centre_hz, band.high_hz)]
            cps = [sample_f.index(f) for f in (band.centre_hz - band.cp_span_hz / 2, band.centre_hz, band.centre_hz + band.cp_span_hz / 2)]
            r = {i: combine(a, i) for i in set(pts) | set(cps)}
            c = r[sample_f.index(band.centre_hz)]
            out[band.name] = BandMetrics(float(s11_db[sel].max()), float(10 * math.log10(max(1e-9, min(r[i]["g_co"] for i in pts)))),
                                         float(max(r[i]["ar"] for i in cps)), 100 * min(1.0, c["eff"]), c["hand"])
            diag[band.name] = {"efficiency_raw": c["eff"], "p_rad_w": c["p_rad"]}
        diag["power_cross_check_primary_centre"] = centre_probe[1] if len(centre_probe) > 1 else None
        diag.update({"note": "Validate against HANDOFF §8 before trusting any of these numbers.", "ports": n,
                     "feed_mode": describe(config, n), "hybrid_weights": [str(x) for x in a],
                     "rhcp_sense_calibrated": sense != 0, "model_notes": list(model.notes)})
        (directory / "openems_diagnostics.json").write_text(json.dumps(diag, indent=2) + "\n")
        return Metrics(out, float(freqs[int(np.argmin(s11_db))]), (), "openEMS – unvalidated")


class CoarseBackend(OpenEMSBackend):
    """openEMS at a coarse mesh and a relaxed end criterion: a fast estimate for antenna types without a cavity
    model (seconds to tens of seconds instead of minutes). Not for final numbers."""

    name = "coarse"
    overrides = {"cells_per_wavelength": 12, "end_criteria": 1e-3, "gap_cells": 4, "substrate_cells": 2, "refine_cell_mm": 0.5}

    def evaluate(self, params: dict, config: Config, directory: Path, geometry_only: bool = False, reuse: bool = False):
        import copy

        raw = copy.deepcopy(config.raw)
        raw["mesh"] = {**raw["mesh"], **{k: v for k, v in self.overrides.items() if k in raw["mesh"] or k in ("cells_per_wavelength", "end_criteria")}}
        raw.setdefault("pattern", {})["cut_step_deg"] = 5.0
        coarse = Config(raw=raw, source=config.source)
        return super().evaluate(params, coarse, directory, geometry_only=geometry_only, reuse=reuse)
