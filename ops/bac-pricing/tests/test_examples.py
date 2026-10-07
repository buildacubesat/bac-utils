# SPDX-License-Identifier: MIT
"""The shipped examples are Build a CubeSat's own numbers; they must load, validate and follow the conventions."""

from __future__ import annotations

import csv
from pathlib import Path

from bac_pricing import engine as eng
from bac_pricing import store

from bac_suite_db.sku import is_sku

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_examples_load_validate_and_price():
    assert sorted(p.name for p in EXAMPLES.iterdir()) == sorted(store.DATA_FILES)
    model = eng.load_model(EXAMPLES)
    assert eng.validate_model(model) == []
    assert store.plan(EXAMPLES)["items"] == len(model.items)
    pr = eng.derive_root_price(model, eng.rollup(model, "dev_kit_v1", 25))
    assert pr.valid and pr.price_rounded > 0


def test_example_skus_follow_the_scheme():
    with (EXAMPLES / "bac-items.csv").open(newline="", encoding="utf-8") as fh:
        skus = [r["sku"] for r in csv.DictReader(fh) if r["sku"]]
    assert skus and all(is_sku(s) for s in skus)
    with (EXAMPLES / "bac-catalog.csv").open(newline="", encoding="utf-8") as fh:
        catalog = {r["sku"] for r in csv.DictReader(fh)}
    assert catalog <= set(skus)


def test_example_typography():
    for path in EXAMPLES.iterdir():
        text = path.read_text(encoding="utf-8")
        assert "\u2014" not in text, path.name
        assert " -> " not in text, path.name
