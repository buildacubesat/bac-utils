"""Far-field pattern analysis over angle.

Works on combined (already superposed) far fields on a (theta, phi) grid. The local transverse
basis (theta_hat, phi_hat, r_hat) is right-handed with r_hat the propagation direction, exactly as
(x, y, z) is at broadside, so the broadside polarization helpers in rf.py apply per direction with
(E_theta, E_phi) in place of (E_x, E_y). At theta = 0, phi = 0 they coincide.

Realized gain is normalised to the incident power, so hybrid-load and mismatch loss stay inside the
number, as in the band metrics.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from .rf import axial_ratio_db, circular_components

ETA0 = 376.730313668
FLOOR_DBI = -60.0            # gain floor for nulls (keeps front-to-back finite)
CUT_PHI_DEG = (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0)


def angular_metrics(et: np.ndarray, ep: np.ndarray, p_inc_w: float, sense: int, wanted: str) -> dict:
    """Per-direction realized gains (dBi / dBic) and axial ratio (dB) for a [theta, phi] field.

    sense: +1 if openEMS (E_theta, E_phi) map to IEEE RHCP as rf.circular_components assumes, -1 if
    the hand is mirrored, 0 if uncalibrated (co = larger CP component). wanted: rhcp | lhcp.
    """
    et = np.asarray(et, dtype=complex)
    ep = np.asarray(ep, dtype=complex)
    u = (np.abs(et) ** 2 + np.abs(ep) ** 2) / (2 * ETA0)
    g_tot = 4 * math.pi * u / p_inc_w
    g_r = np.zeros_like(g_tot)
    g_l = np.zeros_like(g_tot)
    ar = np.full(g_tot.shape, 99.0)
    for i in np.ndindex(g_tot.shape):
        ex, ey = complex(et[i]), complex(ep[i])
        er, el = circular_components(ex, ey)
        tot = abs(er) ** 2 + abs(el) ** 2
        if tot <= 0:
            continue
        g_r[i] = g_tot[i] * abs(er) ** 2 / tot
        g_l[i] = g_tot[i] * abs(el) ** 2 / tot
        ar[i] = axial_ratio_db(ex, ey)
    if sense < 0:
        g_r, g_l = g_l, g_r
    if sense == 0:
        co, cross = np.maximum(g_r, g_l), np.minimum(g_r, g_l)
    elif wanted.lower() == "rhcp":
        co, cross = g_r, g_l
    else:
        co, cross = g_l, g_r

    def db(x):
        return np.maximum(FLOOR_DBI, 10 * np.log10(np.maximum(x, 1e-30)))

    return {"gain_total_dbi": db(g_tot), "gain_co_dbic": db(co), "gain_cross_dbic": db(cross), "ar_db": ar}


def cut_summary(theta_deg: np.ndarray, metrics: dict, angles=(45.0, 60.0)) -> dict:
    """Worst-plane numbers at the given off-axis angles, plus front-to-back.

    The grid is expected to hold theta 0..180 and both halves of each cut plane (phi and phi+180),
    so "worst over phi" at a given theta covers both sides of every plane.
    """
    theta_deg = np.asarray(theta_deg, dtype=float)

    def at(values, ang):        # linear interpolation in theta, per phi column
        return np.array([np.interp(ang, theta_deg, values[:, j]) for j in range(values.shape[1])])

    out = {}
    for ang in angles:
        out[f"gain_co_min_{ang:g}"] = float(np.min(at(metrics["gain_co_dbic"], ang)))
        out[f"ar_max_{ang:g}"] = float(np.max(at(metrics["ar_db"], ang)))
    i0, i180 = int(np.argmin(np.abs(theta_deg))), int(np.argmin(np.abs(theta_deg - 180.0)))
    front = float(np.mean(metrics["gain_total_dbi"][i0]))       # theta = 0 is one direction for every phi
    back = float(np.mean(metrics["gain_total_dbi"][i180]))
    out["gain_co_broadside"] = float(np.mean(metrics["gain_co_dbic"][i0]))
    out["ar_broadside"] = float(np.mean(metrics["ar_db"][i0]))
    out["front_to_back_db"] = front - back
    out["theta_180_reached"] = bool(abs(theta_deg[i180] - 180.0) < 1e-6)
    return out


def back_fraction(et: np.ndarray, ep: np.ndarray, theta_deg: np.ndarray, phi_deg: np.ndarray) -> float:
    """Share of the radiated power in the rear hemisphere (theta > 90), from a full-sphere grid.

    Same Riemann sum as the backend's P_rad, so the two are consistent. Assumes uniform spacing.
    """
    theta = np.radians(np.asarray(theta_deg, dtype=float))
    phi = np.radians(np.asarray(phi_deg, dtype=float))
    dth = float(theta[1] - theta[0]) if len(theta) > 1 else 0.0
    dph = float(phi[1] - phi[0]) if len(phi) > 1 else 2 * math.pi
    u = (np.abs(np.asarray(et)) ** 2 + np.abs(np.asarray(ep)) ** 2) / (2 * ETA0)
    w = u * np.sin(theta)[:, None] * dth * dph
    total = float(np.sum(w))
    if total <= 0:
        return float("nan")
    # trapezoid split: a sample on the equator counts half to each hemisphere
    rear = np.where(theta > math.pi / 2 + 1e-9, 1.0, np.where(np.abs(theta - math.pi / 2) <= 1e-9, 0.5, 0.0))
    return float(np.sum(w * rear[:, None])) / total


def write_cuts_csv(path: Path, freqs_hz, theta_deg, phi_deg, per_freq: list[dict]) -> None:
    """One row per (frequency, phi, theta). `per_freq[i]` is angular_metrics() for freqs_hz[i]."""
    with Path(path).open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["frequency_hz", "phi_deg", "theta_deg", "gain_total_dbi", "gain_co_dbic", "gain_cross_dbic", "ar_db"])
        for f, m in zip(freqs_hz, per_freq):
            for j, ph in enumerate(phi_deg):
                for i, th in enumerate(theta_deg):
                    wr.writerow([f"{f:.6e}", f"{ph:.1f}", f"{th:.1f}", f"{m['gain_total_dbi'][i, j]:.2f}",
                                 f"{m['gain_co_dbic'][i, j]:.2f}", f"{m['gain_cross_dbic'][i, j]:.2f}", f"{m['ar_db'][i, j]:.2f}"])


def read_cuts_csv(path: Path) -> dict:
    """Inverse of write_cuts_csv: {'freqs': [...], 'theta': array, 'phi': array, 'metrics': [dict per freq]}."""
    rows = list(csv.DictReader(Path(path).open(newline="")))
    freqs = sorted({float(r["frequency_hz"]) for r in rows})
    theta = np.array(sorted({float(r["theta_deg"]) for r in rows}))
    phi = np.array(sorted({float(r["phi_deg"]) for r in rows}))
    ti = {t: i for i, t in enumerate(theta)}
    pj = {p: j for j, p in enumerate(phi)}
    keys = ("gain_total_dbi", "gain_co_dbic", "gain_cross_dbic", "ar_db")
    metrics = [{k: np.full((len(theta), len(phi)), np.nan) for k in keys} for _ in freqs]
    fi = {f: i for i, f in enumerate(freqs)}
    for r in rows:
        m = metrics[fi[float(r["frequency_hz"])]]
        i, j = ti[float(r["theta_deg"])], pj[float(r["phi_deg"])]
        for k in keys:
            m[k][i, j] = float(r[k])
    return {"freqs": freqs, "theta": theta, "phi": phi, "metrics": metrics}


def signed_cut(theta_deg: np.ndarray, phi_deg: np.ndarray, values: np.ndarray, plane_phi: float):
    """Return (theta_signed, values) for one plane: +theta along phi = plane_phi, -theta along plane_phi + 180."""
    phi_deg = np.asarray(phi_deg, dtype=float)
    j_pos = int(np.argmin(np.abs(phi_deg - plane_phi)))
    j_neg = int(np.argmin(np.abs(phi_deg - ((plane_phi + 180.0) % 360.0))))
    th = np.asarray(theta_deg, dtype=float)
    keep = th <= 180.0
    xs = np.concatenate([-th[keep][::-1], th[keep][1:]])
    ys = np.concatenate([values[keep, j_neg][::-1], values[keep, j_pos][1:]])
    return xs, ys
