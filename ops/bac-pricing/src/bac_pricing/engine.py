# SPDX-License-Identifier: MIT
"""Build a CubeSat – pricing engine.

Pure computation layer for the BAC multi-level BOM pricing model. Loads the
CSV/TOML data files, rolls up landed cost through the assembly tree, applies
manual cost overrides, derives prices via the discount-tier waterfall, and
rounds final prices. The marimo notebook (notebook.py) is a thin UI on top of
this module; everything here is testable headless.

Cost chain (mirrors the validated spreadsheet model, with the price-break
fallback bug corrected):

    base        = unit_price × fx × qty                      (per leaf, summed)
    + shipping  = base × (ship_factor – 1)
    + bank      = base × ship × (bank_factor – 1)
    + duties    = base × ship × bank × (duties_factor – 1)
    = landed materials
    + consumables (per edge, per parent instance, per unit of root)
    + production labour (minutes → person-days → base currency via salary)
    = direct cost
    × expense_safety × overhead_safety
    = total recoverable cost

Price derivation for the root assembly (batch waterfall):

    target_revenue   = total_cost / (1 – margin)             (true margin)
    at-cost tiers    contribute units × basis_cost_per_unit
    percentage tiers contribute units × (1 – value) × P      (weighted units)
    full-price units contribute units × P
    P = (target_revenue – at_cost_contribution) / weighted_units

Other sellable items are priced cost / (1 – margin) without a waterfall.
"""

from __future__ import annotations

import csv
import json
import math
import tomllib
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__

LEAF_TYPES = ("part", "service")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Model:
    items: dict[str, dict]  # item_id -> row
    edges: list[dict]  # parent_id/child_id/qty/labour/consumables
    breaks: dict[str, list[tuple]]  # item_id -> sorted [(min_qty, unit_price)]
    overrides: dict[str, dict]  # item_id -> override row
    cfg: dict  # parsed TOML
    break_notes: dict[tuple[str, float], str] = field(default_factory=dict)  # (item_id, min_qty) -> note
    vendors: dict[str, dict] = field(init=False)
    children: dict[str, list[dict]] = field(init=False)

    def __post_init__(self):
        self.vendors = {v["key"]: v for v in self.cfg["vendors"]}
        self.children = {}
        for e in self.edges:
            self.children.setdefault(e["parent_id"], []).append(e)


def _require_ccy_col(rows, base: str, stem: str, filename: str) -> None:
    """Cost columns in the hand-edited CSVs must carry the base-currency suffix
    (e.g. consumables_chf when base_currency = CHF). Validate the header exists
    and normalise it to a suffix-less internal key, so the rest of the engine is
    currency-agnostic. Errors loudly if the expected column is absent – a silent
    fallback here would let a currency mismatch through unnoticed."""
    src = f"{stem}_{base}"
    if rows and src not in rows[0]:
        have = [c for c in rows[0] if c.startswith(stem + "_")]
        raise ValueError(
            f"{filename}: expected cost column '{src}' (cost columns must end in "
            f"_<base_currency>; base_currency is '{base.upper()}'). "
            f"Found {have or list(rows[0])}."
        )
    for r in rows:
        if src in r:
            r[stem] = r.pop(src)


def load_model(data_dir: str | Path) -> Model:
    d = Path(data_dir)
    items = {r["item_id"]: r for r in csv.DictReader(open(d / "bac-items.csv"))}
    edges = list(csv.DictReader(open(d / "bac-bom.csv")))
    breaks: dict[str, list] = {}
    break_notes: dict[tuple[str, float], str] = {}
    for b in csv.DictReader(open(d / "bac-price-breaks.csv")):
        breaks.setdefault(b["item_id"], []).append((float(b["min_qty"]), float(b["unit_price"])))
        if (b.get("notes") or "").strip():
            break_notes[(b["item_id"], float(b["min_qty"]))] = b["notes"].strip()
    for k in breaks:
        breaks[k].sort()
    overrides: dict[str, dict] = {}
    ov_path = d / "bac-price-overrides.csv"
    if ov_path.exists():
        for r in csv.DictReader(open(ov_path)):
            if r.get("item_id"):
                overrides[r["item_id"]] = r
    cfg = tomllib.load(open(d / "bac-pricing-config.toml", "rb"))
    base = str(cfg["financials"]["base_currency"]).lower()
    _require_ccy_col(edges, base, "consumables", "bac-bom.csv")
    _ov_rows = list(overrides.values())
    _require_ccy_col(_ov_rows, base, "additive", "bac-price-overrides.csv")
    _require_ccy_col(_ov_rows, base, "absolute", "bac-price-overrides.csv")
    return Model(items, edges, breaks, overrides, cfg, break_notes)


def is_sellable(row: dict) -> bool:
    """``sellable`` as the CSV spells it (``true``) or as a database boolean."""
    value = row.get("sellable")
    return value is True or str(value).strip().lower() == "true"


# ---------------------------------------------------------------------------
# Price breaks
# ---------------------------------------------------------------------------


def price_break_at(table: list[tuple] | None, qty: float):
    """Return (unit_price, how) for a required quantity.

    Selection: largest break <= qty (conservative bracket). If qty is below
    every quoted break, fall back to the smallest break above it ('fallback').
    Returns (None, 'missing') when the item has no quotes at all.
    """
    if not table:
        return None, "missing"
    le = [(q, p) for q, p in table if q <= qty]
    if le:
        return le[-1][1], "exact"
    return table[0][1], "fallback"


# ---------------------------------------------------------------------------
# Tree traversal
# ---------------------------------------------------------------------------


def effective_leaf_qty(model: Model, root: str, batch: float) -> dict[str, float]:
    """Effective procurement quantity per leaf: batch × product of edge
    quantities along every path from root. Shared leaves accumulate."""
    eff: dict[str, float] = {}

    def walk(node: str, mult: float):
        for e in model.children.get(node, []):
            q = float(e["qty_per_parent"])
            cid = e["child_id"]
            if model.items[cid]["type"] in LEAF_TYPES:
                eff[cid] = eff.get(cid, 0.0) + mult * q
            else:
                walk(cid, mult * q)

    walk(root, batch)
    return eff


def parent_instances(model: Model, root: str) -> dict[str, float]:
    """Instances of each composed node per single unit of root (for labour
    and consumables, which attach to edges per parent instance)."""
    inst = {root: 1.0}

    def walk(node: str, mult: float):
        for e in model.children.get(node, []):
            cid = e["child_id"]
            if model.items[cid]["type"] not in LEAF_TYPES:
                inst[cid] = inst.get(cid, 0.0) + mult * float(e["qty_per_parent"])
                walk(cid, mult * float(e["qty_per_parent"]))

    walk(root, 1.0)
    return inst


def labour_minutes_per_unit(model: Model, root: str) -> float:
    """Total labour minutes (assy+qc+pack+ship) for ONE unit of root."""
    inst = parent_instances(model, root)
    total = 0.0
    for e in model.edges:
        m = inst.get(e["parent_id"], 0.0)
        total += m * (float(e["assy_min"]) + float(e["qc_min"]) + float(e["pack_min"]) + float(e["ship_min"]))
    return total


def consumables_per_unit(model: Model, root: str) -> float:
    """Consumables (base ccy) for ONE unit of root (per edge, per parent instance)."""
    inst = parent_instances(model, root)
    return sum(inst.get(e["parent_id"], 0.0) * float(e["consumables"]) for e in model.edges)


# ---------------------------------------------------------------------------
# Cost rollup
# ---------------------------------------------------------------------------


@dataclass
class LeafCost:
    item_id: str
    name: str
    vendor: str
    qty: float
    unit_price: float | None
    currency: str
    how: str  # exact | fallback | missing
    base: float
    shipping: float
    bank: float
    duties: float
    landed: float


def leaf_costs(model: Model, root: str, batch: float) -> list[LeafCost]:
    fx = model.cfg["fx"]
    out = []
    for lid, qty in sorted(effective_leaf_qty(model, root, batch).items()):
        it = model.items[lid]
        up, how = price_break_at(model.breaks.get(lid), qty)
        v = model.vendors.get(it["vendor"], {})
        cur = v.get("currency") or model.cfg["financials"]["base_currency"]
        rate = fx.get(cur, 1.0)
        sf = float(v.get("shipping", 1.0))
        bf = float(v.get("bank", 1.0))
        df = float(v.get("duties", 1.0))
        if up is None:
            base = ship = bank = duty = landed = 0.0
        else:
            base = up * rate * qty
            ship = base * (sf - 1.0)
            bank = base * sf * (bf - 1.0)
            duty = base * sf * bf * (df - 1.0)
            landed = base + ship + bank + duty
            # per-item (leaf) override applies to the unit landed cost; scale the
            # component split so the cost-type breakdown still sums correctly.
            if qty and landed and lid in model.overrides:
                adj_unit, touched = apply_cost_override(model, lid, landed / qty)
                if touched:
                    scale = (adj_unit * qty) / landed if landed else 1.0
                    base *= scale
                    ship *= scale
                    bank *= scale
                    duty *= scale
                    landed = adj_unit * qty
        out.append(LeafCost(lid, it["name"], it["vendor"], qty, up, cur, how, base, ship, bank, duty, landed))
    return out


@dataclass
class CostRollup:
    root: str
    batch: float
    base: float
    shipping: float
    bank: float
    duties: float
    landed: float
    consumables: float  # batch total
    labour_min_per_unit: float
    labour: float  # batch total
    direct: float
    contingency: float
    total: float  # total recoverable cost (batch)
    cost_per_unit: float  # fully loaded
    material_per_unit: float  # excl. labour, incl. safety
    leaves: list[LeafCost]
    missing: list[str]  # item_ids without any quote
    fallback: list[str]  # item_ids priced via higher bracket


def rollup(model: Model, root: str, batch: float) -> CostRollup:
    fin = model.cfg["financials"]
    leaves = leaf_costs(model, root, batch)
    base = sum(leaf.base for leaf in leaves)
    ship = sum(leaf.shipping for leaf in leaves)
    bank = sum(leaf.bank for leaf in leaves)
    duty = sum(leaf.duties for leaf in leaves)
    landed = base + ship + bank + duty
    cons = consumables_per_unit(model, root) * batch
    lab_min = labour_minutes_per_unit(model, root)
    day_rate = fin["salary_monthly"] * fin["social_insurance_factor"] / fin["working_days_per_month"]
    labour = day_rate * (lab_min * batch / (60 * fin["hours_per_day"]))
    direct = landed + cons + labour
    safety = fin["expense_safety_factor"] * fin["overhead_safety_factor"]
    total = direct * safety
    return CostRollup(
        root=root,
        batch=batch,
        base=base,
        shipping=ship,
        bank=bank,
        duties=duty,
        landed=landed,
        consumables=cons,
        labour_min_per_unit=lab_min,
        labour=labour,
        direct=direct,
        contingency=total - direct,
        total=total,
        cost_per_unit=total / batch,
        material_per_unit=(landed + cons) * safety / batch,
        leaves=leaves,
        missing=[leaf.item_id for leaf in leaves if leaf.how == "missing"],
        fallback=[leaf.item_id for leaf in leaves if leaf.how == "fallback"],
    )


# ---------------------------------------------------------------------------
# Overrides & rounding
# ---------------------------------------------------------------------------


def _f(row: dict, key: str) -> float | None:
    v = (row or {}).get(key, "")
    if v in (None, ""):
        return None
    return float(v)


def apply_cost_override(model: Model, item_id: str, cost: float) -> tuple[float, bool]:
    """Apply the manual override chain to a per-unit cost:
    absolute replaces -> factor multiplies -> additive shifts.
    Returns (adjusted_cost, was_overridden)."""
    row = model.overrides.get(item_id)
    if not row:
        return cost, False
    out = cost
    touched = False
    a = _f(row, "absolute")
    if a is not None:
        out = a
        touched = True
    f = _f(row, "factor")
    if f is not None:
        out *= f
        touched = True
    add = _f(row, "additive")
    if add is not None:
        out += add
        touched = True
    return out, touched


def round_price(price: float, direction: str, multiple: float) -> float:
    """Round a FINAL price to a multiple. Never applied to costs."""
    if multiple <= 0:
        return price
    x = price / multiple
    if direction == "up":
        return math.ceil(x - 1e-9) * multiple
    if direction == "down":
        return math.floor(x + 1e-9) * multiple
    return round(x) * multiple


def rounding_for(model: Model, item_id: str) -> tuple[str, float]:
    """Per-item rounding override, falling back to the global rule."""
    g = model.cfg["rounding"]
    row = model.overrides.get(item_id) or {}
    direction = row.get("round_direction") or g["direction"]
    multiple = _f(row, "round_multiple")
    return direction, (multiple if multiple is not None else float(g["multiple"]))


# ---------------------------------------------------------------------------
# Price derivation
# ---------------------------------------------------------------------------


@dataclass
class PriceResult:
    root: str
    batch: float
    cost_per_unit: float  # after overrides
    np_basis_cost: float
    target_revenue: float
    at_cost_contribution: float
    weighted_paying_units: float
    full_price_units: float
    base_price: float  # excl. VAT, unrounded
    price_rounded: float
    price_incl_vat: float
    implied_np_discount: float
    net_revenue: float  # cross-check, must equal target
    realised_margin: float  # cross-check, must equal target margin
    absorbed_discounts: float = 0.0  # forgone revenue vs full price across
    # zero-rev units + partial (edu/NP) tiers
    valid: bool = True  # False when the composition is unpriceable
    error: str | None = None  # human-readable reason when not valid


def derive_root_price(model: Model, ru: CostRollup) -> PriceResult:
    cfg = model.cfg
    fin, batch_cfg = cfg["financials"], cfg["batch"]
    margin = fin["target_margin"]
    tiers = cfg["discount_tiers"]

    cost_unit, _ = apply_cost_override(model, ru.root, ru.cost_per_unit)
    total = cost_unit * ru.batch
    # NP basis follows config: fully loaded vs material-only
    if cfg["nonprofit"]["basis"] == "material_only":
        np_basis = ru.material_per_unit
    else:
        np_basis = cost_unit

    zero_rev = (
        batch_cfg["lost"]
        + batch_cfg["donations"]
        + batch_cfg["returns"]
        + batch_cfg["warranty"]
        + batch_cfg["reserved"]
        + batch_cfg["not_sold"]
    )
    sellable = batch_cfg["ordered"] - zero_rev
    tier_units = sum(t["units"] for t in tiers)
    full_units = sellable - tier_units

    target = total / (1 - margin)
    at_cost = sum(t["units"] * np_basis for t in tiers if t["kind"] == "at_cost")
    weighted = full_units + sum(t["units"] * (1 - t["value"]) for t in tiers if t["kind"] == "percentage")

    # Guard: the composition is unpriceable when revenue-bearing units don't
    # cover the discounted/at-cost commitments. Return a flagged, zeroed result
    # the UI can surface instead of a nonsensical negative price.
    if full_units < 0 or weighted <= 0:
        msg = (
            f"Unpriceable composition: {batch_cfg['ordered']} ordered minus "
            f"{zero_rev} zero-revenue and {tier_units} discounted/at-cost "
            f"units leaves {full_units:.0f} full-price units "
            f"({weighted:.1f} weighted). Increase the order count or reduce "
            f"the tier / zero-revenue units."
        )
        return PriceResult(
            root=ru.root,
            batch=ru.batch,
            cost_per_unit=cost_unit,
            np_basis_cost=np_basis,
            target_revenue=target,
            at_cost_contribution=at_cost,
            weighted_paying_units=weighted,
            full_price_units=full_units,
            base_price=0.0,
            price_rounded=0.0,
            price_incl_vat=0.0,
            implied_np_discount=0.0,
            net_revenue=0.0,
            realised_margin=0.0,
            valid=False,
            error=msg,
        )

    base_price = (target - at_cost) / weighted if weighted else 0.0

    direction, multiple = rounding_for(model, ru.root)
    # Round the base-currency price per the global rule.
    price_rounded_v = round_price(base_price, direction, multiple)

    # cross-checks at the unrounded price
    gross = (full_units + sum(t["units"] for t in tiers if t["kind"] == "percentage")) * base_price
    disc_given = sum(t["units"] * base_price * t["value"] for t in tiers if t["kind"] == "percentage")
    net = gross - disc_given + at_cost

    # Absorbed discounts = revenue forgone against full price, summed over every
    # non-full-price unit: zero-rev units (100% forgone), percentage tiers
    # (forgone = units × discount × price), and at-cost tiers (forgone =
    # units × (price – cost)).
    absorbed = zero_rev * base_price
    for t in tiers:
        if t["kind"] == "percentage":
            absorbed += t["units"] * t["value"] * base_price
        elif t["kind"] == "at_cost":
            absorbed += t["units"] * max(base_price - np_basis, 0.0)

    return PriceResult(
        root=ru.root,
        batch=ru.batch,
        cost_per_unit=cost_unit,
        np_basis_cost=np_basis,
        target_revenue=target,
        at_cost_contribution=at_cost,
        weighted_paying_units=weighted,
        full_price_units=full_units,
        base_price=base_price,
        price_rounded=price_rounded_v,
        price_incl_vat=base_price * (1 + fin["vat"]),
        implied_np_discount=(1 - np_basis / base_price) if base_price else 0.0,
        net_revenue=net,
        realised_margin=(net - total) / net if net else 0.0,
        absorbed_discounts=absorbed,
    )


def regional_prices(model: Model, base_price: float, domestic_label: str | None = None) -> list[dict]:
    """Regional prices in each market's local currency.

    The domestic market is the anchor: its price equals the base price (margin
    is guaranteed in the base ccy). Every market is base × (mult / dom_mult),
    converted to its display currency and rounded per the global rule. A manual
    per-market adjustment, in that market's own currency, is added LAST (after
    rounding) so a typed value lands exactly. Returns rows with: region,
    multiplier, currency, adjust, price_multiplier (rounded, pre-adjust) and
    price (final)."""
    regions = model.cfg.get("regions", [])
    if not regions:
        return []
    dom = next((r for r in regions if r["label"] == domestic_label), regions[0])
    dm = dom["multiplier"] or 1.0
    fx = model.cfg["fx"]
    d = model.cfg["rounding"]["direction"]
    mult = float(model.cfg["rounding"]["multiple"])
    out = []
    for r in regions:
        p_base = base_price * (r["multiplier"] / dm)
        cur = r.get("currency") or model.cfg["financials"]["base_currency"]
        rate = float(fx.get(cur, 1.0)) or 1.0
        rounded = round_price(p_base / rate, d, mult)
        adjust = float(r.get("adjust", 0) or 0)
        out.append(
            {
                "region": r["label"],
                "multiplier": r["multiplier"],
                "currency": cur,
                "adjust": adjust,
                "price_multiplier": rounded,
                "price": rounded + adjust,
                "price_base": p_base,
            }
        )
    return out


def price_list(model: Model, batch: float) -> list[dict]:
    """Price every sellable item, in the base currency. The root assembly uses
    the batch waterfall; other sellables use simple true-margin pricing on their
    rolled-up cost. Per-market prices come from regional_prices, not here."""
    fin = model.cfg["financials"]
    rows = []
    for iid, it in model.items.items():
        if not is_sellable(it):
            continue
        ru = rollup(model, iid, batch)
        cost, overridden = apply_cost_override(model, iid, ru.cost_per_unit)
        if it["type"] == "assembly":
            pr = derive_root_price(model, ru)
            price = pr.base_price
        else:
            d, m = rounding_for(model, iid)
            price = round_price(cost / (1 - fin["target_margin"]), d, m)
        rows.append(
            dict(
                item_id=iid,
                sku=it["sku"],
                name=it["name"],
                type=it["type"],
                cost=round(cost, 2),
                overridden=overridden,
                price=round(price, 2),
                quotes_missing=len(ru.missing),
                quotes_fallback=len(ru.fallback),
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_model(model: Model) -> list[str]:
    """Structural checks on a loaded model; returns problems, one line each.

    Referential integrity (every edge resolves, every vendor key resolves),
    no negative quantities or labour, an acyclic BOM, and the SKU scheme on
    every item that carries a SKU. Missing quotes are not a problem here –
    the rollup reports them as pending.
    """
    from bac_suite_db.sku import SkuError, validate_sku

    problems: list[str] = []
    for e in model.edges:
        for key in ("parent_id", "child_id"):
            if e[key] not in model.items:
                problems.append(f"bac-bom.csv: {key} '{e[key]}' is not in bac-items.csv")
        for key in ("qty_per_parent", "assy_min", "qc_min", "pack_min", "ship_min", "consumables"):
            value = e.get(key)
            if value is None or str(value).strip() == "":
                problems.append(f"bac-bom.csv: {e['parent_id']} → {e['child_id']} has an empty {key}")
                continue
            try:
                if float(value) < 0:
                    problems.append(f"bac-bom.csv: {e['parent_id']} → {e['child_id']} has negative {key}")
            except (TypeError, ValueError):
                problems.append(f"bac-bom.csv: {e['parent_id']} → {e['child_id']} has a non-numeric {key}")
    for iid, it in model.items.items():
        vendor = it.get("vendor", "")
        if vendor and vendor not in model.vendors:
            problems.append(f"bac-items.csv: {iid} names vendor '{vendor}', which is not in the vendor table")
        if it.get("type") not in ("assembly", "subassembly", "part", "service"):
            problems.append(f"bac-items.csv: {iid} has type '{it.get('type')}'")
        sku = (it.get("sku") or "").strip()
        if sku:
            try:
                validate_sku(sku)
            except SkuError as exc:
                problems.append(f"bac-items.csv: {iid}: {exc.message} ({exc.detail})")
        elif is_sellable(it):
            problems.append(f"bac-items.csv: {iid} is sellable but has no SKU")
    for iid in model.breaks:
        if iid not in model.items:
            problems.append(f"bac-price-breaks.csv: item '{iid}' is not in bac-items.csv")
    for iid in model.overrides:
        if iid not in model.items:
            problems.append(f"bac-price-overrides.csv: item '{iid}' is not in bac-items.csv")
    problems.extend(_cycles(model))
    return problems


def _cycles(model: Model) -> list[str]:
    """Report every node that reaches itself through the BOM edges."""
    state: dict[str, int] = {}
    found: list[str] = []

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 1:
            found.append("bac-bom.csv: cycle " + " → ".join(trail[trail.index(node) :] + [node]))
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        for e in model.children.get(node, []):
            visit(e["child_id"], trail + [node])
        state[node] = 2

    for root in list(model.children):
        if state.get(root) != 2:
            visit(root, [])
    return found


# ---------------------------------------------------------------------------
# FX sync
# ---------------------------------------------------------------------------

# Frankfurter's public API moved from api.frankfurter.app to api.frankfurter.dev.
FX_API = "https://api.frankfurter.dev/v1/latest"


def rebase_fx(fx: dict, anchor: str) -> dict:
    """Re-express FX rates relative to a new anchor currency. Input and output
    both use the convention fx[X] = anchor-currency per 1 unit of X. Dividing
    every rate by the new anchor's current rate re-anchors the table; the new
    anchor becomes 1.0. Meta keys (source/updated) pass through. If the anchor
    is absent or zero, the table is returned unchanged (treated as already
    anchored)."""
    div = float(fx.get(anchor, 0) or 0)
    if not div:
        return dict(fx)
    out = {}
    for k, v in fx.items():
        if k in ("source", "updated"):
            out[k] = v
        else:
            out[k] = round(float(v) / div, 6)
    out[anchor] = 1.0
    return out


def sync_currencies(timeout: float = 5.0) -> tuple[dict | None, str | None]:
    """Fetch frankfurter's supported-currency list: {code: full_name}. Useful
    to validate that configured currency codes exist and to label them.
    Note: frankfurter publishes names, not symbols, so this cannot populate
    currency symbols. Returns (names, None) or (None, error_message)."""
    try:
        url = FX_API.rsplit("/", 1)[0] + "/currencies"
        req = urllib.request.Request(
            url, headers={"User-Agent": f"bac-pricing/{__version__} (+https://buildacubesat.space)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def sync_fx(base: str, symbols: tuple, timeout: float = 5.0) -> tuple[dict | None, str | None]:
    """Fetch current FX rates (1 unit of symbol -> base). Returns
    (rates, None) on success, e.g. ({"USD": 0.79, ...}, None), or
    (None, error_message) on failure so the UI can surface it rather than
    silently falling back to the manual config values."""
    try:
        url = f"{FX_API}?base={base}&symbols={','.join(symbols)}"
        req = urllib.request.Request(
            url, headers={"User-Agent": f"bac-pricing/{__version__} (+https://buildacubesat.space)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        # frankfurter returns base->symbol; we store symbol->base, so invert
        rates = {sym: round(1.0 / rate, 4) for sym, rate in data["rates"].items()}
        return rates, None
    except Exception as exc:  # noqa: BLE001 – report any failure to the UI
        return None, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Config writeback
# ---------------------------------------------------------------------------


def dump_config(cfg: dict) -> str:
    """Serialise the pricing config back to TOML in the canonical BAC layout,
    preserving the comment header and section structure. Used by the notebook's
    save feature. Mirrors bac-pricing-config.toml."""
    import datetime as _dt

    def num(x):
        f = float(x)
        return str(int(f)) if f == int(f) and abs(f) >= 1 else f"{f}"

    fin, fx, b, rnd = cfg["financials"], cfg["fx"], cfg["batch"], cfg["rounding"]
    np_basis = cfg["nonprofit"]["basis"]
    L = []
    L.append("# Build a CubeSat – pricing configuration")
    L.append("# Hand-edited. Tabular data lives in the CSV files alongside this.")
    L.append(f'version = "{cfg.get("version", "0.1.0")}"')
    L.append(f'updated = "{_dt.date.today().isoformat()}"')
    L.append("")
    L.append("# Vendor table. currency drives FX conversion; shipping/bank/duties are")
    L.append("# multiplicative overhead factors on landed cost.")
    L.append("vendors = [")
    for v in cfg["vendors"]:
        L.append(
            f'  {{ key = "{v["key"]}", name = "{v["name"]}", '
            f'currency = "{v["currency"]}", shipping = {num(v["shipping"])}, '
            f"bank = {num(v['bank'])}, duties = {num(v['duties'])}, "
            f'true_currency = "{v.get("true_currency", v["currency"])}" }},'
        )
    L.append("]")
    L.append("")
    L.append('# Discount tiers. kind = "percentage" (uses value) or "at_cost".')
    L.append("discount_tiers = [")
    for t in cfg["discount_tiers"]:
        L.append(
            f'  {{ label = "{t["label"]}", kind = "{t["kind"]}", value = {t["value"]}, units = {int(t["units"])} }},'
        )
    L.append("]")
    L.append("")
    L.append("# Regional price multipliers applied to the EU-baseline export price.")
    L.append("regions = [")
    for r in cfg.get("regions", []):
        currency = r.get("currency") or fin["base_currency"]
        adjust = float(r.get("adjust", 0) or 0)
        L.append(
            f'  {{ label = "{r["label"]}", multiplier = {r["multiplier"]}, '
            f'currency = "{currency}", adjust = {adjust} }},'
        )
    L.append("]")
    L.append("")
    L.append("[financials]")
    for k in (
        "base_currency",
        "target_margin",
        "vat",
        "salary_monthly",
        "working_days_per_month",
        "hours_per_day",
        "social_insurance_factor",
        "expense_safety_factor",
        "overhead_safety_factor",
    ):
        val = fin[k]
        L.append(f"{k:<23} = " + (f'"{val}"' if isinstance(val, str) else num(val)))
    L.append("")
    L.append("[nonprofit]")
    L.append(f'basis = "{np_basis}"')
    L.append("")
    L.append("# Exchange rates: 1 unit of <currency> = <rate> of the base currency.")
    L.append("# The base currency itself is 1.0.")
    L.append("[fx]")
    L.append(f'source  = "{fx.get("source", "manual")}"')
    L.append(f'updated = "{fx.get("updated", _dt.date.today().isoformat())}"')
    for c in sorted(k for k in fx if k not in ("source", "updated")):
        L.append(f"{c} = {num(fx[c])}")
    L.append("")
    L.append("# Global price rounding. Applies to FINAL prices only.")
    L.append("[rounding]")
    L.append(f'direction = "{rnd["direction"]}"')
    L.append(f"multiple  = {num(rnd['multiple'])}")
    L.append("")
    L.append("[batch]")
    for k in ("ordered", "lost", "donations", "returns", "warranty", "reserved", "not_sold"):
        L.append(f"{k:<9} = {int(b[k])}")
    return "\n".join(L) + "\n"
