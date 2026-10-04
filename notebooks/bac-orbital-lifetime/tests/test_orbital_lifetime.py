# SPDX-License-Identifier: MIT
"""Checks for bac_orbital_lifetime.py. From the bac-utils root: uv run pytest notebooks/bac-orbital-lifetime -q

The notebook is run once per module through the shared harness; the profile tests run patched copies.
"""

import math
import tomllib

import numpy as np
import pytest

import notebook_harness

NOTEBOOK = notebook_harness.notebook_path("bac_orbital_lifetime")
MOD, OUT, D = notebook_harness.run(NOTEBOOK)


def _run(profile_toml: str) -> dict:
    return notebook_harness.run(NOTEBOOK, profile_toml)[2]


def test_defaults_regression():
    """BAC demo mission at 450 km SSO, 2.0 kg, four tape antennas, launch 2027-06 – the 0.2.0 figures."""
    assert D["TOOL_VERSION"] == "0.2.0"
    assert D["lifetime_nominal"] == pytest.approx(2.385, abs=0.005)
    assert D["lifetime_shortest"] == pytest.approx(1.469, abs=0.005)
    assert D["lifetime_longest"] == pytest.approx(4.205, abs=0.005)
    assert D["h_mission_end_nominal"] == pytest.approx(350.6, abs=0.1)
    assert D["bc_mission"] == pytest.approx(38.48, abs=0.01)
    assert D["ltdn_drift_start"] == pytest.approx(2.45, abs=0.01)
    assert D["complies_5yr_nominal"] and D["complies_25yr_longest"]


def test_defaults_plausible():
    assert 1.0 < D["lifetime_nominal"] < 6.0
    assert D["lifetime_shortest"] < D["lifetime_nominal"] < D["lifetime_longest"]
    assert D["lifetime_shortest"] > 0.5
    assert 300 < D["h_mission_end_nominal"] < 450
    assert not D["input_warnings"]


def test_drag_area_geometry():
    # 1.5U tumbling body: (xy + yz + xz)/2 in m^2 plus four 0.3 × 17 cm cylinders at pi/4
    x, y, z = 0.10, 0.10, 0.1702
    body = (x * y + y * z + x * z) / 2
    ant = 4 * 0.003 * 0.17 * math.pi / 4
    assert D["area_tumbling_m2"] == pytest.approx(body + ant, rel=1e-6)
    assert D["body_surface_m2"] == pytest.approx(2 * (x * y + y * z + x * z), rel=1e-9)


def test_density_table_against_pymsis():
    """Orbit-averaged density at 450 km, F=150, Ap=15, i=97.5 recomputed from pymsis."""
    import pymsis  # a declared test dependency: a missing wheel fails the test rather than skipping it

    tab3 = D["density_slice"](97.5)
    got = D["rho_kg_m3"](450.0, 150.0, 15.0, tab3)
    inc = math.radians(97.5)
    u = np.linspace(0, 2 * np.pi, 36, endpoint=False)
    lat = np.degrees(np.arcsin(np.sin(inc) * np.sin(u)))
    rhos = []
    for raan in np.linspace(0, 2 * np.pi, 4, endpoint=False):
        lon = np.degrees(raan + np.arctan2(np.cos(inc) * np.sin(u), np.cos(u))) % 360 - 180
        for date in ("2025-03-21", "2025-06-21"):
            latr = np.radians(lat)
            a, b = 6378.137, 6356.752
            R = np.sqrt(
                ((a**2 * np.cos(latr)) ** 2 + (b**2 * np.sin(latr)) ** 2)
                / ((a * np.cos(latr)) ** 2 + (b * np.sin(latr)) ** 2)
            )
            h = 6371.0 + 450.0 - R
            n = len(lat)
            res = pymsis.calculate(
                np.full(n, np.datetime64(date), dtype="datetime64[s]"),
                lon,
                lat,
                h,
                f107s=np.full(n, 150.0),
                f107as=np.full(n, 150.0),
                aps=np.tile([15.0] * 7, (n, 1)),
            )
            rhos.append(res[:, pymsis.Variable.MASS_DENSITY])
    ref = float(np.mean(np.concatenate(rhos)))
    assert got == pytest.approx(ref, rel=0.03)


def test_propagator_against_scipy():
    """Constant-flux decay integrated by scipy from the same rate function."""
    from scipy.integrate import solve_ivp  # a declared test dependency, as pymsis above

    rate = D["decay_rate_km_day"]
    bc = D["bc_mission"]
    f107, ap = 150.0, 15.0

    def rhs(t, y):
        return [rate(max(y[0], 120.0), f107, ap, bc)]

    def hit(t, y):
        return y[0] - 120.0

    hit.terminal = True
    sol = solve_ivp(rhs, (0, 30 * 365.25), [450.0], events=hit, rtol=1e-8, atol=1e-8, max_step=5.0)
    t_ref = float(sol.t_events[0][0])
    r = D["propagate"](450.0, D["mi0"], lambda mi: f107, lambda mi: ap, bc, bc, 1e9, record=False)
    assert r["lifetime_days"] == pytest.approx(t_ref, rel=0.02)


def test_monotonic_in_altitude_and_bc():
    y = D["sweep_alt_y"]
    ys = [v for v in y if v is not None]
    assert ys == sorted(ys)
    z = [v for v in D["sweep_bc_y"] if v is not None]
    assert z == sorted(z)


def test_decay_rate_sign_and_scale():
    rate = D["decay_rate_km_day"]
    r = rate(450.0, 150.0, 15.0, 40.0)
    assert -1.0 < r < -0.05  # a few hundred meters a day at moderate flux
    assert rate(450.0, 250.0, 15.0, 40.0) < r  # stronger flux, faster decay
    assert rate(450.0, 150.0, 15.0, 80.0) == pytest.approx(r / 2, rel=1e-9)


def test_profile_round_trip():
    toml = D["profile_toml"]
    p = tomllib.loads(toml)
    assert p["tool"] == "bac_orbital_lifetime"
    assert p["orbit"]["altitude_km"] == 450
    assert p["spacecraft"]["mass_kg"] == pytest.approx(2.0)
    assert len(p["deployables"]) == 1
    assert p["results"]["orbital_lifetime"]["lifetime_years_nominal"] == pytest.approx(D["lifetime_nominal"], rel=1e-5)
    assert len(p["results"]["orbital_lifetime"]["scenarios"]) == len(D["runs"])
    # reload it: identical headline
    d2 = _run(toml)
    assert d2["profile_tool"] == "bac_orbital_lifetime"
    assert d2["lifetime_nominal"] == pytest.approx(D["lifetime_nominal"], rel=1e-6)


def test_generic_profile_loads():
    d = _run(D["PROFILE_GENERIC"])
    assert d["form_factor"] == "3U"
    assert d["att_mission"] == "ram_z"
    assert d["att_after"] == "tumbling"
    assert d["altitude_km"] == 500
    assert d["area_after_m2"] > d["area_mission_m2"]  # wings edge-on in flight, halved when tumbling
    assert d["lifetime_nominal"] > 1.0


def test_sibling_profile_takes_orbit_only():
    toml = """
name = "Demo mission, 500 km SSO"
tool = "bac_link_budget"
tool_version = "0.7.0"

[orbit]
altitude_km = 520
inclination_deg = 97.4
ltdn_hours = 10.5
epoch = "2026-09-14T00:00:00Z"
sim_days = 7
min_elevation_deg = 10

[[modes]]
name = "9k6 FSK"
"""
    d = _run(toml)
    assert d["profile_tool"] == "bac_link_budget"
    assert d["altitude_km"] == 520
    assert d["inclination_deg"] == pytest.approx(97.4)
    assert d["epoch"].isoformat() == "2026-09-14"
    assert d["form_factor"] == "1.5U"  # this tool's default kept


def test_out_of_range_and_bad_values_survive():
    toml = """
tool = "bac_orbital_lifetime"
[orbit]
altitude_km = 5000
inclination_deg = "polar"
[spacecraft]
mass_kg = -3
form_factor = "9U"
[[deployables]]
name = "broken"
count = "many"
"""
    d = _run(toml)
    assert d["altitude_km"] == 1000  # clamped
    assert d["inclination_deg"] == pytest.approx(97.2)  # default kept, reported
    assert d["mass_kg"] == pytest.approx(0.1)
    assert d["form_factor"] == "Custom"
    assert any("skipped" in w for w in d["input_warnings"])
    assert d["profile_warnings"]


def test_analog_scenarios_bracket_band():
    names = {r["name"]: r for r in D["runs"]}
    assert names["Analog cycle 24"]["lifetime_days"] > names["Analog cycle 19"]["lifetime_days"] * 0.9
    lows = min(r["lifetime_days"] for r in D["runs"] if r["group"] != "constant")
    assert lows == D["lifetime_shortest"] * 365.25


def test_ltdn_drift_small_for_sso():
    assert abs(D["ltdn_drift_start"]) < 30  # minutes per year at the design altitude
    assert D["sso_like"]


def test_launch_date_sweep_shape():
    rows = D["sweep_date_rows"]
    assert len(rows) == 3 * 33
    nominal = [r["Lifetime (yr)"] for r in rows if r["which"] == "nominal"]
    assert all(v is None or v > 0.5 for v in nominal)
    assert (
        max(v for v in nominal if v is not None) / min(v for v in nominal if v is not None) > 1.3
    )  # the cycle phase shows


def test_deploy_at_end_of_mission():
    toml = (
        D["PROFILE_BAC"]
        + """
[[deployables]]
name = "Drag sail"
shape = "panel"
count = 1
width_cm = 30
length_cm = 30
flow_angle_deg = 0
deployed = false
deploy_at_end_of_mission = true
"""
    )
    d = _run(toml)
    assert d["area_mission_m2"] == pytest.approx(D["area_mission_m2"], rel=1e-9)
    assert d["area_after_m2"] == pytest.approx(D["area_after_m2"] + 0.09 * 0.5, rel=1e-6)
    assert d["lifetime_nominal"] < D["lifetime_nominal"]
    assert tomllib.loads(d["profile_toml"])["deployables"][1]["deploy_at_end_of_mission"] is True


def test_example_profiles_are_the_shipped_ones():
    examples = NOTEBOOK.parent / "examples"
    shipped = {"bac-demo-450km-sso": D["PROFILE_BAC"], "generic-3u-500km-sso": D["PROFILE_GENERIC"]}
    for slug, text in shipped.items():
        on_disk = (examples / f"bac-orbital-lifetime-profile-{slug}.toml").read_text(encoding="utf-8")
        assert on_disk.strip() == text.strip()
