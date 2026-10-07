# SPDX-License-Identifier: MIT
"""Storage for the pricing engine: its database tables and its files.

Postgres is the single source of truth per the suite concept; the CSV/TOML
files are an import source and an export target (git snapshots, hand-offs),
never a parallel live copy. The ``files`` backend works from the data
directory directly for a checkout without a database.

The engine stays pure: :func:`load_model_pg` rebuilds exactly the
:class:`~bac_pricing.engine.Model` that :func:`~bac_pricing.engine.load_model`
builds from files, so every downstream number is identical between backends
(the tests prove it on the fixture, with and without Postgres).

Tables (schema ``pricing``; the shared ``bac.items`` and ``bac.catalog`` are
bac-suite-db's):

* ``pricing.bom`` – BOM edges; labour minutes and consumables live on the edge
* ``pricing.price_breaks`` – vendor quantity-price breaks, in the vendor's currency
* ``pricing.overrides`` – manual per-item cost and rounding overrides
* ``pricing.params`` – versioned operational-parameter documents (JSONB)

Costs are stored without a currency suffix; their denomination is the
``base_currency`` of the params document in force. The ``_<ccy>`` column
suffix exists only at the file boundary: import validates it, export
re-applies it.
"""

from __future__ import annotations

import csv
import datetime as dt
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bac_common.errors import BacError, ConfigError
from bac_suite_db import config as suite_config
from bac_suite_db import db, items
from bac_suite_db.schema import Engine
from bac_suite_db.sku import SkuError, validate_sku

from . import engine as eng

__all__ = [
    "DDL",
    "TABLES",
    "DATA_FILES",
    "CATALOG_FILE",
    "ENGINE",
    "connect",
    "plan",
    "import_files",
    "load_model_pg",
    "save_pricing",
    "export_files",
    "db_status",
    "load_source",
    "save_files",
    "backup_files",
    "switch_base_currency",
    "primary_price_factor",
]

DDL = """
CREATE SCHEMA IF NOT EXISTS pricing;

CREATE TABLE IF NOT EXISTS pricing.bom (
    parent_id      text NOT NULL REFERENCES bac.items(item_id),
    child_id       text NOT NULL REFERENCES bac.items(item_id),
    qty_per_parent numeric NOT NULL CHECK (qty_per_parent >= 0),
    assy_min       numeric NOT NULL DEFAULT 0,
    qc_min         numeric NOT NULL DEFAULT 0,
    pack_min       numeric NOT NULL DEFAULT 0,
    ship_min       numeric NOT NULL DEFAULT 0,
    consumables    numeric NOT NULL DEFAULT 0,
    ref            text DEFAULT '',
    notes          text DEFAULT '',
    PRIMARY KEY (parent_id, child_id)
);

CREATE TABLE IF NOT EXISTS pricing.price_breaks (
    item_id    text NOT NULL REFERENCES bac.items(item_id),
    min_qty    numeric NOT NULL,
    unit_price numeric NOT NULL,
    notes      text DEFAULT '',
    PRIMARY KEY (item_id, min_qty)
);

CREATE TABLE IF NOT EXISTS pricing.overrides (
    item_id         text PRIMARY KEY REFERENCES bac.items(item_id),
    factor          numeric,
    additive        numeric,
    absolute        numeric,
    round_direction text,
    round_multiple  numeric,
    notes           text DEFAULT ''
);

-- Versioned operational parameters: the whole document (vendors, tiers, regions,
-- financials, fx, rounding, batch) as one JSONB snapshot per save. The latest row
-- is the parameters in force; history comes for free.
CREATE TABLE IF NOT EXISTS pricing.params (
    version    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    note       text DEFAULT '',
    payload    jsonb NOT NULL
);
"""

TABLES = ("pricing.bom", "pricing.price_breaks", "pricing.overrides", "pricing.params")
CATALOG_FILE = "bac-catalog.csv"
DATA_FILES = (
    "bac-items.csv",
    "bac-bom.csv",
    "bac-price-breaks.csv",
    "bac-price-overrides.csv",
    "bac-pricing-config.toml",
    CATALOG_FILE,
)
EDITABLE_FILES = ("bac-bom.csv", "bac-price-breaks.csv", "bac-price-overrides.csv")
CONFIG_FILE = "bac-pricing-config.toml"


def connect(dsn: str) -> Any:
    return db.connect(dsn)


# ---------------------------------------------------------------------------
# Files → database
# ---------------------------------------------------------------------------


def _checked_model(data_dir: Path) -> eng.Model:
    missing = [f for f in DATA_FILES[:5] if not (data_dir / f).exists()]
    if missing:
        raise BacError(f"Data files missing in {data_dir}: {', '.join(missing)}", "See examples/ for the expected set.")
    model = eng.load_model(data_dir)
    problems = eng.validate_model(model)
    if problems:
        shown = "\n      ".join(problems[:8])
        more = f"\n      … and {len(problems) - 8} more" if len(problems) > 8 else ""
        raise BacError(f"The data files have {len(problems)} problem(s).", shown + more)
    return model


def _counts(model: eng.Model, catalog_rows: int) -> dict[str, int]:
    return {
        "items": len(model.items),
        "catalog rows": catalog_rows,
        "bom edges": len(model.edges),
        "price breaks": sum(len(v) for v in model.breaks.values()),
        "overrides": len(model.overrides),
        "params versions": 1,
    }


def _catalog_rows(data_dir: Path, model: eng.Model) -> list[dict[str, str]]:
    """Catalog rows from ``bac-catalog.csv`` when present, else one bare row per sellable item with a SKU.

    Validated here, before any connection: every SKU follows the scheme and
    every ``item_id`` (given, or found through the SKU) is an item.
    """
    path = data_dir / CATALOG_FILE
    if not path.exists():
        return [
            {"sku": it["sku"], "item_id": iid, "name": it["name"], "category": ""}
            for iid, it in model.items.items()
            if eng.is_sellable(it) and (it.get("sku") or "").strip()
        ]
    with path.open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("sku") or "").strip()]
    problems: list[str] = []
    by_sku = {it.get("sku"): iid for iid, it in model.items.items() if it.get("sku")}
    for r in rows:
        r["sku"] = r["sku"].strip()
        try:
            validate_sku(r["sku"])
        except SkuError as exc:
            problems.append(f"{CATALOG_FILE}: {exc.message}")
            continue
        if not (r.get("item_id") or "").strip():
            r["item_id"] = by_sku.get(r["sku"], "")
        if r["item_id"] and r["item_id"] not in model.items:
            problems.append(f"{CATALOG_FILE}: {r['sku']} names item_id '{r['item_id']}', which is not in bac-items.csv")
        if not (r.get("name") or "").strip() and r["item_id"] in model.items:
            r["name"] = model.items[r["item_id"]]["name"]
    if problems:
        raise BacError(f"{CATALOG_FILE} has {len(problems)} problem(s).", "\n      ".join(problems[:8]))
    return rows


def plan(data_dir: Path) -> dict[str, int]:
    """Validate the files and report what an import would load. Touches nothing."""
    data_dir = Path(data_dir)
    model = _checked_model(data_dir)
    return _counts(model, len(_catalog_rows(data_dir, model)))


def import_files(conn: Any, data_dir: Path) -> dict[str, int]:
    """Files → database in one transaction: items and catalog upserted, pricing tables replaced, a params version."""
    data_dir = Path(data_dir)
    model = _checked_model(data_dir)
    catalog = _catalog_rows(data_dir, model)
    with conn.cursor() as cur:
        items.upsert_items(cur, model.items.values())
        items.upsert_catalog(cur, catalog)
        _replace_pricing_data(cur, model)
        _insert_params(cur, model.cfg, f"import from {data_dir.resolve()}")
    conn.commit()
    return _counts(model, len(catalog))


def _jsonb(payload: Mapping[str, Any]) -> Any:
    from psycopg.types.json import Jsonb  # adapts a dict for a jsonb column; the fake connection unwraps it

    return Jsonb(dict(payload))


def _insert_params(cur: Any, cfg: Mapping[str, Any], note: str) -> int:
    cur.execute("INSERT INTO pricing.params (note, payload) VALUES (%s, %s) RETURNING version", (note, _jsonb(cfg)))
    return int(cur.fetchone()[0])


def _replace_pricing_data(cur: Any, model: eng.Model) -> None:
    cur.execute("DELETE FROM pricing.bom")
    for e in model.edges:
        cur.execute(
            """INSERT INTO pricing.bom (parent_id, child_id, qty_per_parent, assy_min, qc_min,
                   pack_min, ship_min, consumables, ref, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (parent_id, child_id) DO UPDATE SET
                   qty_per_parent=EXCLUDED.qty_per_parent, assy_min=EXCLUDED.assy_min,
                   qc_min=EXCLUDED.qc_min, pack_min=EXCLUDED.pack_min, ship_min=EXCLUDED.ship_min,
                   consumables=EXCLUDED.consumables, ref=EXCLUDED.ref, notes=EXCLUDED.notes""",
            (
                e["parent_id"],
                e["child_id"],
                float(e["qty_per_parent"]),
                float(e["assy_min"]),
                float(e["qc_min"]),
                float(e["pack_min"]),
                float(e["ship_min"]),
                float(e["consumables"]),
                e.get("ref", "") or "",
                e.get("notes", "") or "",
            ),
        )
    cur.execute("DELETE FROM pricing.price_breaks")
    for iid, table in model.breaks.items():
        for q, p in table:
            cur.execute(
                "INSERT INTO pricing.price_breaks (item_id, min_qty, unit_price, notes) VALUES (%s,%s,%s,%s)"
                " ON CONFLICT (item_id, min_qty) DO UPDATE SET unit_price=EXCLUDED.unit_price, notes=EXCLUDED.notes",
                (iid, q, p, model.break_notes.get((iid, q), "")),
            )
    cur.execute("DELETE FROM pricing.overrides")
    for iid, o in model.overrides.items():
        cur.execute(
            """INSERT INTO pricing.overrides (item_id, factor, additive, absolute, round_direction,
                   round_multiple, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (
                iid,
                _num(o, "factor"),
                _num(o, "additive"),
                _num(o, "absolute"),
                o.get("round_direction") or None,
                _num(o, "round_multiple"),
                o.get("notes", "") or "",
            ),
        )


def _num(row: Mapping[str, Any], key: str) -> float | None:
    v = row.get(key, "")
    return float(v) if v not in ("", None) else None


# ---------------------------------------------------------------------------
# Database → model, notebook saves
# ---------------------------------------------------------------------------


def load_model_pg(conn: Any) -> eng.Model:
    """The engine Model from the database, shaped exactly like the file-loaded one."""

    def _s(v: Any) -> str:
        return "" if v is None else str(v)

    with conn.cursor() as cur:
        item_rows = items.load_items(cur)
        cur.execute(
            """SELECT parent_id, child_id, qty_per_parent, assy_min, qc_min, pack_min, ship_min,
                      consumables, ref, notes FROM pricing.bom ORDER BY parent_id, child_id"""
        )
        ecols = [d.name for d in cur.description]
        edges = []
        for row in cur.fetchall():
            e = dict(zip(ecols, row, strict=True))
            for k in ("qty_per_parent", "assy_min", "qc_min", "pack_min", "ship_min", "consumables"):
                e[k] = float(e[k])
            e["ref"], e["notes"] = _s(e["ref"]), _s(e["notes"])
            edges.append(e)
        cur.execute("SELECT item_id, min_qty, unit_price, notes FROM pricing.price_breaks ORDER BY item_id, min_qty")
        breaks: dict[str, list] = {}
        break_notes: dict[tuple[str, float], str] = {}
        for iid, q, p, note in cur.fetchall():
            breaks.setdefault(iid, []).append((float(q), float(p)))
            if note:
                break_notes[(iid, float(q))] = str(note)
        for k in breaks:
            breaks[k].sort()
        cur.execute(
            "SELECT item_id, factor, additive, absolute, round_direction, round_multiple, notes FROM pricing.overrides"
            " ORDER BY item_id"
        )
        overrides = {}
        for iid, fac, add, absv, rdir, rmul, notes in cur.fetchall():
            overrides[iid] = {
                "item_id": iid,
                "factor": _s(fac),
                "additive": _s(add),
                "absolute": _s(absv),
                "round_direction": _s(rdir),
                "round_multiple": _s(rmul),
                "notes": _s(notes),
            }
        cur.execute("SELECT payload FROM pricing.params ORDER BY version DESC LIMIT 1")
        row = cur.fetchone()
        if row is None:
            raise BacError("pricing.params is empty.", "Run `bac-db import pricing <data-dir>` first.")
        cfg = row[0]
    return eng.Model(item_rows, edges, breaks, overrides, cfg, break_notes)


def save_pricing(conn: Any, model: eng.Model, *, save_data: bool, save_params: bool, note: str = "") -> dict:
    """Notebook state → database in one transaction: data replaces the pricing tables, params appends a version."""
    out: dict[str, Any] = {"data": False, "params_version": None}
    with conn.cursor() as cur:
        if save_data:
            _replace_pricing_data(cur, model)
            out["data"] = True
        if save_params:
            out["params_version"] = _insert_params(cur, model.cfg, note or "saved from notebook")
    conn.commit()
    return out


def db_status(conn: Any) -> list[tuple[str, str]]:
    """The latest params version, for ``bac-db status`` and the notebook's storage panel."""
    with conn.cursor() as cur:
        cur.execute("SELECT version, created_at, note FROM pricing.params ORDER BY version DESC LIMIT 1")
        row = cur.fetchone()
    if row is None:
        return [("pricing.params", "none – run `bac-db import pricing <data-dir>`")]
    created = row[1]
    if isinstance(created, dt.datetime):
        stamp = created.astimezone(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    else:
        stamp = str(created)
    return [("params", f"v{row[0]} · {stamp} · {row[2]}")]


# ---------------------------------------------------------------------------
# Database → files
# ---------------------------------------------------------------------------


def export_files(conn: Any, out_dir: Path) -> list[str]:
    """Database → the canonical file layout; ``load_model`` on the export rebuilds the same Model."""
    model = load_model_pg(conn)
    with conn.cursor() as cur:
        catalog = items.load_catalog(cur)
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with (d / "bac-items.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(items.ITEM_COLUMNS))
        w.writeheader()
        for iid in sorted(model.items):
            w.writerow({k: model.items[iid].get(k, "") for k in items.ITEM_COLUMNS})
    written.append("bac-items.csv")
    written += _write_editable(model, d)
    (d / CONFIG_FILE).write_text(eng.dump_config(model.cfg), encoding="utf-8")
    written.append(CONFIG_FILE)
    with (d / CATALOG_FILE).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(items.CATALOG_COLUMNS))
        w.writeheader()
        for row in catalog:
            w.writerow(row)
    written.append(CATALOG_FILE)
    return written


def _write_editable(model: eng.Model, d: Path) -> list[str]:
    """The three editable CSVs (bom, overrides, price breaks) with the base-currency suffixes re-applied."""
    base = str(model.cfg["financials"]["base_currency"]).lower()
    cons_h, add_h, abs_h = f"consumables_{base}", f"additive_{base}", f"absolute_{base}"
    with (d / "bac-bom.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "parent_id",
                "child_id",
                "qty_per_parent",
                "assy_min",
                "qc_min",
                "pack_min",
                "ship_min",
                "ref",
                "notes",
                cons_h,
            ],
        )
        w.writeheader()
        for e in model.edges:
            w.writerow(
                {
                    **{
                        k: e.get(k, "")
                        for k in (
                            "parent_id",
                            "child_id",
                            "qty_per_parent",
                            "assy_min",
                            "qc_min",
                            "pack_min",
                            "ship_min",
                        )
                    },
                    cons_h: e.get("consumables", ""),
                    "ref": e.get("ref", "") or "",
                    "notes": e.get("notes", "") or "",
                }
            )
    with (d / "bac-price-breaks.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["item_id", "min_qty", "unit_price", "notes"])
        w.writeheader()
        for iid in sorted(model.breaks):
            for q, p in sorted(model.breaks[iid]):
                w.writerow(
                    {"item_id": iid, "min_qty": q, "unit_price": p, "notes": model.break_notes.get((iid, q), "")}
                )
    with (d / "bac-price-overrides.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["item_id", "factor", add_h, abs_h, "round_direction", "round_multiple", "notes"]
        )
        w.writeheader()
        for iid, o in model.overrides.items():
            w.writerow(
                {
                    "item_id": o.get("item_id", iid),
                    "factor": o.get("factor", ""),
                    add_h: o.get("additive", ""),
                    abs_h: o.get("absolute", ""),
                    "round_direction": o.get("round_direction", ""),
                    "round_multiple": o.get("round_multiple", ""),
                    "notes": o.get("notes", ""),
                }
            )
    return list(EDITABLE_FILES)


# ---------------------------------------------------------------------------
# Files backend (and the notebook's save paths in both modes)
# ---------------------------------------------------------------------------


def load_source(settings: suite_config.Settings) -> eng.Model:
    """The Model from whichever backend the settings name."""
    if settings.uses_db:
        with connect(suite_config.require_dsn(settings)) as conn:
            return load_model_pg(conn)
    if not (settings.data_dir / "bac-items.csv").exists():
        raise ConfigError(
            f"No pricing data in {settings.data_dir}.",
            "Copy ops/bac-pricing/examples/ there, or point storage.data_dir at your data.",
        )
    return eng.load_model(settings.data_dir)


def backup_files(data_dir: Path, names: tuple[str, ...] = DATA_FILES, when: dt.datetime | None = None) -> Path:
    """Copy the data files to ``<data_dir>/backups/<timestamp>/`` and return that folder."""
    stamp = (when or dt.datetime.now()).strftime("%Y-%m-%dT%H-%M-%S")
    target = Path(data_dir) / "backups" / stamp
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        src = Path(data_dir) / name
        if src.exists():
            shutil.copy2(src, target / name)
    return target


def save_files(model: eng.Model, data_dir: Path, *, data: bool, config: bool) -> list[str]:
    """Write the notebook's editable files and/or the config TOML into the data directory."""
    d = Path(data_dir)
    written: list[str] = []
    if data:
        written += _write_editable(model, d)
    if config:
        (d / CONFIG_FILE).write_text(eng.dump_config(model.cfg), encoding="utf-8")
        written.append(CONFIG_FILE)
    return written


def switch_base_currency(settings: suite_config.Settings, new: str, *, add_columns: bool = True) -> dict[str, Any]:
    """Change ``base_currency`` on whichever backend is in use.

    Costs are re-labelled, not converted. Files mode renames nothing but adds
    the ``_<new>`` cost columns (copies of the old ones) when ``add_columns``
    is set, then rewrites the config; database mode writes a params version.
    Returns ``old``, ``new``, ``added`` (columns) and ``missing`` (columns that
    would have been needed), or ``version`` in database mode.
    """
    new = new.strip().upper()
    if settings.uses_db:
        with connect(suite_config.require_dsn(settings)) as conn:
            cfg = load_model_pg(conn).cfg
            old = str(cfg["financials"]["base_currency"])
            if old == new:
                return {"old": old, "new": new, "unchanged": True}
            cfg["financials"]["base_currency"] = new
            with conn.cursor() as cur:
                version = _insert_params(cur, cfg, f"base currency {old} → {new}")
            conn.commit()
        return {"old": old, "new": new, "version": version}

    import tomllib

    d = settings.data_dir
    cfg = tomllib.loads((d / CONFIG_FILE).read_text(encoding="utf-8"))
    old = str(cfg["financials"]["base_currency"])
    if old == new:
        return {"old": old, "new": new, "unchanged": True}
    ol, nl = old.lower(), new.lower()
    added: list[str] = []
    missing: list[str] = []
    writes: dict[str, tuple[list[str], list[dict[str, str]]]] = {}
    for fname, stems in (("bac-bom.csv", ["consumables"]), ("bac-price-overrides.csv", ["additive", "absolute"])):
        with (d / fname).open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            header = list(reader.fieldnames or [])
            rows = list(reader)
        dirty = False
        for stem in stems:
            newc, oldc = f"{stem}_{nl}", f"{stem}_{ol}"
            if newc in header:
                continue
            if add_columns and oldc in header:
                header.append(newc)
                for r in rows:
                    r[newc] = r.get(oldc, "")
                added.append(f"{fname} → {newc}")
                dirty = True
            else:
                missing.append(f"{fname} → {newc}")
        if dirty:
            writes[fname] = (header, rows)
    if missing:
        return {"old": old, "new": new, "added": added, "missing": missing}
    for fname, (header, rows) in writes.items():
        with (d / fname).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
    cfg["financials"]["base_currency"] = new
    (d / CONFIG_FILE).write_text(eng.dump_config(cfg), encoding="utf-8")
    return {"old": old, "new": new, "added": added, "missing": []}


# ---------------------------------------------------------------------------
# Shared chart helper
# ---------------------------------------------------------------------------


def primary_price_factor(cfg: Mapping[str, Any], primary: str | None, domestic: str | None) -> tuple[float, str]:
    """``(factor, currency)`` such that a base-currency price × factor is the primary market's price.

    The domestic market anchors the base price; every market is base ×
    (its multiplier / the domestic multiplier) converted to its currency.
    Both chart cells of the notebook use this instead of carrying the
    arithmetic twice.
    """
    regions = {r["label"]: r for r in cfg.get("regions", [])}
    base_ccy = str(cfg["financials"]["base_currency"])
    p, d = regions.get(primary or ""), regions.get(domestic or "")
    pmult = float(p["multiplier"]) if p else 1.0
    dmult = (float(d["multiplier"]) if d else 1.0) or 1.0
    pccy = str(p.get("currency") or base_ccy) if p else base_ccy
    rate = float(cfg["fx"].get(pccy, 1.0) or 1.0)
    return (pmult / dmult) / rate, pccy


ENGINE = Engine(
    name="pricing",
    ddl=DDL,
    tables=TABLES,
    files=DATA_FILES,
    plan=plan,
    import_files=import_files,
    export_files=export_files,
    status=db_status,
    description="BOM cost rollup and price derivation",
    replaced=("pricing.bom", "pricing.price_breaks", "pricing.overrides"),
)
