# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh
from bac_cad_preview.mesh import Mesh, smooth_corner_normals


@pytest.fixture(autouse=True)
def fixed_terminal(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")


@pytest.fixture
def box_stl(tmp_path: Path) -> Path:
    """A 40 × 25 × 3 mm box written as binary STL."""
    m = trimesh.creation.box(extents=(40, 25, 3))
    p = tmp_path / "box.stl"
    m.export(p)
    return p


@pytest.fixture
def box_mesh() -> Mesh:
    m = trimesh.creation.box(extents=(10, 10, 10))
    v = np.asarray(m.vertices, np.float64)
    f = np.asarray(m.faces, np.int64)
    return Mesh(v, f, smooth_corner_normals(v, f, 30.0), np.tile(np.array([0.5, 0.6, 0.7], np.float32), (len(f), 1)))
