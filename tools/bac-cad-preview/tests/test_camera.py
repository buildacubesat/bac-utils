# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np
import pytest
from bac_cad_preview.camera import auto_face, base_frame, normalize_face, parse_rotate, view_rotation


def test_parse_rotate():
    assert parse_rotate("22.5,-22.5,0") == (22.5, -22.5, 0.0)
    assert parse_rotate(" 1 , 2 , 3 ") == (1.0, 2.0, 3.0)
    with pytest.raises(ValueError):
        parse_rotate("1,2")
    with pytest.raises(ValueError):
        parse_rotate("a,b,c")


def test_normalize_face():
    assert normalize_face("Z") == "zp"
    assert normalize_face("+y") == "yp"
    assert normalize_face("-x") == "xm"
    assert normalize_face("Ym") == "ym"
    assert normalize_face("top") == "zp"
    assert normalize_face("front") == "ym"
    assert normalize_face("bottom") == "zm"
    assert normalize_face("AUTO") == "auto"
    with pytest.raises(ValueError):
        normalize_face("w")


def test_default_face_is_z_up():
    """face ym: Z up, X right, Y away, camera front right above at 22.5° elevation."""
    R = view_rotation(face="ym")
    ex, ey, ez = (R @ e for e in np.eye(3))
    assert ez[1] > 0.9 and abs(ez[0]) < 1e-9  # Z straight up
    assert ex[0] > 0.9  # X right
    assert ey[2] < -0.8 and ey[1] > 0  # Y away from the viewer and slightly up
    cam = R.T @ np.array([0.0, 0.0, 1.0])
    assert cam[0] > 0 and cam[1] < 0 and cam[2] > 0
    assert np.degrees(np.arcsin(cam[2])) == pytest.approx(22.5)


def test_face_z_matches_kicad_chain():
    """face zp is Rx(22.5) · Ry(-22.5) on the KiCad frame: X right, Y up, camera in the Xp Yp Zp octant."""
    R = view_rotation((22.5, -22.5, 0.0), "zp")
    ex, ey, ez = (R @ e for e in np.eye(3))
    assert ex[0] > 0.9 and abs(ex[1]) < 0.2
    assert ey[1] > 0.9 and abs(ey[0]) < 1e-9
    assert ez[2] > 0.8
    cam = R.T @ np.array([0.0, 0.0, 1.0])
    np.testing.assert_allclose(cam, [0.3536, 0.3827, 0.8536], atol=1e-3)


def test_identity_for_face_z_without_rotation():
    np.testing.assert_allclose(view_rotation((0, 0, 0), "zp"), np.eye(3), atol=1e-12)


@pytest.mark.parametrize("face", ["xp", "xm", "yp", "ym", "zp", "zm"])
def test_faces_are_rotations_toward_viewer(face):
    B = base_frame(face)
    np.testing.assert_allclose(B @ B.T, np.eye(3), atol=1e-12)
    assert np.linalg.det(B) == pytest.approx(1.0)
    sign = 1 if face[1] == "p" else -1
    axis = "xyz".index(face[0])
    e = np.zeros(3)
    e[axis] = sign
    np.testing.assert_allclose(B @ e, [0, 0, 1], atol=1e-12)  # the face points at the viewer
    up = [0, 1, 0] if axis == 2 else [0, 0, 1]
    np.testing.assert_allclose(B @ np.array(up, float), [0, 1, 0], atol=1e-12)


def test_auto_face():
    assert auto_face(np.array([40.0, 25.0, 20.0])) == ("ym", False)  # bracket: not flat
    assert auto_face(np.array([81.0, 81.0, 6.0])) == ("zp", True)  # end piece lying flat
    assert auto_face(np.array([6.0, 81.0, 81.0])) == ("xp", True)  # plate standing in YZ
    assert auto_face(np.array([81.0, 6.0, 81.0])) == ("ym", True)
    assert auto_face(np.array([8.5, 8.5, 340.0])) == ("ym", False)  # rail: two thin axes, not a plate
    assert auto_face(np.array([22.0, 17.5, 5.6]), flat_ratio=3.0) == ("zp", True)
    assert auto_face(np.array([22.0, 17.5, 5.6]), flat_ratio=4.0) == ("ym", False)
    assert auto_face(np.array([0.0, 1.0, 1.0])) == ("ym", False)
