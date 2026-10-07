# SPDX-License-Identifier: MIT
"""The parity suite of bac-pricing 1.3.0 (``test_parity.py``) as pytest, plus the validator."""

from __future__ import annotations

import copy
import tomllib

import pytest
from bac_pricing import engine as eng
from pricing_testkit import BATCH, FIXTURES, ROOT


@pytest.fixture(scope="module")
def model():
    return eng.load_model(FIXTURES)


@pytest.fixture(scope="module")
def rollup(model):
    return eng.rollup(model, ROOT, BATCH)


@pytest.fixture(scope="module")
def price(model, rollup):
    return eng.derive_root_price(model, rollup)


def test_cost_rollup_batch_25(rollup):
    assert rollup.base == pytest.approx(10470.23, abs=0.01)
    assert rollup.landed == pytest.approx(12058.69, abs=0.01)
    assert rollup.consumables == pytest.approx(175.25, abs=0.01)
    assert rollup.labour_min_per_unit == pytest.approx(239.00, abs=0.01)
    assert rollup.labour == pytest.approx(1369.27, abs=0.01)
    assert rollup.total == pytest.approx(15711.71, abs=0.01)
    assert rollup.cost_per_unit == pytest.approx(628.47, abs=0.01)


def test_price_derivation(price):
    assert price.valid
    assert price.weighted_paying_units == 14.5
    assert price.base_price == pytest.approx(1137.74, abs=0.01)
    assert price.price_rounded == 1138.00
    assert price.net_revenue == pytest.approx(price.target_revenue, abs=0.01)
    assert price.realised_margin == pytest.approx(0.20, abs=1e-9)


def test_legacy_chain_reproduced(rollup):
    """The spreadsheet's figure with its buggy landed cost: 1'449.42 USD."""
    direct = 11452.79 + 175.25 + rollup.labour
    legacy = ((direct * 1.155 / 0.8) - 5 * (direct * 1.155 / 25)) / 14.5 / 0.75
    assert legacy == pytest.approx(1449.42, abs=0.01)


def test_rounding():
    assert eng.round_price(1516.99, "up", 1.0) == 1517
    assert eng.round_price(1516.99, "down", 5.0) == 1515
    assert eng.round_price(1516.99, "nearest", 49.0) == 1519.0
    assert eng.round_price(12.3, "up", 0) == 12.3


def _with_batch(model, **batch):
    m = copy.deepcopy(model)
    m.cfg["batch"].update(batch)
    return m


def test_unpriceable_composition_is_flagged_not_negative(model):
    bad = _with_batch(model, ordered=5)
    pr = eng.derive_root_price(bad, eng.rollup(bad, ROOT, 5))
    assert pr.valid is False and pr.base_price == 0.0 and "Unpriceable" in pr.error


def test_single_clean_unit_keeps_the_margin(model):
    lo = _with_batch(model, ordered=1, lost=0, donations=0, returns=0, warranty=0, reserved=0, not_sold=0)
    for t in lo.cfg["discount_tiers"]:
        t["units"] = 0
    pr = eng.derive_root_price(lo, eng.rollup(lo, ROOT, 1))
    assert pr.valid and pr.realised_margin == pytest.approx(0.20, abs=1e-9)


def test_absorbed_discounts(model, price):
    bc = model.cfg["batch"]
    zero = sum(bc[k] for k in ("lost", "donations", "returns", "warranty", "reserved", "not_sold"))
    expected = zero * price.base_price
    for t in model.cfg["discount_tiers"]:
        if t["kind"] == "percentage":
            expected += t["units"] * t["value"] * price.base_price
        elif t["kind"] == "at_cost":
            expected += t["units"] * max(price.base_price - price.np_basis_cost, 0)
    assert price.absorbed_discounts == pytest.approx(expected, abs=0.01)


def test_domestic_anchor_and_manual_adjust(model, price):
    reg = {r["region"]: r for r in eng.regional_prices(model, price.base_price, "CH")}
    rounded = eng.round_price(
        price.base_price, model.cfg["rounding"]["direction"], float(model.cfg["rounding"]["multiple"])
    )
    assert reg["CH"]["price_multiplier"] == rounded
    m2 = copy.deepcopy(model)
    for r in m2.cfg["regions"]:
        if r["label"] == "CA":
            r["adjust"] = 2.0
    ca = {r["region"]: r for r in eng.regional_prices(m2, price.base_price, "CH")}["CA"]
    assert ca["price"] == ca["price_multiplier"] + 2.0
    assert tomllib.loads(eng.dump_config(m2.cfg))["regions"][4]["adjust"] == 2.0


def test_rebase_fx_round_trips():
    fx0 = {"CHF": 1.0, "USD": 0.75, "EUR": 0.94}
    usd = eng.rebase_fx(fx0, "USD")
    assert usd["USD"] == 1.0 and abs(usd["CHF"] - 1 / 0.75) < 1e-3
    back = eng.rebase_fx(usd, "CHF")
    assert abs(back["USD"] - 0.75) < 1e-4 and back["CHF"] == 1.0
    assert eng.rebase_fx(fx0, "JPY") == fx0


def test_dump_config_round_trips_and_keeps_every_currency(model):
    text = eng.dump_config(model.cfg)
    parsed = tomllib.loads(text)
    assert parsed["financials"]["target_margin"] == 0.20
    for c in ("USD", "EUR", "GBP", "AUD", "CAD", "CHF"):
        assert c in parsed["fx"]
    assert "\u2014" not in text and " - " not in text
    assert text.startswith("# Build a CubeSat – pricing configuration")


def test_price_list_covers_every_sellable_item(model):
    rows = eng.price_list(model, BATCH)
    assert {r["sku"] for r in rows} == {"bac-dev-kit-2u-v1r1", "bac-dev-eps-main-board-v2r2", "bac-edu-kit-1u-v1r1"}
    kit = next(r for r in rows if r["item_id"] == ROOT)
    assert kit["price"] == pytest.approx(1137.74, abs=0.01)


def test_validate_model_is_clean_on_the_fixture(model):
    assert eng.validate_model(model) == []


def test_validate_model_reports_each_kind_of_problem(model):
    m = copy.deepcopy(model)
    m.items["ghost_ref"] = {
        "item_id": "ghost_ref",
        "sku": "",
        "name": "x",
        "type": "part",
        "vendor": "Nobody",
        "sellable": "false",
    }
    m.edges.append(
        {
            "parent_id": ROOT,
            "child_id": "nowhere",
            "qty_per_parent": "-1",
            "assy_min": 0,
            "qc_min": 0,
            "pack_min": 0,
            "ship_min": 0,
            "consumables": 0,
        }
    )
    m.edges.append(
        {
            "parent_id": "structure",
            "child_id": ROOT,
            "qty_per_parent": 1,
            "assy_min": 0,
            "qc_min": 0,
            "pack_min": 0,
            "ship_min": 0,
            "consumables": 0,
        }
    )
    m.items[ROOT]["sku"] = "BAC-HW-KIT-0001-R1"
    m.items["eps_v2"]["sku"] = ""
    m.breaks["stray"] = [(1.0, 1.0)]
    m.children = {}
    for e in m.edges:
        m.children.setdefault(e["parent_id"], []).append(e)
    problems = eng.validate_model(m)
    text = "\n".join(problems)
    assert "child_id 'nowhere'" in text
    assert "negative qty_per_parent" in text
    assert "vendor 'Nobody'" in text
    assert "does not follow the scheme: BAC-HW-KIT-0001-R1" in text
    assert "eps_v2 is sellable but has no SKU" in text
    assert "item 'stray'" in text
    assert "cycle" in text and "structure" in text
