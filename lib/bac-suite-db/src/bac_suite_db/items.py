# SPDX-License-Identifier: MIT
"""Reading and writing the shared tables.

Items are upserted, never deleted, by an engine's import: an item row may
be referenced by tables the importing engine knows nothing about, and the
importing engine's file is the register's source, so every column of a row
it names is replaced. The catalog is different: it is edited from several
places, so a column the import leaves empty keeps its stored value. Every
non-empty SKU is validated against the scheme on the way in.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .sku import validate_sku

__all__ = [
    "ITEM_COLUMNS",
    "CATALOG_COLUMNS",
    "upsert_items",
    "load_items",
    "upsert_catalog",
    "load_catalog",
    "sellable",
]

ITEM_COLUMNS = (
    "item_id",
    "sku",
    "name",
    "type",
    "category",
    "subcategory",
    "vendor",
    "hs_code",
    "country_of_origin",
    "unit",
    "sellable",
    "domain",
    "notes",
)

CATALOG_COLUMNS = (
    "sku",
    "item_id",
    "name",
    "category",
    "shopify_handle",
    "net_weight_g",
    "shipping_weight_g",
    "package_length_mm",
    "package_width_mm",
    "package_height_mm",
    "hs_code",
    "legal_country_of_origin",
    "customs_description",
    "declared_value",
    "declared_value_currency",
    "eccn",
    "origin_story",
    "barcode",
    "image_ref",
    "license",
)

_INT_COLUMNS = {"net_weight_g", "shipping_weight_g", "package_length_mm", "package_width_mm", "package_height_mm"}
_NUM_COLUMNS = {"declared_value"}


def sellable(row: Mapping[str, Any]) -> bool:
    value = row.get("sellable")
    return value is True or str(value).strip().lower() == "true"


def upsert_items(cur: Any, items: Iterable[Mapping[str, Any]]) -> int:
    """Insert or update item rows given as string-valued mappings (the CSV shape)."""
    count = 0
    for it in items:
        sku = (it.get("sku") or "").strip() or None
        if sku:
            validate_sku(sku)
        cur.execute(
            """INSERT INTO bac.items (item_id, sku, name, type, category, subcategory, vendor,
                   hs_code, country_of_origin, unit, sellable, domain, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (item_id) DO UPDATE SET
                   sku=EXCLUDED.sku, name=EXCLUDED.name, type=EXCLUDED.type,
                   category=EXCLUDED.category, subcategory=EXCLUDED.subcategory,
                   vendor=EXCLUDED.vendor, hs_code=EXCLUDED.hs_code,
                   country_of_origin=EXCLUDED.country_of_origin, unit=EXCLUDED.unit,
                   sellable=EXCLUDED.sellable, domain=EXCLUDED.domain, notes=EXCLUDED.notes,
                   updated_at=now()""",
            (
                it["item_id"],
                sku,
                it["name"],
                it["type"],
                it.get("category", "") or "",
                it.get("subcategory", "") or "",
                it.get("vendor", "") or "",
                it.get("hs_code", "") or "",
                it.get("country_of_origin", "") or "",
                it.get("unit", "") or "",
                sellable(it),
                it.get("domain", "") or "",
                it.get("notes", "") or "",
            ),
        )
        count += 1
    return count


def load_items(cur: Any) -> dict[str, dict[str, str]]:
    """Items as string-valued rows keyed by item_id – the shape the CSV loader produces."""
    cur.execute(f"SELECT {', '.join(ITEM_COLUMNS)} FROM bac.items")
    out: dict[str, dict[str, str]] = {}
    for row in cur.fetchall():
        rec = {col: ("" if value is None else str(value)) for col, value in zip(ITEM_COLUMNS, row, strict=True)}
        rec["sellable"] = "true" if row[ITEM_COLUMNS.index("sellable")] else "false"
        out[rec["item_id"]] = rec
    return out


def _typed(column: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        if column in _INT_COLUMNS:
            return int(float(text))
        if column in _NUM_COLUMNS:
            return float(text)
        return text
    return value


def upsert_catalog(cur: Any, rows: Iterable[Mapping[str, Any]]) -> int:
    """Insert or update catalog rows. An empty value never overwrites a stored one."""
    count = 0
    columns = CATALOG_COLUMNS
    updates = ", ".join(f"{c}=COALESCE(EXCLUDED.{c}, bac.catalog.{c})" for c in columns if c != "sku")
    name_at = columns.index("name")
    for row in rows:
        sku = validate_sku(str(row["sku"]))
        values = [sku] + [_typed(c, row.get(c)) for c in columns[1:]]
        if values[name_at] is None:
            # NOT NULL on insert; on conflict COALESCE would keep the stored name, so look it up first
            cur.execute("SELECT name FROM bac.catalog WHERE sku = %s", (sku,))
            found = cur.fetchone()
            values[name_at] = found[0] if found else sku
        cur.execute(
            f"INSERT INTO bac.catalog ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"
            f" ON CONFLICT (sku) DO UPDATE SET {updates}, updated_at=now()",
            tuple(values),
        )
        count += 1
    return count


def load_catalog(cur: Any) -> list[dict[str, str]]:
    cur.execute(f"SELECT {', '.join(CATALOG_COLUMNS)} FROM bac.catalog ORDER BY sku")
    out = []
    for row in cur.fetchall():
        out.append(
            {col: ("" if value is None else str(value)) for col, value in zip(CATALOG_COLUMNS, row, strict=True)}
        )
    return out
