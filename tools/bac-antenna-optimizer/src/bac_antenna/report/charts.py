"""Charts and a summary table for the datasheet / simulation report, from one evaluated case directory.

Writes into the output directory (SVG for the line charts, lossless WebP for the raster images):
  s11.svg            hybrid-input S11, per-probe S11 and probe-to-probe coupling vs frequency, bands shaded
  smith.svg          per-probe S11 on a Smith chart across the excitation band (sparams_complex.csv)
  gain_ar_vs_f.svg   broadside RHCP realized gain and axial ratio vs frequency (farfield_samples.csv)
  pattern_cuts.svg   RHCP/LHCP realized gain and AR vs angle, four planes, at the band centre (farfield_cuts.csv)
  pattern_3d.webp    3D realized-gain surface at the band centre (farfield_sphere.csv)
  efield_*.webp      |E| on the dumped planes, per-port dumps combined with the hybrid weights (needs h5py)
  summary.md         the numbers, as a markdown table
  data/              the CSV/JSON inputs the charts were drawn from (for notebooks; --no-data to skip)
Charts whose input files are missing are skipped with a note (older runs: `sweep --reprocess` adds the newer files;
the E-field dumps need a run with [dump] efield = true).
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

from ..pattern import read_cuts_csv, signed_cut

BAND_COLORS = {"tx": "#1f77b4", "rx": "#2ca02c", "s2400": "#ff7f0e"}


def read_csv(path: Path) -> dict[str, np.ndarray]:
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return {}
    out = {}
    for k in rows[0]:
        try:
            out[k] = np.array([float(r[k]) for r in rows])
        except ValueError:
            out[k] = np.array([r[k] for r in rows])
    return out


def bands_from(case: Path) -> list[dict]:
    """Band list from the run's config copy if present, else from result.json (frequencies unknown -> skip shading)."""
    res = json.loads((case / "result.json").read_text()) if (case / "result.json").exists() else {}
    bands = []
    for cfg_name in ("config.toml",):
        p = case / cfg_name
        if p.exists():
            import tomllib
            for b in tomllib.loads(p.read_text()).get("band", []):
                bands.append({"name": b["name"], "low": float(b["low_hz"]), "high": float(b["high_hz"]), "weight": float(b.get("weight", 0))})
    if not bands:
        known = {"tx": (2.200e9, 2.290e9), "rx": (2.025e9, 2.110e9), "s2400": (2.400e9, 2.450e9)}
        for name in (res.get("metrics", {}).get("bands", {}) or {}):
            if name in known:
                bands.append({"name": name, "low": known[name][0], "high": known[name][1], "weight": 0.0})
    return bands


def shade(ax, bands, primary=None):
    for b in bands:
        alpha = 0.18 if b["name"] == primary else 0.07
        ax.axvspan(b["low"] / 1e9, b["high"] / 1e9, color=BAND_COLORS.get(b["name"], "#888"), alpha=alpha, lw=0)


def chart_s11(case, out, bands, primary, plt):
    sw = read_csv(case / "s11_sweep.csv") if (case / "s11_sweep.csv").exists() else {}
    sp = read_csv(case / "sparams.csv") if (case / "sparams.csv").exists() else {}
    if not sw and not sp:
        return None
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    shade(ax, bands, primary)
    if sp:
        f = sp["frequency_hz"] / 1e9
        if "s21_db" in sp:
            ax.plot(f, np.maximum(sp["s21_db"], -40), color="#7f7f7f", lw=3.0, alpha=0.5, label="probe-to-probe coupling (S21)")
        ax.plot(f, np.maximum(sp["s11_db"], -40), color="#1f77b4", lw=1.4, label="probe 1 alone (S11)")
        if "s22_db" in sp:
            ax.plot(f, np.maximum(sp["s22_db"], -40), color="#2ca02c", lw=1.0, ls="--", label="probe 2 alone (S22)")
    if sw:
        ax.plot(sw["frequency_hz"] / 1e9, np.maximum(sw["s11_db"], -40), color="#d62728", lw=1.6,
                label="S11 at the hybrid input (= coupling for identical probes)")
    ax.set_xlabel("frequency (GHz)")
    ax.set_ylabel("dB")
    ax.set_ylim(-40, 0)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=8)
    ax.set_title("Reflection and coupling – hybrid input vs individual probes")
    fig.tight_layout()
    return fig


def chart_smith(case, out, bands, primary, plt):
    p = case / "sparams_complex.csv"
    if not p.exists():
        return None
    d = read_csv(p)
    if "s11_re" not in d:
        return None
    f = d["frequency_hz"]
    lo, hi = (min(b["low"] for b in bands) - 0.1e9, max(b["high"] for b in bands) + 0.1e9) if bands else (f[0], f[-1])
    sel = (f >= lo) & (f <= hi)
    g = d["s11_re"][sel] + 1j * d["s11_im"][sel]
    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    ax.set_aspect("equal")
    ax.axis("off")
    for r in (0.0, 0.2, 0.5, 1.0, 2.0, 5.0):        # constant-resistance circles
        c, rad = r / (1 + r), 1 / (1 + r)
        ax.add_patch(plt.Circle((c, 0), rad, fill=False, color="#bbb", lw=0.6))
    for x in (0.2, 0.5, 1.0, 2.0, 5.0):            # constant-reactance arcs
        for sgn in (1, -1):
            t = np.linspace(0, 2 * math.pi, 400)
            cx, cy, rad = 1.0, sgn / x, 1 / x
            xs, ys = cx + rad * np.cos(t), cy + rad * np.sin(t)
            keep = xs ** 2 + ys ** 2 <= 1.0001
            ax.plot(np.where(keep, xs, np.nan), np.where(keep, ys, np.nan), color="#bbb", lw=0.6)
    ax.add_patch(plt.Circle((0, 0), 1.0, fill=False, color="#333", lw=1.0))
    ax.plot([-1, 1], [0, 0], color="#bbb", lw=0.6)
    ax.plot(g.real, g.imag, color="#1f77b4", lw=1.8)
    for b in bands:
        if b["name"] != primary:
            continue
        for fm, mk, lab in ((b["low"], "s", "band low"), ((b["low"] + b["high"]) / 2, "o", "centre"), (b["high"], "^", "band high")):
            i = int(np.argmin(np.abs(f[sel] - fm)))
            ax.plot(g.real[i], g.imag[i], marker=mk, color="#d62728", ms=7, ls="none", label=f"{lab} {fm / 1e9:.3f} GHz")
    ax.legend(loc="lower left", fontsize=8, frameon=False)
    ax.set_title(f"Probe 1 impedance, {lo / 1e9:.2f}–{hi / 1e9:.2f} GHz (other probe terminated)", fontsize=10)
    fig.tight_layout()
    return fig


def chart_gain_ar(case, out, bands, primary, plt):
    p = case / "farfield_samples.csv"
    if not p.exists():
        return None
    d = read_csv(p)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    shade(ax, bands, primary)
    f = d["frequency_hz"] / 1e9
    ax.plot(f, d["gain_co_dbic"], "o-", color="#1f77b4", lw=1.6, ms=4, label="realized RHCP gain, boresight (dBic)")
    ax.set_xlabel("frequency (GHz)")
    ax.set_ylabel("gain (dBic)", color="#1f77b4")
    ax.set_ylim(0, 12)
    ax.grid(True, alpha=0.3)
    ax2 = ax.twinx()
    ax2.plot(f, d["ar_db"], "s--", color="#d62728", lw=1.4, ms=4, label="axial ratio, boresight (dB)")
    ax2.set_ylabel("axial ratio (dB)", color="#d62728")
    ax2.set_ylim(0, 6)
    ax2.axhline(3, color="#d62728", lw=0.6, alpha=0.5)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="lower right", fontsize=8)
    ax.set_title("Broadside gain and axial ratio vs frequency")
    fig.tight_layout()
    return fig


def chart_cuts(case, out, plt, freq_hz=None):
    p = case / "farfield_cuts.csv"
    if not p.exists():
        return None
    cuts = read_cuts_csv(p)
    freqs, theta, phi, metrics = cuts["freqs"], cuts["theta"], cuts["phi"], cuts["metrics"]
    fi = 1 if freq_hz is None and len(freqs) >= 3 else (int(np.argmin(np.abs(np.array(freqs) - freq_hz))) if freq_hz else 0)
    m = metrics[fi]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    g_lo, ar_hi, ar_window_db = -25.0, 8.0, 15.0
    peak = float(np.max(m["gain_co_dbic"]))
    for plane in (0.0, 90.0, 45.0, 135.0):
        xs, g = signed_cut(theta, phi, m["gain_co_dbic"], plane)
        _, gx = signed_cut(theta, phi, m["gain_cross_dbic"], plane)
        _, ar = signed_cut(theta, phi, m["ar_db"], plane)
        # clip in data, not only by the axes clip path: some SVG viewers ignore clipPath
        line, = axes[0].plot(xs, np.maximum(g, g_lo), lw=1.6, label=f"RHCP, phi = {plane:g} deg")
        axes[0].plot(xs, np.maximum(gx, g_lo), lw=0.9, ls=":", color=line.get_color())
        # axial ratio only where there is a signal to have a polarization: in the nulls it is noise over noise
        meaningful = np.maximum(g, gx) >= peak - ar_window_db
        ar_shown = np.where(meaningful, np.minimum(ar, ar_hi), np.nan)
        axes[1].plot(xs, ar_shown, lw=1.4, color=line.get_color(), label=f"phi = {plane:g} deg")
    axes[0].set_ylim(g_lo, 12)
    axes[0].set_ylabel("realized gain (dBic), RHCP solid / LHCP dotted")
    axes[1].set_ylim(0, ar_hi)
    axes[1].axhline(3, color="0.6", lw=0.8)
    axes[1].set_ylabel(f"axial ratio (dB), where gain > peak - {ar_window_db:.0f} dB")
    for ax, span in ((axes[0], 180), (axes[1], 90)):     # AR panel: front hemisphere only
        ax.set_xlim(-span, span)
        ax.set_xticks(range(-span, span + 1, 30 if span == 90 else 60))
        ax.set_xlabel("theta (deg), signed along the plane")
        ax.axvline(-60, color="0.8", lw=0.7)
        ax.axvline(60, color="0.8", lw=0.7)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8, loc="lower center" if span == 180 else "upper center")
    fig.suptitle(f"Pattern cuts at {freqs[fi] / 1e9:.3f} GHz")
    fig.tight_layout()
    return fig


def chart_3d(case, out, plt):
    p = case / "farfield_sphere.csv"
    if not p.exists():
        return None
    d = read_csv(p)
    th = np.unique(d["theta_deg"])
    ph = np.unique(d["phi_deg"])
    G = np.full((len(th), len(ph)), np.nan)
    ti = {t: i for i, t in enumerate(th)}
    pj = {q: j for j, q in enumerate(ph)}
    for t, q, g in zip(d["theta_deg"], d["phi_deg"], d["gain_co_dbic"]):
        G[ti[t], pj[q]] = g
    ph2 = np.append(ph, ph[0] + 360.0)           # close the surface in phi
    G2 = np.concatenate([G, G[:, :1]], axis=1)
    floor = -15.0
    R = np.clip(G2 - floor, 0, None)             # radius = gain above the floor (dB)
    T, P = np.meshgrid(np.radians(th), np.radians(ph2), indexing="ij")
    X, Y, Z = R * np.sin(T) * np.cos(P), R * np.sin(T) * np.sin(P), R * np.cos(T)
    fig = plt.figure(figsize=(6.5, 6))
    ax = fig.add_subplot(111, projection="3d")
    norm = plt.Normalize(vmin=floor, vmax=np.nanmax(G2))
    colors = plt.cm.viridis(norm(G2))
    ax.plot_surface(X, Y, Z, facecolors=colors, rstride=1, cstride=1, linewidth=0, antialiased=True, shade=False)
    lim = np.nanmax(R) * 1.05
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim * 0.6, lim)
    ax.set_box_aspect((1, 1, 0.8))
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z (boresight)")
    ax.view_init(elev=22, azim=-55)
    mappable = plt.cm.ScalarMappable(norm=norm, cmap="viridis")
    fig.colorbar(mappable, ax=ax, shrink=0.55, pad=0.08, label="realized RHCP gain (dBic)")
    ax.set_title(f"Realized RHCP gain, radius = gain above {floor:.0f} dBic")
    fig.tight_layout()
    return fig


def read_fd_dump(path: Path):
    """openEMS frequency-domain HDF5 dump -> (E complex, shape (3, nx, ny, nz)), mesh dict in mm.

    Current openEMS writes one compound-complex dataset per frequency (`/FieldData/FD/f0`, dims N,X,Y,Z);
    the legacy format (openEMS started with --legacy-hdf5 or older builds) writes `f0_real` and `f0_imag`
    with dims N,Z,Y,X. Both are handled; the first frequency is returned.
    """
    import h5py
    with h5py.File(path, "r") as h:
        mesh = {ax: np.array(h["Mesh"][ax], dtype=float) for ax in "xyz"}
        fd = h["FieldData"]["FD"]
        keys = sorted(fd.keys())
        legacy = [k for k in keys if k.endswith("_real")]
        if legacy:
            k = legacy[0]
            E = np.array(fd[k]) + 1j * np.array(fd[k[:-5] + "_imag"])     # (N, Z, Y, X)
            E = np.transpose(E, (0, 3, 2, 1))                               # -> (N, X, Y, Z)
        else:
            ds = fd[keys[0]]
            raw = np.array(ds)
            if raw.dtype.names and set(raw.dtype.names) >= {"r", "i"}:      # compound not auto-mapped by h5py
                raw = raw["r"] + 1j * raw["i"]
            E = np.asarray(raw, dtype=complex)                              # (N, X, Y, Z)
    scale = 1e3 if max(np.max(np.abs(v)) for v in mesh.values()) < 1.0 else 1.0   # metres -> mm
    mesh = {k: v * scale for k, v in mesh.items()}
    # tolerate a dump whose axes come in a different order than the mesh lengths suggest
    want = (3, len(mesh["x"]), len(mesh["y"]), len(mesh["z"]))
    if E.shape != want and sorted(E.shape) == sorted(want):
        order = [E.shape.index(w) if E.shape.count(w) == 1 else None for w in want]
        if None not in order:
            E = np.transpose(E, order)
    return E, mesh


def chart_efield(case, out, plt, diag):
    info = diag.get("efield_dump")
    if not info:
        return []
    try:
        import h5py  # noqa: F401
    except ImportError:
        print("h5py not available: skipping E-field planes (run with --with h5py)")
        return []
    figs = []
    w = [complex(a, b) for a, b in info["weights"]]
    for fname in info["files"]:
        fields, mesh = [], None
        for k, pdir in enumerate(info["port_dirs"]):
            p = case / pdir / fname
            if not p.exists():
                fields = []
                break
            E, mesh = read_fd_dump(p)
            fields.append(w[k] * E)
        if not fields:
            print(f"{fname}: dump missing in a port directory, skipped")
            continue
        E = sum(fields)
        mag = np.sqrt(np.sum(np.abs(E) ** 2, axis=0))       # (nx, ny, nz)
        x, y, z = mesh["x"], mesh["y"], mesh["z"]
        fig, ax = plt.subplots(figsize=(6.5, 5.6))
        if mag.shape[2] == 1:                                # xy plane
            img, ex, ey, xl, yl = mag[:, :, 0].T, x, y, "x (mm)", "y (mm)"
        elif mag.shape[1] == 1:                              # xz plane
            img, ex, ey, xl, yl = mag[:, 0, :].T, x, z, "x (mm)", "z (mm)"
        elif mag.shape[0] == 1:                              # yz plane
            img, ex, ey, xl, yl = mag[0, :, :].T, y, z, "y (mm)", "z (mm)"
        else:
            img, ex, ey, xl, yl = mag[:, :, mag.shape[2] // 2].T, x, y, "x (mm)", "y (mm)"
        db = 20 * np.log10(np.maximum(img, 1e-12) / np.max(img))
        pc = ax.pcolormesh(ex, ey, db, cmap="inferno", vmin=-40, vmax=0, shading="auto")
        fig.colorbar(pc, ax=ax, label="|E| (dB rel. max)")
        ax.set_aspect("equal")
        ax.set_xlabel(xl); ax.set_ylabel(yl)
        ax.set_title(f"|E| at {info['frequency_hz'] / 1e9:.3f} GHz – {fname[:-3]}")
        fig.tight_layout()
        figs.append((fname[:-3].lower(), fig))
    return figs


def summary_table(case: Path, label: str) -> str:
    res = json.loads((case / "result.json").read_text()) if (case / "result.json").exists() else {}
    diag = json.loads((case / "openems_diagnostics.json").read_text()) if (case / "openems_diagnostics.json").exists() else {}
    params = json.loads((case / "parameters.json").read_text()) if (case / "parameters.json").exists() else {}
    bands = res.get("metrics", {}).get("bands", {})
    pat = (diag.get("pattern") or {})
    w = pat.get("worst", {})
    rows = [("Case", f"`{case.name}` ({label})")]
    if params:
        rows.append(("Patch (arms × width, feed, pad)", f"{params.get('arm_x_mm', 0):.1f} × {params.get('arm_width_mm', 0):.1f} mm, {params.get('feed_offset_mm', 0):.1f} mm, r {params.get('pad_radius_mm', 0):.2f} mm"))
    for name, b in bands.items():
        rows.append((f"Band `{name}`: S11 / gain / AR / efficiency", f"≤ {b['s11_worst_db']:.1f} dB / ≥ {b['gain_min_dbic']:.2f} dBic / ≤ {b['ar_worst_db']:.2f} dB / {b['efficiency_percent']:.1f} % ({b['hand'].upper()})"))
    if "probe_resonance_hz" in diag:
        rows.append(("Probe S11 minimum", f"{diag['probe_resonance_hz'] / 1e9:.4f} GHz"))
    if "hybrid_load_fraction_at_primary_centre" in diag:
        lf = diag["hybrid_load_fraction_at_primary_centre"]
        rows.append(("Hybrid load at band centre", f"{100 * lf:.1f} % ({-10 * math.log10(1 - lf):.2f} dB)"))
    if w:
        rows.append(("Gain at 45° / 60° off boresight (worst plane)", f"{w['gain_co_min_45']:.1f} / {w['gain_co_min_60']:.1f} dBic"))
        rows.append(("AR at 45° / 60° (worst plane)", f"{w['ar_max_45']:.1f} / {w['ar_max_60']:.1f} dB"))
        rows.append(("Front-to-back, rear-hemisphere power", f"{w['front_to_back_db']:.1f} dB, {100 * w['back_fraction']:.0f} %"))
    cuts = case / "farfield_cuts.csv"
    if cuts.exists():
        c = read_cuts_csv(cuts)
        m = c["metrics"][1 if len(c["freqs"]) >= 3 else 0]
        g0 = float(np.mean(m["gain_co_dbic"][0]))
        bw = []
        for plane in (0.0, 90.0):
            xs, g = signed_cut(c["theta"], c["phi"], m["gain_co_dbic"], plane)
            inside = xs[g >= g0 - 3]
            bw.append(float(inside.max() - inside.min()))
        rows.append(("3 dB beamwidth (phi = 0 / 90)", f"{bw[0]:.0f}° / {bw[1]:.0f}°"))
    lines = ["| parameter | value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines) + "\n"


def save_raster(fig, path: Path, dpi: int = 150) -> Path:
    """Save a matplotlib figure as lossless WebP (about a third smaller than PNG for line art), through Pillow.
    Falls back to PNG when Pillow is missing; the returned path says which."""
    import io
    path = Path(path)
    try:
        from PIL import Image
    except ImportError:
        png = path.with_suffix(".png")
        fig.savefig(png, dpi=dpi)
        return png
    buf = io.BytesIO()
    fig.savefig(buf, dpi=dpi, format="png")
    buf.seek(0)
    Image.open(buf).convert("RGBA").save(path.with_suffix(".webp"), format="WEBP", lossless=True, quality=100, method=6)
    return path.with_suffix(".webp")


def make_charts(case: Path, out: Path, label: str = "", png: bool = False, copy_data: bool = True) -> list[str]:
    """Write the chart set + summary.md (+ data/) for one case directory; returns the files written.
    `png=True` writes the line charts as raster too (WebP) instead of SVG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # svg.hashsalt fixes matplotlib's element ids, which are random by default; with the Date metadata off
    # below, an unchanged case gives a byte-identical SVG on every run.
    plt.rcParams.update({"font.size": 9, "font.family": "sans-serif", "svg.hashsalt": "bac-antenna-optimizer"})
    case, out = Path(case), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    diag = json.loads((case / "openems_diagnostics.json").read_text()) if (case / "openems_diagnostics.json").exists() else {}
    bands = bands_from(case)
    primary = None
    if bands:
        primary = max(bands, key=lambda b: b["weight"])["name"] if any(b["weight"] > 0 for b in bands) else bands[0]["name"]
        if diag.get("pattern"):
            fc = diag["pattern"]["frequencies_hz"][1]
            primary = next((b["name"] for b in bands if b["low"] <= fc <= b["high"]), primary)
    written = []
    for name, fig in (("s11", chart_s11(case, out, bands, primary, plt)), ("smith", chart_smith(case, out, bands, primary, plt)),
                      ("gain_ar_vs_f", chart_gain_ar(case, out, bands, primary, plt)), ("pattern_cuts", chart_cuts(case, out, plt))):
        if fig is None:
            continue
        if png:
            written.append(save_raster(fig, out / f"{name}.webp").name)
        else:
            fig.savefig(out / f"{name}.svg", metadata={"Date": None})     # no timestamp: identical input, identical file
            written.append(f"{name}.svg")
        plt.close(fig)
    fig = chart_3d(case, out, plt)
    if fig is not None:
        written.append(save_raster(fig, out / "pattern_3d.webp").name)
        plt.close(fig)
    for name, fig in chart_efield(case, out, plt, diag):
        written.append(save_raster(fig, out / f"efield_{name}.webp").name)
        plt.close(fig)
    for stale in list(out.glob("*.png")):          # leftovers from the PNG era of this tool
        if stale.with_suffix(".webp").exists():
            stale.unlink()
    (out / "summary.md").write_text(summary_table(case, label))
    written.append("summary.md")
    if copy_data:
        import shutil
        data = out / "data"
        data.mkdir(exist_ok=True)
        for name in ("s11_sweep.csv", "sparams.csv", "sparams_complex.csv", "farfield_samples.csv", "farfield_cuts.csv",
                     "farfield_sphere.csv", "openems_diagnostics.json", "result.json", "parameters.json"):
            if (case / name).exists():
                shutil.copy(case / name, data / name)
        written.append("data/")
    return written
