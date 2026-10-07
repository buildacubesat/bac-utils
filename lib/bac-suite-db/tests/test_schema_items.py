# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from bac_suite_db import items, schema
from bac_suite_db.sku import SkuError
from bac_suite_db.testing import FakeConn


def test_table_names_in_ddl_order():
    assert schema.table_names(schema.SHARED_DDL) == ["bac.items", "bac.catalog"]
    assert schema.SHARED_TABLES == ("bac.items", "bac.catalog")


def test_migrate_runs_shared_then_engine_scripts(stub_engine):
    conn = FakeConn()
    created = schema.migrate(conn, [stub_engine.engine])
    assert created == ["bac.items", "bac.catalog", "stub.rows"]
    assert conn.commits == 1
    assert conn.ddl[0].strip().startswith("CREATE SCHEMA IF NOT EXISTS bac;")
    assert set(conn.tables) == {"bac.items", "bac.catalog", "stub.rows"}


def test_find_engine(stub_engine):
    assert schema.find_engine([stub_engine.engine], "stub") is stub_engine.engine
    assert schema.find_engine([stub_engine.engine], "nope") is None


def test_discover_engines_sees_the_installed_pricing_engine():
    names = [e.name for e in schema.discover_engines()]
    assert "pricing" in names


def test_table_counts():
    conn = FakeConn()
    schema.migrate(conn, [])
    assert schema.table_counts(conn, schema.SHARED_TABLES) == {"bac.items": 0, "bac.catalog": 0}


def _item(item_id, **kw):
    row = {"item_id": item_id, "sku": "", "name": item_id.title(), "type": "part", "sellable": "false"}
    row.update(kw)
    return row


def test_upsert_items_round_trips_as_strings():
    conn = FakeConn()
    schema.migrate(conn, [])
    with conn.cursor() as cur:
        n = items.upsert_items(
            cur,
            [_item("rail", vendor="PCBWay"), _item("kit", sku="bac-dev-kit-2u-v1r1", type="assembly", sellable="true")],
        )
        assert n == 2
        loaded = items.load_items(cur)
    assert loaded["rail"]["sellable"] == "false" and loaded["rail"]["vendor"] == "PCBWay"
    assert loaded["kit"]["sellable"] == "true" and loaded["kit"]["sku"] == "bac-dev-kit-2u-v1r1"
    assert loaded["rail"]["sku"] == ""  # NULL comes back as the empty string, like the CSV
    with conn.cursor() as cur:
        items.upsert_items(cur, [_item("rail", vendor="Digikey")])
        assert items.load_items(cur)["rail"]["vendor"] == "Digikey"
        assert len(conn.tables["bac.items"]) == 2


def test_upsert_items_rejects_a_bad_sku_before_writing():
    conn = FakeConn()
    schema.migrate(conn, [])
    with conn.cursor() as cur, pytest.raises(SkuError):
        items.upsert_items(cur, [_item("kit", sku="BAC-HW-KIT-0001-R1")])
    assert conn.tables["bac.items"] == []


def test_catalog_upsert_keeps_stored_values_when_the_import_leaves_them_empty():
    conn = FakeConn()
    schema.migrate(conn, [])
    with conn.cursor() as cur:
        items.upsert_catalog(
            cur,
            [
                {
                    "sku": "bac-dev-kit-2u-v1r1",
                    "item_id": "kit",
                    "name": "Kit",
                    "hs_code": "902300",
                    "net_weight_g": "1200",
                }
            ],
        )
        items.upsert_catalog(cur, [{"sku": "bac-dev-kit-2u-v1r1", "item_id": "kit", "name": "Kit", "category": "dev"}])
        rows = items.load_catalog(cur)
    assert len(rows) == 1
    assert rows[0]["hs_code"] == "902300" and rows[0]["net_weight_g"] == "1200" and rows[0]["category"] == "dev"


def test_catalog_typed_columns_and_sku_validation():
    assert items._typed("net_weight_g", "12.0") == 12
    assert items._typed("declared_value", "990.50") == 990.5
    assert items._typed("hs_code", " 902300 ") == "902300"
    assert items._typed("hs_code", "") is None
    conn = FakeConn()
    schema.migrate(conn, [])
    with conn.cursor() as cur, pytest.raises(SkuError):
        items.upsert_catalog(cur, [{"sku": "nope", "name": "x"}])


def test_catalog_row_without_a_name_keeps_the_stored_one():
    conn = FakeConn()
    schema.migrate(conn, [])
    with conn.cursor() as cur:
        items.upsert_catalog(cur, [{"sku": "bac-dev-kit-2u-v1r1", "name": "Dev Kit v1"}])
        items.upsert_catalog(cur, [{"sku": "bac-dev-kit-2u-v1r1", "hs_code": "902300"}])
        items.upsert_catalog(cur, [{"sku": "bac-edu-kit-1u-v1r1"}])
        rows = {r["sku"]: r for r in items.load_catalog(cur)}
    assert rows["bac-dev-kit-2u-v1r1"]["name"] == "Dev Kit v1" and rows["bac-dev-kit-2u-v1r1"]["hs_code"] == "902300"
    assert rows["bac-edu-kit-1u-v1r1"]["name"] == "bac-edu-kit-1u-v1r1"  # nothing better known yet


def test_engine_replaced_defaults_to_every_table(stub_engine):
    assert stub_engine.engine.replaced == stub_engine.engine.tables
    partial = schema.Engine(
        "x", "", ("a.b", "a.c"), (), lambda d: {}, lambda c, d: {}, lambda c, d: [], replaced=("a.b",)
    )
    assert partial.replaced == ("a.b",)
