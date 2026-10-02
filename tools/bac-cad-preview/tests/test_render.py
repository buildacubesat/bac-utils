# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np
import pytest
from bac_cad_preview.camera import view_rotation
from bac_cad_preview.gizmo import GizmoSpec, choose_unit, draw_gizmo, format_unit
from bac_cad_preview.image import OUTPUT_SIZE, crop_pad_square_resize_rgba
from bac_cad_preview.mesh import Mesh, smooth_corner_normals
from bac_cad_preview.raster import RENDER_FILL, RENDER_SIZE, render
from PIL import Image


def _quad(z: float, color, size=10.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    v = np.array([[-size, -size, z], [size, -size, z], [size, size, z], [-size, size, z]], np.float64)
    f = np.array([[0, 1, 2], [0, 2, 3]], np.int64)
    c = np.tile(np.asarray(color, np.float32), (2, 1))
    return v, f, c


def _mesh(*quads) -> Mesh:
    vs, fs, cs, off = [], [], [], 0
    for v, f, c in quads:
        vs.append(v)
        fs.append(f + off)
        cs.append(c)
        off += len(v)
    v = np.vstack(vs)
    f = np.vstack(fs)
    return Mesh(v, f, smooth_corner_normals(v, f, 30.0), np.vstack(cs))


def test_render_fills_canvas_fraction(box_mesh):
    r = render(box_mesh, view_rotation(), edges=False)
    assert r.image.shape == (RENDER_SIZE, RENDER_SIZE, 4)
    alpha = r.image[:, :, 3] > 0
    rows = np.nonzero(alpha.any(axis=1))[0]
    cols = np.nonzero(alpha.any(axis=0))[0]
    extent = max(rows[-1] - rows[0], cols[-1] - cols[0]) + 1
    assert extent == pytest.approx(RENDER_SIZE * RENDER_FILL, rel=0.01)
    # centred
    assert (rows[0] + rows[-1]) / 2 == pytest.approx(RENDER_SIZE / 2, abs=2)
    assert (cols[0] + cols[-1]) / 2 == pytest.approx(RENDER_SIZE / 2, abs=2)


def test_depth_test_keeps_nearer_quad():
    far = _quad(0.0, (1.0, 0.0, 0.0))
    near = _quad(1.0, (0.0, 0.0, 1.0), size=5.0)
    m = _mesh(far, near)
    r = render(m, np.eye(3), edges=False)
    c = r.image[RENDER_SIZE // 2, RENDER_SIZE // 2]
    assert c[2] > c[0] and c[3] == 255  # blue (near) wins at the centre
    corner = r.image[int(RENDER_SIZE * 0.15), int(RENDER_SIZE * 0.15)]
    assert corner[0] > corner[2]  # red (far) visible where the near quad does not cover


def test_order_independence():
    far = _quad(0.0, (1.0, 0.0, 0.0))
    near = _quad(1.0, (0.0, 0.0, 1.0), size=5.0)
    a = render(_mesh(far, near), np.eye(3), edges=False).image
    b = render(_mesh(near, far), np.eye(3), edges=False).image
    assert np.array_equal(a, b)


def test_edges_darken_silhouette():
    far = _quad(0.0, (0.8, 0.8, 0.8))
    near = _quad(2.0, (0.8, 0.8, 0.8), size=5.0)
    m = _mesh(far, near)
    plain = render(m, np.eye(3), edges=False).image
    edged = render(m, np.eye(3), edges=True).image
    assert plain[:, :, :3].sum() > edged[:, :, :3].sum()
    assert np.array_equal(plain[:, :, 3], edged[:, :, 3])  # coverage unchanged


def test_two_sided_shading():
    """A quad seen from behind is lit like one seen from the front."""
    v, f, c = _quad(0.0, (0.5, 0.5, 0.5))
    front = render(_mesh((v, f, c)), np.eye(3), edges=False).image
    back = render(_mesh((v, f[:, ::-1], c)), np.eye(3), edges=False).image
    assert np.array_equal(front[:, :, 3], back[:, :, 3])
    assert np.abs(front.astype(int) - back.astype(int)).max() <= 1  # rounding of the interpolated intensity


def test_crop_pad_square_resize_geometry():
    img = Image.new("RGBA", (2160, 2160), (0, 0, 0, 0))
    img.paste((255, 0, 0, 255), (500, 800, 1500, 1200))  # 1000 × 400 content
    framed = crop_pad_square_resize_rgba(img)
    assert framed.image.size == (OUTPUT_SIZE, OUTPUT_SIZE)
    alpha = np.asarray(framed.image)[:, :, 3] > 128  # ignore the resampling fringe
    cols = np.nonzero(alpha.any(axis=0))[0]
    rows = np.nonzero(alpha.any(axis=1))[0]
    assert cols[-1] - cols[0] + 1 == pytest.approx(OUTPUT_SIZE / 1.2, abs=2)  # 10 % pad per side
    assert (rows[0] + rows[-1]) / 2 == pytest.approx(OUTPUT_SIZE / 2, abs=2)
    assert framed.scale == pytest.approx(OUTPUT_SIZE / 1200)
    # mapping check: content left edge (render x=500) lands at the padded left edge
    assert (500 - framed.offset[0]) * framed.scale == pytest.approx(cols[0], abs=1.5)


def test_crop_empty_raises():
    with pytest.raises(ValueError):
        crop_pad_square_resize_rgba(Image.new("RGBA", (10, 10), (0, 0, 0, 0)))


def test_choose_unit():
    assert choose_unit(28.7) == 2  # 22 mm board: 2 mm = 57 px, 5 mm = 144 px
    assert choose_unit(5.5) == 10  # 55 px
    assert choose_unit(9.5) == 5  # 10 mm would be 95 px, over the 90 px budget
    assert choose_unit(0.05) == 1000
    assert choose_unit(5000.0) == 0.1  # never below the smallest unit
    assert format_unit(2) == "2 mm"
    assert format_unit(0.5) == "0.5 mm"
    assert format_unit(1000) == "1 m"


def test_draw_gizmo_bottom_left_only():
    base = Image.new("RGBA", (OUTPUT_SIZE, OUTPUT_SIZE), (0, 0, 0, 0))
    out = draw_gizmo(base, GizmoSpec(unit_mm=2, px_per_mm=28.7, rot=view_rotation(), size=OUTPUT_SIZE))
    assert out.size == base.size
    a = np.asarray(out)[:, :, 3]
    assert a[: OUTPUT_SIZE // 2].max() == 0 and a[:, OUTPUT_SIZE // 2 :].max() == 0
    assert a[OUTPUT_SIZE // 2 :, : OUTPUT_SIZE // 2].max() > 0
    # nothing touches the outer margin
    assert a[:, :8].max() == 0 and a[-8:, :].max() == 0


def test_gizmo_axis_length_is_true_scale():
    """The Z axis is vertical in the default view: origin dot and end bar sit unit × px/mm × cos(22.5°) apart."""
    base = Image.new("RGBA", (OUTPUT_SIZE, OUTPUT_SIZE), (0, 0, 0, 0))
    spec = GizmoSpec(unit_mm=2, px_per_mm=28.7, rot=view_rotation(), size=OUTPUT_SIZE, show_label=False)
    out = np.asarray(draw_gizmo(base, spec))
    blue = (out[:, :, 2] > 150) & (out[:, :, 0] < 160) & (out[:, :, 1] < 190) & (out[:, :, 3] > 100)
    counts = blue.sum(axis=1)
    wide = np.nonzero(counts >= 10)[0]  # the end bar (12 px wide) and the "Zp" letters above it; the axis is 2 px
    bar_rows = np.split(wide, np.nonzero(np.diff(wide) > 1)[0] + 1)[-1]  # the cluster nearest the origin is the bar
    assert bar_rows.size >= 1
    grey = (
        (np.abs(out[:, :, 0].astype(int) - 0x6E) < 12)
        & (np.abs(out[:, :, 2].astype(int) - 0x6E) < 12)
        & (out[:, :, 3] > 100)
    )
    dot_rows = np.nonzero(grey.sum(axis=1) >= 3)[0]  # the origin dot
    assert dot_rows.size >= 1
    unit_px = 2 * 28.7 * np.cos(np.radians(22.5))
    assert dot_rows.mean() - bar_rows.mean() == pytest.approx(unit_px, abs=1.5)


def test_choose_unit_keeps_axis_under_max():
    from bac_cad_preview.gizmo import MAX_AXIS_PX

    for ppm in (0.5, 1.9, 6.8, 12.9, 28.7, 100.0):
        assert choose_unit(ppm) * ppm <= MAX_AXIS_PX or choose_unit(ppm) == 0.1
