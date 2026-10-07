# SPDX-License-Identifier: MIT
"""The in-memory connection must behave like the subset of Postgres the suite relies on."""

from __future__ import annotations

import pytest

from bac_suite_db.testing import FakeConn

DDL = """
CREATE SCHEMA IF NOT EXISTS t;
CREATE TABLE IF NOT EXISTS t.params (
    version    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    note       text DEFAULT '',
    payload    jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS t.things (
    id   text PRIMARY KEY,
    a    text,
    b    text
);
"""


def test_identity_returning_and_order_limit():
    conn = FakeConn()
    conn.execute(DDL)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO t.params (note, payload) VALUES (%s, %s) RETURNING version", ("one", {"x": 1}))
        assert cur.fetchone() == (1,)
        cur.execute("INSERT INTO t.params (note, payload) VALUES (%s, %s) RETURNING version", ("two", {"x": 2}))
        assert cur.fetchone() == (2,)
        cur.execute("SELECT payload FROM t.params ORDER BY version DESC LIMIT 1")
        assert cur.fetchone() == ({"x": 2},)
        cur.execute("SELECT version, created_at, note FROM t.params ORDER BY version DESC LIMIT 1")
        version, created, note = cur.fetchone()
        assert version == 2 and note == "two" and created.tzinfo is not None
        cur.execute("SELECT count(*) FROM t.params")
        assert cur.fetchone() == (2,)


def test_upsert_semantics():
    conn = FakeConn()
    conn.execute(DDL)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO t.things (id, a, b) VALUES (%s,%s,%s)", ("k", "a1", "b1"))
        cur.execute(
            "INSERT INTO t.things (id, a, b) VALUES (%s,%s,%s) ON CONFLICT (id) DO UPDATE SET"
            " a=EXCLUDED.a, b=COALESCE(EXCLUDED.b, t.things.b)",
            ("k", "a2", None),
        )
        cur.execute("SELECT id, a, b FROM t.things")
        assert cur.fetchall() == [("k", "a2", "b1")]
        cur.execute(
            "INSERT INTO t.things (id, a, b) VALUES (%s,%s,%s) ON CONFLICT (id) DO UPDATE SET"
            " a=COALESCE(NULLIF(EXCLUDED.a,''), t.things.a), b=EXCLUDED.b",
            ("k", "", "b3"),
        )
        cur.execute("SELECT a, b FROM t.things WHERE id = %s", ("k",))
        assert cur.fetchall() == [("a2", "b3")]
        cur.execute("DELETE FROM t.things")
        cur.execute("SELECT count(*) FROM t.things")
        assert cur.fetchone() == (0,)


def test_unknown_statements_are_refused_loudly():
    conn = FakeConn()
    with pytest.raises(NotImplementedError):
        conn.execute("UPDATE t.things SET a = 1")
    with pytest.raises(ValueError):
        conn.execute("INSERT INTO t.things (id, a) VALUES (%s,%s,%s)", ("k",))


def test_context_manager_commits_and_closes():
    with FakeConn() as conn:
        pass
    assert conn.commits == 1 and conn.closed


def test_rollback_restores_the_last_commit():
    conn = FakeConn()
    conn.execute(DDL)
    conn.execute("INSERT INTO t.things (id, a, b) VALUES (%s,%s,%s)", ("k", "a", "b"))
    conn.commit()
    conn.execute("INSERT INTO t.things (id, a, b) VALUES (%s,%s,%s)", ("k2", "a", "b"))
    conn.rollback()
    assert [r["id"] for r in conn.tables["t.things"]] == ["k"]
    try:
        with conn:
            conn.execute("DELETE FROM t.things")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert [r["id"] for r in conn.tables["t.things"]] == ["k"] and conn.closed


def test_multi_column_order_by():
    conn = FakeConn()
    conn.execute(DDL)
    for row in (("b", "2", "x"), ("a", "2", "y"), ("a", "1", "z")):
        conn.execute("INSERT INTO t.things (id, a, b) VALUES (%s,%s,%s)", row)
    cur = conn.execute("SELECT id, a, b FROM t.things ORDER BY id, a")
    assert cur.fetchall() == [("a", "1", "z"), ("a", "2", "y"), ("b", "2", "x")]
