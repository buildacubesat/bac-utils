"""Cavity model for an arbitrary patch shape.

Classic cavity model (Lo, Richards) with numerically computed eigenmodes:

* the patch outline, extended by the Hammerstad edge extension, is rasterised;
  open edges are magnetic walls, a shorting tube is a PEC wall;
* the TM eigenmodes follow from a finite-difference Laplacian;
* input impedance is the modal sum  Z = j w mu h sum psi_m(p)^2 / (k_m^2 - k^2 (1 - j delta_m));
* radiation comes from the edge magnetic currents M = 2 E_z h (z x n) over an infinite ground,
  giving Q_rad per mode, directivity, axial ratio and hand (IEEE, e^{jwt}, broadside = +z).

Resonances and mode structure are physical; absolute impedance and gain are cavity-model
estimates (typically within 5–10 % in frequency, tens of percent in resistance).
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.optimize import brentq
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import eigsh
from scipy.special import jv, jvp, yv, yvp

from .config import Config
from .geometry import Shape
from .metrics import BandMetrics, Metrics
from .rf import axial_ratio_db, circular_components

C0 = 299792458.0
MU0 = 4e-7 * math.pi
EPS0 = 1 / (MU0 * C0**2)
ETA0 = MU0 * C0
COPPER_SIGMA = 5.8e7


def eps_eff(eps_r: float, h_mm: float, w_mm: float) -> float:
    return (eps_r + 1) / 2 + (eps_r - 1) / 2 * (1 + 12 * h_mm / w_mm) ** -0.5


def edge_extension_mm(h_mm: float, w_mm: float, ee: float) -> float:
    """Hammerstad open-end extension."""
    return 0.412 * h_mm * (ee + 0.3) * (w_mm / h_mm + 0.264) / ((ee - 0.258) * (w_mm / h_mm + 0.8))


# ------------------------------------------------------------------ rasterise + eigen

def _inside(poly: np.ndarray, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    inside = np.zeros(X.shape, dtype=bool)
    for i in range(len(poly)):
        x1, y1 = poly[i - 1]
        x2, y2 = poly[i]
        if y1 == y2:
            continue
        cross = (y1 > Y) != (y2 > Y)
        x_at = (x2 - x1) * (Y - y1) / (y2 - y1) + x1
        inside ^= cross & (X < x_at)
    return inside


@dataclass
class Grid:
    xs: np.ndarray
    ys: np.ndarray
    d_mm: float
    mask: np.ndarray        # cavity cells
    pec: np.ndarray         # shorting tube cells


def rasterise(shape: Shape, d_mm: float, extension_mm: float) -> Grid:
    poly = np.asarray(shape.outline, dtype=float)
    pad = extension_mm + 3 * d_mm
    xs = np.arange(poly[:, 0].min() - pad + d_mm / 2, poly[:, 0].max() + pad, d_mm)
    ys = np.arange(poly[:, 1].min() - pad + d_mm / 2, poly[:, 1].max() + pad, d_mm)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    R = np.hypot(X, Y)
    copper = _inside(poly, X, Y)
    if shape.hole_radius > 0:
        copper &= R >= shape.hole_radius
    mask = distance_transform_edt(~copper) * d_mm <= extension_mm if extension_mm > 0 else copper
    pec = R < shape.short_radius if shape.short_radius > 0 else np.zeros_like(mask)
    mask &= ~pec
    mask[0, :] = mask[-1, :] = mask[:, 0] = mask[:, -1] = False
    return Grid(xs, ys, d_mm, mask, pec)


def _neighbour(a: np.ndarray, di: int, dj: int) -> np.ndarray:
    out = np.zeros_like(a)
    src = a[max(di, 0): a.shape[0] + min(di, 0), max(dj, 0): a.shape[1] + min(dj, 0)]
    out[max(-di, 0): a.shape[0] + min(-di, 0), max(-dj, 0): a.shape[1] + min(-dj, 0)] = src
    return out


@dataclass
class Modes:
    lam: np.ndarray             # eigenvalues k_m^2, 1/m^2
    vec: np.ndarray             # (cells, n), sum vec^2 = 1
    grid: Grid
    index: np.ndarray           # cell index map, -1 outside
    face_pos: np.ndarray        # (F, 2) m
    face_dir: np.ndarray        # (F, 2) z x n
    face_cell: np.ndarray       # (F,) cell index

    @property
    def d_m(self) -> float:
        return self.grid.d_mm * 1e-3

    def psi_at(self, x_mm: float, y_mm: float) -> np.ndarray:
        """Normalised eigenfunctions (1/m) at a point: nearest cavity cell."""
        g = self.grid
        i = int(np.clip(np.searchsorted(g.xs, x_mm) - 1, 0, len(g.xs) - 1))
        j = int(np.clip(np.searchsorted(g.ys, y_mm) - 1, 0, len(g.ys) - 1))
        best = None
        for di in (0, 1):
            for dj in (0, 1):
                ii, jj = min(i + di, len(g.xs) - 1), min(j + dj, len(g.ys) - 1)
                if self.index[ii, jj] >= 0:
                    dist = math.hypot(g.xs[ii] - x_mm, g.ys[jj] - y_mm)
                    if best is None or dist < best[0]:
                        best = (dist, self.index[ii, jj])
        if best is None:
            raise ValueError(f"feed ({x_mm:.2f}, {y_mm:.2f}) mm is not on the cavity")
        return self.vec[best[1]] / self.d_m


def eigenmodes(grid: Grid, count: int = 12) -> Modes:
    mask, pec, d = grid.mask, grid.pec, grid.d_mm
    index = -np.ones(mask.shape, dtype=int)
    n = int(mask.sum())
    index[mask] = np.arange(n)
    diag = np.zeros(n)
    rows, cols = [], []
    face_pos, face_dir, face_cell = [], [], []
    X, Y = np.meshgrid(grid.xs, grid.ys, indexing="ij")
    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb_mask = _neighbour(mask, di, dj)
        nb_pec = _neighbour(pec, di, dj)
        nb_index = _neighbour(index, di, dj)
        both = mask & nb_mask
        rows.append(index[both])
        cols.append(nb_index[both])
        diag += np.bincount(index[both], minlength=n)
        diag += 2 * np.bincount(index[mask & nb_pec], minlength=n)
        open_face = mask & ~nb_mask & ~nb_pec
        cells = index[open_face]
        face_cell.append(cells)
        face_pos.append(np.column_stack([X[open_face] + di * d / 2, Y[open_face] + dj * d / 2]))
        # z x n for outward normal (di, dj)
        face_dir.append(np.tile([-dj, di], (len(cells), 1)))
    r = np.concatenate(rows)
    c = np.concatenate(cols)
    A = csr_matrix((np.full(len(r), -1.0), (r, c)), shape=(n, n))
    A = A + csr_matrix((diag, (np.arange(n), np.arange(n))), shape=(n, n))
    A = A / d**2
    k = min(count, n - 2)
    lam, vec = eigsh(A, k=k, sigma=-1e-4, which="LM")
    order = np.argsort(lam)
    lam, vec = np.maximum(lam[order], 0.0), vec[:, order]
    return Modes(lam * 1e6, vec, grid, index, np.concatenate(face_pos) * 1e-3,
                 np.concatenate(face_dir).astype(float), np.concatenate(face_cell))


# ------------------------------------------------------------------ radiation

def _directions(n_theta: int = 18, n_phi: int = 36):
    dt, dp = (math.pi / 2) / n_theta, 2 * math.pi / n_phi
    th = (np.arange(n_theta) + 0.5) * dt
    ph = np.arange(n_phi) * dp
    T, P = np.meshgrid(th, ph, indexing="ij")
    return T.ravel(), P.ravel(), (np.sin(T) * dt * dp).ravel()


def radiation_vectors(modes: Modes, h_m: float, k0: float, theta, phi):
    """Magnetic radiation vectors Lx, Ly, shape (n_modes, n_dirs)."""
    u, v = np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi)
    phase = np.exp(1j * k0 * (np.outer(modes.face_pos[:, 0], u) + np.outer(modes.face_pos[:, 1], v)))
    m = 2 * h_m * modes.vec[modes.face_cell]      # psi (1/m) * face length (m) = vec
    lx = (m * modes.face_dir[:, [0]]).T @ phase
    ly = (m * modes.face_dir[:, [1]]).T @ phase
    return lx, ly


def far_field(lx, ly, k0: float, theta, phi):
    lt = (lx * np.cos(phi) + ly * np.sin(phi)) * np.cos(theta)
    lp = -lx * np.sin(phi) + ly * np.cos(phi)
    return -1j * k0 / (4 * math.pi) * lp, 1j * k0 / (4 * math.pi) * lt


def broadside(modes: Modes, h_m: float, k0: float) -> tuple[np.ndarray, np.ndarray]:
    """Per-mode broadside (Ex, Ey) for unit modal amplitude."""
    m = 2 * h_m * modes.vec[modes.face_cell]
    lx = (m * modes.face_dir[:, [0]]).sum(axis=0)
    ly = (m * modes.face_dir[:, [1]]).sum(axis=0)
    return -1j * k0 / (4 * math.pi) * ly, 1j * k0 / (4 * math.pi) * lx


# ------------------------------------------------------------------ the model

@dataclass
class Cavity:
    modes: Modes
    h_m: float
    gap_m: float
    ee: float
    tan_d: float
    feeds_psi: np.ndarray       # (ports, n)
    q_rad: np.ndarray           # per mode
    f_modes: np.ndarray
    probe_radius_m: float
    pad_c: float | None
    z0: float
    extension_mm: float

    @classmethod
    def build(cls, shape: Shape, config: Config, grid_mm: float | None = None, count: int | None = None) -> "Cavity":
        cav = config.cavity
        h = config.patch_height_mm()
        eq = config.epsilon_eq()
        ee = eps_eff(eq, h, shape.fringe_width_mm)
        ext = edge_extension_mm(h, shape.fringe_width_mm, ee) * float(cav.get("extension_scale", 1.0))
        d = grid_mm or float(cav.get("grid_mm", 0.5))
        modes = eigenmodes(rasterise(shape, d, ext), count or int(cav.get("modes", 12)))
        f_modes = C0 * np.sqrt(modes.lam) / (2 * math.pi * math.sqrt(ee))
        psi = np.array([modes.psi_at(x, y) for x, y in shape.feeds])
        h_m = h * 1e-3
        theta, phi, dom = _directions()
        q = np.full(len(f_modes), np.inf)
        stored = EPS0 * ee * h_m / 2
        for i, f in enumerate(f_modes):
            if f < 1e6:
                continue
            k0 = 2 * math.pi * f / C0
            lx, ly = radiation_vectors(modes, h_m, k0, theta, phi)
            et, ep = far_field(lx[i], ly[i], k0, theta, phi)
            p = float(np.sum((abs(et) ** 2 + abs(ep) ** 2) * dom) / (2 * ETA0))
            q[i] = 2 * math.pi * f * stored / p if p > 0 else np.inf
        s, f = config.stack, config.feed
        return cls(modes, h_m, float(s["gap_mm"]) * 1e-3, ee, config.loss_tangent_eq(), psi, q, f_modes,
                   float(f["probe_diameter_mm"]) * 0.5e-3, None, float(f["impedance_ohm"]), ext)

    def with_pad(self, radius_mm: float, config: Config) -> "Cavity":
        s = config.stack
        self.pad_c = EPS0 * float(s["top_board_epsilon_r"]) * math.pi * (radius_mm * 1e-3) ** 2 / (float(s["top_board_mm"]) * 1e-3)
        return self

    def delta(self, f: float) -> np.ndarray:
        qc = self.h_m * math.sqrt(math.pi * f * MU0 * COPPER_SIGMA)
        with np.errstate(divide="ignore"):
            return 1 / self.q_rad + self.tan_d + 1 / qc

    def feed_series(self, f: float) -> complex:
        w = 2 * math.pi * f
        k0 = w / C0
        x = ETA0 * k0 * self.gap_m / (2 * math.pi) * (math.log(2 / (k0 * self.probe_radius_m)) - 0.5772)
        z = 1j * x
        if self.pad_c:
            z += 1 / (1j * w * self.pad_c)
        return z

    def z_matrix(self, f: float) -> tuple[np.ndarray, np.ndarray]:
        w = 2 * math.pi * f
        k2 = (w / C0) ** 2 * self.ee
        den = self.modes.lam - k2 * (1 - 1j * self.delta(f))
        zc = 1j * w * MU0 * self.h_m * (self.feeds_psi / den) @ self.feeds_psi.T
        z = zc + np.eye(len(zc)) * self.feed_series(f)
        return z, den

    def drive(self, f: float, a: np.ndarray):
        z, den = self.z_matrix(f)
        n = len(a)
        i = np.linalg.solve(z + self.z0 * np.eye(n), 2 * math.sqrt(self.z0) * a)
        b = (z - self.z0 * np.eye(n)) @ i / (2 * math.sqrt(self.z0))
        amp = -1j * 2 * math.pi * f * MU0 * (i @ self.feeds_psi) / den
        v = z @ i
        p_acc = 0.5 * float(np.real(np.vdot(i, v)))
        return b, amp, p_acc, den

    def reflection(self, f: float, a: np.ndarray) -> complex:
        b, *_ = self.drive(f, a)
        # through an ideal hybrid the reflected waves return with the same transmission factors
        return complex(np.dot(a, b)) if len(a) > 1 else complex(b[0] / a[0])

    def radiation(self, f: float, a: np.ndarray, lxly) -> dict:
        """Gain, AR and hand at f. `lxly` = hemisphere radiation vectors (precomputed near f)."""
        b, amp, p_acc, den = self.drive(f, a)
        k0 = 2 * math.pi * f / C0
        theta, phi, dom = _directions()
        lx, ly = lxly
        et, ep = far_field(amp @ lx, amp @ ly, k0, theta, phi)
        p_rad = float(np.sum((abs(et) ** 2 + abs(ep) ** 2) * dom) / (2 * ETA0))
        qc = self.h_m * math.sqrt(math.pi * f * MU0 * COPPER_SIGMA)
        w_tot = EPS0 * self.ee * self.h_m / 2 * np.abs(amp) ** 2
        p_diss = float(np.sum(2 * math.pi * f * w_tot * (self.tan_d + 1 / qc)))
        bx, by = broadside(self.modes, self.h_m, k0)
        ex, ey = complex(amp @ bx), complex(amp @ by)
        u0 = (abs(ex) ** 2 + abs(ey) ** 2) / (2 * ETA0)
        d0 = 4 * math.pi * u0 / p_rad if p_rad > 0 else 0.0
        e_rad = p_rad / (p_rad + p_diss) if p_rad > 0 else 0.0
        p_inc = 0.5 * float(np.sum(np.abs(a) ** 2))
        g = d0 * e_rad * max(p_acc, 0.0) / p_inc
        er, el = circular_components(ex, ey)
        tot = abs(er) ** 2 + abs(el) ** 2
        return {"ex": ex, "ey": ey, "gain_lin": g, "g_rhcp": g * abs(er) ** 2 / tot if tot else 0.0,
                "g_lhcp": g * abs(el) ** 2 / tot if tot else 0.0, "ar_db": axial_ratio_db(ex, ey),
                "e_rad": e_rad, "d0": d0}

    def mode_table(self, k_ref: float) -> list[dict]:
        bx, by = broadside(self.modes, self.h_m, k_ref)
        norm = np.sqrt(np.abs(bx) ** 2 + np.abs(by) ** 2)
        out = []
        top = norm.max() if len(norm) else 1.0
        for i, f in enumerate(self.f_modes):
            if f < 1e6:
                kind = "static"
            elif norm[i] < 0.05 * top:
                kind = "no broadside (monopolar/higher)"
            else:
                angle = math.degrees(math.atan2(abs(by[i]), abs(bx[i])))
                kind = "broadside, x-pol" if angle < 30 else "broadside, y-pol" if angle > 60 else f"broadside, {angle:.0f} deg"
            out.append({"f_hz": float(f), "q_rad": float(self.q_rad[i]), "kind": kind})
        return out


def _excitations(config: Config) -> list[np.ndarray]:
    if config.feed["mode"] == "dual":
        from .rf import hybrid_weights

        pol = config.polarization
        return hybrid_weights(float(pol.get("hybrid_phase_deg", 90.0)), float(pol.get("hybrid_amplitude_db", 0.0)))
    return [np.array([1.0 + 0j])]


def evaluate_cavity(cav: Cavity, config: Config) -> Metrics:
    wanted = config.polarization["hand"].lower()
    bands = config.bands
    primary = config.primary_band
    theta, phi, _ = _directions()
    lx_cache = {}

    def lxly(fc: float):
        if fc not in lx_cache:
            lx_cache[fc] = radiation_vectors(cav.modes, cav.h_m, 2 * math.pi * fc / C0, theta, phi)
        return lx_cache[fc]

    # dual feed: pick the hybrid orientation that radiates the wanted hand
    options = _excitations(config)
    a = options[0]
    if len(options) > 1:
        key = "g_rhcp" if wanted == "rhcp" else "g_lhcp"
        a = max(options, key=lambda x: cav.radiation(primary.centre_hz, x, lxly(primary.centre_hz))[key])

    lo = min(b.low_hz for b in bands) - 0.1e9
    hi = max(b.high_hz for b in bands) + 0.1e9
    sweep = np.linspace(lo, hi, 401)
    s11 = np.array([abs(cav.reflection(f, a)) for f in sweep])
    s11_db = 20 * np.log10(np.maximum(s11, 1e-9))
    out = {}
    for band in bands:
        sel = (sweep >= band.low_hz) & (sweep <= band.high_hz)
        c = band.centre_hz
        samples = np.linspace(band.low_hz, band.high_hz, 5)
        cp = np.linspace(c - band.cp_span_hz / 2, c + band.cp_span_hz / 2, 5)
        rad = {f: cav.radiation(f, a, lxly(c)) for f in sorted(set(samples) | set(cp))}
        key = "g_rhcp" if wanted == "rhcp" else "g_lhcp"
        centre = cav.radiation(c, a, lxly(c))
        if centre["ar_db"] > 20:
            hand = "linear"
        else:
            hand = "rhcp" if centre["g_rhcp"] > centre["g_lhcp"] else "lhcp"
        out[band.name] = BandMetrics(
            s11_worst_db=float(s11_db[sel].max()),
            gain_min_dbic=float(10 * math.log10(max(1e-6, min(rad[f][key] for f in samples)))),
            ar_worst_db=float(max(rad[f]["ar_db"] for f in cp)),
            efficiency_percent=100 * centre["e_rad"],
            hand=hand,
        )
    modes = tuple(cav.mode_table(2 * math.pi * primary.centre_hz / C0))
    note = f"cavity model; edge extension {cav.extension_mm:.2f} mm, eps_eff {cav.ee:.3f}"
    return Metrics(out, float(sweep[int(np.argmin(s11))]), modes, note)


class CavityBackend:
    name = "cavity"

    def evaluate(self, params: dict, config: Config, directory: Path) -> Metrics:
        from .topologies import get_topology

        shape = get_topology(config).shape(params, config)
        cav = Cavity.build(shape, config)
        if "pad_radius_mm" in params:
            cav.with_pad(params["pad_radius_mm"], config)
        return evaluate_cavity(cav, config)


# ------------------------------------------------------------------ analytic references (tests)

def ring_root(inner_over_outer: float, shorted_inner: bool, n: int = 1) -> float:
    """Smallest k*b for an annular cavity: magnetic wall at b; magnetic (open) or electric (shorted) wall at a."""
    r = inner_over_outer
    if shorted_inner:
        g = lambda x: jv(n, x * r) * yvp(n, x) - jvp(n, x) * yv(n, x * r)
    else:
        g = lambda x: jvp(n, x * r) * yvp(n, x) - jvp(n, x) * yvp(n, x * r)
    xs = np.linspace(0.05, 12, 6000)
    v = g(xs)
    for i in range(len(xs) - 1):
        if np.isfinite(v[i]) and np.isfinite(v[i + 1]) and np.sign(v[i]) != np.sign(v[i + 1]):
            return brentq(g, xs[i], xs[i + 1])
    raise ValueError("no root")


def bore_isolation_db_per_mm(bore_diameter_mm: float, f_hz: float) -> float:
    """TE11 attenuation of a circular bore below cutoff."""
    fc = 1.8412 * C0 / (math.pi * bore_diameter_mm * 1e-3)
    if f_hz >= fc:
        return 0.0
    return 20 * math.log10(math.e) * (1.8412 / (bore_diameter_mm / 2)) * math.sqrt(1 - (f_hz / fc) ** 2)
