# SPDX-License-Identifier: MIT
"""The shared schema and the engine registry.

``bac.items`` is the item register every engine keys on, ``bac.catalog`` the
sellable-SKU catalog (suite concept §4.3). Each engine owns its own schema
(``pricing``, later ``inventory``, ``qc``, ``fulfillment``) and registers
an :class:`Engine` under the ``bac_suite.engines`` entry-point group::

    [project.entry-points."bac_suite.engines"]
    pricing = "bac_pricing.store:ENGINE"

``bac-db migrate`` then creates every installed engine's tables after the
shared ones, and ``bac-db import``/``export`` route to the engine by name.
Every statement uses ``IF NOT EXISTS``, so migrate is safe to re-run.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

__all__ = [
    "SHARED_DDL",
    "SHARED_TABLES",
    "Engine",
    "discover_engines",
    "find_engine",
    "migrate",
    "table_names",
    "table_counts",
]

SHARED_TABLES = ("bac.items", "bac.catalog")

SHARED_DDL = """
CREATE SCHEMA IF NOT EXISTS bac;

-- Shared item register: one row per BOM node (assembly, subassembly, part, service).
-- Owned by the shared layer; pricing reads it, inventory edits it (concept 4.3).
CREATE TABLE IF NOT EXISTS bac.items (
    item_id     text PRIMARY KEY,
    sku         text UNIQUE,
    name        text NOT NULL,
    type        text NOT NULL
                CHECK (type IN ('assembly','subassembly','part','service')),
    category    text DEFAULT '',
    subcategory text DEFAULT '',
    vendor      text DEFAULT '',
    hs_code     text DEFAULT '',
    country_of_origin text DEFAULT '',
    unit        text DEFAULT '',
    sellable    boolean NOT NULL DEFAULT false,
    domain      text DEFAULT '' CHECK (domain IN ('ground','flight','both','')),
    notes       text DEFAULT '',
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Shared sellable-SKU catalog (concept 4.3). Storefront copy stays in the store;
-- this holds the stable engineering, shipping and customs attributes.
CREATE TABLE IF NOT EXISTS bac.catalog (
    sku                     text PRIMARY KEY,
    item_id                 text REFERENCES bac.items(item_id),
    name                    text NOT NULL,
    category                text DEFAULT '',
    shopify_handle          text,
    net_weight_g            integer,
    shipping_weight_g       integer,
    package_length_mm       integer,
    package_width_mm        integer,
    package_height_mm       integer,
    hs_code                 text,
    legal_country_of_origin char(2),
    customs_description     text,
    declared_value          numeric(12,2),
    declared_value_currency char(3),
    eccn                    text,
    origin_story            text,
    barcode                 text,
    image_ref               text,
    license                 text,
    updated_at              timestamptz NOT NULL DEFAULT now()
);
"""

PlanFn = Callable[[Path], dict[str, int]]
ImportFn = Callable[[Any, Path], dict[str, int]]
ExportFn = Callable[[Any, Path], list[str]]
StatusFn = Callable[[Any], list[tuple[str, str]]]


@dataclass(frozen=True)
class Engine:
    """What ``bac-db`` needs to know about one engine.

    ``plan(data_dir)`` validates every file an import would read and returns
    what it would load (counts by kind) without touching the database.
    ``import_files`` replaces the tables named in ``replaced`` from the files,
    appends to the others and upserts the shared ones; ``export_files``
    writes the files from the database and returns their names. ``tables``
    are all the engine's tables (counted by ``status``). ``status`` adds
    rows to ``bac-db status`` (latest params, say). Import and export commit
    their own transaction.
    """

    name: str
    ddl: str
    tables: tuple[str, ...]
    files: tuple[str, ...]
    plan: PlanFn
    import_files: ImportFn
    export_files: ExportFn
    status: StatusFn | None = None
    description: str = ""
    replaced: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.replaced:
            object.__setattr__(self, "replaced", self.tables)


def discover_engines() -> list[Engine]:
    """Every installed engine, by entry-point name."""
    found: list[Engine] = []
    for ep in sorted(entry_points(group="bac_suite.engines"), key=lambda e: e.name):
        obj = ep.load()
        if isinstance(obj, Engine):
            found.append(obj)
    return found


def find_engine(engines: Iterable[Engine], name: str) -> Engine | None:
    return next((e for e in engines if e.name == name), None)


_TABLE_RE = re.compile(r"CREATE TABLE IF NOT EXISTS\s+([\w.]+)", re.IGNORECASE)


def table_names(ddl: str) -> list[str]:
    """The tables a DDL script creates, in order."""
    return _TABLE_RE.findall(ddl)


def migrate(conn: Any, engines: Sequence[Engine]) -> list[str]:
    """Create the shared schema and every engine's tables; returns the table names touched."""
    scripts = [SHARED_DDL] + [e.ddl for e in engines]
    with conn.cursor() as cur:
        for script in scripts:
            cur.execute(script)
    conn.commit()
    return [t for script in scripts for t in table_names(script)]


def table_counts(conn: Any, tables: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 – table names come from the DDL, not the user
            out[table] = int(cur.fetchone()[0])
    return out
