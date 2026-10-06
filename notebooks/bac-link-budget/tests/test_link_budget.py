# SPDX-License-Identifier: MIT
"""Regression checks for bac_link_budget.py against the 0.7.1 handoff (§5, numbers at the defaults, 500 km).

From the bac-utils root: uv run pytest notebooks/bac-link-budget -q
"""

import tomllib

import pytest

import notebook_harness

NOTEBOOK = notebook_harness.notebook_path("bac_link_budget")
MOD, OUT, D = notebook_harness.run(NOTEBOOK)


def _run(profile_toml: str) -> dict:
    return notebook_harness.run(NOTEBOOK, profile_toml)[2]


def _mode(defs, name):
    table = defs["mode_summary"]
    row = table[table["mode"] == name]
    assert len(row) == 1, f"mode {name!r} not found once in {list(table['mode'])}"
    return row.iloc[0]


def test_version_and_defaults():
    assert D["TOOL_VERSION"] == "0.7.1"
    assert D["profile_tool"] == "bac_link_budget"
    assert D["half_duplex"] is True
    assert not D["profile_warnings"]


def test_pass_statistics_bern_500_km():
    """Bern, 500 km SSO, 10° minimum elevation, seven days × eight phases."""
    assert D["passes_per_day"] == pytest.approx(3.679, abs=0.001)
    assert D["mean_pass_min"] == pytest.approx(5.67, abs=0.01)
    assert D["contact_min_per_day"] == pytest.approx(20.85, abs=0.01)
    assert D["longest_gap_h"] == pytest.approx(12.85, abs=0.01)
    assert float(D["orbital_period_min"]) == pytest.approx(94.47, abs=0.01)
    assert D["vis_radius_km"] == pytest.approx(1563, abs=1)


def test_gfsk_row():
    r = _mode(D, "50k GFSK")
    assert r["info_rate_bps"] == 50_000
    assert r["margin_at_min_el_db"] == pytest.approx(1.0, abs=0.05)
    assert r["margin_at_zenith_db"] == pytest.approx(12.7, abs=0.05)
    assert r["kB_per_avg_pass"] == pytest.approx(862, abs=1)
    assert r["kB_per_day"] == pytest.approx(3171, abs=1)
    assert r["kB_per_day_p10"] == pytest.approx(2720, abs=1)
    assert r["kB_per_day_if_only_closing"] == pytest.approx(5005, abs=1)
    assert r["uplink_margin_at_min_el_db"] == pytest.approx(12.6, abs=0.05)
    assert r["uplink_kB_per_day"] == pytest.approx(1251, abs=1)


def test_cw_beacon_margins():
    r = _mode(D, "CW beacon")
    assert r["margin_at_min_el_db"] == pytest.approx(31.8, abs=0.05)
    assert r["margin_at_zenith_db"] == pytest.approx(43.5, abs=0.05)


def test_lora_rows_use_packet_airtime():
    """SX1276 §4.1.1.7: 32-byte payload, 8-symbol preamble, explicit header, CRC on."""
    sf7 = _mode(D, "LoRa SF7")
    assert sf7["info_rate_bps"] == pytest.approx(3559, abs=1)
    assert sf7["packet_airtime_ms"] == pytest.approx(71.9, abs=0.1)
    assert sf7["margin_at_min_el_db"] == pytest.approx(8.4, abs=0.05)
    assert sf7["kB_per_day"] == pytest.approx(445, abs=1)
    assert sf7["uplink_margin_at_min_el_db"] == pytest.approx(29.9, abs=0.05)
    sf12 = _mode(D, "LoRa SF12")
    assert sf12["info_rate_bps"] == pytest.approx(141, abs=1)
    assert sf12["packet_airtime_ms"] == pytest.approx(1810, abs=1)
    assert sf12["margin_at_min_el_db"] == pytest.approx(20.9, abs=0.05)
    assert sf12["kB_per_day"] == pytest.approx(17.7, abs=0.1)
    assert sf12["uplink_margin_at_min_el_db"] == pytest.approx(42.4, abs=0.05)
    # the datasheet formula itself
    assert D["lora_packet_s"](12, 125_000, 32, 8) == pytest.approx(1.810, abs=0.001)


def test_profile_export_contract():
    p = tomllib.loads(D["profile_toml"])
    assert p["tool"] == "bac_link_budget"
    assert p["tool_version"] == "0.7.1"
    assert p["spacecraft"]["duplex"] == "half"
    res = p["results"]["link_budget"]
    assert res["featured_mode"] == "50k GFSK"
    assert res["usable_kb_per_day"] == pytest.approx(3171, abs=1)
    assert res["usable_kb_per_day_p10"] == pytest.approx(2720, abs=1)
    assert res["passes_per_day"] == pytest.approx(3.679, abs=0.001)
    assert res["downlink_share_pct"] == 80
    modes = {m["mode"]: m for m in res["modes"]}
    assert modes["LoRa SF12"]["packet_airtime_ms"] == pytest.approx(1810, abs=1)
    # reload: the results table is ignored and the headline is reproduced
    d2 = _run(D["profile_toml"])
    assert d2["profile_tool"] == "bac_link_budget"
    assert _mode(d2, "50k GFSK")["kB_per_day"] == pytest.approx(3171, abs=1)


def test_s_band_profile_is_full_duplex():
    d = _run(D["PROFILE_SBAND"])
    assert d["half_duplex"] is False
    r = _mode(d, d["featured_mode"])
    assert r["kB_per_day"] == pytest.approx(2395, abs=1)
    assert r["kB_per_day_p10"] == pytest.approx(400, abs=1)


def test_generic_profile():
    d = _run(D["PROFILE_GENERIC"])
    assert d["half_duplex"] is True
    r = _mode(d, d["featured_mode"])
    assert "GMSK" in r["modulation"] or "9k6" in d["featured_mode"]
    assert r["kB_per_day"] == pytest.approx(1364, abs=1)


def test_duplicate_mode_names_are_skipped():
    toml = (
        D["PROFILE_BAC"]
        + """
[[modes]]
mode = "50k GFSK"
modulation = "GFSK h=1, non-coherent"
bitrate_bps = 9600
tx_dbm = 30.0
downlink = true
"""
    )
    d = _run(toml)
    assert d["duplicate_modes"]
    assert list(d["mode_summary"]["mode"]).count("50k GFSK") == 1


def test_example_profiles_are_the_shipped_ones():
    examples = NOTEBOOK.parent / "examples"
    shipped = {
        "bac-demo-uhf": D["PROFILE_BAC"],
        "bac-demo-s-band": D["PROFILE_SBAND"],
        "generic-amateur-1u": D["PROFILE_GENERIC"],
    }
    for slug, text in shipped.items():
        on_disk = (examples / f"bac-link-budget-profile-{slug}.toml").read_text(encoding="utf-8")
        assert on_disk.strip() == text.strip()
