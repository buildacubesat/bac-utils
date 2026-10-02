# SPDX-License-Identifier: MIT
"""Triangle mesh container and loaders for STEP (OCP) and mesh formats (trimesh)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from bac_common.errors import BacError

STEP_SUFFIXES = {".step", ".stp"}
MESH_SUFFIXES = {".stl", ".obj", ".ply", ".3mf", ".off", ".glb", ".gltf"}
SUPPORTED_SUFFIXES = STEP_SUFFIXES | MESH_SUFFIXES

SMOOTH_ANGLE_DEG = 30.0  # mesh formats: vertex normals averaged below this crease angle
STEP_INSTALL_HINT = "install with `uv tool install './tools/bac-cad-preview[step]'`"


class LoadError(BacError):
    """A file could not be loaded; the message is user-facing. The batch loop catches it per file."""


@dataclass
class Mesh:
    vertices: np.ndarray  # (N, 3) float64, mm
    faces: np.ndarray  # (M, 3) int64
    normals: np.ndarray  # (M, 3, 3) float32, per-corner unit normals
    colors: np.ndarray  # (M, 3) float32 sRGB 0..1, per face
    stats: dict = field(default_factory=dict)

    @property
    def n_triangles(self) -> int:
        return int(self.faces.shape[0])

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    def size_mm(self) -> np.ndarray:
        lo, hi = self.bounds()
        return hi - lo


def kind_of(path: Path) -> str:
    s = path.suffix.lower()
    if s in STEP_SUFFIXES:
        return "step"
    if s in MESH_SUFFIXES:
        return "mesh"
    return "unknown"


def hex_to_rgb(text: str) -> tuple[float, float, float]:
    t = text.strip().lstrip("#")
    if len(t) == 3:
        t = "".join(ch * 2 for ch in t)
    if len(t) != 6:
        raise ValueError(f"colour must be #RRGGBB, got {text!r}")
    try:
        v = int(t, 16)
    except ValueError as e:
        raise ValueError(f"colour must be #RRGGBB, got {text!r}") from e
    return ((v >> 16) / 255.0, ((v >> 8) & 0xFF) / 255.0, (v & 0xFF) / 255.0)


def step_available() -> bool:
    try:
        import OCP  # noqa: F401
    except ImportError:
        return False
    return True


def load(path: Path, default_color: tuple[float, float, float], deflection: float | None = None) -> Mesh:
    k = kind_of(path)
    if k == "step":
        return load_step(path, default_color, deflection)
    if k == "mesh":
        return load_mesh(path, default_color)
    raise LoadError(f"Unsupported file type {path.suffix!r}.")


# --- geometry helpers -------------------------------------------------------


def face_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    v0, v1, v2 = (vertices[faces[:, i]] for i in range(3))
    n = np.cross(v1 - v0, v2 - v0)
    length = np.linalg.norm(n, axis=1)
    length[length == 0] = 1.0
    return (n / length[:, None]).astype(np.float32)


def smooth_corner_normals(vertices: np.ndarray, faces: np.ndarray, angle_deg: float) -> np.ndarray:
    """Per-corner normals: average of adjacent face normals within the crease angle."""
    fn = face_normals(vertices, faces)
    m = faces.shape[0]
    if m == 0:
        return np.zeros((0, 3, 3), np.float32)
    cos_lim = math.cos(math.radians(angle_deg))
    # incidence lists: for every (face, corner) the faces sharing that vertex
    corner_v = faces.reshape(-1)  # (3M,)
    order = np.argsort(corner_v, kind="stable")
    sorted_v = corner_v[order]
    sorted_f = order // 3
    starts = np.searchsorted(sorted_v, np.arange(vertices.shape[0]), side="left")
    counts = np.bincount(sorted_v, minlength=vertices.shape[0])
    out = np.empty((3 * m, 3), np.float32)
    chunk = 200_000
    for lo in range(0, 3 * m, chunk):
        hi = min(lo + chunk, 3 * m)
        cv = corner_v[lo:hi]
        cf = np.arange(lo, hi) // 3
        cnt = counts[cv]
        maxdeg = int(cnt.max()) if cnt.size else 0
        acc = np.zeros((hi - lo, 3), np.float32)
        base = starts[cv]
        own = fn[cf]
        for d in range(maxdeg):
            valid = d < cnt
            idx = base + np.minimum(d, np.maximum(cnt - 1, 0))
            nb = fn[sorted_f[idx]]
            dot = np.einsum("ij,ij->i", own, nb)
            use = valid & (dot >= cos_lim)
            acc[use] += nb[use]
        length = np.linalg.norm(acc, axis=1)
        bad = length < 1e-12
        acc[bad] = own[bad]
        length[bad] = 1.0
        out[lo:hi] = acc / length[:, None]
    return out.reshape(m, 3, 3)


def _normalize_rows(a: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(a, axis=1)
    length[length == 0] = 1.0
    return a / length[:, None]


# --- mesh formats via trimesh ------------------------------------------------


def load_mesh(path: Path, default_color: tuple[float, float, float]) -> Mesh:
    try:
        import trimesh
    except ImportError as e:  # pragma: no cover
        raise LoadError("trimesh is not installed.") from e
    try:
        loaded = trimesh.load(str(path), force="mesh", process=True)
    except Exception as e:
        raise LoadError(f"Could not read {path.name}: {e}") from e
    if not isinstance(loaded, trimesh.Trimesh) or loaded.faces.shape[0] == 0:
        raise LoadError(f"{path.name} contains no triangles.")
    units = loaded.units  # 3MF declares its unit; STL, OBJ and PLY do not and are taken as mm
    if units and units not in ("mm", "millimeter", "millimeters"):
        try:
            loaded.convert_units("millimeters")
        except Exception:  # noqa: BLE001 – unknown unit string: keep the raw numbers
            units = None
    vertices = np.asarray(loaded.vertices, dtype=np.float64)
    faces = np.asarray(loaded.faces, dtype=np.int64)
    colors = np.tile(np.asarray(default_color, np.float32), (faces.shape[0], 1))
    try:
        kind = loaded.visual.kind
    except Exception:
        kind = None
    if kind == "face":
        colors = np.asarray(loaded.visual.face_colors[:, :3], np.float32) / 255.0
    elif kind == "vertex":
        vc = np.asarray(loaded.visual.vertex_colors[:, :3], np.float32) / 255.0
        colors = vc[faces].mean(axis=1)
    normals = smooth_corner_normals(vertices, faces, SMOOTH_ANGLE_DEG)
    stats = {"format": path.suffix.lower().lstrip("."), "colored": kind in ("face", "vertex"), "units": units}
    return Mesh(vertices, faces, normals, colors, stats)


# --- STEP via OCP ------------------------------------------------------------


def auto_deflection(diag_mm: float) -> float:
    return max(0.005, diag_mm * 5e-4)


def _silence_occt() -> None:
    """Drop OCCT's stdout printer so transfer statistics do not clutter the step log."""
    try:
        from OCP.Message import Message

        messenger = Message.DefaultMessenger_s()
        printers = messenger.Printers()
        for i in range(printers.Size(), 0, -1):
            messenger.RemovePrinter(printers.Value(i))
    except Exception:  # noqa: BLE001 – cosmetic only
        pass


def load_step(path: Path, default_color: tuple[float, float, float], deflection: float | None = None) -> Mesh:
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRep import BRep_Tool
        from OCP.BRepBndLib import BRepBndLib
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.gp import gp_Trsf
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.Quantity import Quantity_Color, Quantity_TypeOfColor
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
        from OCP.TDF import TDF_Label, TDF_Tool
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
        from OCP.TopExp import TopExp, TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS
        from OCP.XCAFApp import XCAFApp_Application
        from OCP.XCAFDoc import (
            XCAFDoc_ColorGen,
            XCAFDoc_ColorSurf,
            XCAFDoc_ColorTool,
            XCAFDoc_DocumentTool,
            XCAFDoc_ShapeTool,
        )
    except ImportError as e:
        raise LoadError(f"STEP support missing – {STEP_INSTALL_HINT}") from e
    # OCP 7.x exposes the classic collection names, OCP 8 the templated ones.
    try:
        from OCP.TDF import TDF_LabelSequence
    except ImportError:
        from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence
    try:
        from OCP.TopTools import TopTools_IndexedMapOfShape
    except ImportError:
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
    _silence_occt()

    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(False)
    reader.SetLayerMode(False)
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise LoadError(f"Could not read {path.name} as STEP.")
    if not reader.Transfer(doc):
        raise LoadError(f"STEP transfer failed for {path.name}.")
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    XCAFDoc_DocumentTool.ColorTool_s(doc.Main())  # creates the colour tool on the document
    srgb = Quantity_TypeOfColor.Quantity_TOC_sRGB

    def label_color(label: TDF_Label) -> tuple[float, float, float] | None:
        c = Quantity_Color()
        for typ in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen):
            if XCAFDoc_ColorTool.GetColor_s(label, typ, c):
                r, g, b = c.Values(srgb)
                return (float(r), float(g), float(b))
        return None

    def entry(label: TDF_Label) -> str:
        s = TCollection_AsciiString()
        TDF_Tool.Entry_s(label, s)
        return s.ToCString()

    # Walk the assembly tree; collect (part label, world transform, inherited colour).
    instances: list[tuple[TDF_Label, gp_Trsf, tuple[float, float, float] | None]] = []

    def walk(label: TDF_Label, trsf: gp_Trsf, inherited, depth: int = 0) -> None:
        if depth > 64:
            return
        own = label_color(label) or inherited
        if XCAFDoc_ShapeTool.IsAssembly_s(label):
            comps = TDF_LabelSequence()
            XCAFDoc_ShapeTool.GetComponents_s(label, comps)
            for i in range(1, comps.Length() + 1):
                comp = comps.Value(i)
                ref = TDF_Label()
                if not XCAFDoc_ShapeTool.GetReferredShape_s(comp, ref):
                    continue
                loc = XCAFDoc_ShapeTool.GetLocation_s(comp)
                walk(ref, trsf.Multiplied(loc.Transformation()), label_color(comp) or own, depth + 1)
        elif XCAFDoc_ShapeTool.IsReference_s(label):
            ref = TDF_Label()
            if XCAFDoc_ShapeTool.GetReferredShape_s(label, ref):
                loc = XCAFDoc_ShapeTool.GetLocation_s(label)
                walk(ref, trsf.Multiplied(loc.Transformation()), own, depth + 1)
        else:
            instances.append((label, trsf, own))

    free = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free)
    for i in range(1, free.Length() + 1):
        walk(free.Value(i), gp_Trsf(), None)
    if not instances:
        raise LoadError(f"{path.name} contains no shapes.")

    # Overall size for the deflection choice.
    box = Bnd_Box()
    for label, trsf, _ in instances:
        shp = XCAFDoc_ShapeTool.GetShape_s(label).Moved(TopLoc_Location(trsf))
        BRepBndLib.Add_s(shp, box, False)
    if box.IsVoid():
        raise LoadError(f"{path.name} has an empty bounding box.")
    cmin, cmax = box.CornerMin(), box.CornerMax()
    diag = math.dist((cmin.X(), cmin.Y(), cmin.Z()), (cmax.X(), cmax.Y(), cmax.Z()))
    lin = deflection if deflection else auto_deflection(diag)
    ang = 0.25

    # Tessellate each distinct part once, then instance it.
    cache: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None] = {}
    all_v: list[np.ndarray] = []
    all_f: list[np.ndarray] = []
    all_n: list[np.ndarray] = []
    all_c: list[np.ndarray] = []
    offset = 0
    colored_faces = 0
    n_parts = 0

    def tessellate(label: TDF_Label, fallback: tuple[float, float, float]):
        shape = XCAFDoc_ShapeTool.GetShape_s(label)
        BRepMesh_IncrementalMesh(shape, lin, False, ang, True)
        face_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)
        solid_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_SOLID, solid_map)
        face_col: dict[int, tuple[float, float, float]] = {}
        solid_col: dict[int, tuple[float, float, float]] = {}
        subs = TDF_LabelSequence()
        XCAFDoc_ShapeTool.GetSubShapes_s(label, subs)
        for i in range(1, subs.Length() + 1):
            sub = subs.Value(i)
            col = label_color(sub)
            if col is None:
                continue
            sshape = XCAFDoc_ShapeTool.GetShape_s(sub)
            if sshape.IsNull():
                continue
            st = sshape.ShapeType()
            if st == TopAbs_FACE:
                idx = face_map.FindIndex(sshape)
                if idx:
                    face_col[idx] = col
            elif st == TopAbs_SOLID:
                idx = solid_map.FindIndex(sshape)
                if idx:
                    solid_col[idx] = col
        # face index → owning solid colour
        face_solid_col: dict[int, tuple[float, float, float]] = {}
        if solid_col:
            for sidx, col in solid_col.items():
                ex = TopExp_Explorer(solid_map.FindKey(sidx), TopAbs_FACE)
                while ex.More():
                    fidx = face_map.FindIndex(ex.Current())
                    if fidx and fidx not in face_col:
                        face_solid_col[fidx] = col
                    ex.Next()
        vs, fs, ns, cs = [], [], [], []
        off = 0
        colored = 0
        for fidx in range(1, face_map.Extent() + 1):
            face = TopoDS.Face(face_map.FindKey(fidx))
            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(face, loc)
            if tri is None or tri.NbTriangles() == 0:
                continue
            nn, nt = tri.NbNodes(), tri.NbTriangles()
            pts = np.empty((nn, 3), np.float64)
            for k in range(1, nn + 1):
                p = tri.Node(k)
                pts[k - 1] = (p.X(), p.Y(), p.Z())
            t = loc.Transformation()
            if t.Form() != 0:  # gp_Identity
                m = np.array([[t.Value(r, c) for c in range(1, 5)] for r in range(1, 4)])
                pts = pts @ m[:, :3].T + m[:, 3]
            tris = np.empty((nt, 3), np.int64)
            for k in range(1, nt + 1):
                a, b, c = tri.Triangle(k).Get()
                tris[k - 1] = (a - 1, b - 1, c - 1)
            if face.Orientation() == TopAbs_REVERSED:
                tris = tris[:, ::-1]
            col = face_col.get(fidx) or face_solid_col.get(fidx) or fallback
            if fidx in face_col or fidx in face_solid_col:
                colored += nt
            # smooth normals within the face: average of adjacent triangle normals
            fnrm = face_normals(pts, tris)
            acc = np.zeros((nn, 3), np.float64)
            for corner in range(3):
                np.add.at(acc, tris[:, corner], fnrm)
            vn = _normalize_rows(acc)
            vs.append(pts)
            fs.append(tris + off)
            ns.append(vn[tris].astype(np.float32))
            cs.append(np.tile(np.asarray(col, np.float32), (nt, 1)))
            off += nn
        if not fs:
            return None
        return (np.vstack(vs), np.vstack(fs), np.vstack(ns), np.vstack(cs), colored)

    for label, trsf, inherited in instances:
        fallback = inherited or default_color
        key = entry(label) + "|" + ",".join(f"{c:.4f}" for c in fallback)
        if key not in cache:
            cache[key] = tessellate(label, fallback)
        part = cache[key]
        if part is None:
            continue
        v, f, n, c, colored = part
        if trsf.Form() != 0:
            m = np.array([[trsf.Value(r, cc) for cc in range(1, 5)] for r in range(1, 4)])
            v = v @ m[:, :3].T + m[:, 3]
            n = (n.reshape(-1, 3) @ m[:, :3].T).reshape(n.shape).astype(np.float32)
            if np.linalg.det(m[:, :3]) < 0:
                f = f[:, ::-1]
                n = n[:, ::-1, :]
            n = n / np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-12)
        all_v.append(v)
        all_f.append(f + offset)
        all_n.append(n)
        all_c.append(c)
        offset += v.shape[0]
        colored_faces += colored
        n_parts += 1

    if not all_f:
        raise LoadError(f"{path.name} produced no triangles.")
    mesh = Mesh(np.vstack(all_v), np.vstack(all_f), np.vstack(all_n), np.vstack(all_c))
    mesh.stats = {
        "format": "step",
        "parts": n_parts,
        "unique_parts": len(cache),
        "deflection_mm": lin,
        "colored": colored_faces > 0 or any(inh is not None for _, _, inh in instances),
    }
    return mesh
