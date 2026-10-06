# SPDX-License-Identifier: MIT
"""Regression checks for bac_power_budget.py against the 0.5.1 handoff (§4 and §12, numbers at the defaults, 500 km).

From the bac-utils root: uv run pytest notebooks/bac-power-budget -q
"""

import tomllib

import pytest

import notebook_harness

NOTEBOOK = notebook_harness.notebook_path("bac_power_budget")
MOD, OUT, D = notebook_harness.run(NOTEBOOK)


def _run(profile_toml: str) -> dict:
    return notebook_harness.run(NOTEBOOK, profile_toml)[2]


def test_version_and_defaults():
    assert D["TOOL_VERSION"] == "0.5.1"
    assert D["profile_tool"] == "bac_power_budget"
    assert D["station_name"] == "Bern" and D["target_name"] == "Bern"
    assert not D["profile_warnings"]


def test_bac_profile_energy_balance():
    """500 km SSO, LTDN 10:30, epoch 2027-06-21, two days, tumbling, 2S2P modules as shipped."""
    assert D["gen_wh_day"] == pytest.approx(50.3, abs=0.05)
    assert D["sched_wh_day"] == pytest.approx(89.5, abs=0.1)
    assert D["requested_margin_w"] == pytest.approx(-1.63, abs=0.01)
    assert D["margin_w"] == pytest.approx(-0.30, abs=0.01)
    assert D["min_soc"] == pytest.approx(0.39, abs=0.005)
    assert D["safe_hours"] == pytest.approx(23.2, abs=0.1)
    assert D["eclipse_fraction"] == pytest.approx(0.37, abs=0.005)
    assert D["cw_wh_day"] == pytest.approx(5.76, abs=0.01)
    assert D["sustainable_pass_min"] == 0.0 and D["sustainable_frames"] == 0.0  # nominal watts alone exceed generation


def test_pack_and_charger_headroom():
    assert D["pack_wh"] == pytest.approx(50.9, abs=0.05)
    assert D["usable_wh"] == pytest.approx(15.3, abs=0.05)
    assert D["module_vmpp_hot"] == pytest.approx(10.0, abs=0.05)
    assert D["float_v"] == pytest.approx(8.4)
    assert D["module_vmpp_hot"] < D["float_v"] + 3.3  # the LTM8062 headroom callout fires on the shipped profile


def test_pass_statistics_single_phase():
    assert D["passes_per_day"] == pytest.approx(4.0, abs=0.01)
    assert D["period_min"] == pytest.approx(94.47, abs=0.01)


def test_mode_totals_are_ordered():
    t = D["mode_total_w"]
    assert t["Degraded"] < t["Safe"] < t["Nominal"] < t["Pass"] < t["Payload"]


def test_profile_export_contract():
    p = tomllib.loads(D["profile_toml"])
    assert p["tool"] == "bac_power_budget"
    assert p["tool_version"] == "0.5.1"
    assert p["loads"], "the loads travel as [[loads]] tables"
    assert "power_budget" in p["results"]
    d2 = _run(D["profile_toml"])
    assert d2["profile_tool"] == "bac_power_budget"
    assert d2["gen_wh_day"] == pytest.approx(D["gen_wh_day"], rel=1e-6)
    assert d2["margin_w"] == pytest.approx(D["margin_w"], rel=1e-6)


def test_generic_profile():
    d = _run(D["PROFILE_GENERIC"])
    assert d["profile_tool"] == "bac_power_budget"
    assert d["gen_wh_day"] > 0
    assert len(d["loads"]) == len(tomllib.loads(D["PROFILE_GENERIC"])["loads"])


def test_bad_loads_and_thresholds_are_reported():
    toml = (
        D["profile_toml"]
        + """
[[loads]]
consumer = "Broken"
node = "medium"
rail = "5V"
peak_w = 1.0
safe_w = -1
nominal_w = "many"
pass_w = 0
payload_w = 0
degraded_w = 0
"""
    )
    d = _run(toml)
    assert d["invalid_loads"]


def test_example_profiles_are_the_shipped_ones():
    examples = NOTEBOOK.parent / "examples"
    shipped = {"bac-demo-1u5": D["PROFILE_BAC"], "generic-1u": D["PROFILE_GENERIC"]}
    for slug, text in shipped.items():
        on_disk = (examples / f"bac-power-budget-profile-{slug}.toml").read_text(encoding="utf-8")
        assert on_disk.strip() == text.strip()
