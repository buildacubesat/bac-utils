# SPDX-License-Identifier: MIT
"""Regenerate the example models: bracket.stl (trimesh), demo-board.step and assembly-board.step (OCP, with colours).

From the bac-utils root: uv run --extra step python tools/bac-cad-preview/examples/make_examples.py
"""

from __future__ import annotations

import math
from pathlib import Path

import trimesh

HERE = Path(__file__).parent


def make_bracket() -> None:
    base = trimesh.creation.box(extents=(40, 25, 3))
    base.apply_translation((0, 0, 1.5))
    wall = trimesh.creation.box(extents=(3, 25, 20))
    wall.apply_translation((-18.5, 0, 10))
    boss = trimesh.creation.cylinder(radius=4, height=8, sections=48)
    boss.apply_translation((8, 0, 4))
    trimesh.util.concatenate([base, wall, boss]).export(HERE / "bracket.stl")


def make_steps() -> None:
    from OCP.BRep import BRep_Builder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS, TopoDS_Compound
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_ColorSurf, XCAFDoc_DocumentTool

    srgb = Quantity_TypeOfColor.Quantity_TOC_sRGB

    def col(r: float, g: float, b: float) -> Quantity_Color:
        return Quantity_Color(r, g, b, srgb)

    def new_doc():
        app = XCAFApp_Application.GetApplication_s()
        doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
        app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
        return doc, XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()), XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

    def write(doc, st, name: str) -> None:
        st.UpdateAssemblies()
        w = STEPCAFControl_Writer()
        w.SetColorMode(True)
        w.Transfer(doc, STEPControl_AsIs)
        if w.Write(str(HERE / name)) != IFSelect_RetDone:
            raise SystemExit(f"could not write {name}")

    # demo-board.step: a 22 × 17.5 mm board with a hole, pads, an IC, a capacitor with a lighter
    # top face, a can and a marker
    doc, st, ct = new_doc()
    board = BRepPrimAPI_MakeBox(gp_Pnt(-11, -8.75, 0), 22, 17.5, 1.6).Shape()
    hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(8, 6, -1), gp_Dir(0, 0, 1)), 1.1, 5).Shape()
    board = BRepAlgoAPI_Cut(board, hole).Shape()
    ct.SetColor(st.AddShape(board, False), col(0.07, 0.35, 0.16), XCAFDoc_ColorSurf)
    for i in range(4):
        pad = BRepPrimAPI_MakeBox(gp_Pnt(-9 + i * 2.5, -7, 1.6), 1.2, 1.8, 0.05).Shape()
        ct.SetColor(st.AddShape(pad, False), col(0.85, 0.70, 0.25), XCAFDoc_ColorSurf)
    ic = BRepPrimAPI_MakeBox(gp_Pnt(-3, -2.5, 1.6), 5, 5, 1.0).Shape()
    ct.SetColor(st.AddShape(ic, False), col(0.12, 0.12, 0.13), XCAFDoc_ColorSurf)
    cap = BRepPrimAPI_MakeBox(gp_Pnt(4, -6, 1.6), 3.5, 2.8, 1.9).Shape()
    lcap = st.AddShape(cap, False)
    ct.SetColor(lcap, col(0.85, 0.45, 0.10), XCAFDoc_ColorSurf)
    ex = TopExp_Explorer(cap, TopAbs_FACE)
    top = None
    while ex.More():
        face = TopoDS.Face(ex.Current())
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        z = props.CentreOfMass().Z()
        if top is None or z > top[0]:
            top = (z, face)
        ex.Next()
    ct.SetColor(st.AddSubShape(lcap, top[1]), col(0.95, 0.75, 0.35), XCAFDoc_ColorSurf)
    can = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(-7, 5, 1.6), gp_Dir(0, 0, 1)), 2.0, 4.0).Shape()
    ct.SetColor(st.AddShape(can, False), col(0.9, 0.9, 0.88), XCAFDoc_ColorSurf)
    marker = BRepPrimAPI_MakeBox(gp_Pnt(9, 6.5, 1.6), 1.5, 1.5, 1.5).Shape()  # at the Xp Yp corner
    ct.SetColor(st.AddShape(marker, False), col(0.9, 0.2, 0.2), XCAFDoc_ColorSurf)
    write(doc, st, "demo-board.step")

    # assembly-board.step: a 100 × 80 mm board with one resistor part instanced 30 times and a capacitor 3 times
    doc, st, ct = new_doc()
    builder = BRep_Builder()
    root = st.NewShape()
    board = BRepPrimAPI_MakeBox(gp_Pnt(-50, -40, -1.6), 100, 80, 1.6).Shape()
    lboard = st.AddShape(board, False)
    ct.SetColor(lboard, col(0.1, 0.4, 0.2), XCAFDoc_ColorSurf)
    st.AddComponent(root, lboard, TopLoc_Location())
    body = BRepPrimAPI_MakeBox(gp_Pnt(-0.8, -0.4, 0), 1.6, 0.8, 0.45).Shape()
    t1 = BRepPrimAPI_MakeBox(gp_Pnt(-0.85, -0.42, 0), 0.35, 0.84, 0.5).Shape()
    t2 = BRepPrimAPI_MakeBox(gp_Pnt(0.5, -0.42, 0), 0.35, 0.84, 0.5).Shape()
    resistor = TopoDS_Compound()
    builder.MakeCompound(resistor)
    for s in (body, t1, t2):
        builder.Add(resistor, s)
    lres = st.AddShape(resistor, False)
    ct.SetColor(lres, col(0.15, 0.15, 0.15), XCAFDoc_ColorSurf)
    for t in (t1, t2):
        ct.SetColor(st.AddSubShape(lres, t), col(0.8, 0.8, 0.82), XCAFDoc_ColorSurf)
    for i in range(30):
        tr = gp_Trsf()
        tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), (i % 4) * math.pi / 2)
        tr.SetTranslationPart(gp_Vec(-40 + (i % 10) * 8.5, -25 + (i // 10) * 20, 0))
        st.AddComponent(root, lres, TopLoc_Location(tr))
    cap = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 4, 10).Shape()
    lcap = st.AddShape(cap, False)
    ct.SetColor(lcap, col(0.2, 0.3, 0.7), XCAFDoc_ColorSurf)
    for i in range(3):
        tr = gp_Trsf()
        tr.SetTranslationPart(gp_Vec(-20 + i * 20, 30, 0))
        st.AddComponent(root, lcap, TopLoc_Location(tr))
    write(doc, st, "assembly-board.step")


if __name__ == "__main__":
    make_bracket()
    make_steps()
    print("examples written to", HERE)
