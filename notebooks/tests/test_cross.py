# SPDX-License-Identifier: MIT
"""The profile exchange between the siblings: each tool loads what the others export.

What each tool takes from a sibling's profile is in the handoffs (link budget §3, optical payload §3,
power budget §12, orbital lifetime §7). Every run here is a patched headless run of the loading tool.
"""

import tomllib

import pytest

import notebook_harness

LB = notebook_harness.notebook_path("bac_link_budget")
OP = notebook_harness.notebook_path("bac_optical_payload")
PB = notebook_harness.notebook_path("bac_power_budget")
OL = notebook_harness.notebook_path("bac_orbital_lifetime")

LB_PROFILE = notebook_harness.run(LB)[2]["profile_toml"]
OP_PROFILE = notebook_harness.run(OP)[2]["profile_toml"]
PB_PROFILE = notebook_harness.run(PB)[2]["profile_toml"]


def test_exports_name_their_tool():
    for text, tool in (
        (LB_PROFILE, "bac_link_budget"),
        (OP_PROFILE, "bac_optical_payload"),
        (PB_PROFILE, "bac_power_budget"),
    ):
        doc = tomllib.loads(text)
        assert doc["tool"] == tool
        assert "orbit" in doc and doc["orbit"]["altitude_km"] == 450


def test_optical_payload_takes_the_link_budget_volume():
    """The featured mode's usable kB/day lands in the slot the link budget's role names (low rate)."""
    d = notebook_harness.run(OP, LB_PROFILE)[2]
    assert d["profile_tool"] == "bac_link_budget"
    assert d["target_name"] == "Bern"
    assert d["low_kb"] == pytest.approx(3221, abs=1)
    assert d["days_raw_low"] == pytest.approx(5.74, abs=0.01)


def test_link_budget_takes_the_target_as_station():
    d = notebook_harness.run(LB, OP_PROFILE)[2]
    assert d["profile_tool"] == "bac_optical_payload"
    assert d["station_name"] == "Bern"
    assert d["passes_per_day"] == pytest.approx(3.429, abs=0.001)


def test_power_budget_takes_station_share_and_backstop_airtime():
    d = notebook_harness.run(PB, LB_PROFILE)[2]
    assert d["profile_tool"] == "bac_link_budget"
    assert d["station_name"] == "Bern"
    assert 45 < d["gen_wh_day"] < 55  # generation stays this tool's own; the link budget's epoch moves it a little
    # the LoRa backstop's time on air comes from the link budget's SF12 row (1.81 s for 32 bytes), not the 2.5 s default
    res = tomllib.loads(LB_PROFILE)["results"]["link_budget"]
    sf12 = next(m for m in res["modes"] if m["mode"] == "LoRa SF12")
    assert sf12["packet_airtime_ms"] == pytest.approx(1810, abs=1)
    assert d["ui_lora_s"].value == pytest.approx(1.81, abs=0.01)


def test_power_budget_takes_target_reach_and_frames_from_the_optical_payload():
    d = notebook_harness.run(PB, OP_PROFILE)[2]
    assert d["profile_tool"] == "bac_optical_payload"
    assert d["target_name"] == "Bern"
    assert d["sim_days"] == 7  # the optical payload's 30-day span is clamped to this tool's slider


def test_orbital_lifetime_takes_the_orbit_only():
    d = notebook_harness.run(OL, PB_PROFILE)[2]
    assert d["profile_tool"] == "bac_power_budget"
    assert d["altitude_km"] == 450
    assert d["form_factor"] == "1.5U"  # this tool's default kept
