# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from bac_cad_preview.mesh import LoadError, hex_to_rgb, kind_of, load, smooth_corner_normals, step_available


def test_hex_to_rgb():
    assert hex_to_rgb("#FFffFF") == (1.0, 1.0, 1.0)
    assert hex_to_rgb("000") == (0.0, 0.0, 0.0)
    assert hex_to_rgb("#A9ADB2") == pytest.approx((0xA9 / 255, 0xAD / 255, 0xB2 / 255))
    with pytest.raises(ValueError):
        hex_to_rgb("#12345")
    with pytest.raises(ValueError):
        hex_to_rgb("zzzzzz")


def test_kind_of():
    assert kind_of(Path("a.STEP")) == "step"
    assert kind_of(Path("a.stp")) == "step"
    assert kind_of(Path("a.stl")) == "mesh"
    assert kind_of(Path("a.kicad_pcb")) == "unknown"


def test_load_stl(box_stl):
    m = load(box_stl, (0.5, 0.5, 0.5))
    assert m.n_triangles == 12
    np.testing.assert_allclose(m.size_mm(), [40, 25, 3])
    assert m.colors.shape == (12, 3) and np.allclose(m.colors, 0.5)
    assert m.stats["colored"] is False


def test_smooth_normals_keep_box_creases(box_mesh):
    """A box has only 90° creases, so every corner normal equals its face normal."""
    v, f = box_mesh.vertices, box_mesh.faces
    n = smooth_corner_normals(v, f, 30.0)
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    fn /= np.linalg.norm(fn, axis=1, keepdims=True)
    np.testing.assert_allclose(n, np.repeat(fn[:, None, :], 3, axis=1), atol=1e-6)


def test_load_unsupported(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("hi")
    with pytest.raises(LoadError):
        load(p, (0.5, 0.5, 0.5))


@pytest.mark.skipif(not step_available(), reason="cadquery-ocp not installed")
def test_load_step_colors(tmp_path):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_ColorSurf, XCAFDoc_DocumentTool

    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    red = st.AddShape(BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 10, 10, 2).Shape(), False)
    ct.SetColor(red, Quantity_Color(0.8, 0.2, 0.1, Quantity_TypeOfColor.Quantity_TOC_sRGB), XCAFDoc_ColorSurf)
    st.AddShape(BRepPrimAPI_MakeBox(gp_Pnt(20, 0, 0), 5, 5, 5).Shape(), False)  # no colour
    st.UpdateAssemblies()
    w = STEPCAFControl_Writer()
    w.SetColorMode(True)
    w.Transfer(doc, STEPControl_AsIs)
    p = tmp_path / "two.step"
    assert w.Write(str(p)) == IFSelect_RetDone

    m = load(p, (0.5, 0.5, 0.5))
    assert m.n_triangles == 24
    np.testing.assert_allclose(m.size_mm(), [25, 10, 5])
    colors = {tuple(round(float(x), 2) for x in c) for c in m.colors}
    assert colors == {(0.8, 0.2, 0.1), (0.5, 0.5, 0.5)}
    assert m.stats["colored"] is True and m.stats["parts"] == 2


def test_load_3mf(tmp_path):
    import trimesh

    p = tmp_path / "box.3mf"
    trimesh.creation.box(extents=(30, 10, 5)).export(p)
    m = load(p, (0.5, 0.5, 0.5))
    assert m.n_triangles == 12
    np.testing.assert_allclose(m.size_mm(), [30, 10, 5])
