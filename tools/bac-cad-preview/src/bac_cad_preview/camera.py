# SPDX-License-Identifier: MIT
"""Camera: a model face toward the viewer, then the kicad-cli oblique rotation.

The view is R = O · B.  B is the base frame that turns the chosen model axis
toward the viewer (view +Z) with the up axis on view +Y; O is the oblique
Rx(x) · Ry(y) · Rz(z) exactly as `kicad-cli pcb render --rotate` applies it
(glm::rotate chain in CAMERA::updateRotationMatrix).  View space is X right,
Y up, Z toward the viewer.  With face "zp" (model Zp toward the viewer, Y up)
B is the identity and R is the bac-kicad-generate-artifacts render view; with
the default face "ym" the model stands Z up as in FreeCAD.

Faces are named with the project's axis letters: xp, xm, yp, ym, zp, zm.
The signed spellings (x, -x, +y …) and kicad-cli's side names are accepted
as aliases and normalised to the letter form.
"""

from __future__ import annotations

import math

import numpy as np

DEFAULT_ROTATE = (22.5, -22.5, 0.0)
DEFAULT_FACE = "auto"
FLAT_RATIO = 3.0  # a part is flat when its thinnest extent is at most 1/ratio of both others

CANONICAL_FACES = ("xp", "xm", "yp", "ym", "zp", "zm")
_AXES = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}
_ALIASES = {
    # signed spellings
    "x": "xp",
    "+x": "xp",
    "-x": "xm",
    "y": "yp",
    "+y": "yp",
    "-y": "ym",
    "z": "zp",
    "+z": "zp",
    "-z": "zm",
    # kicad-cli --side names
    "top": "zp",
    "bottom": "zm",
    "front": "ym",
    "back": "yp",
    "right": "xp",
    "left": "xm",
}
FACES = ("auto", *CANONICAL_FACES, *_ALIASES)


def _rx(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def _ry(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def _rz(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


def parse_rotate(text: str) -> tuple[float, float, float]:
    """Parse 'X,Y,Z' degrees as accepted by kicad-cli --rotate."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        raise ValueError("rotation must be three comma-separated angles, e.g. 22.5,-22.5,0")
    try:
        x, y, z = (float(p) for p in parts)
    except ValueError as e:
        raise ValueError(f"rotation angles must be numbers: {text!r}") from e
    return (x, y, z)


def normalize_face(face: str) -> str:
    """Return "auto" or one of the canonical letter faces (xp, xm, yp, ym, zp, zm)."""
    f = face.strip().lower()
    f = _ALIASES.get(f, f)
    if f != "auto" and f not in CANONICAL_FACES:
        raise ValueError(f"face must be one of {', '.join(FACES)}; got {face!r}")
    return f


def auto_face(size_mm: np.ndarray, flat_ratio: float = FLAT_RATIO) -> tuple[str, bool]:
    """Default face "ym" (Z up); for a flat part the thin axis faces the viewer. Returns (face, is_flat)."""
    size = np.asarray(size_mm, dtype=np.float64)
    if size.shape != (3,) or not np.all(np.isfinite(size)) or size.min() <= 0:
        return ("ym", False)
    thin = int(np.argmin(size))
    others = np.delete(size, thin)
    if others.min() >= flat_ratio * size[thin]:
        return (("xp", "ym", "zp")[thin], True)
    return ("ym", False)


def base_frame(face: str) -> np.ndarray:
    """Rows: the model-space directions that map to view X (right), Y (up), Z (toward viewer)."""
    f = normalize_face(face)
    if f == "auto":
        raise ValueError("base_frame needs a resolved face, not 'auto'")
    axis, sign = f[0], (1.0 if f[1] == "p" else -1.0)
    toward = sign * np.array(_AXES[axis], dtype=np.float64)
    up = np.array(_AXES["y"] if axis == "z" else _AXES["z"], dtype=np.float64)
    right = np.cross(up, toward)
    return np.vstack([right, up, toward])


def oblique(rotate: tuple[float, float, float] = DEFAULT_ROTATE) -> np.ndarray:
    x, y, z = (math.radians(a) for a in rotate)
    return _rx(x) @ _ry(y) @ _rz(z)


def view_rotation(rotate: tuple[float, float, float] = DEFAULT_ROTATE, face: str = "ym") -> np.ndarray:
    """3×3 matrix taking model points to view space (X right, Y up, Z toward viewer)."""
    return oblique(rotate) @ base_frame(face)
