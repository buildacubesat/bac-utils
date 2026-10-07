# SPDX-License-Identifier: MIT
"""An in-memory stand-in for a psycopg connection, for tests without Postgres.

:class:`FakeConn` understands exactly the statements the suite issues –
``CREATE SCHEMA``/``CREATE TABLE``, ``INSERT … ON CONFLICT … DO UPDATE``
with ``COALESCE(EXCLUDED.x, table.x)`` and ``NULLIF(EXCLUDED.x, '')``,
``RETURNING`` an identity column, ``DELETE FROM``, ``SELECT count(*)`` and
plain ``SELECT cols FROM table [WHERE col = %s] [ORDER BY cols [DESC]]
[LIMIT n]`` – and nothing else. It is a test harness, not a database: the
live tests (``BAC_TEST_DSN``) are what prove the SQL against Postgres.
"""

from __future__ import annotations

import copy
import datetime as dt
import re
from typing import Any

__all__ = ["FakeConn", "FakeCursor"]

_WS = re.compile(r"\s+")
_INSERT = re.compile(
    r"^INSERT INTO (?P<table>[\w.]+) \((?P<cols>[^)]*)\) VALUES \((?P<vals>[^)]*)\)"
    r"(?: ON CONFLICT \((?P<keys>[^)]*)\) DO UPDATE SET (?P<set>.*?))?(?: RETURNING (?P<ret>\w+))?$",
    re.IGNORECASE,
)
_DELETE = re.compile(r"^DELETE FROM (?P<table>[\w.]+)(?: WHERE (?P<col>\w+) = %s)?$", re.IGNORECASE)
_COUNT = re.compile(r"^SELECT count\(\*\) FROM (?P<table>[\w.]+)$", re.IGNORECASE)
_SELECT = re.compile(
    r"^SELECT (?P<cols>.+?) FROM (?P<table>[\w.]+)(?: WHERE (?P<wcol>\w+) = %s)?"
    r"(?: ORDER BY (?P<ocol>\w+(?:, \w+)*)(?P<desc> DESC)?)?(?: LIMIT (?P<limit>\d+))?$",
    re.IGNORECASE,
)
_CREATE_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS ([\w.]+)", re.IGNORECASE)
_IDENTITY = re.compile(r"(\w+)\s+integer GENERATED ALWAYS AS IDENTITY", re.IGNORECASE)
_SET_ITEM = re.compile(r"(\w+)=(COALESCE\(NULLIF\(EXCLUDED\.\1,''\),|COALESCE\(EXCLUDED\.\1,|EXCLUDED\.\1|now\(\))")


class _Column:
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


class FakeConn:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.identity: dict[str, str] = {}
        self.ddl: list[str] = []
        self.commits = 0
        self.closed = False
        self._committed: dict[str, list[dict[str, Any]]] = {}

    # psycopg connection API -------------------------------------------------
    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def execute(self, sql: str, params: tuple | None = None) -> FakeCursor:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self) -> None:
        self.commits += 1
        self._committed = copy.deepcopy(self.tables)

    def rollback(self) -> None:
        """Back to the last commit – so a test can see that a failed import leaves nothing behind."""
        self.tables = copy.deepcopy(self._committed)
        for table in self.identity:
            self.tables.setdefault(table, [])

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> FakeConn:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()

    # helpers ----------------------------------------------------------------
    def rows(self, table: str) -> list[dict[str, Any]]:
        return self.tables.setdefault(table, [])


class FakeCursor:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn
        self._result: list[tuple] = []
        self.description: list[_Column] | None = None
        self.rowcount = -1

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc) -> None:
        pass

    def execute(self, sql: str, params: tuple | list | None = None) -> None:
        params = tuple(params or ())
        text = _WS.sub(" ", sql).strip().rstrip(";")
        self._result, self.description = [], None
        if _CREATE_TABLE.search(text) or text.upper().startswith("CREATE SCHEMA"):
            self._ddl(sql)
            return
        if text.upper() == "SELECT 1":
            self._result, self.description = [(1,)], [_Column("?column?")]
            return
        if m := _INSERT.match(text):
            self._insert(m, params)
            return
        if m := _DELETE.match(text):
            rows = self.conn.rows(m["table"])
            if m["col"]:
                rows[:] = [r for r in rows if r.get(m["col"]) != params[0]]
            else:
                rows.clear()
            return
        if m := _COUNT.match(text):
            self._result, self.description = [(len(self.conn.rows(m["table"])),)], [_Column("count")]
            return
        if m := _SELECT.match(text):
            self._select(m, params)
            return
        raise NotImplementedError(f"FakeConn does not understand: {text[:80]}")

    def fetchone(self) -> tuple | None:
        return self._result[0] if self._result else None

    def fetchall(self) -> list[tuple]:
        return list(self._result)

    # statements -------------------------------------------------------------
    def _ddl(self, script: str) -> None:
        self.conn.ddl.append(script)
        for table in _CREATE_TABLE.findall(script):
            self.conn.rows(table)
            self.conn._committed.setdefault(table, [])  # DDL survives a rollback here; it is the baseline
        for block in re.split(r"CREATE TABLE IF NOT EXISTS", script, flags=re.IGNORECASE)[1:]:
            name = block.split("(", 1)[0].strip()
            if ident := _IDENTITY.search(block):
                self.conn.identity[name] = ident.group(1)

    def _insert(self, m: re.Match, params: tuple) -> None:
        table = m["table"]
        cols = [c.strip() for c in m["cols"].split(",")]
        if len(cols) != len(params):
            raise ValueError(f"{table}: {len(cols)} columns but {len(params)} parameters")
        row = {c: copy.deepcopy(_plain(v)) for c, v in zip(cols, params, strict=True)}
        rows = self.conn.rows(table)
        now = dt.datetime.now(dt.UTC)
        if ident := self.conn.identity.get(table):
            row[ident] = max((r.get(ident, 0) for r in rows), default=0) + 1
            row.setdefault("created_at", now)
        row.setdefault("updated_at", now)
        existing = None
        if m["keys"]:
            keys = [k.strip() for k in m["keys"].split(",")]
            existing = next((r for r in rows if all(r.get(k) == row.get(k) for k in keys)), None)
        if existing is not None:
            for col, how in _SET_ITEM.findall(m["set"] or ""):
                if how == "now()":
                    existing[col] = now
                elif how.startswith("COALESCE(NULLIF"):
                    if row.get(col) not in (None, ""):
                        existing[col] = row[col]
                elif how.startswith("COALESCE("):
                    if row.get(col) is not None:
                        existing[col] = row[col]
                else:
                    existing[col] = row.get(col)
            target = existing
        else:
            rows.append(row)
            target = row
        if m["ret"]:
            self._result, self.description = [(target[m["ret"]],)], [_Column(m["ret"])]

    def _select(self, m: re.Match, params: tuple) -> None:
        rows = list(self.conn.rows(m["table"]))
        if m["wcol"]:
            rows = [r for r in rows if r.get(m["wcol"]) == params[0]]
        if m["ocol"]:
            keys = [c.strip() for c in m["ocol"].split(",")]
            rows.sort(key=lambda r: tuple(r.get(c) for c in keys), reverse=bool(m["desc"]))
        if m["limit"]:
            rows = rows[: int(m["limit"])]
        cols = [c.strip() for c in m["cols"].split(",")]
        self.description = [_Column(c) for c in cols]
        # values are copied, as a database would serialise them: a caller cannot mutate stored rows
        self._result = [tuple(copy.deepcopy(r.get(c)) for c in cols) for r in rows]


def _plain(value: Any) -> Any:
    """psycopg adapters (``Jsonb``) carry the Python object as ``.obj``."""
    return value.obj if hasattr(value, "obj") and not isinstance(value, (str, bytes)) else value
