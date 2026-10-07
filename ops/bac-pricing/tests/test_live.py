# SPDX-License-Identifier: MIT
"""The same import → load → export round trip against a PostgreSQL server.

Runs only with ``BAC_TEST_DSN`` set, and only when the database it names has
``test`` in its name: the test drops and recreates the ``bac`` and ``pricing``
schemas, so it must never see the production store. The configured suite DSN
(``BAC_DB_DSN``) is deliberately ignored here.
"""

from __future__ import annotations

import os

import pytest
from bac_pricing import engine as eng
from bac_pricing import store
from pricing_testkit import BATCH, FIXTURES, ROOT

from bac_suite_db import schema
from bac_suite_db.dsn import describe

DSN = os.environ.get("BAC_TEST_DSN", "")


def is_test_database(name: str) -> bool:
    """``test``, ``bac_test``, ``test_bac``, ``pricing_test_db`` – a whole segment, never a substring."""
    return "test" in name.lower().replace("-", "_").split("_")


def test_the_guard_itself():
    assert is_test_database("bac_test") and is_test_database("test") and is_test_database("TEST-pricing")
    assert not is_test_database("latest") and not is_test_database("contest") and not is_test_database("bac")


@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from psycopg import conninfo

    database = str(conninfo.conninfo_to_dict(DSN).get("dbname") or describe(DSN).rsplit("/", 1)[-1])
    if not is_test_database(database):
        pytest.skip(f"BAC_TEST_DSN names '{database}', not a test database – refusing to drop its schemas")
    c = psycopg.connect(DSN)
    with c.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS pricing CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS bac CASCADE")
    c.commit()
    yield c
    c.close()


LIVE = pytest.mark.skipif(not DSN, reason="BAC_TEST_DSN not set – no live database")


@LIVE
def test_migrate_is_idempotent(conn):
    created = schema.migrate(conn, [store.ENGINE])
    assert created == ["bac.items", "bac.catalog", *store.TABLES]
    assert schema.migrate(conn, [store.ENGINE]) == created


@LIVE
def test_import_parity_export_round_trip(conn, tmp_path):
    counts = store.import_files(conn, FIXTURES)
    assert counts["items"] == 62 and counts["bom edges"] == 67
    model = store.load_model_pg(conn)
    files = eng.load_model(FIXTURES)
    assert eng.rollup(model, ROOT, BATCH).landed == pytest.approx(eng.rollup(files, ROOT, BATCH).landed, abs=1e-6)
    pr = eng.derive_root_price(model, eng.rollup(model, ROOT, BATCH))
    assert pr.base_price == pytest.approx(1137.74, abs=0.01) and pr.price_rounded == 1138.0
    assert schema.table_counts(conn, schema.SHARED_TABLES + store.TABLES) == {
        "bac.items": 62,
        "bac.catalog": 3,
        "pricing.bom": 67,
        "pricing.price_breaks": 46,
        "pricing.overrides": 0,
        "pricing.params": 1,
    }
    out = tmp_path / "export"
    store.export_files(conn, out)
    again = eng.load_model(out)
    assert eng.derive_root_price(again, eng.rollup(again, ROOT, BATCH)).base_price == pytest.approx(
        pr.base_price, abs=1e-6
    )
    with conn.cursor() as cur:
        cur.execute("SELECT legal_country_of_origin, hs_code FROM bac.catalog WHERE item_id = 'dev_kit_v1'")
        assert cur.fetchone() == ("CH", "902300")


@LIVE
def test_reimport_asks_nothing_of_the_store_and_versions_params(conn):
    store.import_files(conn, FIXTURES)
    label, value = store.db_status(conn)[0]
    assert label == "params" and value.startswith("v2 · ") and " UTC · import from " in value
    model = store.load_model_pg(conn)
    out = store.save_pricing(conn, model, save_data=True, save_params=True, note="live test")
    assert out == {"data": True, "params_version": 3}
