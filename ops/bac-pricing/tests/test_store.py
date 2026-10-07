# SPDX-License-Identifier: MIT
"""The store on the in-memory connection: import, load, export round trip, saves, files mode."""

from __future__ import annotations

import datetime as dt
import tomllib

import pytest
from bac_pricing import engine as eng
from bac_pricing import store
from pricing_testkit import BATCH, ROOT, write_db_config

from bac_common.errors import BacError, ConfigError
from bac_suite_db import config, schema
from bac_suite_db.testing import FakeConn


def _price(model):
    return eng.derive_root_price(model, eng.rollup(model, ROOT, BATCH))


@pytest.fixture
def conn():
    c = FakeConn()
    schema.migrate(c, [store.ENGINE])
    return c


def test_engine_registration():
    assert store.ENGINE.name == "pricing"
    assert store.ENGINE.tables == store.TABLES
    assert schema.table_names(store.DDL) == list(store.TABLES)
    assert store.ENGINE.files[-1] == "bac-catalog.csv"


def test_plan_counts_without_touching_anything(fixtures):
    assert store.plan(fixtures) == {
        "items": 62,
        "catalog rows": 3,
        "bom edges": 67,
        "price breaks": 46,
        "overrides": 0,
        "params versions": 1,
    }


def test_plan_reports_missing_files_and_bad_data(tmp_path, data_dir):
    with pytest.raises(BacError, match="missing"):
        store.plan(tmp_path)
    items = data_dir / "bac-items.csv"
    items.write_text(items.read_text().replace("bac-dev-kit-2u-v1r1", "BAC-HW-KIT-0001-R1"))
    with pytest.raises(BacError, match="problem") as info:
        store.plan(data_dir)
    assert "BAC-HW-KIT-0001-R1" in info.value.detail


def test_import_load_parity_and_export_round_trip(conn, fixtures, tmp_path):
    counts = store.import_files(conn, fixtures)
    assert counts["items"] == 62 and counts["catalog rows"] == 3
    assert conn.commits == 2
    model = store.load_model_pg(conn)
    file_model = eng.load_model(fixtures)
    pr, pr_files = _price(model), _price(file_model)
    assert pr.base_price == pytest.approx(pr_files.base_price, abs=1e-9)
    assert pr.price_rounded == 1138.0
    assert eng.rollup(model, ROOT, BATCH).landed == pytest.approx(eng.rollup(file_model, ROOT, BATCH).landed, abs=1e-9)
    assert model.cfg == file_model.cfg
    out = tmp_path / "export"
    written = store.export_files(conn, out)
    assert written == list(store.DATA_FILES)
    again = eng.load_model(out)
    assert _price(again).base_price == pytest.approx(pr.base_price, abs=1e-9)
    assert eng.validate_model(again) == []
    catalog = (out / "bac-catalog.csv").read_text().splitlines()
    assert catalog[0].startswith("sku,item_id,name,category")
    assert any(
        line.startswith("bac-dev-kit-2u-v1r1,dev_kit_v1,Dev Kit v1,dev,") and ",902300,CH," in line for line in catalog
    )


def test_catalog_seed_comes_from_the_file_not_the_code(conn, data_dir):
    (data_dir / "bac-catalog.csv").unlink()
    store.import_files(conn, data_dir)
    rows = {r["sku"]: r for r in conn.tables["bac.catalog"]}
    assert set(rows) == {"bac-dev-kit-2u-v1r1", "bac-dev-eps-main-board-v2r2", "bac-edu-kit-1u-v1r1"}
    assert rows["bac-dev-kit-2u-v1r1"]["hs_code"] is None  # nothing seeded by the code


def test_reimport_keeps_catalog_values_the_files_do_not_carry(conn, fixtures, data_dir):
    store.import_files(conn, fixtures)
    conn.execute(
        "INSERT INTO bac.catalog (sku, item_id, name, net_weight_g) VALUES (%s,%s,%s,%s) ON CONFLICT (sku) DO UPDATE SET"
        " net_weight_g=EXCLUDED.net_weight_g",
        ("bac-dev-kit-2u-v1r1", "dev_kit_v1", "Dev Kit v1", 1200),
    )
    store.import_files(conn, data_dir)
    row = next(r for r in conn.tables["bac.catalog"] if r["sku"] == "bac-dev-kit-2u-v1r1")
    assert row["net_weight_g"] == 1200 and row["hs_code"] == "902300"


def test_load_without_params_points_at_import(conn):
    with pytest.raises(BacError, match="pricing.params is empty"):
        store.load_model_pg(conn)


def test_save_pricing_replaces_data_and_appends_params(conn, fixtures):
    store.import_files(conn, fixtures)
    model = store.load_model_pg(conn)
    model.edges = model.edges[:10]
    model.cfg["financials"]["target_margin"] = 0.25
    out = store.save_pricing(conn, model, save_data=True, save_params=False)
    assert out == {"data": True, "params_version": None}
    assert len(conn.tables["pricing.bom"]) == 10
    assert store.load_model_pg(conn).cfg["financials"]["target_margin"] == 0.2
    out = store.save_pricing(conn, model, save_data=False, save_params=True, note="margin 25")
    assert out["params_version"] == 2
    assert store.load_model_pg(conn).cfg["financials"]["target_margin"] == 0.25


def test_db_status_labels_utc_after_converting(conn, fixtures):
    assert store.db_status(conn)[0][1].startswith("none")
    store.import_files(conn, fixtures)
    conn.tables["pricing.params"][0]["created_at"] = dt.datetime(
        2026, 10, 7, 12, 30, tzinfo=dt.timezone(dt.timedelta(hours=2))
    )
    label, value = store.db_status(conn)[0]
    assert label == "params" and value.startswith("v1 · 2026-10-07 10:30 UTC · import from")


def test_files_mode_load_save_backup(files_settings, data_dir):
    model = store.load_source(files_settings)
    assert _price(model).price_rounded == 1138.0
    backup = store.backup_files(data_dir, when=dt.datetime(2026, 10, 7, 8, 0, 0))
    assert backup == data_dir / "backups" / "2026-10-07T08-00-00"
    assert sorted(p.name for p in backup.iterdir()) == sorted(store.DATA_FILES)
    model.cfg["financials"]["target_margin"] = 0.3
    model.breaks["rails_2u"] = [(10.0, 20.0)]
    assert store.save_files(model, data_dir, data=True, config=False) == list(store.EDITABLE_FILES)
    assert "consumables_chf" in (data_dir / "bac-bom.csv").read_text().splitlines()[0]
    assert "rails_2u,10.0,20.0" in (data_dir / "bac-price-breaks.csv").read_text()
    assert store.save_files(model, data_dir, data=False, config=True) == ["bac-pricing-config.toml"]
    assert tomllib.loads((data_dir / "bac-pricing-config.toml").read_text())["financials"]["target_margin"] == 0.3
    assert _price(eng.load_model(data_dir)).valid


def test_files_mode_without_data_is_a_config_error(tmp_path):
    settings = config.Settings("files", tmp_path / "empty", None, tmp_path / "c.toml", None)
    with pytest.raises(ConfigError, match="No pricing data"):
        store.load_source(settings)


def test_switch_base_currency_files(files_settings, data_dir):
    assert store.switch_base_currency(files_settings, "chf")["unchanged"]
    r = store.switch_base_currency(files_settings, "USD", add_columns=False)
    assert r["missing"] == [
        "bac-bom.csv → consumables_usd",
        "bac-price-overrides.csv → additive_usd",
        "bac-price-overrides.csv → absolute_usd",
    ]
    assert tomllib.loads((data_dir / "bac-pricing-config.toml").read_text())["financials"]["base_currency"] == "CHF"
    r = store.switch_base_currency(files_settings, "USD")
    assert r["missing"] == [] and len(r["added"]) == 3
    assert tomllib.loads((data_dir / "bac-pricing-config.toml").read_text())["financials"]["base_currency"] == "USD"
    header = (data_dir / "bac-bom.csv").read_text().splitlines()[0]
    assert "consumables_chf" in header and "consumables_usd" in header
    model = eng.load_model(data_dir)  # loads with the new suffix
    assert model.cfg["financials"]["base_currency"] == "USD"


def test_switch_base_currency_db(fake_conn, fixtures, tmp_path, monkeypatch):
    schema.migrate(fake_conn, [store.ENGINE])
    store.import_files(fake_conn, fixtures)
    monkeypatch.setenv(config.DSN_ENV, "postgresql://bac@h/bac")
    settings = config.load_settings(write_db_config(tmp_path, tmp_path))
    assert store.switch_base_currency(settings, "CHF")["unchanged"]
    r = store.switch_base_currency(settings, "EUR")
    assert r == {"old": "CHF", "new": "EUR", "version": 2}
    assert store.load_model_pg(fake_conn).cfg["financials"]["base_currency"] == "EUR"


def test_primary_price_factor(fixtures):
    cfg = eng.load_model(fixtures).cfg
    factor, ccy = store.primary_price_factor(cfg, "US", "CH")
    assert ccy == "USD" and factor == pytest.approx((1.1 / 1.1) / 0.75)
    factor, ccy = store.primary_price_factor(cfg, "EU", "CH")
    assert ccy == "EUR" and factor == pytest.approx((1.0 / 1.1) / 0.94)
    factor, ccy = store.primary_price_factor(cfg, None, None)
    assert ccy == "CHF" and factor == 1.0


def test_price_break_notes_and_edge_notes_survive_the_round_trip(conn, data_dir, tmp_path):
    breaks = data_dir / "bac-price-breaks.csv"
    breaks.write_text(breaks.read_text().replace("rails_2u,10.0,18.0,", "rails_2u,10.0,18.0,PCBWay quote 2026-05"))
    model = eng.load_model(data_dir)
    assert model.break_notes == {("rails_2u", 10.0): "PCBWay quote 2026-05"}
    store.import_files(conn, data_dir)
    loaded = store.load_model_pg(conn)
    assert loaded.break_notes == {("rails_2u", 10.0): "PCBWay quote 2026-05"}
    assert sum(1 for e in loaded.edges if e["notes"]) == sum(1 for e in model.edges if e["notes"]) == 11
    out = tmp_path / "export"
    store.export_files(conn, out)
    assert "rails_2u,10.0,18.0,PCBWay quote 2026-05" in (out / "bac-price-breaks.csv").read_text()
    assert "Shared fastener reused in packaging" in (out / "bac-bom.csv").read_text()
    header = (out / "bac-bom.csv").read_text().splitlines()[0]
    assert header == (data_dir / "bac-bom.csv").read_text().splitlines()[0]


def test_exports_are_deterministic(conn, fixtures, tmp_path):
    store.import_files(conn, fixtures)
    store.export_files(conn, tmp_path / "a")
    store.export_files(conn, tmp_path / "b")
    for name in store.DATA_FILES:
        if name != "bac-pricing-config.toml":  # carries today's date
            assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_plan_rejects_a_bad_catalog_file(data_dir):
    cat = data_dir / "bac-catalog.csv"
    cat.write_text(cat.read_text().replace("bac-edu-kit-1u-v1r1,edu_kit_v1", "bac-edu-kit-1u-v1r1,ghost"))
    with pytest.raises(BacError, match="bac-catalog.csv") as info:
        store.plan(data_dir)
    assert "ghost" in info.value.detail
    cat.write_text(cat.read_text().replace("bac-edu-kit-1u-v1r1,ghost", "BAC-EDU,edu_kit_v1"))
    with pytest.raises(BacError, match="bac-catalog.csv"):
        store.plan(data_dir)


def test_a_failed_import_leaves_the_database_as_it_was(conn, fixtures, data_dir, monkeypatch):
    """Validation catches bad files before a connection; a failure inside the transaction rolls back."""
    store.import_files(conn, fixtures)
    before = {t: len(rows) for t, rows in conn.tables.items()}
    bom = data_dir / "bac-bom.csv"
    bom.write_text(bom.read_text().replace("structure,rails_2u,4,2.0", "structure,rails_2u,,2.0"))
    with pytest.raises(BacError, match="problem") as info:
        store.import_files(conn, data_dir)
    assert "empty qty_per_parent" in info.value.detail
    assert {t: len(rows) for t, rows in conn.tables.items()} == before

    def boom(cur, rows):
        raise RuntimeError("catalog write failed")

    monkeypatch.setattr(store.items, "upsert_catalog", boom)
    with pytest.raises(RuntimeError), conn:  # the CLI's `with state.connect() as conn` pattern
        store.import_files(conn, fixtures)
    conn.closed = False
    assert {t: len(rows) for t, rows in conn.tables.items()} == before


def test_engine_replaced_tables_exclude_params():
    assert store.ENGINE.replaced == ("pricing.bom", "pricing.price_breaks", "pricing.overrides")
