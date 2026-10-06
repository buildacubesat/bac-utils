# SPDX-License-Identifier: MIT
"""Regression checks for bac_optical_payload.py against the 0.7.1 handoff (§5, numbers at the defaults, 500 km).

From the bac-utils root: uv run pytest notebooks/bac-optical-payload -q
"""

import math
import tomllib

import pytest

import notebook_harness

NOTEBOOK = notebook_harness.notebook_path("bac_optical_payload")
MOD, OUT, D = notebook_harness.run(NOTEBOOK)


def _run(profile_toml: str) -> dict:
    return notebook_harness.run(NOTEBOOK, profile_toml)[2]


def test_version_and_defaults():
    assert D["TOOL_VERSION"] == "0.7.1"
    assert D["profile_tool"] == "bac_optical_payload"
    assert not D["profile_warnings"]
    assert D["focus_invalid"] is False


def test_primary_imager_geometry():
    """BAC primary imager: IMX477, C-mount 16 mm f/1.4, 500 km, Bern."""
    assert D["gsd_m"] == pytest.approx(48.4, abs=0.05)
    assert D["swath_x_km"] == pytest.approx(196.5, abs=0.05)
    assert D["swath_y_km"] == pytest.approx(147.25, abs=0.05)
    assert D["fov_x_deg"] == pytest.approx(22.23, abs=0.01)
    assert D["fov_y_deg"] == pytest.approx(16.75, abs=0.01)
    assert D["rayleigh_ground_m"] == pytest.approx(29.4, abs=0.05)
    assert D["q_factor"] == pytest.approx(0.50, abs=0.005)
    assert D["smear_px"] == pytest.approx(0.07, abs=0.005)
    assert D["skew_px"] == pytest.approx(2.9, abs=0.05)
    assert D["period_min"] == pytest.approx(94.47, abs=0.01)


def test_data_volume():
    assert D["raw_kb"] == pytest.approx(18_495, abs=1)
    assert D["comp_kb"] == pytest.approx(1_850, abs=1)
    # the panel's own daily volumes; with a link budget profile loaded the handoff's 5.83 / 7.72 days apply (test_cross)
    assert D["days_raw_low"] == pytest.approx(D["raw_kb"] / D["low_kb"], rel=1e-9)
    assert D["days_raw_high"] == pytest.approx(D["raw_kb"] / D["high_kb"], rel=1e-9)


def test_reach_and_accesses_are_solved_between_samples():
    assert D["reach_km"] == pytest.approx(98.2, abs=0.05)
    assert D["reach_eff_km"] == pytest.approx(54.5, abs=0.05)
    durations = sorted((a["duration_s"] for a in D["accesses"]), reverse=True)
    assert durations == pytest.approx([14.7, 14.2, 13.2, 12.2], abs=0.1)
    assert D["acc_per_day"] == pytest.approx(0.133, abs=0.001)
    assert D["lit_per_day"] == pytest.approx(0.067, abs=0.001)
    for a in D["accesses"]:
        assert a["t_end"] > a["t_start"]
        assert a["min_psi_km"] < D["reach_eff_km"]


def test_ground_offset_uses_the_spherical_earth():
    g = D["ground_offset_km"]
    assert g(60.0, 500.0) == pytest.approx(1008, abs=1)
    assert g(5.0, 500.0) == pytest.approx(500.0 * math.tan(math.radians(5.0)), abs=0.05)


def test_boom_profile():
    d = _run(D["PROFILE_BOOM"])
    assert d["fill_fraction"] == pytest.approx(0.384, abs=0.001)
    assert d["corners_in_frame"] == 8
    assert d["dist_center_mm"] == pytest.approx(598, abs=1)
    assert d["hyperfocal_mm"] == pytest.approx(11_437, abs=1)
    assert d["dof_near_mm"] == pytest.approx(569, abs=1)
    assert d["dof_far_mm"] == pytest.approx(631, abs=1)


def test_generic_profile():
    d = _run(D["PROFILE_GENERIC"])
    assert d["gsd_m"] == pytest.approx(147.7, abs=0.1)
    assert d["acc_per_day"] == pytest.approx(0.53, abs=0.01)
    assert d["lit_per_day"] == pytest.approx(0.23, abs=0.01)


def test_focus_inside_focal_length_is_refused():
    toml = D["PROFILE_BOOM"].replace("focus_mm = 0", "focus_mm = 8")  # the S-mount lens is 8 mm
    assert toml != D["PROFILE_BOOM"]
    d = _run(toml)
    assert d["focus_invalid"] is True


def test_profile_export_contract():
    p = tomllib.loads(D["profile_toml"])
    assert p["tool"] == "bac_optical_payload"
    assert p["tool_version"] == "0.7.1"
    assert "map" in p
    res = p["results"]["optical_payload"]
    assert res["reach_km"] == pytest.approx(98.2, abs=0.05)
    d2 = _run(D["profile_toml"])
    assert d2["profile_tool"] == "bac_optical_payload"
    assert d2["gsd_m"] == pytest.approx(D["gsd_m"], rel=1e-6)


def test_example_profiles_are_the_shipped_ones():
    examples = NOTEBOOK.parent / "examples"
    shipped = {
        "bac-demo-primary-imager": D["PROFILE_BAC"],
        "bac-demo-boom-camera": D["PROFILE_BOOM"],
        "generic-1u-camera-module-3": D["PROFILE_GENERIC"],
    }
    for slug, text in shipped.items():
        on_disk = (examples / f"bac-optical-payload-profile-{slug}.toml").read_text(encoding="utf-8")
        assert on_disk.strip() == text.strip()
