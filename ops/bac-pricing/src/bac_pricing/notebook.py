# SPDX-License-Identifier: MIT
# Build a CubeSat – pricing notebook. Thin UI over bac_pricing.engine and bac_pricing.store.

import marimo

__generated_with = "0.25.0"
app = marimo.App(width="medium", app_title="BAC Pricing")


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md("""
    # BAC Assembly Pricing

    Roll up the landed cost of an assembly through its bill of materials and
    derive the batch price that recovers it at the target margin. Pick the
    assembly, set the batch size and its composition, and tune the financial
    assumptions in Settings; the headline numbers, charts and tables follow.

    Compare the primary market's price against the domestic one, see how the
    price moves with batch size and margin, and where the cost sits by
    subsystem, cost type or vendor.

    Part of the [Build a CubeSat](https://buildacubesat.space) business
    operations suite; source in
    [bac-utils](https://github.com/buildacubesat/bac-utils).
    """),
            mo.callout(
                mo.md(
                    "Every figure is a modeled cost from quotes, factors and assumptions, "
                    "not an invoice. Items without a quote contribute nothing and the "
                    "rollup is a lower bound until they are priced."
                ),
                kind="warn",
                title="Modeled Costs, Not Actuals",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,400;6..12,500;6..12,600;6..12,700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');

    :root {
      --text:       #3F3F3F;
      --bg:         #efefed;
      --text-muted: #888884;
    }

    /* Track marimo's own light/dark setting rather than the operating system.
       marimo sets color-scheme from that setting and light-dark() follows it. */
    :root {
      --text: light-dark(#3F3F3F, #efefed);
      --bg:   light-dark(#efefed, #201e1c);
    }

    h1, h2, h3, h4 {
      font-family: 'Nunito Sans', system-ui, sans-serif;
      color: var(--text);
    }

    body, p, li, .prose {
      font-family: 'IBM Plex Mono', ui-monospace, monospace;
      color: var(--text);
    }

    .marimo-callout { border-radius: 6px; }

    /* Chart text follows the same variable, so axis labels and legends stay
       legible even when the notebook theme and the chart palette disagree. */
    .vega-embed text { fill: var(--text); }

    /* marimo styles markdown headings through --heading-font with a selector
       more specific than the rule above, which would leave them in its serif. */
    :root { --heading-font: 'Nunito Sans', system-ui, sans-serif; }

    .bac-sub { color: var(--text-muted); font-size: .85rem; }
    .bac-tg-lab { display: inline-block; min-width: 96px; font-size: .85rem; color: var(--text-muted); }
    </style>
    """)
    return


@app.cell
def _():
    import copy
    import datetime as dt

    import altair as alt
    import marimo as mo
    import pandas as pd
    from wigglystuff import TangleSlider

    from bac_common.errors import BacError
    from bac_pricing import engine as eng
    from bac_pricing import store
    from bac_suite_db import config as suite_config
    from bac_suite_db.dsn import describe, scrub

    return (
        BacError,
        TangleSlider,
        alt,
        copy,
        describe,
        dt,
        eng,
        mo,
        pd,
        scrub,
        store,
        suite_config,
    )


@app.cell
def _(suite_config):
    TOOL_VERSION = "1.4.0"
    SETTINGS = suite_config.load_settings()

    # Currency symbols for display. Unknown codes fall back to the code itself.
    CCY_SYMBOLS = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "CHF": "CHF ",
        "AUD": "A$",
        "CAD": "C$",
        "JPY": "¥",
        "CNY": "¥",
        "INR": "₹",
        "SEK": "kr ",
        "NOK": "kr ",
        "DKK": "kr ",
        "PLN": "zł ",
        "CZK": "Kč ",
        "HUF": "Ft ",
        "NZD": "NZ$",
        "SGD": "S$",
        "HKD": "HK$",
        "KRW": "₩",
        "BRL": "R$",
        "ZAR": "R ",
        "MXN": "$",
        "TRY": "₺",
        "ILS": "₪",
        "THB": "฿",
    }

    def fmt(value, decimals=0):
        """Swiss style: apostrophe thousands, decimal point (1'137.74)."""
        return f"{value:,.{decimals}f}".replace(",", "'")

    def money(value, currency, decimals=0):
        return f"{CCY_SYMBOLS.get(currency, currency + ' ')}{fmt(value, decimals)}"

    return SETTINGS, TOOL_VERSION, fmt, money


@app.cell
def _(BacError, SETTINGS, describe, mo, scrub, store, suite_config):
    # Storage: the Model comes from the configured backend. Editors are built from
    # it in both modes, so nothing downstream can tell the backends apart.
    _error = None
    try:
        suite_config.require_setup(SETTINGS)
        model_src = store.load_source(SETTINGS)
    except BacError as _exc:
        model_src, _error = None, _exc.message + (f" {_exc.detail}" if _exc.detail else "")
    except Exception as _exc:  # noqa: BLE001 – shown as a callout, never a traceback
        model_src, _error = None, scrub(f"{type(_exc).__name__}: {_exc}", SETTINGS.dsn)
    if SETTINGS.uses_db:
        _where = f"Postgres at `{describe(SETTINGS.dsn or '')}`" if SETTINGS.dsn else "Postgres (no `BAC_DB_DSN` set)"
        _fix = (
            "First run? `bac-db --init`, then `bac-db migrate` and `bac-db import pricing <data-dir>`. "
            'Or set `backend = "files"` in the suite config to work from the CSV/TOML files.'
        )
    else:
        _where = f"files in `{SETTINGS.data_dir}`"
        _fix = "Copy `ops/bac-pricing/examples/` there, or point `storage.data_dir` at your data."
    mo.stop(
        _error is not None,
        mo.callout(mo.md(f"**Storage not reachable.** Backend: {_where}.\n\n`{_error}`\n\n{_fix}"), kind="danger"),
    )
    if SETTINGS.uses_db:
        with store.connect(SETTINGS.dsn) as _conn:
            _status = store.db_status(_conn)
        storage_lines = [f"Postgres · {describe(SETTINGS.dsn)}"] + [f"{k}: {v}" for k, v in _status]
    else:
        storage_lines = [f"Files · {SETTINGS.data_dir}"] + [
            f"{'✓' if (SETTINGS.data_dir / f).exists() else '✗'} {f}" for f in store.DATA_FILES
        ]
    return model_src, storage_lines


@app.cell
def _(mo, model_src):
    # FX state (runs once): the currency list is derived from markets and vendors.
    # Rates are base currency per 1 unit; the base currency itself is 1.0.
    _cfg = model_src.cfg
    base_ccy_fx = _cfg["financials"]["base_currency"]
    fx_ccys = sorted(
        {r["currency"] for r in _cfg.get("regions", [])}
        | {v.get("true_currency", v["currency"]) for v in _cfg.get("vendors", [])}
        | {v["currency"] for v in _cfg.get("vendors", [])}
        | {base_ccy_fx}
    )
    _fx = _cfg["fx"]
    get_fx, set_fx = mo.state(
        {
            "rates": {c: float(_fx.get(c, 1.0)) for c in fx_ccys},
            "updated": str(_fx.get("updated", "")),
            "err": None,
            "source": str(_fx.get("source", "manual")),
            "names": {},
        }
    )
    return base_ccy_fx, fx_ccys, get_fx, set_fx


@app.cell
def _(base_ccy_fx, dt, eng, fx_ccys, get_fx, mo, set_fx):
    # FX sync against frankfurter.dev (a network call), plus its currency list for validation.
    def _do_sync(_v=None):
        _others = tuple(c for c in fx_ccys if c != base_ccy_fx)
        rates, err = eng.sync_fx(base=base_ccy_fx, symbols=_others)
        names, _ = eng.sync_currencies()
        if rates:
            rates[base_ccy_fx] = 1.0
            set_fx(
                {
                    "rates": {**get_fx()["rates"], **rates},
                    "updated": dt.date.today().isoformat(),
                    "err": None,
                    "source": "frankfurter.dev",
                    "names": names or get_fx().get("names", {}),
                }
            )
        else:
            set_fx({**get_fx(), "err": err, "names": names or get_fx().get("names", {})})

    fx_sync_ui = mo.ui.run_button(label=f"Sync FX (base {base_ccy_fx})", on_change=_do_sync)
    return (fx_sync_ui,)


@app.cell
def _(base_ccy_fx, eng, fx_ccys, get_fx, mo, pd):
    # FX rate table, anchored on the base currency (anchor = 1.00).
    _reb = eng.rebase_fx(dict(get_fx()["rates"]), base_ccy_fx)
    _rows = [{"currency": c, "rate": round(_reb.get(c, 1.0), 6)} for c in fx_ccys]
    fx_editor = mo.ui.data_editor(pd.DataFrame(_rows), label="Exchange rates (base currency per 1 unit)")

    _names = get_fx().get("names") or {}
    fx_note = None
    if _names:
        _unknown = [c for c in fx_ccys if c not in _names]
        if _unknown:
            fx_note = mo.callout(
                mo.md(
                    "**Not recognised by frankfurter:** "
                    + ", ".join(f"`{c}`" for c in _unknown)
                    + ". Check the code – these will not sync and have no published rate."
                ),
                kind="warn",
            )
        else:
            fx_note = mo.md("<span class='bac-sub'>✓ All currency codes recognised by frankfurter.</span>")
    return fx_editor, fx_note


@app.cell
def _(TangleSlider, mo, model_src):
    # Control elements – every input of the notebook, defined here and laid out in the panel cell.
    _cfg = model_src.cfg
    _fin, _b, _rnd = _cfg["financials"], _cfg["batch"], _cfg["rounding"]
    # The two tier controls bind to the first percentage tier and the first at-cost tier, by kind.
    pct_tier = next((t["label"] for t in _cfg["discount_tiers"] if t["kind"] == "percentage"), None)
    cost_tier = next((t["label"] for t in _cfg["discount_tiers"] if t["kind"] == "at_cost"), None)
    _tiers = {t["label"]: t for t in _cfg["discount_tiers"]}
    _assemblies = {it["name"]: i for i, it in model_src.items.items() if it["type"] == "assembly"}
    mo.stop(
        not _assemblies,
        mo.callout(mo.md("**No assembly in the data.** Mark at least one item `type = assembly`."), kind="danger"),
    )

    def tangle(value, hi=999, suffix=""):
        return mo.ui.anywidget(
            TangleSlider(
                amount=round(value), min_value=0 if suffix == "" else 1, max_value=hi, step=1, digits=0, suffix=suffix
            )
        )

    def number(value, label, step=0.01, hi=9999):
        return mo.ui.number(value=value, start=0, stop=hi, step=step, label=label)

    assembly_ui = mo.ui.dropdown(options=_assemblies, value=next(iter(_assemblies)), label="Assembly")
    _rlabels = [r["label"] for r in _cfg.get("regions", [])]

    def _pick(want):
        return want if want in _rlabels else (_rlabels[0] if _rlabels else None)

    primary_ui = mo.ui.dropdown(options=_rlabels, value=_pick("US"), label="Primary market (retail)")
    secondary_ui = mo.ui.dropdown(options=_rlabels, value=_pick("EU"), label="Secondary market (retail)")
    domestic_ui = mo.ui.dropdown(options=_rlabels, value=_pick("CH"), label="Domestic market (production)")

    batch_ui = tangle(_b["ordered"], hi=300, suffix=" kits")
    margin_ui = tangle(_fin["target_margin"] * 100, hi=60, suffix=" %")
    lost_ui, donations_ui = tangle(_b["lost"]), tangle(_b["donations"])
    returns_ui, warranty_ui = tangle(_b["returns"]), tangle(_b["warranty"])
    reserved_ui, notsold_ui = tangle(_b["reserved"]), tangle(_b["not_sold"])
    edu_units_ui = tangle(_tiers[pct_tier]["units"] if pct_tier else 0)
    np_units_ui = tangle(_tiers[cost_tier]["units"] if cost_tier else 0)

    edu_disc_ui = number(
        _tiers[pct_tier]["value"] * 100 if pct_tier else 0, f"{pct_tier or 'Percentage tier'} discount (%)", 1, 100
    )
    np_basis_ui = mo.ui.radio(
        options={"Fully loaded (incl. labour)": "fully_loaded", "Material only (excl. labour)": "material_only"},
        value=(
            "Material only (excl. labour)"
            if _cfg["nonprofit"]["basis"] == "material_only"
            else "Fully loaded (incl. labour)"
        ),
        label="Nonprofit cost basis",
    )
    round_dir_ui = mo.ui.radio(options=["up", "down", "nearest"], value=_rnd["direction"], inline=True, label="Round")
    round_mult_ui = number(float(_rnd["multiple"]), "Round to a multiple of", 0.01, 100.0)
    salary_ui = number(_fin["salary_monthly"], "Salary per month (base currency)", 50, 99999)
    social_ui = number(_fin["social_insurance_factor"], "Social insurance factor (×)")
    expense_ui = number(_fin["expense_safety_factor"], "Expense safety factor (×)")
    overhead_ui = number(_fin["overhead_safety_factor"], "Overhead safety factor (×)")
    vat_ui = number(_fin["vat"] * 100, "VAT (%)", 0.1, 100)
    workdays_ui = number(_fin["working_days_per_month"], "Working days per month", 1, 31)
    hours_ui = number(_fin["hours_per_day"], "Working hours per day", 1, 24)

    _cur_base = str(_fin["base_currency"])
    _ccy_opts = sorted(
        {_cur_base}
        | {"CHF", "USD", "EUR", "GBP", "AUD", "CAD"}
        | {r["currency"] for r in _cfg.get("regions", [])}
        | {v.get("true_currency", v.get("currency", "")) for v in _cfg.get("vendors", [])}
        | {k for k in _cfg.get("fx", {}) if k not in ("source", "updated")}
    )
    base_ccy_ui = mo.ui.dropdown(options=[c for c in _ccy_opts if c], value=_cur_base, label="Base currency")
    base_ccy_addcols_ui = mo.ui.checkbox(
        value=True, label="Add cost columns for the new currency if missing (copies current values)"
    )
    apply_base_btn = mo.ui.run_button(label="Apply base-currency change")

    costby_ui = mo.ui.radio(
        options=["Subsystem", "Cost type", "Vendor"], value="Subsystem", inline=True, label="Cost breakdown by"
    )
    bom_view_ui = mo.ui.radio(options=["Structure", "Overrides"], value="Structure", inline=True, label="BOM view")
    backup_ui = mo.ui.checkbox(value=False, label="Back up before saving")
    save_data_btn = mo.ui.run_button(label="Save data")
    save_config_btn = mo.ui.run_button(label="Save config")
    return (
        apply_base_btn,
        assembly_ui,
        backup_ui,
        base_ccy_addcols_ui,
        base_ccy_ui,
        batch_ui,
        bom_view_ui,
        cost_tier,
        costby_ui,
        domestic_ui,
        donations_ui,
        edu_disc_ui,
        edu_units_ui,
        expense_ui,
        hours_ui,
        lost_ui,
        margin_ui,
        notsold_ui,
        np_basis_ui,
        np_units_ui,
        overhead_ui,
        pct_tier,
        primary_ui,
        reserved_ui,
        returns_ui,
        round_dir_ui,
        round_mult_ui,
        salary_ui,
        save_config_btn,
        save_data_btn,
        secondary_ui,
        social_ui,
        vat_ui,
        warranty_ui,
        workdays_ui,
    )


@app.cell
def _(eng, mo, model_src, pd):
    # Editors over the loaded Model: BOM structure and overrides, vendors, regions, price breaks.
    _items = model_src.items
    _id2name = {i: it["name"] for i, it in _items.items()}
    _child_ids = {e["child_id"] for e in model_src.edges}
    _node_rows = [
        {"parent_id": "", "child_id": i}
        for i, it in _items.items()
        if i not in _child_ids and (eng.is_sellable(it) or it["type"] == "assembly")
    ]

    def _row(src, is_edge):
        cid = src["child_id"]
        it = _items.get(cid, {})
        o = model_src.overrides.get(cid, {})
        return {
            "parent": _id2name.get(src.get("parent_id", ""), ""),
            "item": it.get("name", cid),
            "type": it.get("type", ""),
            "vendor": it.get("vendor", ""),
            "parent_id": src.get("parent_id", ""),
            "child_id": cid,
            "qty_per_parent": float(src["qty_per_parent"]) if is_edge else None,
            "assy_min": float(src["assy_min"]) if is_edge else None,
            "qc_min": float(src["qc_min"]) if is_edge else None,
            "pack_min": float(src["pack_min"]) if is_edge else None,
            "ship_min": float(src["ship_min"]) if is_edge else None,
            "consumables": float(src["consumables"]) if is_edge else None,
            "ov_factor": o.get("factor", ""),
            "ov_additive": o.get("additive", ""),
            "ov_absolute": o.get("absolute", ""),
            "ov_round_dir": o.get("round_direction", ""),
            "ov_round_mult": o.get("round_multiple", ""),
        }

    _full = pd.DataFrame([_row(nr, False) for nr in _node_rows] + [_row(e, True) for e in model_src.edges])
    _struct_cols = [
        "parent",
        "item",
        "type",
        "vendor",
        "parent_id",
        "child_id",
        "qty_per_parent",
        "assy_min",
        "qc_min",
        "pack_min",
        "ship_min",
        "consumables",
    ]
    _ov_cols = [
        "parent",
        "item",
        "child_id",
        "ov_factor",
        "ov_additive",
        "ov_absolute",
        "ov_round_dir",
        "ov_round_mult",
    ]
    bom_struct_editor = mo.ui.data_editor(
        _full[_struct_cols], label="BOM structure: quantity, labour and consumables per usage"
    )
    bom_ov_editor = mo.ui.data_editor(_full[_ov_cols], label="BOM overrides per item: absolute → factor → additive")
    vendor_editor = mo.ui.data_editor(pd.DataFrame(model_src.cfg["vendors"]), label="Vendor table")
    region_editor = mo.ui.data_editor(
        pd.DataFrame(model_src.cfg.get("regions", [])), label="Markets: multiplier, currency, adjustment"
    )

    _brk = pd.DataFrame(
        [
            {"item": _id2name.get(_iid, _iid), "item_id": _iid, "min_qty": _q, "unit_price": _p}
            for _iid in sorted(model_src.breaks)
            for _q, _p in model_src.breaks[_iid]
        ]
        or [{"item": "", "item_id": "", "min_qty": None, "unit_price": None}]
    )
    breaks_editor = mo.ui.data_editor(
        _brk[["item", "item_id", "min_qty", "unit_price"]], label="Price breaks: one row per (item_id, min_qty)"
    )
    return (
        bom_ov_editor,
        bom_struct_editor,
        breaks_editor,
        region_editor,
        vendor_editor,
    )


@app.cell
def _(
    assembly_ui,
    batch_ui,
    bom_ov_editor,
    bom_struct_editor,
    breaks_editor,
    copy,
    cost_tier,
    domestic_ui,
    donations_ui,
    dt,
    edu_disc_ui,
    edu_units_ui,
    eng,
    expense_ui,
    fx_editor,
    get_fx,
    hours_ui,
    lost_ui,
    margin_ui,
    model_src,
    notsold_ui,
    np_basis_ui,
    np_units_ui,
    overhead_ui,
    pct_tier,
    primary_ui,
    region_editor,
    reserved_ui,
    returns_ui,
    round_dir_ui,
    round_mult_ui,
    salary_ui,
    secondary_ui,
    social_ui,
    vat_ui,
    vendor_editor,
    warranty_ui,
    workdays_ui,
):
    # Resolve: the working Model from the controls and editors, then the computation.
    model = copy.deepcopy(model_src)
    root = assembly_ui.value
    primary, secondary, domestic = primary_ui.value, secondary_ui.value, domestic_ui.value
    base_ccy = model.cfg["financials"]["base_currency"]

    _fx = {
        r["currency"]: float(r["rate"])
        for r in fx_editor.value.to_dict("records")
        if str(r.get("currency", "")).strip()
    }
    _fx[base_ccy] = 1.0
    _fxs = get_fx()
    _synced = eng.rebase_fx(dict(_fxs["rates"]), base_ccy)
    _edited = any(abs(_fx[c] - float(_synced.get(c, 1.0))) > 1e-9 for c in _fx)
    fx_source = "manual" if _edited else _fxs["source"]
    _updated = dt.date.today().isoformat() if _edited else _fxs["updated"]
    model.cfg["fx"] = {**_fx, "source": fx_source, "updated": _updated}
    fx_err = _fxs["err"]

    batch = int(batch_ui.value["amount"])
    fin = model.cfg["financials"]
    fin["target_margin"] = float(margin_ui.value["amount"]) / 100
    fin["salary_monthly"] = float(salary_ui.value)
    fin["social_insurance_factor"] = float(social_ui.value)
    fin["expense_safety_factor"] = float(expense_ui.value)
    fin["overhead_safety_factor"] = float(overhead_ui.value)
    fin["vat"] = float(vat_ui.value) / 100
    fin["working_days_per_month"] = int(workdays_ui.value)
    fin["hours_per_day"] = int(hours_ui.value)
    model.cfg["nonprofit"]["basis"] = np_basis_ui.value
    model.cfg["rounding"].update(direction=round_dir_ui.value, multiple=float(round_mult_ui.value))
    model.cfg["batch"].update(
        ordered=batch,
        lost=int(lost_ui.value["amount"]),
        donations=int(donations_ui.value["amount"]),
        returns=int(returns_ui.value["amount"]),
        warranty=int(warranty_ui.value["amount"]),
        reserved=int(reserved_ui.value["amount"]),
        not_sold=int(notsold_ui.value["amount"]),
    )
    for _t in model.cfg["discount_tiers"]:
        if _t["label"] == pct_tier:
            _t["units"] = int(edu_units_ui.value["amount"])
            _t["value"] = float(edu_disc_ui.value) / 100
        elif _t["label"] == cost_tier:
            _t["units"] = int(np_units_ui.value["amount"])
    model.cfg["regions"] = [
        {
            "label": r["label"],
            "multiplier": float(r["multiplier"]),
            "currency": r.get("currency") or base_ccy,
            "adjust": float(r.get("adjust", 0) or 0),
        }
        for r in region_editor.value.to_dict("records")
        if str(r.get("label", "")).strip()
    ]
    model.cfg["vendors"] = [
        {
            "key": r["key"],
            "name": r["name"],
            "currency": r["currency"],
            "shipping": float(r["shipping"]),
            "bank": float(r["bank"]),
            "duties": float(r["duties"]),
            "true_currency": r.get("true_currency", r["currency"]),
        }
        for r in vendor_editor.value.to_dict("records")
        if str(r.get("key", "")).strip()
    ]
    model.vendors = {v["key"]: v for v in model.cfg["vendors"]}

    def _s(v):
        return "" if v is None else str(v).strip()

    # The editors do not show ref, notes or price-break notes; they are carried from the loaded data.
    _kept = {(e["parent_id"], e["child_id"]): e for e in model_src.edges}
    _edges = []
    for r in bom_struct_editor.value.to_dict("records"):
        if _s(r["parent_id"]):
            _old = _kept.get((_s(r["parent_id"]), _s(r["child_id"])), {})
            _edges.append(
                {
                    "parent_id": _s(r["parent_id"]),
                    "child_id": _s(r["child_id"]),
                    "qty_per_parent": r["qty_per_parent"],
                    "assy_min": r["assy_min"],
                    "qc_min": r["qc_min"],
                    "pack_min": r["pack_min"],
                    "ship_min": r["ship_min"],
                    "consumables": r["consumables"],
                    "ref": _old.get("ref", "") or "",
                    "notes": _old.get("notes", "") or "",
                }
            )
    _ov, _seen = {}, set()
    for r in bom_ov_editor.value.to_dict("records"):
        cid = _s(r["child_id"])
        if cid and cid not in _seen:
            o = {
                "factor": _s(r["ov_factor"]),
                "additive": _s(r["ov_additive"]),
                "absolute": _s(r["ov_absolute"]),
                "round_direction": _s(r["ov_round_dir"]),
                "round_multiple": _s(r["ov_round_mult"]),
            }
            if any(o.values()):
                _ov[cid] = {"item_id": cid, **o, "notes": model_src.overrides.get(cid, {}).get("notes", "")}
                _seen.add(cid)
    model.edges, model.overrides = _edges, _ov
    model.children = {}
    for _e in model.edges:
        model.children.setdefault(_e["parent_id"], []).append(_e)

    _brk = {}
    for r in breaks_editor.value.to_dict("records"):
        _iid = _s(r.get("item_id"))
        if _iid and _s(r.get("min_qty")) != "" and _s(r.get("unit_price")) != "":
            try:
                _brk.setdefault(_iid, []).append((float(r["min_qty"]), float(r["unit_price"])))
            except (TypeError, ValueError):
                pass
    for _k in _brk:
        _brk[_k].sort()
    model.breaks = _brk
    model.break_notes = {k: v for k, v in model_src.break_notes.items() if k[0] in _brk and k[1] in dict(_brk[k[0]])}

    problems = eng.validate_model(model)
    ru = eng.rollup(model, root, batch)
    pr = eng.derive_root_price(model, ru)
    plist = eng.price_list(model, batch)
    regions = eng.regional_prices(model, pr.base_price, domestic) if pr.valid else []
    return (
        base_ccy,
        batch,
        domestic,
        fx_err,
        model,
        plist,
        pr,
        primary,
        problems,
        regions,
        root,
        ru,
        secondary,
    )


@app.cell
def _(SETTINGS, backup_ui, mo, model, save_config_btn, save_data_btn, store):
    # Save: data replaces the pricing tables (database) or rewrites the editable files; config appends
    # a params version (database) or rewrites the TOML. The backup box writes a snapshot first.
    _written, _backup = [], None
    _want_data, _want_config = bool(save_data_btn.value), bool(save_config_btn.value)
    if _want_data or _want_config:
        if SETTINGS.uses_db:
            with store.connect(SETTINGS.dsn) as _conn:
                if backup_ui.value:
                    _backup = store.backup_files(SETTINGS.data_dir, names=())
                    store.export_files(_conn, _backup)
                _res = store.save_pricing(
                    _conn, model, save_data=_want_data, save_params=_want_config, note="saved from notebook"
                )
            if _res["data"]:
                _written.append("pricing.bom, pricing.price_breaks, pricing.overrides replaced")
            if _res["params_version"] is not None:
                _written.append(f"params v{_res['params_version']}")
        else:
            if backup_ui.value:
                _backup = store.backup_files(SETTINGS.data_dir)
            _written = store.save_files(model, SETTINGS.data_dir, data=_want_data, config=_want_config)
    save_status = (
        mo.callout(
            mo.md(f"Saved {', '.join(_written)}" + (f" · backup → `{_backup}`" if _backup else " · no backup")),
            kind="success",
        )
        if _written
        else mo.md("")
    )
    return (save_status,)


@app.cell
def _(
    SETTINGS,
    apply_base_btn,
    backup_ui,
    base_ccy_addcols_ui,
    base_ccy_ui,
    mo,
    store,
):
    # Base-currency switch on whichever backend is in use (re-labels costs, never converts them).
    bstatus = None
    if apply_base_btn.value:
        if backup_ui.value and not SETTINGS.uses_db:
            store.backup_files(SETTINGS.data_dir)
        _r = store.switch_base_currency(SETTINGS, str(base_ccy_ui.value), add_columns=bool(base_ccy_addcols_ui.value))
        if _r.get("unchanged"):
            bstatus = mo.callout(mo.md(f"Base currency is already **{_r['old']}** – nothing to change."), kind="info")
        elif _r.get("missing"):
            bstatus = mo.callout(
                mo.md(
                    f"Cannot switch to **{_r['new']}**: these cost columns are missing and could not be "
                    "created (tick the box, or add them by hand): " + ", ".join(f"`{m}`" for m in _r["missing"])
                ),
                kind="danger",
            )
        else:
            _msg = f"Base currency changed **{_r['old']} → {_r['new']}**"
            if "version" in _r:
                _msg += (
                    f" (params v{_r['version']}). Stored costs are re-read as {_r['new']} – re-labelled, not converted."
                )
            elif _r.get("added"):
                _msg += ". Added " + ", ".join(f"`{a}`" for a in _r["added"]) + " (values copied as-is)."
            _msg += " Restart the notebook to load with the new base currency."
            bstatus = mo.callout(mo.md(_msg), kind="success")
    return (bstatus,)


@app.cell(hide_code=True)
def _(
    apply_base_btn,
    assembly_ui,
    backup_ui,
    base_ccy,
    base_ccy_addcols_ui,
    base_ccy_ui,
    batch_ui,
    bstatus,
    domestic_ui,
    donations_ui,
    edu_disc_ui,
    edu_units_ui,
    expense_ui,
    fx_editor,
    fx_note,
    fx_sync_ui,
    hours_ui,
    lost_ui,
    margin_ui,
    mo,
    notsold_ui,
    np_basis_ui,
    np_units_ui,
    overhead_ui,
    primary_ui,
    region_editor,
    reserved_ui,
    returns_ui,
    round_dir_ui,
    round_mult_ui,
    salary_ui,
    save_config_btn,
    save_data_btn,
    save_status,
    secondary_ui,
    social_ui,
    storage_lines,
    vat_ui,
    vendor_editor,
    warranty_ui,
    workdays_ui,
):
    # Control panel: the everyday inputs in two columns, the rarely touched groups in accordions.
    def _row(l1, w1, l2, w2):
        return mo.md(
            f"<span style='display:inline-block;min-width:175px'>"
            f"<span class='bac-tg-lab'>{l1}</span>{w1}</span>"
            f"<span class='bac-tg-lab'>{l2}</span>{w2}"
        )

    _left = mo.vstack(
        [
            assembly_ui,
            mo.md("**Ordered assembly count**"),
            batch_ui,
            mo.md("**Target margin** (true margin)"),
            margin_ui,
        ],
        gap=0.4,
    )
    _right = mo.vstack(
        [
            mo.md("**Batch composition** (units that earn nothing or less)"),
            _row("Lost", lost_ui, "Donations", donations_ui),
            _row("Returns", returns_ui, "Warranty", warranty_ui),
            _row("Reserved", reserved_ui, "Not sold", notsold_ui),
            _row("Edu units", edu_units_ui, "NP units", np_units_ui),
        ],
        gap=0.35,
    )
    _settings = mo.vstack(
        [
            mo.md("#### Base Currency"),
            mo.md(
                f"<span class='bac-sub'>The base currency ({base_ccy}) is the one all costs settle in: vendor "
                "prices convert into it, salary and consumables are read as it, and it is the 1.00 FX anchor. "
                "Changing it re-labels the stored costs (it does not convert them) and, in files mode with the "
                "box ticked, adds matching cost columns to the CSVs. Restart afterwards.</span>"
            ),
            mo.hstack([base_ccy_ui, apply_base_btn], justify="start", gap=1, align="center"),
            base_ccy_addcols_ui,
            *([bstatus] if bstatus else []),
            mo.md("#### Markets and Exchange Rates"),
            mo.md(
                "<span class='bac-sub'>Market multipliers and per-currency rates. A rate is 1 unit = rate × the "
                f"base currency; the base currency ({base_ccy}) is the 1.00 anchor. Sync fetches rates from "
                "frankfurter.dev.</span>"
            ),
            region_editor,
            fx_editor,
            fx_sync_ui,
            *([fx_note] if fx_note else []),
            mo.md("#### Market Roles"),
            mo.vstack([primary_ui, secondary_ui, domestic_ui], gap=0.4),
            mo.md("#### Financial Assumptions"),
            mo.md(
                f"<span class='bac-sub'>Salary, overhead and absolute overrides are in the base currency "
                f"({base_ccy}); costs always settle there.</span>"
            ),
            mo.vstack([salary_ui, social_ui, expense_ui, overhead_ui, vat_ui, workdays_ui, hours_ui], gap=0.4),
            mo.md("#### Discounts, Nonprofit and Rounding"),
            mo.vstack([edu_disc_ui, np_basis_ui, round_dir_ui, round_mult_ui], gap=0.4),
            mo.md("#### Vendors"),
            vendor_editor,
        ],
        gap=0.6,
    )
    _storage = mo.vstack(
        [
            mo.md("<br>".join(f"<span class='bac-sub'>{line}</span>" for line in storage_lines)),
            mo.md(
                "<span class='bac-sub'>Save data replaces the BOM, price breaks and overrides; Save config "
                "writes the parameters (a new version in the database, the TOML in files mode). Backup writes "
                "a snapshot under backups/ first.</span>"
            ),
            mo.hstack([save_data_btn, save_config_btn, backup_ui], justify="start", gap=1),
            save_status,
        ],
        gap=0.4,
    )
    mo.vstack(
        [
            mo.hstack([_left, _right], justify="start", gap=2, widths=[1, 1.2], align="start"),
            mo.accordion({"Settings": _settings, "Storage": _storage}),
        ]
    )
    return


@app.cell
def _(alt, mo):
    IS_DARK = mo.app_meta().theme == "dark"
    MUTED = "#888884"
    TEXT = "#efefed" if IS_DARK else "#3F3F3F"
    FONT = "IBM Plex Mono, ui-monospace, monospace"
    PALETTE = (
        ["#087C9B", "#625DC6", "#C88732", "#6F6497", "#84C45A"]
        if IS_DARK
        else ["#087C9B", "#3B35B8", "#C88732", "#21105F", "#84C45A"]
    )
    SEQUENTIAL = ["#DCEFF3", "#087C9B", "#21105F"]

    def _tint(color, amount=0.45):
        r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
        mix = (32, 30, 28) if IS_DARK else (255, 255, 255)
        return "#" + "".join(f"{round(c + (m - c) * amount):02X}" for c, m in zip((r, g, b), mix, strict=True))

    # Up to ten categories: the five palette colours, then their tints.
    PALETTE_WIDE = PALETTE + [_tint(c) for c in PALETTE]
    # Vega's format() uses a comma for thousands; the apostrophe is the Swiss style used everywhere else.
    APOSTROPHE_AXIS = "replace(format(datum.value, ',.0f'), /,/g, \"'\")"

    def style_chart(chart):
        return (
            chart.configure(font=FONT, background="transparent")
            .configure_axis(grid=False, labelColor=TEXT, titleColor=TEXT, domainColor=MUTED, tickColor=MUTED)
            .configure_legend(labelColor=TEXT, titleColor=TEXT)
            .configure_title(color=TEXT, anchor="start", fontWeight="normal")
            .configure_view(strokeWidth=0)
        )

    def chart_title(text, *notes):
        """A short title with the reading notes as subtitle lines – Altair never wraps a title."""
        return alt.Title(text, subtitle=list(notes), subtitleColor=MUTED, subtitleFontSize=11) if notes else text

    def rule_y(value, dashed=True):
        return (
            alt.Chart(alt.Data(values=[{"y": value}]))
            .mark_rule(strokeDash=[6, 4] if dashed else [2, 2], color=MUTED)
            .encode(y="y:Q")
        )

    def rule_x(value, dashed=True):
        return (
            alt.Chart(alt.Data(values=[{"x": value}]))
            .mark_rule(strokeDash=[6, 4] if dashed else [2, 2], color=MUTED)
            .encode(x="x:Q")
        )

    return (
        APOSTROPHE_AXIS,
        PALETTE,
        PALETTE_WIDE,
        SEQUENTIAL,
        chart_title,
        rule_x,
        rule_y,
        style_chart,
    )


@app.cell(hide_code=True)
def _(
    base_ccy,
    domestic,
    fmt,
    mo,
    model,
    money,
    pr,
    primary,
    regions,
    ru,
    secondary,
):
    # Headline numbers: six cards, the callouts below do the judging.
    _reg = {r["region"]: r for r in regions}
    _fx = model.cfg["fx"]
    _vat = model.cfg["financials"]["vat"]
    _prim, _sec, _dom = _reg.get(primary), _reg.get(secondary), _reg.get(domestic)
    _domccy = _dom["currency"] if _dom else base_ccy

    def _stat(value, label, caption):
        return mo.stat(value=value, label=label, caption=caption, bordered=True)

    if pr.valid:
        _cost_prim = pr.cost_per_unit / float(_fx.get(_prim["currency"], 1.0) or 1.0) if _prim else 0.0
        _cards = [
            _stat(
                money(_prim["price"], _prim["currency"]) if _prim else "–",
                f"{primary} price" if _prim else "Primary price",
                f"primary market · ×{_prim['multiplier']:.2f}" if _prim else "",
            ),
            _stat(
                money(_cost_prim, _prim["currency"]) if _prim else "–",
                "Assembly cost",
                f"{money(pr.cost_per_unit, base_ccy, 2)} fully loaded",
            ),
            _stat(
                money(_sec["price"], _sec["currency"]) if _sec else "–",
                f"{secondary} price" if _sec else "Secondary price",
                f"secondary market · ×{_sec['multiplier']:.2f}" if _sec else "",
            ),
            _stat(
                money(_dom["price"] * (1 + _vat), _domccy) if _dom else "–",
                f"{domestic} price incl. VAT" if _dom else "Domestic price",
                f"domestic market · ×{_dom['multiplier']:.2f}" if _dom else "",
            ),
            _stat(
                f"{pr.realised_margin:.1%}", "Realised margin", f"target {model.cfg['financials']['target_margin']:.0%}"
            ),
            _stat(f"{fmt(pr.net_revenue - ru.total)} {base_ccy}", "Operating profit", f"on {fmt(ru.batch)} units"),
        ]
    else:
        _cards = [
            _stat("–", "Price", "see the callout below"),
            _stat(f"{fmt(ru.total)} {base_ccy}", "Total cost", "batch"),
            _stat(f"{fmt(ru.cost_per_unit)} {base_ccy}", "Cost per unit", "fully loaded"),
            _stat(f"{fmt(pr.weighted_paying_units, 1)}", "Weighted paying units", "must be positive"),
        ]
    mo.vstack([mo.md("### Headline Numbers"), mo.hstack(_cards, widths="equal", wrap=True)])
    return


@app.cell(hide_code=True)
def _(base_ccy, fmt, mo, pr, ru):
    def _stat(value, label, caption=None):
        return mo.stat(value=value, label=label, caption=caption, bordered=True)

    if pr.valid:
        _cards = [
            _stat(f"{fmt(pr.net_revenue)} {base_ccy}", "Net revenue"),
            _stat(f"{fmt(ru.total)} {base_ccy}", "Total cost", "incl. safety factors"),
            _stat(f"{fmt(pr.net_revenue - ru.total)} {base_ccy}", "Operating profit"),
            _stat(f"{pr.realised_margin:.1%}", "Realised margin"),
            _stat(f"{fmt(pr.weighted_paying_units, 1)} / {fmt(ru.batch)}", "Weighted paying units"),
            _stat(f"{fmt(pr.absorbed_discounts)} {base_ccy}", "Absorbed cost", "forgone against full price"),
        ]
        _out = mo.vstack([mo.md("### Batch Economics"), mo.hstack(_cards, widths="equal", wrap=True)])
    else:
        _out = mo.md("")
    _out
    return


@app.cell(hide_code=True)
def _(fx_err, mo, model, pr, problems, ru):
    _w = []
    if not pr.valid:
        _w.append(mo.callout(mo.md(f"**{pr.error}**"), kind="danger", title="Unpriceable Composition"))
    if problems:
        _w.append(
            mo.callout(
                mo.md("\n".join(f"- {p}" for p in problems[:10]) + ("\n- …" if len(problems) > 10 else "")),
                kind="warn",
                title="Data Problems",
            )
        )
    if fx_err:
        _w.append(
            mo.callout(mo.md(f"FX sync failed ({fx_err}). Using the stored rates."), kind="warn", title="FX Sync")
        )
    if ru.missing:
        _names = ", ".join(model.items[i]["name"] for i in ru.missing)
        _w.append(
            mo.callout(
                mo.md(f"{_names}. These contribute zero cost – the rollup is a lower bound."),
                kind="warn",
                title="Quotes Pending",
            )
        )
    _fb = [i for i in ru.fallback if model.breaks.get(i) and model.breaks[i][0][1] > 0]
    if _fb:
        _w.append(
            mo.callout(
                mo.md(
                    f"{len(_fb)} leaves are priced at the lowest quoted break because the order quantity is below it."
                ),
                kind="info",
                title="Higher-Bracket Fallback",
            )
        )
    mo.vstack([mo.md("### Checks"), *_w]) if _w else None
    return


@app.cell(hide_code=True)
def _(
    APOSTROPHE_AXIS,
    PALETTE,
    alt,
    batch,
    chart_title,
    copy,
    domestic,
    eng,
    mo,
    model,
    pd,
    primary,
    root,
    rule_x,
    rule_y,
    store,
    style_chart,
):
    # Price against batch size, one line per margin around the current one.
    _factor, _pccy = store.primary_price_factor(model.cfg, primary, domestic)
    _zero = sum(model.cfg["batch"][k] for k in ("lost", "donations", "returns", "warranty", "reserved", "not_sold"))
    _floor = _zero + sum(t["units"] for t in model.cfg["discount_tiers"]) + 1
    _cur = model.cfg["financials"]["target_margin"]
    _ms = sorted({round(_cur + d, 4) for d in (-0.10, -0.05, 0, 0.05, 0.10) if 0.01 <= _cur + d <= 0.60})
    _order = [f"{x:.0%}" for x in _ms]

    def _price(n, mrg):
        _m2 = copy.deepcopy(model)
        _m2.cfg["batch"]["ordered"] = n
        _r = eng.rollup(_m2, root, n)
        _m2.cfg["financials"]["target_margin"] = mrg
        _pp = eng.derive_root_price(_m2, _r)
        return _pp.base_price * _factor if _pp.valid else None

    _ref = _price(batch, _cur)
    _rows = [
        {"batch": _n, "margin": f"{_mrg:.0%}", "price": _v}
        for _n in range(max(10, _floor), 201, 4)
        for _mrg in _ms
        if (_v := _price(_n, _mrg))
    ]
    _df = pd.DataFrame(_rows)
    _ref = _ref or (_df["price"].min() if len(_df) else 1) or 1
    _df["pct"] = _df["price"] / _ref * 100
    _df["price_text"] = _df["price"].map(lambda v: f"{v:,.0f}".replace(",", "'"))

    _base = alt.Chart(_df).encode(alt.X("batch:Q", title="Ordered assembly count"))
    _lines = _base.mark_line(point=True).encode(
        alt.Y(
            "pct:Q", scale=alt.Scale(domainMin=0), axis=alt.Axis(title="Share of the current price (%)", orient="left")
        ),
        alt.Color(
            "margin:N",
            title="Margin",
            scale=alt.Scale(domain=_order, range=PALETTE[: len(_order)]),
            sort=_order,
            legend=alt.Legend(orient="bottom"),
        ),
        tooltip=[
            alt.Tooltip("batch:Q", title="Batch"),
            alt.Tooltip("margin:N", title="Margin"),
            alt.Tooltip("price_text:N", title=f"Price ({_pccy})"),
        ],
    )
    _rax = _base.mark_line(opacity=0).encode(
        alt.Y(
            "pct:Q",
            scale=alt.Scale(domainMin=0),
            axis=alt.Axis(
                title=f"{primary} price ({_pccy})",
                orient="right",
                labelExpr=APOSTROPHE_AXIS.replace("datum.value", f"datum.value * {_ref} / 100"),
            ),
        ),
        alt.Detail("margin:N"),
    )
    _chart = alt.layer(_lines, _rax, rule_y(100), rule_x(batch)).properties(
        width="container",
        height=270,
        title=chart_title(
            "Price Against Batch Size",
            f"left axis: share of the current price; right axis: {primary} price in {_pccy}",
            "dashed lines mark the current batch and 100 %; margins are the selected value ±5 and ±10 points",
        ),
    )
    mo.ui.altair_chart(style_chart(_chart))
    return


@app.cell(hide_code=True)
def _(
    APOSTROPHE_AXIS,
    SEQUENTIAL,
    alt,
    chart_title,
    copy,
    domestic,
    eng,
    mo,
    model,
    pd,
    primary,
    root,
    store,
    style_chart,
):
    # Price landscape: batch × margin, coloured by the primary market's price.
    _factor, _pccy = store.primary_price_factor(model.cfg, primary, domestic)
    _zero = sum(model.cfg["batch"][k] for k in ("lost", "donations", "returns", "warranty", "reserved", "not_sold"))
    _floor = _zero + sum(t["units"] for t in model.cfg["discount_tiers"]) + 1
    _batches = [b for b in range(10, 201, 10) if b >= _floor][:14]
    _rows = []
    for _n in _batches:
        _m2 = copy.deepcopy(model)
        _m2.cfg["batch"]["ordered"] = _n
        _r = eng.rollup(_m2, root, _n)
        for _mp in range(10, 41, 5):
            _m2.cfg["financials"]["target_margin"] = _mp / 100
            _pp = eng.derive_root_price(_m2, _r)
            if _pp.valid:
                _p = round(_pp.base_price * _factor)
                _rows.append({"batch": _n, "margin": _mp, "price": _p, "price_text": f"{_p:,.0f}".replace(",", "'")})
    _heat = (
        alt.Chart(pd.DataFrame(_rows))
        .mark_rect()
        .encode(
            alt.X("batch:O", title="Ordered assembly count"),
            alt.Y("margin:O", title="Target margin (%)", sort="descending"),
            alt.Color(
                "price:Q",
                title=f"{_pccy} price",
                scale=alt.Scale(range=SEQUENTIAL),
                legend=alt.Legend(labelExpr=APOSTROPHE_AXIS),
            ),
            tooltip=[
                alt.Tooltip("batch:O", title="Batch"),
                alt.Tooltip("margin:O", title="Margin (%)"),
                alt.Tooltip("price_text:N", title=f"Price ({_pccy})"),
            ],
        )
        .properties(
            width="container",
            height=240,
            title=chart_title("Price Landscape", f"{primary} price in {_pccy}; light is cheaper, dark is dearer"),
        )
    )
    mo.ui.altair_chart(style_chart(_heat))
    return


@app.cell(hide_code=True)
def _(
    PALETTE_WIDE,
    alt,
    base_ccy,
    chart_title,
    costby_ui,
    fmt,
    mo,
    model,
    pd,
    ru,
    style_chart,
):
    # Cost breakdown of the batch's direct cost, in the base currency.
    _mode = costby_ui.value
    if _mode == "Cost type":
        _agg = {
            "Base materials": ru.base,
            "Supplier shipping": ru.shipping,
            "Bank and fees": ru.bank,
            "Import duties": ru.duties,
            "Consumables": ru.consumables,
            "Labour": ru.labour,
        }
    else:
        _agg = {}
        for _l in ru.leaves:
            _k = (_l.vendor or "–") if _mode == "Vendor" else (model.items[_l.item_id].get("subcategory") or "–")
            _agg[_k] = _agg.get(_k, 0.0) + _l.landed
        _agg["Labour and consumables"] = ru.labour + ru.consumables
    _tot = sum(_agg.values()) or 1
    _df = pd.DataFrame(
        [
            {"group": k, "amount": round(v, 2), "share": v / _tot * 100, "amount_text": fmt(v, 2)}
            for k, v in sorted(_agg.items(), key=lambda x: -x[1])
            if v
        ]
    )
    _palette = (PALETTE_WIDE * ((len(_df) // len(PALETTE_WIDE)) + 1))[: max(len(_df), 1)]
    _donut = (
        alt.Chart(_df)
        .mark_arc(innerRadius=62, strokeWidth=0)
        .encode(
            theta=alt.Theta("amount:Q", stack=True),
            color=alt.Color(
                "group:N",
                title=None,
                scale=alt.Scale(range=_palette),
                sort=alt.SortField("amount", "descending"),
                legend=alt.Legend(orient="bottom", columns=3),
            ),
            tooltip=[
                alt.Tooltip("group:N", title="Group"),
                alt.Tooltip("amount_text:N", title=base_ccy),
                alt.Tooltip("share:Q", format=".1f", title="%"),
            ],
        )
        .properties(
            width="container",
            height=270,
            title=chart_title(
                "Cost Breakdown",
                f"direct cost of the batch: {fmt(_tot)} {base_ccy}, before the expense and overhead safety factors",
            ),
        )
    )
    mo.vstack([costby_ui, mo.ui.altair_chart(style_chart(_donut))])
    return


@app.cell(hide_code=True)
def _(domestic, mo, money, pd, regions):
    if regions:
        _df = pd.DataFrame(
            [
                {
                    "Market": r["region"],
                    "Multiplier": f"×{r['multiplier']:.2f}",
                    "Currency": r["currency"],
                    "Calculated price": money(r["price_multiplier"], r["currency"]),
                    "Adjustment": (f"{r['adjust']:+,.0f}".replace(",", "'") if r["adjust"] else "–"),
                    "Final price": money(r["price"], r["currency"]),
                }
                for r in regions
            ]
        )
        _out = mo.vstack(
            [
                mo.md(
                    f"### Regional Prices <span class='bac-sub'>· domestic anchor {domestic} · adjust in Settings</span>"
                ),
                mo.ui.table(_df, selection=None),
            ]
        )
    else:
        _out = mo.md("")
    _out
    return


@app.cell(hide_code=True)
def _(base_ccy, fmt, mo, pd, plist):
    _df = pd.DataFrame(plist)[
        ["sku", "name", "type", "cost", "overridden", "price", "quotes_missing", "quotes_fallback"]
    ].copy()
    _df["cost"] = _df["cost"].map(lambda v: fmt(v, 2))
    _df["price"] = _df["price"].map(lambda v: fmt(v, 2))
    _df = _df.rename(columns={"cost": f"cost ({base_ccy})", "price": f"price ({base_ccy})"})
    mo.vstack(
        [
            mo.md("### Price List"),
            mo.md(
                "<span class='bac-sub'>Every item marked sellable. Assemblies are priced through the batch "
                "waterfall (cost recovered across the whole order); individual sellable parts take a simple "
                "margin on their rolled-up cost. Cost and price are in the base currency – the regional "
                "table has each market's price.</span>"
            ),
            mo.ui.table(_df, selection=None),
        ]
    )
    return


@app.cell(hide_code=True)
def _(bom_ov_editor, bom_struct_editor, bom_view_ui, mo):
    _editor = bom_struct_editor if bom_view_ui.value == "Structure" else bom_ov_editor
    mo.vstack(
        [
            mo.md("### Bill of Materials"),
            bom_view_ui,
            mo.md(
                "<span class='bac-sub'>Both views persist with Save data. Rows without a parent are "
                "assemblies themselves.</span>"
            ),
            _editor,
        ]
    )
    return


@app.cell(hide_code=True)
def _(breaks_editor, mo):
    mo.vstack(
        [
            mo.md("### Price Breaks"),
            mo.md(
                "<span class='bac-sub'>Per-item quantity quotes in the vendor's currency. For an order, the "
                "largest min_qty at or below the ordered quantity wins; below the smallest break the lowest "
                "is used and the item is flagged as a fallback. The item column is a label – item_id is what "
                "binds. Persists with Save data.</span>"
            ),
            breaks_editor,
        ]
    )
    return


@app.cell(hide_code=True)
def _(TOOL_VERSION, mo):
    mo.md(f"""
    ### Revision History

    BAC Pricing {TOOL_VERSION}. The full history is in the tool's README.

    | Version | Date | Change |
    | :-- | :-- | :-- |
    | 1.4.0 | 2026-10-07 | Joins bac-utils on bac-common and bac-suite-db: settings from the suite config, one control panel, labels on every input, stat cards, the shared style and chart conventions, data checks as a callout, files-mode save and the base-currency switch moved into the store. |
    | 1.3.0 | 2026-07-06 | Database-first storage: Postgres tables, versioned parameters, the suite shell. |
    | 1.2.0 | 2026-06-26 | Editable price breaks; dynamic currency symbols; frankfurter currency list. |
    | 1.1.0 | 2026-06-26 | Base-currency switch from within the tool; TangleSliders for the batch composition. |
    | 1.0.0 | 2026-06-18 | Currency-agnostic: the base currency is the single anchor. |
    """)
    return


if __name__ == "__main__":
    app.run()
