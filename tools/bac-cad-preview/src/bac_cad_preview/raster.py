# SPDX-License-Identifier: MIT
"""Orthographic z-buffer rasterizer in numpy (no OpenGL, no display).

Triangles are scan-converted exactly: for every pixel row a triangle covers,
the span between its edge crossings is filled, so cost is proportional to the
covered pixels and no bucketing by triangle size is needed.  Samples are taken
at pixel centres; depth and shading are interpolated with barycentric weights.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .mesh import Mesh

RENDER_SIZE = 2160  # square render canvas, px (matches the artifacts tool)
RENDER_FILL = 0.8  # fraction of the canvas the model's larger extent fills
SAMPLE_BUDGET = 4_000_000  # pixel samples per rasterization chunk


EDGE_DEPTH_FRAC = 0.004  # depth step (fraction of the model diagonal) that counts as a silhouette
EDGE_NORMAL_COS = 0.848  # neighbouring face normals below this cosine (~32°) form a crease
EDGE_DARKEN = 0.62  # colour multiplier on edge pixels (at render resolution)


@dataclass
class Lighting:
    ambient: float = 0.26
    # (direction toward the light in view space, intensity); normalised at use
    lights: list[tuple[tuple[float, float, float], float]] = field(
        default_factory=lambda: [((0.0, 0.0, 1.0), 0.30), ((-0.4, 0.6, 0.7), 0.44)]
    )
    world_top: float = 0.20  # light along the model's Zp axis (board normal), like KiCad's side lights at elevation 90


@dataclass
class RenderResult:
    image: np.ndarray  # (H, W, 4) uint8 RGBA, transparent background
    px_per_mm: float
    center_px: tuple[float, float]  # canvas position of the model's bbox centre


def shade(mesh: Mesh, rot: np.ndarray, lighting: Lighting) -> tuple[np.ndarray, np.ndarray]:
    """Per-corner intensity (M, 3) in [0, 1] with two-sided Lambert shading, and the
    camera-facing unit face normals (M, 3) in view space."""
    n = mesh.normals.reshape(-1, 3) @ rot.T  # view space
    n = n.reshape(mesh.normals.shape)
    v = mesh.vertices @ rot.T
    f = mesh.faces
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    flip = fn[:, 2] < 0
    n = n.copy()
    n[flip] = -n[flip]
    fn[flip] = -fn[flip]
    lights = [(np.asarray(d, np.float64) / np.linalg.norm(d), k) for d, k in lighting.lights]
    if lighting.world_top:
        lights.append((rot @ np.array([0.0, 0.0, 1.0]), lighting.world_top))
    intensity = np.full(n.shape[:2], lighting.ambient, np.float32)
    for d, k in lights:
        intensity += k * np.maximum(0.0, n @ d).astype(np.float32)
    return np.clip(intensity, 0.0, 1.0), fn.astype(np.float32)


def edge_mask(zbuf: np.ndarray, nbuf: np.ndarray, depth_step: float) -> np.ndarray:
    """Pixels on a silhouette (depth jump) or crease (normal jump) between two covered pixels."""
    H, W = zbuf.shape
    covered = np.isfinite(zbuf)
    z = np.where(covered, zbuf, 0.0)
    mask = np.zeros((H, W), bool)
    for axis in (0, 1):
        a = np.take(z, np.arange(0, z.shape[axis] - 1), axis=axis)
        b = np.take(z, np.arange(1, z.shape[axis]), axis=axis)
        ca = np.take(covered, np.arange(0, z.shape[axis] - 1), axis=axis)
        cb = np.take(covered, np.arange(1, z.shape[axis]), axis=axis)
        na = np.take(nbuf, np.arange(0, z.shape[axis] - 1), axis=axis)
        nb = np.take(nbuf, np.arange(1, z.shape[axis]), axis=axis)
        both = ca & cb
        depth_edge = both & (np.abs(a - b) > depth_step)
        crease = both & (np.einsum("...i,...i->...", na, nb) < EDGE_NORMAL_COS)
        e = depth_edge | crease
        if axis == 0:
            mask[:-1] |= e
            mask[1:] |= e
        else:
            mask[:, :-1] |= e
            mask[:, 1:] |= e
    return mask


def render(
    mesh: Mesh,
    rot: np.ndarray,
    size: int = RENDER_SIZE,
    fill: float = RENDER_FILL,
    lighting: Lighting | None = None,
    edges: bool = True,
    progress: Callable[[float], None] | None = None,
) -> RenderResult:
    lighting = lighting or Lighting()
    lo, hi = mesh.bounds()
    center = (lo + hi) / 2.0
    v = (mesh.vertices - center) @ rot.T
    x, y, depth = v[:, 0], v[:, 1], -v[:, 2]  # camera looks down -Z, so nearer = smaller depth
    xmin, xmax, ymin, ymax = x.min(), x.max(), y.min(), y.max()
    extent = max(xmax - xmin, ymax - ymin)
    if extent <= 0:
        raise ValueError("model has no extent in the view plane")
    s = size * fill / extent
    cx = size / 2.0 - (xmin + xmax) / 2.0 * s
    cy = size / 2.0 + (ymin + ymax) / 2.0 * s
    px = cx + x * s
    py = cy - y * s

    f = mesh.faces
    P = px[f]  # (M, 3)
    Q = py[f]
    D = depth[f].astype(np.float32)
    I, fnorm = shade(mesh, rot, lighting)  # noqa: E741
    albedo = mesh.colors.astype(np.float32)

    W = H = size
    zbuf = np.full(W * H, np.inf, np.float32)
    cbuf = np.zeros((W * H, 3), np.float32)
    nbuf = np.zeros((W * H, 3), np.float32)

    # drop degenerate triangles and those fully outside the canvas
    area = (P[:, 1] - P[:, 0]) * (Q[:, 2] - Q[:, 0]) - (P[:, 2] - P[:, 0]) * (Q[:, 1] - Q[:, 0])
    j0 = np.ceil(Q.min(axis=1) - 0.5)
    j1 = np.floor(Q.max(axis=1) - 0.5)
    i0 = np.ceil(P.min(axis=1) - 0.5)
    i1 = np.floor(P.max(axis=1) - 0.5)
    keep = (np.abs(area) > 1e-9) & (j1 >= 0) & (j0 <= H - 1) & (i1 >= 0) & (i0 <= W - 1)
    idx_all = np.nonzero(keep)[0]
    if idx_all.size == 0:
        return RenderResult(_to_rgba(cbuf, zbuf, W, H), s, (cx, cy))

    est = (np.minimum(i1, W - 1) - np.maximum(i0, 0) + 1) * (np.minimum(j1, H - 1) - np.maximum(j0, 0) + 1)
    est = np.maximum(est[idx_all], 1)
    bounds = np.searchsorted(
        np.cumsum(est), np.arange(SAMPLE_BUDGET, est.sum() + SAMPLE_BUDGET, SAMPLE_BUDGET), side="right"
    )
    starts = [0, *bounds.tolist()]
    chunks = [(a, b) for a, b in zip(starts, starts[1:] + [idx_all.size], strict=False) if b > a]

    for n_chunk, (a, b) in enumerate(chunks):
        t_idx = idx_all[a:b]
        _raster_chunk(
            P[t_idx], Q[t_idx], D[t_idx], I[t_idx], albedo[t_idx], fnorm[t_idx], area[t_idx], W, H, zbuf, cbuf, nbuf
        )
        if progress:
            progress((n_chunk + 1) / len(chunks))

    if edges:
        diag = float(np.linalg.norm(hi - lo))
        mask = edge_mask(zbuf.reshape(H, W), nbuf.reshape(H, W, 3), diag * EDGE_DEPTH_FRAC)
        cbuf[mask.reshape(-1)] *= EDGE_DARKEN
    return RenderResult(_to_rgba(cbuf, zbuf, W, H), s, (cx, cy))


def _to_rgba(cbuf: np.ndarray, zbuf: np.ndarray, W: int, H: int) -> np.ndarray:
    out = np.zeros((H * W, 4), np.uint8)
    covered = np.isfinite(zbuf)
    out[:, :3] = np.clip(cbuf * 255.0 + 0.5, 0, 255).astype(np.uint8)
    out[covered, 3] = 255
    out[~covered, :3] = 0
    return out.reshape(H, W, 4)


def _raster_chunk(P, Q, D, I, albedo, fnorm, area, W, H, zbuf, cbuf, nbuf) -> None:  # noqa: E741
    m = P.shape[0]
    j0 = np.maximum(np.ceil(Q.min(axis=1) - 0.5), 0).astype(np.int64)
    j1 = np.minimum(np.floor(Q.max(axis=1) - 0.5), H - 1).astype(np.int64)
    nrows = np.maximum(j1 - j0 + 1, 0)
    total_rows = int(nrows.sum())
    if total_rows == 0:
        return
    tri = np.repeat(np.arange(m), nrows)
    row_start = np.cumsum(nrows) - nrows
    j = j0[tri] + (np.arange(total_rows) - np.repeat(row_start, nrows))
    yc = j + 0.5

    xl = np.full(total_rows, np.inf)
    xr = np.full(total_rows, -np.inf)
    for ea, eb in ((0, 1), (1, 2), (2, 0)):
        xa, ya = P[tri, ea], Q[tri, ea]
        xb, yb = P[tri, eb], Q[tri, eb]
        dy = yb - ya
        crosses = ((yc - ya) * (yc - yb) <= 0) & (dy != 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            xc = xa + (yc - ya) * (xb - xa) / dy
        xc = np.where(crosses, xc, np.nan)
        xl = np.fmin(xl, xc)
        xr = np.fmax(xr, xc)
        horiz = (dy == 0) & (ya == yc)
        if horiz.any():
            lo = np.minimum(xa, xb)
            hi = np.maximum(xa, xb)
            xl = np.where(horiz, np.minimum(xl, lo), xl)
            xr = np.where(horiz, np.maximum(xr, hi), xr)

    valid = np.isfinite(xl) & np.isfinite(xr)
    i0 = np.where(valid, np.maximum(np.ceil(np.where(valid, xl, 0) - 0.5), 0), 0).astype(np.int64)
    i1 = np.where(valid, np.minimum(np.floor(np.where(valid, xr, 0) - 0.5), W - 1), -1).astype(np.int64)
    npx = np.maximum(i1 - i0 + 1, 0)
    total = int(npx.sum())
    if total == 0:
        return
    row_of = np.repeat(np.arange(total_rows), npx)
    px_start = np.cumsum(npx) - npx
    i = i0[row_of] + (np.arange(total) - np.repeat(px_start, npx))
    jj = j[row_of]
    t = tri[row_of]

    sx = i.astype(np.float64) + 0.5
    sy = jj.astype(np.float64) + 0.5
    x0, y0 = P[t, 0], Q[t, 0]
    x1, y1 = P[t, 1], Q[t, 1]
    x2, y2 = P[t, 2], Q[t, 2]
    inv = 1.0 / area[t]
    w0 = ((x1 - sx) * (y2 - sy) - (x2 - sx) * (y1 - sy)) * inv
    w1 = ((x2 - sx) * (y0 - sy) - (x0 - sx) * (y2 - sy)) * inv
    w2 = 1.0 - w0 - w1
    w0 = w0.astype(np.float32)
    w1 = w1.astype(np.float32)
    w2 = w2.astype(np.float32)
    del sx, sy, x0, y0, x1, y1, x2, y2, inv

    depth = w0 * D[t, 0] + w1 * D[t, 1] + w2 * D[t, 2]
    inten = w0 * I[t, 0] + w1 * I[t, 1] + w2 * I[t, 2]
    pix = jj * W + i

    order = np.lexsort((depth, pix))
    pix_s = pix[order]
    first = np.empty(order.size, bool)
    first[0] = True
    first[1:] = pix_s[1:] != pix_s[:-1]
    sel = order[first]
    p = pix[sel]
    d = depth[sel]
    closer = d < zbuf[p]
    p = p[closer]
    sel = sel[closer]
    zbuf[p] = d[closer]
    cbuf[p] = albedo[t[sel]] * np.clip(inten[sel], 0.0, 1.0)[:, None]
    nbuf[p] = fnorm[t[sel]]
