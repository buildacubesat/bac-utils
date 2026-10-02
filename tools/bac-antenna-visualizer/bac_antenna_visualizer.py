# SPDX-License-Identifier: MIT
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo>=0.14",
#     "numpy>=2.0",
#     "scipy>=1.11",
#     "pandas>=2.0",
#     "altair>=5.0",
#     "plotly>=5.20",
#     "pyarrow>=15.0",
#     "bac-antenna-optimizer",
# ]
#
# [tool.uv.sources]
# bac-antenna-optimizer = { path = "../bac-antenna-optimizer", editable = true }
# ///

import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium", auto_download=["html"])


@app.cell
def _(mo):
    mo.vstack(
        [
            mo.md("""
    # BAC Antenna Visualizer

    See how an antenna's behavior moves when its geometry moves. Pick a pack – a set
    of simulated cases of one antenna, each with a single dimension changed from the
    nominal design – and drive the sliders. The 3D geometry follows live; the numbers,
    S-parameters, gain, axial ratio, pattern and fields follow along the axis you moved,
    interpolated between the two nearest simulated cases.

    Compare the sensitivity table – per millimeter of each dimension, what happens to
    the resonance, the gain, the polarization purity and the power the feed wastes –
    with the tolerances you can hold when the boards are made and stacked. That is the
    question every antenna design has to answer before anyone orders copper.

    The packs come from [bac-antenna-optimizer](https://github.com/buildacubesat/bac-utils/tree/main/tools/bac-antenna-optimizer),
    which drives the open-source field solver [openEMS](https://openems.de). The first
    packs are the Build a CubeSat S-band camera-through patch in its two bands; any
    antenna the optimizer models can be packed the same way. The notebook finds packs
    in an antenna folder of a bac-hardware checkout next to bac-utils, in its own
    `packs/` folder, or from a path, a URL or an upload under Other Packs.

    This tool runs locally from [bac-utils](https://github.com/buildacubesat/bac-utils)
    (`tools/bac-antenna-visualizer`); its siblings are the [Link Budget](https://bac.page/link-budget-tool),
    [Optical Payload](https://bac.page/optical-payload-tool),
    [Power Budget](https://bac.page/power-budget-tool) and
    [Orbital Lifetime](https://bac.page/orbital-lifetime-tool) tools. All of them
    belong to the [Build a CubeSat](https://buildacubesat.space) project.
    """),
            mo.callout(
                mo.md(
                    "Every simulated case is a full FDTD run, but everything between two cases is a "
                    "straight-line interpolation along one axis, and several sliders at once give a "
                    "first-order estimate. Nothing here has been measured; the pack's notes say at what "
                    "fidelity it was simulated."
                ),
                kind="warn",
                title="Planning Estimates Only",
            ),
        ]
    )
    return


@app.cell
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
    </style>
    """)
    return


@app.cell
def _():
    import datetime as dt
    import gzip
    import io
    import json
    import os
    import zipfile
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go

    return Path, alt, dt, go, gzip, io, json, mo, np, os, pd, zipfile


@app.cell
def _(Path, mo, os):
    # Constants: where packs are looked for, what a pack contains, and the glossary.

    TOOL_VERSION = "0.3.1"
    PACK_FILES = (
        "pack.json",
        "cases.csv.gz",
        "sweeps.csv.gz",
        "samples.csv.gz",
        "cuts.csv.gz",
        "sphere.csv.gz",
        "efield.csv.gz",
        "models.json",
        "config.toml",
        "design.json",
    )
    try:
        _here = Path(str(mo.notebook_location())).resolve()
    except Exception:
        _here = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
    HERE = _here
    # Search roots for packs, in order: BAC_ANTENNA_PACKS (colon-separated folders, each
    # a pack, a folder of packs or an antenna folder), the notebook's own packs/ folder
    # (gitignored; drop release zips there), and the antenna folders of a bac-hardware
    # checkout next to bac-utils.
    SEARCH_ROOTS = [Path(_x).expanduser() for _x in os.environ.get("BAC_ANTENNA_PACKS", "").split(":") if _x]
    SEARCH_ROOTS += [HERE / "packs"]
    _repo = HERE.parent.parent  # bac-utils/
    SEARCH_ROOTS += (
        sorted((_repo.parent / "bac-hardware" / "rf" / "antenna").glob("*"))
        if (_repo.parent / "bac-hardware").exists()
        else []
    )

    GLOSSARY = "https://cubesat-resources.space/references/glossary/#"

    def gl(text, slug):
        return f"[{text}]({GLOSSARY}{slug})"

    return GLOSSARY, HERE, PACK_FILES, SEARCH_ROOTS, TOOL_VERSION, gl


@app.cell
def _(PACK_FILES, Path, gzip, io, json, pd, zipfile):
    # Pack readers. A pack is the folder `bac-antenna pack` writes, or the zip of it
    # (`pack --zip`, the form attached to an antenna's release). Either arrives here
    # as a dict of file name -> bytes, from a local path, a URL or an upload.

    def _is_url(x):
        return str(x).startswith(("http://", "https://"))

    def read_zip(data):
        _out = {}
        with zipfile.ZipFile(io.BytesIO(data)) as _z:
            for _info in _z.infolist():
                _name = _info.filename.split("/")[-1]
                if _name in PACK_FILES:
                    _out[_name] = _z.read(_info)
        return _out

    def read_folder(folder):
        _f = Path(folder)
        return {_n: (_f / _n).read_bytes() for _n in PACK_FILES if (_f / _n).exists()}

    def read_location(location):
        """Bytes of a pack from a folder, a zip file, a folder URL or a zip URL."""
        location = str(location).strip()
        if not location:
            return {}
        if _is_url(location):
            import urllib.request

            if location.lower().endswith(".zip"):
                with urllib.request.urlopen(location, timeout=60) as _r:
                    return read_zip(_r.read())
            _out = {}
            for _n in PACK_FILES:
                try:
                    with urllib.request.urlopen(f"{location.rstrip('/')}/{_n}", timeout=30) as _r:
                        _out[_n] = _r.read()
                except Exception:
                    if _n == "pack.json":
                        return {}
            return _out
        _p = Path(location).expanduser()
        if _p.is_file() and _p.suffix.lower() == ".zip":
            return read_zip(_p.read_bytes())
        if _p.is_dir():
            return read_folder(_p)
        return {}

    def parse_pack(blobs):
        _meta = json.loads(blobs["pack.json"])

        def _frame(name):
            _raw = blobs.get(name)
            if not _raw:
                return pd.DataFrame()
            with gzip.open(io.BytesIO(_raw), "rt") as _fh:
                return pd.read_csv(_fh)

        return {
            "meta": _meta,
            "cases": _frame("cases.csv.gz"),
            "sweeps": _frame("sweeps.csv.gz"),
            "samples": _frame("samples.csv.gz"),
            "cuts": _frame("cuts.csv.gz"),
            "sphere": _frame("sphere.csv.gz"),
            "efield": _frame("efield.csv.gz"),
            "models": json.loads(blobs["models.json"]) if blobs.get("models.json") else {},
            "config_text": blobs.get("config.toml", b"").decode(),
            "design": json.loads(blobs["design.json"]) if blobs.get("design.json") else {},
        }

    def pack_name_of(location):
        """The name in pack.json without reading the whole pack; None when it is not a pack."""
        try:
            _p = Path(location)
            if _p.is_dir() and (_p / "pack.json").exists():
                return json.loads((_p / "pack.json").read_text()).get("name")
            if _p.is_file() and _p.suffix.lower() == ".zip":
                with zipfile.ZipFile(_p) as _z:
                    for _info in _z.infolist():
                        if _info.filename.split("/")[-1] == "pack.json":
                            return json.loads(_z.read(_info)).get("name")
        except Exception:
            return None
        return None

    return pack_name_of, parse_pack, read_location, read_zip


@app.cell
def _(SEARCH_ROOTS, pack_name_of):
    # Discovery: every pack folder or pack zip under the search roots, one level deep
    # plus an antenna folder's generated/sensitivity*. First hit per name wins.
    FOUND = {}  # name -> location (Path)

    def _consider(loc):
        _name = pack_name_of(loc)
        if _name and _name not in FOUND:
            FOUND[_name] = loc

    for _root in SEARCH_ROOTS:
        if not _root.exists():
            continue
        _consider(_root)
        _candidates = (
            sorted(_root.glob("*"))
            + sorted(_root.glob("generated/sensitivity*"))
            + sorted(_root.glob("generated/*-pack.zip"))
        )
        for _c in _candidates:
            _consider(_c)
    return (FOUND,)


@app.cell
def _(FOUND, mo):
    # Pack loader elements. Separate from the parse cell because a cell cannot read a
    # UI element it defines.
    _names = list(FOUND) or [
        "(no pack found)"
    ]  # discovery order: BAC_ANTENNA_PACKS first, then packs/, then the checkout
    ui_pack = mo.ui.dropdown(options=_names, value=_names[0], label="Pack")
    ui_pack_path = mo.ui.text(value="", label="Path or URL of a pack folder or pack zip (optional)", full_width=True)
    ui_pack_upload = mo.ui.file(filetypes=[".zip"], kind="button", label="Load a pack (.zip)")
    return ui_pack, ui_pack_path, ui_pack_upload


@app.cell
def _(FOUND, SEARCH_ROOTS, mo, parse_pack, read_location, read_zip, ui_pack, ui_pack_path, ui_pack_upload):
    # Parse the chosen pack. An upload wins over a typed path or URL, and that over the
    # dropdown of discovered packs.
    _blobs = {}
    if ui_pack_upload.value:
        _blobs = read_zip(ui_pack_upload.value[0].contents)
        pack_source = f"uploaded {ui_pack_upload.value[0].name}"
    elif ui_pack_path.value.strip():
        _blobs = read_location(ui_pack_path.value)
        pack_source = ui_pack_path.value.strip()
    elif ui_pack.value in FOUND:
        _blobs = read_location(FOUND[ui_pack.value])
        pack_source = str(FOUND[ui_pack.value])
    else:
        pack_source = "nothing selected"
    PACK = parse_pack(_blobs) if "pack.json" in _blobs else None
    mo.stop(
        PACK is None,
        mo.callout(
            mo.md(
                f"No pack loaded ({pack_source}). A pack is the folder `bac-antenna pack` writes – pack.json, "
                "cases.csv.gz and the rest – or its zip. Looked in: "
                + ", ".join(f"`{_r}`" for _r in SEARCH_ROOTS)
                + ". Set `BAC_ANTENNA_PACKS`, drop a zip into "
                "the notebook's `packs/` folder, or give a path, URL or upload under Other Packs."
            ),
            kind="danger",
            title="No Pack Loaded",
        ),
    )
    return PACK, pack_source


@app.cell
def _(PACK, mo, pack_source, ui_pack, ui_pack_path, ui_pack_upload):
    # Loader status: what is loaded, from where, what it contains, what is missing.
    _m = PACK["meta"]
    _missing = [(a["id"], a["missing"]) for a in _m["axes"] if a["missing"]]
    _tool = _m.get("tool", "bac-antenna-optimizer") + (f" {_m['tool_version']}" if _m.get("tool_version") else "")
    _lines = [
        f"**{_m['name']}** – antenna type `{_m['antenna_type']}`, {len(_m['cases'])} simulated cases on "
        f"{len(_m['axes'])} axes, packed {_m['generated']} with {_tool}. Loaded from `{pack_source}`."
    ]
    if _m.get("source") or _m.get("release"):
        _lines.append("Source: " + " – ".join(_x for _x in (_m.get("source", ""), _m.get("release", "")) if _x) + ".")
    if _m.get("notes"):
        _lines.append(" ".join(_m["notes"]))
    if _missing:
        _lines.append(
            "Levels without a simulated case, where the slider interpolates over the gap: "
            + "; ".join(f"{_a}: {', '.join(f'{_x:g}' for _x in _miss)}" for _a, _miss in _missing)
            + "."
        )
    pack_block = mo.vstack(
        [
            mo.md("\n\n".join(_lines)),
            mo.accordion({"Other Packs": mo.vstack([ui_pack, ui_pack_path, ui_pack_upload])}),
        ]
    )
    return (pack_block,)


@app.cell
def _(PACK, mo):
    # Control panel – the only place inputs live. One slider per axis of the pack,
    # clamped into the axis' range, starting at the nominal design.
    def S(**kw):
        kw["value"] = min(max(float(kw["value"]), kw["start"]), kw["stop"])
        if float(kw["step"]).is_integer():
            kw["value"] = int(round(kw["value"]))
        return mo.ui.slider(**kw)

    AXES = PACK["meta"]["axes"]
    _sliders = {}
    for _a in AXES:
        _levels = sorted(float(_x["level"]) for _x in _a["levels"])
        _step = min(_b - _c for _c, _b in zip(_levels, _levels[1:], strict=False)) / 5 if len(_levels) > 1 else 0.1
        _sliders[_a["id"]] = S(
            start=_levels[0],
            stop=_levels[-1],
            step=round(_step, 4),
            value=float(_a["nominal"]),
            show_value=True,
            include_input=True,
            label=f"{_a['label']} ({_a['unit']})" if _a.get("unit") else _a["label"],
        )
    ui_axes = mo.ui.dictionary(_sliders)
    _bands = [_b["name"] for _b in PACK["meta"]["bands"]]
    ui_band = mo.ui.dropdown(options=_bands, value=PACK["meta"]["primary_band"], label="Band for the numbers")
    ui_freq = mo.ui.dropdown(options=["low", "centre", "high"], value="centre", label="Pattern frequency in the band")
    ui_planes = mo.ui.multiselect(options=["0", "45", "90", "135"], value=["0", "90"], label="Cut planes (phi, deg)")
    ui_show_geometry = mo.ui.switch(value=True, label="3D geometry")
    ui_show_pattern = mo.ui.switch(value=True, label="3D pattern")
    ui_show_efield = mo.ui.switch(value=True, label="3D electric field")
    ui_sidebar = mo.ui.switch(value=False, label="Controls in a sidebar")
    return AXES, ui_axes, ui_band, ui_freq, ui_planes, ui_show_efield, ui_show_geometry, ui_show_pattern, ui_sidebar


@app.cell
def _(mo, ui_axes, ui_band, ui_freq, ui_planes, ui_show_efield, ui_show_geometry, ui_show_pattern):
    # Two columns: the geometry you move on the left, how to look at it on the right.
    _left = [
        mo.md("**Geometry**"),
        ui_axes,
        mo.md("Sliders start at the nominal design. The axis moved furthest from nominal drives the charts."),
    ]
    _right = [
        mo.md("**View**"),
        ui_band,
        ui_freq,
        ui_planes,
        ui_show_geometry,
        ui_show_pattern,
        ui_show_efield,
    ]
    knobs_wide = mo.hstack(
        [mo.vstack(_left, gap=0.5), mo.vstack(_right, gap=0.5)], justify="start", gap=2, wrap=True, widths="equal"
    )
    knobs_tall = mo.vstack(_left + _right, gap=0.5)
    return knobs_tall, knobs_wide


@app.cell
def _(knobs_tall, mo, ui_sidebar):
    # mo.sidebar has to be the last expression of its own cell.
    mo.sidebar([mo.md("### Control Panel"), knobs_tall], width="360px") if ui_sidebar.value else None
    return


@app.cell
def _(knobs_wide, mo, pack_block, ui_sidebar):
    mo.vstack(
        [
            mo.md("## Control Panel"),
            pack_block,
            ui_sidebar,
            mo.md("The knobs are in the sidebar. Turn this off to bring them back here.")
            if ui_sidebar.value
            else knobs_wide,
        ]
    )
    return


@app.cell
def _(AXES, PACK, ui_axes, ui_band, ui_freq, ui_planes):
    # Resolve: slider values, how far each axis sits from nominal, which one drives the
    # charts, and which band and frequency the numbers refer to.
    VALUES = {_a["id"]: float(ui_axes.value[_a["id"]]) for _a in AXES}
    _dev = {}
    for _a in AXES:
        _levels = sorted(float(_x["level"]) for _x in _a["levels"])
        _span = (_levels[-1] - _levels[0]) or 1.0
        _dev[_a["id"]] = (VALUES[_a["id"]] - float(_a["nominal"])) / _span
    MOVED = [_k for _k, _v in _dev.items() if abs(_v) > 1e-9]
    ACTIVE = max(_dev, key=lambda _k: abs(_dev[_k])) if MOVED else None
    MODE = "nominal" if not MOVED else ("axis" if len(MOVED) == 1 else "estimate")
    BAND = next(_b for _b in PACK["meta"]["bands"] if _b["name"] == ui_band.value)
    F_PICK = {"low": BAND["low_hz"], "centre": (BAND["low_hz"] + BAND["high_hz"]) / 2, "high": BAND["high_hz"]}[
        ui_freq.value
    ]
    PLANES = [float(_p) for _p in ui_planes.value] or [0.0]
    AXIS_LABEL = {_a["id"]: _a["label"] for _a in AXES}
    AXIS_UNIT = {_a["id"]: _a.get("unit", "") for _a in AXES}
    return ACTIVE, AXIS_LABEL, AXIS_UNIT, BAND, F_PICK, MODE, MOVED, PLANES, VALUES


@app.cell
def _(AXES, PACK, pd):
    # Interpolation along one axis: the two simulated cases bracketing the slider value
    # and their weights. Tables without rows for a bracketing case fall back to the
    # nearest case that has them, and say so.
    CASES = PACK["cases"].set_index("case")
    NOMINAL = PACK["meta"]["nominal_case"]
    NUMERIC = [
        _c
        for _c in CASES.columns
        if _c not in ("axis", "run", "files")
        and not _c.startswith("axis:")
        and pd.api.types.is_numeric_dtype(CASES[_c])
    ]

    def axis_cases(axis_id):
        _a = next(_x for _x in AXES if _x["id"] == axis_id)
        return sorted((float(_x["level"]), _x["case"]) for _x in _a["levels"] if _x["case"])

    def bracket(axis_id, value):
        _pts = axis_cases(axis_id)
        if not _pts:
            return NOMINAL, NOMINAL, 0.0
        if value <= _pts[0][0]:
            return _pts[0][1], _pts[0][1], 0.0
        if value >= _pts[-1][0]:
            return _pts[-1][1], _pts[-1][1], 0.0
        for (_l0, _c0), (_l1, _c1) in zip(_pts, _pts[1:], strict=False):
            if _l0 <= value <= _l1:
                return _c0, _c1, (value - _l0) / (_l1 - _l0) if _l1 > _l0 else 0.0
        return _pts[-1][1], _pts[-1][1], 0.0

    def scalars_at(axis_id, value):
        _c0, _c1, _w = bracket(axis_id, value)
        _a, _b = CASES.loc[_c0, NUMERIC].astype(float), CASES.loc[_c1, NUMERIC].astype(float)
        return ((1 - _w) * _a + _w * _b).to_dict()

    def nominal_scalars():
        return CASES.loc[NOMINAL, NUMERIC].astype(float).to_dict()

    def blend_table(table, keys, axis_id, value):
        if len(table) == 0:
            return pd.DataFrame(), "no data in this pack"
        _c0, _c1, _w = bracket(axis_id, value)
        _have = set(table["case"].unique())
        if _c0 not in _have or _c1 not in _have:
            _near = (
                _c0
                if (_w < 0.5 and _c0 in _have)
                else (_c1 if _c1 in _have else (NOMINAL if NOMINAL in _have else None))
            )
            if _near is None:
                return pd.DataFrame(), "no data in this pack"
            return table[table["case"] == _near].drop(columns=["case"]).reset_index(
                drop=True
            ), f"nearest simulated case with this data: {_near}"
        _t0 = table[table["case"] == _c0].drop(columns=["case"]).set_index(keys)
        _t1 = table[table["case"] == _c1].drop(columns=["case"]).set_index(keys)
        _cols = [_c for _c in _t0.columns if pd.api.types.is_numeric_dtype(_t0[_c])]
        _common = _t0.index.intersection(_t1.index)
        _out = (1 - _w) * _t0.loc[_common, _cols] + _w * _t1.loc[_common, _cols]
        return _out.reset_index(), ""

    def table_for(table, keys, mode, active, values):
        # The table at the current slider position: nominal, blended, or nearest.
        if mode == "nominal" or active is None:
            if len(table) == 0 or NOMINAL not in set(table["case"].unique()):
                return pd.DataFrame(), "no data in this pack"
            return table[table["case"] == NOMINAL].drop(columns=["case"]).reset_index(drop=True), ""
        return blend_table(table, keys, active, values[active])

    return CASES, NOMINAL, NUMERIC, axis_cases, blend_table, bracket, nominal_scalars, scalars_at, table_for


@app.cell
def _(ACTIVE, MODE, MOVED, VALUES, nominal_scalars, scalars_at):
    # The numbers at the current position: exact interpolation on one axis, a
    # first-order sum of single-axis changes on several.
    if MODE == "nominal":
        NUMBERS = nominal_scalars()
    elif MODE == "axis":
        NUMBERS = scalars_at(ACTIVE, VALUES[ACTIVE])
    else:
        _base = nominal_scalars()
        NUMBERS = dict(_base)
        for _k in MOVED:
            _delta = scalars_at(_k, VALUES[_k])
            for _key in NUMBERS:
                NUMBERS[_key] = NUMBERS[_key] + (_delta[_key] - _base[_key])
    return (NUMBERS,)


@app.cell
def _(AXES, BAND, CASES, axis_cases, np, pd):
    # Sensitivity: the slope of each quantity along each axis, a straight line through
    # that axis' simulated cases, per unit of the axis.
    _b = BAND["name"]
    _quantities = [
        ("probe_res_hz", "Resonance (MHz)", 1e-6),
        ("load_fraction", "Feed-network load (%)", 100.0),
        (f"{_b}_gain_min_dbic", "Gain, band minimum (dBic)", 1.0),
        (f"{_b}_ar_worst_db", "Axial ratio, band maximum (dB)", 1.0),
        ("gain_co_min_60", "Gain at 60° (dBic)", 1.0),
        (f"{_b}_efficiency_percent", "Efficiency (%)", 1.0),
    ]
    _rows = []
    for _a in AXES:
        _pts = axis_cases(_a["id"])
        if len(_pts) < 2:
            continue
        _x = np.array([_p[0] for _p in _pts])
        for _col, _label, _scale in _quantities:
            if _col not in CASES.columns:
                continue
            _y = CASES.loc[[_p[1] for _p in _pts], _col].astype(float).to_numpy() * _scale
            if np.all(np.isfinite(_y)) and len(_y) >= 2:
                _slope, _icpt = np.polyfit(_x, _y, 1)
                _resid = float(np.max(np.abs(_y - (_slope * _x + _icpt)))) if len(_y) > 2 else 0.0
                _rows.append(
                    {
                        "Axis": _a["label"],
                        "Quantity": _label,
                        "Per unit": f"per {_a.get('unit', 'unit')}",
                        "Slope": _slope,
                        "Worst deviation from a line": _resid,
                        "Cases": len(_y),
                    }
                )
    SENS = pd.DataFrame(
        _rows, columns=["Axis", "Quantity", "Per unit", "Slope", "Worst deviation from a line", "Cases"]
    )
    return (SENS,)


@app.cell
def _(alt, mo):
    # Chart conventions from the Interface Design Guide §8: series in the nebula
    # order, shape markers so color is never the only channel, dashed for targets,
    # dotted for reference lines. On a dark surface the two dark series use lighter
    # derived tints to keep 3:1 graphical contrast.

    IS_DARK = mo.app_meta().theme == "dark"
    MUTED = "#888884"
    TEXT = "#efefed" if IS_DARK else "#3F3F3F"
    FONT = "IBM Plex Mono, ui-monospace, monospace"
    PALETTE = (
        ["#087C9B", "#625DC6", "#C88732", "#6F6497", "#84C45A"]
        if IS_DARK
        else ["#087C9B", "#3B35B8", "#C88732", "#21105F", "#84C45A"]
    )
    _BASE = PALETTE
    _SHAPES = ["circle", "square", "triangle-up", "diamond", "cross"]

    def _tint(hexs, t):
        _r, _g, _b = (int(hexs[_i : _i + 2], 16) for _i in (1, 3, 5))
        return "#{:02X}{:02X}{:02X}".format(*(round(_c + (255 - _c) * t) for _c in (_r, _g, _b)))

    def series_style(order):
        _cols, _shp = [], []
        for _i in range(len(order)):
            _cols.append(_tint(_BASE[_i % len(_BASE)], 0.28 * (_i // len(_BASE))))
            _shp.append(_SHAPES[_i % len(_SHAPES)])
        return _cols, _shp

    def rule_y(value, dashed):
        return (
            alt.Chart(alt.Data(values=[{"y": value}]))
            .mark_rule(strokeDash=[6, 4] if dashed else [2, 2], color=MUTED)
            .encode(y="y:Q")
        )

    def rule_x(value):
        return alt.Chart(alt.Data(values=[{"x": value}])).mark_rule(strokeDash=[2, 2], color=MUTED).encode(x="x:Q")

    def rule_label(x, y, text):
        return (
            alt.Chart(alt.Data(values=[{"x": x, "y": y, "label": text}]))
            .mark_text(align="right", dx=-2, dy=-7, color=MUTED, font=FONT, fontSize=11)
            .encode(x="x:Q", y="y:Q", text="label:N")
        )

    def style_chart(chart):
        return (
            chart.configure(font=FONT, background="transparent")
            .configure_axis(grid=False, labelColor=TEXT, titleColor=TEXT, domainColor=MUTED, tickColor=MUTED)
            .configure_legend(labelColor=TEXT, titleColor=TEXT)
            .configure_title(color=TEXT, anchor="start", fontWeight="normal")
            .configure_view(strokeWidth=0)
        )

    def plotly_layout(fig, title, height=520):
        fig.update_layout(
            title=title,
            height=height,
            margin={"l": 0, "r": 0, "t": 40, "b": 0},
            paper_bgcolor="rgba(0,0,0,0)",
            font={"family": FONT, "color": TEXT},
            scene={
                "aspectmode": "data",
                "xaxis": {"title": "x (mm)", "color": TEXT},
                "yaxis": {"title": "y (mm)", "color": TEXT},
                "zaxis": {"title": "z (mm)", "color": TEXT},
            },
        )
        return fig

    # The band as a light BAC-yellow strip behind the curves: the yellow blended into
    # the surface color, as a solid fill so it renders the same everywhere. Yellow is
    # too pale for a line on the light surface, and fine as a fill.
    def band_strip(lo, hi):
        return (
            alt.Chart(alt.Data(values=[{"x0": lo, "x1": hi}]))
            .mark_rect(color="#3E3718" if IS_DARK else "#F1E7AB")
            .encode(
                x=alt.X("x0:Q", scale=alt.Scale(zero=False)), x2="x1:Q"
            )  # a rect's axis would include zero by default
        )

    return (
        FONT,
        IS_DARK,
        MUTED,
        PALETTE,
        TEXT,
        band_strip,
        plotly_layout,
        rule_label,
        rule_x,
        rule_y,
        series_style,
        style_chart,
    )


@app.cell
def _(ACTIVE, AXIS_LABEL, AXIS_UNIT, BAND, MODE, MOVED, NUMBERS, VALUES, gl, mo):
    # Headline cards. Gray, no direction coloring: the callouts below do the judging.
    def _stat(value, label, caption):
        return mo.stat(value=value, label=label, caption=caption, bordered=True)

    def _num(key):
        _v = NUMBERS.get(key)
        return None if _v is None or _v != _v else float(_v)

    _b = BAND["name"]
    _res = _num("probe_res_hz") or _num("resonance_hz")
    _g = _num(f"{_b}_gain_min_dbic")
    _ar = _num(f"{_b}_ar_worst_db")
    _load = _num("load_fraction")
    _g60 = _num("gain_co_min_60")
    _eff = _num(f"{_b}_efficiency_percent")
    _s11 = _num(f"{_b}_s11_worst_db")
    _fb = _num("front_to_back_db")

    if MODE == "nominal":
        _how = "These are the nominal simulated case."
    elif MODE == "axis":
        _how = f"These are interpolated along the {AXIS_LABEL[ACTIVE]} axis at {VALUES[ACTIVE]:g} {AXIS_UNIT[ACTIVE]}."
    else:
        _how = (
            "These add the single-axis effects of "
            + ", ".join(f"{AXIS_LABEL[_k]} {VALUES[_k]:g} {AXIS_UNIT[_k]}" for _k in MOVED)
            + " – an estimate, see the callout below."
        )

    mo.vstack(
        [
            mo.md(f"## Headline Numbers · {BAND['name']} band"),
            mo.md(
                _how
                + " "
                + gl("Resonance", "resonance")
                + " is where the probe sees the patch's own frequency; "
                + gl("realized gain", "realized-gain")
                + " is in the wanted circular hand and already includes every loss; "
                + gl("axial ratio", "axial-ratio")
                + " says how circular the polarization is (0 dB is perfect, 3 dB is the usual limit); "
                "the feed-network load is the power the two probes reflect into the hybrid's termination instead of radiating it."
            ),
            mo.hstack(
                [
                    _stat(
                        "–" if _res is None else f"{_res / 1e9:.4f} GHz",
                        "Resonance",
                        f"band {BAND['low_hz'] / 1e6:.0f}–{BAND['high_hz'] / 1e6:.0f} MHz",
                    ),
                    _stat(
                        "–" if _g is None else f"{_g:.2f} dBic",
                        "Gain, Band Minimum",
                        "–" if _g60 is None else f"{_g60:.1f} dBic at 60° off boresight",
                    ),
                    _stat("–" if _ar is None else f"{_ar:.2f} dB", "Axial Ratio, Band Maximum", "0 dB is circular"),
                ],
                widths="equal",
            ),
            mo.hstack(
                [
                    _stat(
                        "–" if _load is None else f"{100 * _load:.1f} %",
                        "Feed-Network Load",
                        "power the probes reflect",
                    ),
                    _stat("–" if _eff is None else f"{_eff:.1f} %", "Efficiency", "radiated over accepted power"),
                    _stat(
                        "–" if _s11 is None else f"{_s11:.1f} dB",
                        "Input S11, Band Worst",
                        "–" if _fb is None else f"front-to-back {_fb:.1f} dB",
                    ),
                ],
                widths="equal",
            ),
        ]
    )
    return


@app.cell
def _(AXIS_LABEL, BAND, MODE, MOVED, NUMBERS, mo):
    # Model callouts: the band targets from the pack's config, and the estimate warning.
    _b = BAND["name"]

    def _num(key):
        _v = NUMBERS.get(key)
        return None if _v is None or _v != _v else float(_v)

    _s11, _g, _ar = _num(f"{_b}_s11_worst_db"), _num(f"{_b}_gain_min_dbic"), _num(f"{_b}_ar_worst_db")
    _fails = []
    if _s11 is not None and _s11 > BAND["max_s11_db"]:
        _fails.append(f"input S11 {_s11:.1f} dB, above the {BAND['max_s11_db']:.0f} dB limit")
    if _g is not None and _g < BAND["min_gain_dbic"]:
        _fails.append(f"gain {_g:.2f} dBic, below the {BAND['min_gain_dbic']:.1f} dBic target")
    if _ar is not None and _ar > BAND["max_ar_db"]:
        _fails.append(f"axial ratio {_ar:.2f} dB, above the {BAND['max_ar_db']:.1f} dB limit")
    _out = [
        mo.callout(
            mo.md("Below the pack's targets: " + "; ".join(_fails) + "."),
            kind="warn",
            title=f"{_b} Band Misses a Target",
        )
        if _fails
        else mo.callout(
            mo.md(f"The {_b} band meets its S11, gain and axial-ratio targets at this position."),
            kind="success",
            title="Band Targets Met",
        )
    ]
    if MODE == "estimate":
        _out.append(
            mo.callout(
                mo.md(
                    "More than one slider is off nominal ("
                    + ", ".join(AXIS_LABEL[_k] for _k in MOVED)
                    + "). The numbers add up "
                    "single-axis effects and ignore how the parameters interact; the charts follow the axis moved furthest. "
                    "To know the combined case, simulate it – the optimizer takes the same config and design."
                ),
                kind="info",
                title="Several Axes Moved",
            )
        )
    mo.vstack(_out)
    return


@app.cell
def _(ACTIVE, BAND, MODE, PACK, VALUES, alt, band_strip, gl, mo, pd, series_style, style_chart, table_for):
    # Reflection and coupling versus frequency.
    _df, _note = table_for(PACK["sweeps"], ["frequency_hz"], MODE, ACTIVE, VALUES)
    _traces = [("s11_in_db", "network input"), ("s11_db", "one probe alone"), ("s21_db", "probe to probe")]
    _rows = [
        pd.DataFrame({"f": _df["frequency_hz"] / 1e9, "db": _df[_c].clip(lower=-40), "trace": _l})
        for _c, _l in _traces
        if len(_df) and _c in _df
    ]
    if not _rows:
        _out = mo.md("No S-parameter data in this pack.")
    else:
        _d = pd.concat(_rows)
        _order = [_l for _c, _l in _traces if _c in _df]
        _cols, _shp = series_style(_order)
        _chart = (
            band_strip(BAND["low_hz"] / 1e9, BAND["high_hz"] / 1e9)
            + alt.Chart(_d)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X("f:Q", title="Frequency (GHz)"),
                y=alt.Y("db:Q", title="dB", scale=alt.Scale(domain=[-40, 0])),
                color=alt.Color("trace:N", title=None, sort=_order, scale=alt.Scale(domain=_order, range=_cols)),
                tooltip=[
                    alt.Tooltip("trace:N", title="Trace"),
                    alt.Tooltip("f:Q", title="GHz", format=".3f"),
                    alt.Tooltip("db:Q", title="dB", format=".1f"),
                ],
            )
        ).properties(
            title="Reflection and coupling versus frequency (the yellow strip is the band)",
            width="container",
            height=300,
        )
        _out = mo.vstack([mo.ui.altair_chart(style_chart(_chart)), mo.md(_note) if _note else mo.md("")])
    mo.vstack(
        [
            mo.md("## Reflection and Coupling"),
            mo.md(
                "Three curves that answer different questions. **One probe alone** is the antenna: its minimum is the "
                + gl("resonance", "resonance")
                + ", its depth is the "
                + gl("match", "impedance-matching")
                + ". "
                "**Network input** is what the radio sees behind the 90° "
                + gl("hybrid coupler", "hybrid-coupler")
                + " – "
                "with two identical probes the hybrid cancels their reflections and sends them to its load, so this curve is "
                "not a match measurement, it mostly shows the probe-to-probe coupling. The feed-network load in the cards is "
                "the mismatch loss the link budget should carry."
            ),
            _out,
        ]
    )
    return


@app.cell
def _(ACTIVE, BAND, MODE, PACK, PALETTE, VALUES, alt, gl, mo, np, pd, style_chart, table_for):
    # Smith chart of one probe, 0.1 GHz either side of the band, beside the impedance
    # at the band edges and centre – the numbers to hold a VNA measurement against.
    import tomllib as _tomllib

    try:
        _raw = _tomllib.loads(PACK["config_text"]) if PACK["config_text"] else {}
        _feed = (_raw.get("geometry", _raw)).get("feed", {})
        Z0 = float(_feed.get("impedance_ohm", 50.0))
    except Exception:
        Z0 = 50.0
    _df, _note = table_for(PACK["sweeps"], ["frequency_hz"], MODE, ACTIVE, VALUES)
    SMITH_TABLE = pd.DataFrame()
    if len(_df) == 0 or "s11_re" not in _df:
        _out = mo.md("No complex probe S-parameters in this pack (cases need sparams_complex.csv).")
    else:
        _lo, _hi = BAND["low_hz"] - 1e8, BAND["high_hz"] + 1e8
        _loc = _df[(_df["frequency_hz"] >= _lo) & (_df["frequency_hz"] <= _hi)].sort_values("frequency_hz")
        _loc = _loc.assign(f=_loc["frequency_hz"] / 1e9, re=_loc["s11_re"], im=_loc["s11_im"])
        _grid = []
        _t = np.linspace(0, 2 * np.pi, 181)
        _grid.append(pd.DataFrame({"x": np.cos(_t), "y": np.sin(_t), "g": "unit", "i": range(181)}))
        for _r in (0.2, 0.5, 1.0, 2.0, 5.0):
            _grid.append(
                pd.DataFrame(
                    {
                        "x": _r / (1 + _r) + np.cos(_t) / (1 + _r),
                        "y": np.sin(_t) / (1 + _r),
                        "g": f"r{_r}",
                        "i": range(181),
                    }
                )
            )
        for _x in (0.5, 1.0, 2.0, -0.5, -1.0, -2.0):
            _cx, _cy, _rad = 1.0, 1.0 / _x, 1.0 / abs(_x)
            _px, _py = _cx + _rad * np.cos(_t), _cy + _rad * np.sin(_t)
            _keep = _px**2 + _py**2 <= 1.0001
            _grid.append(pd.DataFrame({"x": _px[_keep], "y": _py[_keep], "g": f"x{_x}", "i": np.arange(181)[_keep]}))
        _g = pd.concat(_grid)
        _bg = (
            alt.Chart(_g)
            .mark_line(color="#888884", strokeWidth=0.6, opacity=0.6)
            .encode(
                x=alt.X("x:Q", title="", scale=alt.Scale(domain=[-1.05, 1.05]), axis=None),
                y=alt.Y("y:Q", title="", scale=alt.Scale(domain=[-1.05, 1.05]), axis=None),
                detail="g:N",
                order="i:O",
            )
        )
        _line = (
            alt.Chart(_loc)
            .mark_line(color=PALETTE[0], strokeWidth=2.2)
            .encode(
                x="re:Q",
                y="im:Q",
                order="f:Q",
                tooltip=[
                    alt.Tooltip("f:Q", title="GHz", format=".3f"),
                    alt.Tooltip("re:Q", format=".3f"),
                    alt.Tooltip("im:Q", format=".3f"),
                ],
            )
        )
        _picks = [
            ("band low", BAND["low_hz"]),
            ("band centre", (BAND["low_hz"] + BAND["high_hz"]) / 2),
            ("band high", BAND["high_hz"]),
        ]
        _rows = []
        for _label, _f in _picks:
            _r = _loc.iloc[int(np.argmin(np.abs(_loc["frequency_hz"] - _f)))]
            _gam = complex(float(_r["re"]), float(_r["im"]))
            _z = Z0 * (1 + _gam) / (1 - _gam) if abs(1 - _gam) > 1e-9 else complex(float("inf"), 0)
            _mag = abs(_gam)
            _rows.append(
                {
                    "Point": _label,
                    "Frequency (MHz)": float(_r["frequency_hz"]) / 1e6,
                    "R (Ω)": _z.real,
                    "X (Ω)": _z.imag,
                    "Return loss (dB)": -20 * np.log10(max(_mag, 1e-9)),
                    "VSWR": (1 + _mag) / (1 - _mag) if _mag < 1 else float("inf"),
                    "re": _gam.real,
                    "im": _gam.imag,
                }
            )
        SMITH_TABLE = pd.DataFrame(_rows)
        _pts = (
            alt.Chart(SMITH_TABLE)
            .mark_point(filled=True, size=90, color=PALETTE[2])
            .encode(
                x="re:Q", y="im:Q", tooltip=[alt.Tooltip("Point:N"), alt.Tooltip("Frequency (MHz):Q", format=".0f")]
            )
        )
        _labels = (
            alt.Chart(SMITH_TABLE)
            .mark_text(
                align="left", dx=8, dy=-6, font="IBM Plex Mono, ui-monospace, monospace", fontSize=11, color="#888884"
            )
            .encode(x="re:Q", y="im:Q", text="Point:N")
        )
        _chart = (_bg + _line + _pts + _labels).properties(
            title="Smith chart of one probe, 0.1 GHz either side of the band", width=420, height=420
        )
        _table = mo.ui.table(
            SMITH_TABLE.drop(columns=["re", "im"]),
            selection=None,
            show_column_summaries=False,
            format_mapping={
                "Frequency (MHz)": "{:.0f}",
                "R (Ω)": "{:.1f}",
                "X (Ω)": "{:+.1f}",
                "Return loss (dB)": "{:.1f}",
                "VSWR": "{:.2f}",
            },
        )
        _out = mo.vstack(
            [
                mo.hstack(
                    [
                        mo.ui.altair_chart(style_chart(_chart)),
                        mo.vstack(
                            [
                                mo.md(f"**Probe impedance** (reference {Z0:g} Ω)"),
                                _table,
                                mo.md(
                                    "R + jX is the impedance the probe presents; 50 + j0 Ω is a perfect match. "
                                    "Return loss and VSWR say the same thing as the distance from the chart's centre."
                                ),
                            ],
                            gap=0.5,
                        ),
                    ],
                    justify="center",
                    align="center",
                    gap=2,
                    wrap=True,
                ),
                mo.md(_note) if _note else mo.md(""),
            ]
        )
    mo.vstack(
        [
            mo.md("## Probe Impedance"),
            mo.md(
                "The "
                + gl("Smith chart", "smith-chart")
                + " draws the probe's reflection coefficient as frequency runs through the "
                "band: the centre of the chart is a perfect 50 Ω match, the rim is total reflection. The loop is the patch's "
                "resonance; where its near side passes the centre is where the feed offset put it. The table gives the same "
                "points as numbers, which is what to hold a bench measurement against."
            ),
            _out,
        ]
    )
    return SMITH_TABLE, Z0


@app.cell
def _(ACTIVE, BAND, MODE, PACK, PALETTE, VALUES, alt, band_strip, gl, mo, style_chart, table_for):
    # Broadside gain and axial ratio versus frequency.
    _df, _note = table_for(PACK["samples"], ["frequency_hz"], MODE, ACTIVE, VALUES)
    if len(_df) == 0:
        _out = mo.md("No broadside gain samples in this pack.")
    else:
        _d = _df.sort_values("frequency_hz").assign(f=lambda _x: _x["frequency_hz"] / 1e9)
        _g = (
            alt.Chart(_d)
            .mark_line(point=True, color=PALETTE[0], strokeWidth=2)
            .encode(
                x=alt.X("f:Q", title="Frequency (GHz)"),
                y=alt.Y("gain_co_dbic:Q", title="Realized gain (dBic)"),
                tooltip=[alt.Tooltip("f:Q", format=".3f"), alt.Tooltip("gain_co_dbic:Q", format=".2f")],
            )
        )
        _a = (
            alt.Chart(_d)
            .mark_line(point=True, color=PALETTE[2], strokeWidth=2, strokeDash=[6, 4])
            .encode(
                x="f:Q",
                y=alt.Y("ar_db:Q", title="Axial ratio (dB)"),
                tooltip=[alt.Tooltip("f:Q", format=".3f"), alt.Tooltip("ar_db:Q", format=".2f")],
            )
        )
        _chart = (
            alt.layer(band_strip(BAND["low_hz"] / 1e9, BAND["high_hz"] / 1e9) + _g, _a)
            .resolve_scale(y="independent")
            .properties(
                title="Broadside gain (solid) and axial ratio (dashed) versus frequency (the yellow strip is the band)",
                width="container",
                height=280,
            )
        )
        _out = mo.vstack([mo.ui.altair_chart(style_chart(_chart)), mo.md(_note) if _note else mo.md("")])
    mo.vstack(
        [
            mo.md("## Gain and Axial Ratio Versus Frequency"),
            mo.md(
                "Gain at "
                + gl("boresight", "boresight")
                + " in the wanted hand, sampled at the band edges and centre of every "
                "band the pack knows. The axial ratio stays flat far outside the patch's own bandwidth because the 90° "
                "between the two feeds comes from the hybrid, not from the patch."
            ),
            _out,
        ]
    )
    return


@app.cell
def _(ACTIVE, F_PICK, IS_DARK, MODE, PACK, PALETTE, PLANES, VALUES, alt, gl, mo, np, pd, style_chart, table_for):
    # Pattern cuts: co- and cross-polar gain versus angle in the chosen planes. The
    # planes take the four most distinct colors of the family palette (teal, ochre,
    # indigo, green – the deep violet sits too close to the indigo), each with its own
    # marker shape every 30°; the opposite hand is a thinner, lighter dashed line.
    _plane_colors = [PALETTE[0], PALETTE[2], PALETTE[1], PALETTE[4]]
    _plane_shapes = ["circle", "triangle-up", "square", "diamond"]

    def _lighter(hexs, t):
        _r, _g, _b = (int(hexs[_i : _i + 2], 16) for _i in (1, 3, 5))
        if IS_DARK:
            return "#{:02X}{:02X}{:02X}".format(*(round(_c * (1 - t)) for _c in (_r, _g, _b)))
        return "#{:02X}{:02X}{:02X}".format(*(round(_c + (255 - _c) * t) for _c in (_r, _g, _b)))

    _t = PACK["cuts"]
    if len(_t) == 0:
        _out = mo.md("No pattern cuts in this pack.")
    else:
        _fs = np.sort(_t["frequency_hz"].unique())
        _f = float(_fs[np.argmin(np.abs(_fs - F_PICK))])
        _df, _note = table_for(
            _t[np.isclose(_t["frequency_hz"], _f)], ["frequency_hz", "phi_deg", "theta_deg"], MODE, ACTIVE, VALUES
        )
        _co, _cross = [], []
        for _p in PLANES:
            _pos = _df[np.isclose(_df["phi_deg"], _p)].sort_values("theta_deg")
            _neg = _df[np.isclose(_df["phi_deg"], (_p + 180) % 360)].sort_values("theta_deg")
            if len(_pos) == 0 or len(_neg) == 0:
                continue
            _theta = np.concatenate([-_neg["theta_deg"].to_numpy()[::-1], _pos["theta_deg"].to_numpy()[1:]])
            for _col, _bucket in (("gain_co_dbic", _co), ("gain_cross_dbic", _cross)):
                _bucket.append(
                    pd.DataFrame(
                        {
                            "theta": _theta,
                            "gain": np.concatenate([_neg[_col].to_numpy()[::-1], _pos[_col].to_numpy()[1:]]).clip(
                                -25, 15
                            ),
                            "plane": f"phi {_p:g}°",
                        }
                    )
                )
        if not _co:
            _out = mo.md("The chosen planes are not in this pack's cuts.")
        else:
            _order = [f"phi {_p:g}°" for _p in PLANES if any(_d["plane"].iloc[0] == f"phi {_p:g}°" for _d in _co)]
            _cols = [_plane_colors[_i % 4] for _i in range(len(_order))]
            _shapes = [_plane_shapes[_i % 4] for _i in range(len(_order))]
            _co_df, _cross_df = pd.concat(_co), pd.concat(_cross)
            _x = alt.X(
                "theta:Q",
                title="Angle off boresight along the plane (deg)",
                scale=alt.Scale(domain=[-180, 180]),
                axis=alt.Axis(values=list(range(-180, 181, 30))),
            )
            _y = alt.Y("gain:Q", title="Realized gain (dBic)", scale=alt.Scale(domain=[-25, 15]))
            _color = alt.Color("plane:N", title="Plane", sort=_order, scale=alt.Scale(domain=_order, range=_cols))
            _tip = [
                alt.Tooltip("plane:N", title="Plane"),
                alt.Tooltip("theta:Q", title="Angle (deg)"),
                alt.Tooltip("gain:Q", title="dBic", format=".1f"),
            ]
            _co_lines = alt.Chart(_co_df).mark_line(strokeWidth=2.4).encode(x=_x, y=_y, color=_color, tooltip=_tip)
            _co_marks = (
                alt.Chart(_co_df[np.isclose(_co_df["theta"] % 30, 0)])
                .mark_point(filled=True, size=65)
                .encode(
                    x="theta:Q",
                    y="gain:Q",
                    color=_color,
                    shape=alt.Shape(
                        "plane:N", title="Plane", sort=_order, scale=alt.Scale(domain=_order, range=_shapes)
                    ),
                    tooltip=_tip,
                )
            )
            # one layer per plane with a fixed color, so the cross-polar lines share no
            # color scale with the wanted hand and leave its legend alone
            _cross_layers = [
                alt.Chart(_cross_df[_cross_df["plane"] == _pl])
                .mark_line(strokeWidth=1.3, strokeDash=[5, 4], color=_lighter(_c, 0.35))
                .encode(x="theta:Q", y="gain:Q", tooltip=_tip)
                for _pl, _c in zip(_order, _cols, strict=True)
            ]
            _chart = alt.layer(*_cross_layers, _co_lines, _co_marks).properties(
                title=f"Pattern cuts at {_f / 1e9:.3f} GHz – wanted hand bold with markers, opposite hand thin and dashed",
                width="container",
                height=340,
            )
            _out = mo.vstack([mo.ui.altair_chart(style_chart(_chart)), mo.md(_note) if _note else mo.md("")])
    mo.vstack(
        [
            mo.md("## Pattern Cuts"),
            mo.md(
                "The "
                + gl("radiation pattern", "radiation-pattern")
                + " along planes through boresight: 0° is straight out of "
                "the antenna, ±90° along the panel. The thin dashed opposite hand shows where the polarization degrades; the "
                + gl("beamwidth", "beamwidth")
                + " and the shoulder near 60° are what pointing has to live with."
            ),
            _out,
        ]
    )
    return


@app.cell
def _(ACTIVE, MODE, PACK, VALUES, go, mo, np, plotly_layout, table_for, ui_show_pattern):
    # 3D realized gain at band centre, radius = gain above -15 dBic.
    if not ui_show_pattern.value:
        _out = None
    else:
        _df, _note = table_for(PACK["sphere"], ["theta_deg", "phi_deg"], MODE, ACTIVE, VALUES)
        if len(_df) == 0:
            _out = mo.md(
                "No full-sphere pattern in this pack (cases need farfield_sphere.csv, optimizer 0.4.6 or later)."
            )
        else:
            _th = np.sort(_df["theta_deg"].unique())
            _ph = np.sort(_df["phi_deg"].unique())
            _G = _df.pivot(index="theta_deg", columns="phi_deg", values="gain_co_dbic").loc[_th, _ph].to_numpy()
            _ph2 = np.append(_ph, _ph[0] + 360)
            _G2 = np.concatenate([_G, _G[:, :1]], axis=1)
            _R = np.clip(_G2 + 15.0, 0, None)
            _T, _P = np.meshgrid(np.radians(_th), np.radians(_ph2), indexing="ij")

            def _grid(col):
                if col not in _df:
                    return None
                _A = _df.pivot(index="theta_deg", columns="phi_deg", values=col).loc[_th, _ph].to_numpy()
                return np.concatenate([_A, _A[:, :1]], axis=1)

            _X2, _AR2 = _grid("gain_cross_dbic"), _grid("ar_db")
            _PH2 = np.tile(np.mod(_ph2, 360), (len(_th), 1))
            _TH2 = np.tile(_th[:, None], (1, len(_ph2)))
            _hover = np.empty(_G2.shape, dtype=object)
            for _i in range(_G2.shape[0]):
                for _j in range(_G2.shape[1]):
                    _txt = f"θ {_TH2[_i, _j]:.0f}°, φ {_PH2[_i, _j]:.0f}°<br>wanted hand {_G2[_i, _j]:.1f} dBic"
                    if _X2 is not None:
                        _txt += f"<br>opposite hand {_X2[_i, _j]:.1f} dBic"
                    if _AR2 is not None:
                        _txt += f"<br>axial ratio {_AR2[_i, _j]:.1f} dB"
                    _hover[_i, _j] = _txt
            _fig = go.Figure(
                go.Surface(
                    x=_R * np.sin(_T) * np.cos(_P),
                    y=_R * np.sin(_T) * np.sin(_P),
                    z=_R * np.cos(_T),
                    surfacecolor=_G2,
                    colorscale="Viridis",
                    colorbar={"title": "dBic"},
                    cmin=-15,
                    cmax=float(np.nanmax(_G2)),
                    text=_hover,
                    hovertemplate="%{text}<extra></extra>",
                )
            )
            _fig = plotly_layout(_fig, "3D realized gain in the wanted hand (radius: gain above −15 dBic)")
            _fig.update_layout(
                scene={
                    "aspectmode": "data",
                    "xaxis": {"title": "", "visible": False},
                    "yaxis": {"title": "", "visible": False},
                    "zaxis": {"title": "", "visible": False},
                }
            )
            _out = mo.vstack(
                [
                    mo.md("## 3D Pattern"),
                    mo.md(
                        "The same pattern as a surface: one lobe out of the panel, no sidelobes above the shoulder, and the same in every azimuth – the rotational symmetry a circularly polarized antenna should have. θ is the angle off boresight, φ the direction around it. Drag to rotate; hover for the values in that direction."
                    ),
                    mo.ui.plotly(_fig),
                    mo.md(_note) if _note else mo.md(""),
                ]
            )
    _out
    return


@app.cell
def _(ACTIVE, MODE, PACK, VALUES, go, mo, np, plotly_layout, table_for, ui_show_efield):
    # 3D electric field: |E| on each dumped plane, placed where the plane sits.
    if not ui_show_efield.value:
        _out = None
    else:
        _t = PACK["efield"]
        _df, _note = table_for(_t, ["plane", "u", "v"], MODE, ACTIVE, VALUES) if len(_t) else (_t, "")
        if len(_df) == 0:
            _out = mo.md(
                "No field planes in this pack (cases need E-field dumps, `simulate --set dump.efield=true`, and the pack needs h5py)."
            )
        else:
            _traces = []
            for _name, _g in _df.groupby("plane"):
                _axes, _fixed, _coord = str(_g["axes"].iloc[0]), str(_g["fixed"].iloc[0]), float(_g["coord"].iloc[0])
                _u = np.sort(_g["u"].unique())
                _v = np.sort(_g["v"].unique())
                _E = _g.pivot(index="u", columns="v", values="e_db").loc[_u, _v].to_numpy().clip(-40, 0)
                _U, _V = np.meshgrid(_u, _v, indexing="ij")
                _C = np.full_like(_U, _coord)
                _xyz = {_axes[0]: _U, _axes[1]: _V, _fixed: _C}
                _hover = np.empty(_E.shape, dtype=object)
                for _i in range(_E.shape[0]):
                    for _j in range(_E.shape[1]):
                        _hover[_i, _j] = (
                            f"{_name}<br>x {_xyz['x'][_i, _j]:.1f}, y {_xyz['y'][_i, _j]:.1f}, z {_xyz['z'][_i, _j]:.2f} mm"
                            f"<br>|E| {_E[_i, _j]:.1f} dB rel. plane max"
                        )
                _traces.append(
                    go.Surface(
                        x=_xyz["x"],
                        y=_xyz["y"],
                        z=_xyz["z"],
                        surfacecolor=_E,
                        colorscale="Inferno",
                        cmin=-40,
                        cmax=0,
                        colorbar={"title": "|E| dB"},
                        showscale=(len(_traces) == 0),
                        opacity=0.92,
                        name=_name,
                        text=_hover,
                        hovertemplate="%{text}<extra></extra>",
                    )
                )
            _fig = plotly_layout(
                go.Figure(_traces), "|E| at band centre on the dumped planes (dB relative to each plane's maximum)"
            )
            _out = mo.vstack(
                [
                    mo.md("## 3D Electric Field"),
                    mo.md(
                        "The standing wave under the patch and the fringing at the arm ends, which is where the radiation comes from. The null at the centre is why the camera tube can pass through the middle without disturbing the antenna. Each plane is normalized to its own maximum; hover for the position and the level."
                    ),
                    mo.ui.plotly(_fig),
                    mo.md(_note) if _note else mo.md(""),
                ]
            )
    _out
    return


@app.cell
def _(AXES, PACK, VALUES):
    # Geometry at the current slider position, rebuilt from the optimizer's model. The
    # optimizer is a workspace dependency, so this is always live; the nominal case's
    # stored model is only the fallback when the pack's config no longer validates.
    import tomllib

    from bac_antenna.antennas import get_antenna
    from bac_antenna.config import Config, apply_overrides, validate
    from bac_antenna.core import full_params

    def live_model():
        _raw = tomllib.loads(PACK["config_text"])
        _design = dict(PACK["design"])
        _over = []
        for _a in AXES:
            _v = VALUES[_a["id"]]
            if _a.get("params"):
                for _p in _a["params"]:
                    _design[_p] = _v
            elif _a.get("set"):
                _over.append(f"{_a['set']}={_v:g}")
        from pathlib import Path as _P

        _cfg = Config(raw=apply_overrides(_raw, _over), source=_P("pack-config.toml"))
        validate(_cfg)
        _model = get_antenna(_cfg).model(full_params(_design, _cfg), _cfg)
        _prims = []
        for _q in _model.primitives:
            _d = {"kind": _q.kind, "prop": _q.prop, "material": _q.material, "priority": _q.priority}
            if _q.kind in ("box", "cylinder"):
                _d.update(start=list(_q.start), stop=list(_q.stop), radius=_q.radius)
            else:
                _d.update(points=[list(_pt) for _pt in _q.points], elevation=_q.elevation, length=_q.length)
            _prims.append(_d)
        return _prims, "Geometry rebuilt from the optimizer's model at this slider position."

    try:
        GEOMETRY, GEOMETRY_NOTE = live_model()
    except Exception as _exc:
        _nom = PACK["meta"]["nominal_case"]
        GEOMETRY = PACK["models"].get(_nom, [])
        GEOMETRY_NOTE = (
            f"The pack's config did not rebuild at this position ({_exc}); showing the nominal case's stored geometry."
        )
    return GEOMETRY, GEOMETRY_NOTE, live_model


@app.cell
def _(GEOMETRY, GEOMETRY_NOTE, go, mo, np, plotly_layout, ui_show_geometry):
    # 3D geometry from the model's primitives: boxes, cylinders and polygons.
    def _box(d, color, opacity):
        _x0, _y0, _z0 = d["start"]
        _x1, _y1, _z1 = d["stop"]
        if abs(_z1 - _z0) < 1e-9:
            _z1 = _z0 + 0.05
        _xs = [_x0, _x1, _x1, _x0, _x0, _x1, _x1, _x0]
        _ys = [_y0, _y0, _y1, _y1, _y0, _y0, _y1, _y1]
        _zs = [_z0, _z0, _z0, _z0, _z1, _z1, _z1, _z1]
        _i = [7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2]
        _j = [3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3]
        _k = [0, 7, 2, 3, 6, 7, 1, 1, 5, 5, 7, 6]
        return [
            go.Mesh3d(
                x=_xs, y=_ys, z=_zs, i=_i, j=_j, k=_k, color=color, opacity=opacity, name=d["prop"], showlegend=False
            )
        ]

    def _inside(pt, poly):
        _x, _y = pt
        _n = len(poly)
        _in = False
        for _a in range(_n):
            _x0, _y0 = poly[_a]
            _x1, _y1 = poly[(_a + 1) % _n]
            if (_y0 > _y) != (_y1 > _y):
                _xi = _x0 + (_y - _y0) * (_x1 - _x0) / (_y1 - _y0)
                if _x < _xi:
                    _in = not _in
        return _in

    def _polygon(d, color, opacity):
        from scipy.spatial import Delaunay

        _pts = np.array(d["points"], dtype=float)
        if len(_pts) < 3:
            return []
        _z0 = d["elevation"]
        _z1 = _z0 + (d["length"] or 0.0)
        _tri = Delaunay(_pts).simplices
        _keep = np.array([_t for _t in _tri if _inside(_pts[_t].mean(axis=0), _pts)])
        if len(_keep) == 0:
            return []
        _out = []
        for _z in (_z0,) if d["length"] == 0 else (_z0, _z1):
            _out.append(
                go.Mesh3d(
                    x=_pts[:, 0],
                    y=_pts[:, 1],
                    z=np.full(len(_pts), _z),
                    i=_keep[:, 0],
                    j=_keep[:, 1],
                    k=_keep[:, 2],
                    color=color,
                    opacity=opacity,
                    name=d["prop"],
                    showlegend=False,
                )
            )
        return _out

    def _cylinder(d, color, opacity):
        _r = d["radius"]
        _x0, _y0, _z0 = d["start"]
        _z1 = d["stop"][2]
        _a = np.linspace(0, 2 * np.pi, 24)
        _X = np.outer(np.ones(2), _x0 + _r * np.cos(_a))
        _Y = np.outer(np.ones(2), _y0 + _r * np.sin(_a))
        _Z = np.outer([_z0, _z1], np.ones(24))
        return [
            go.Surface(
                x=_X,
                y=_Y,
                z=_Z,
                showscale=False,
                opacity=opacity,
                colorscale=[[0, color], [1, color]],
                name=d["prop"],
                showlegend=False,
            )
        ]

    if not ui_show_geometry.value:
        _out = None
    else:
        _traces = []
        for _d in GEOMETRY:
            _metal = _d["material"] == "metal"
            _color = (
                "#F7D400"
                if _metal and _d["prop"] in ("patch", "arm", "element")
                else ("#C88732" if _metal else "#9AB08A")
            )
            _opacity = 0.95 if _metal else 0.25
            _fn = {"box": _box, "cylinder": _cylinder}.get(_d["kind"], _polygon)
            _traces.extend(_fn(_d, _color, _opacity))
        _fig = plotly_layout(
            go.Figure(_traces), "Geometry – patch in yellow, other metal in bronze, dielectric translucent"
        )
        _out = mo.vstack(
            [
                mo.md("## Geometry"),
                mo.md(
                    GEOMETRY_NOTE
                    + " The origin is the centre of the bore on the ground plane; z points out of the panel. Drag to rotate, scroll to zoom."
                ),
                mo.ui.plotly(_fig),
            ]
        )
    _out
    return


@app.cell
def _(CASES, PACK, SENS, mo, np):
    # Sensitivity and case tables.
    _f = np.sort(PACK["sweeps"]["frequency_hz"].unique()) if len(PACK["sweeps"]) else np.array([])
    _df_hz = float(np.median(np.diff(_f))) if len(_f) > 2 else 0.0
    F_RES_NOTE = (
        (
            f" Resonances are read off a frequency grid of {_df_hz / 1e6:.2f} MHz, so deviations of that size in the "
            "resonance rows are grid noise, not curvature."
        )
        if _df_hz
        else ""
    )
    _tbl = SENS.copy()
    if len(_tbl):
        _tbl["Slope"] = _tbl["Slope"].map(lambda _v: f"{_v:+.3f}")
        _tbl["Worst deviation from a line"] = _tbl["Worst deviation from a line"].map(lambda _v: f"{_v:.3f}")
        _sens_view = mo.ui.table(_tbl, selection=None, show_column_summaries=False, page_size=40)
    else:
        _sens_view = mo.md("Not enough cases along any axis for a slope.")
    _cols = ["axis", "level", "run"] + [_c for _c in ("probe_res_hz", "load_fraction", "gain_co_min_60") if _c in CASES]
    _cases = CASES.reset_index()[["case"] + _cols]
    mo.vstack(
        [
            mo.md("## Sensitivity Table"),
            mo.md(
                "For every axis, the straight line through its simulated cases: the slope is the effect per unit of that "
                "dimension, the worst deviation says how straight the line is over the swept range – small means the "
                "interpolation between cases is safe, large means the effect is curved and the slider value between cases "
                "is less certain." + F_RES_NOTE
            ),
            _sens_view,
            mo.md("## Simulated Cases"),
            mo.md("Every case behind the sliders, with the run directory it came from in the antenna's folder."),
            mo.ui.table(_cases, selection=None, show_column_summaries=False, page_size=40),
        ]
    )
    return


@app.cell
def _(
    ACKNOWLEDGMENT_MD, ASSUMPTIONS_MD, AXIS_LABEL, AXIS_UNIT, MODE, NUMBERS, PACK, SENS, TOOL_VERSION, VALUES, dt, mo
):
    # Export: the sensitivity table and the current position as one markdown report,
    # the table as CSV.
    def _dedent(text):
        return "\n".join(_l[4:] if _l.startswith("    ") else _l for _l in text.strip("\n").splitlines())

    _now = dt.datetime.now(dt.timezone.utc)
    _name = PACK["meta"]["name"]
    _slug = "".join(_c if _c.isalnum() else "-" for _c in _name.lower()).strip("-")
    _pos = "\n".join(
        ["| Axis | Value |", "|---|---|"]
        + [f"| {AXIS_LABEL[_k]} | {_v:g} {AXIS_UNIT[_k]} |" for _k, _v in VALUES.items()]
    )
    _keys = [
        ("probe_res_hz", "Resonance (Hz)"),
        ("load_fraction", "Feed-network load"),
        ("gain_co_min_60", "Gain at 60° (dBic)"),
        ("front_to_back_db", "Front-to-back (dB)"),
    ]
    _nums = "\n".join(
        ["| Quantity | Value |", "|---|---|"]
        + [f"| {_l} | {NUMBERS.get(_k, float('nan')):.4g} |" for _k, _l in _keys if _k in NUMBERS]
    )
    _sens = "\n".join(
        ["| Axis | Quantity | Per | Slope | Worst deviation | Cases |", "|---|---|---|---|---|---|"]
        + [
            f"| {_r['Axis']} | {_r['Quantity']} | {_r['Per unit']} | {_r['Slope']:+.4g} | {_r['Worst deviation from a line']:.3g} | {_r['Cases']} |"
            for _, _r in SENS.iterrows()
        ]
    )
    report_md = (
        "\n\n".join(
            [
                f"# BAC Antenna Visualizer · {_name}",
                f"Generated {_now:%Y-%m-%d %H:%M} UTC (Unix {int(_now.timestamp())}) with BAC Antenna Visualizer {TOOL_VERSION}, "
                f"bac-utils/tools/bac-antenna-visualizer. Pack: {_name}, packed {PACK['meta']['generated']} with {PACK['meta']['tool']}"
                + (f" {PACK['meta']['tool_version']}" if PACK["meta"].get("tool_version") else "")
                + ".",
                "## Slider Position",
                _pos,
                f"Mode: {MODE}.",
                "## Numbers at This Position",
                _nums,
                "## Sensitivity",
                _sens,
                _dedent(ASSUMPTIONS_MD),
                _dedent(ACKNOWLEDGMENT_MD),
            ]
        )
        + "\n"
    )
    sens_csv = (
        SENS.to_csv(index=False) if len(SENS) else "Axis,Quantity,Per unit,Slope,Worst deviation from a line,Cases\n"
    )
    mo.vstack(
        [
            mo.md("## Export"),
            mo.md(
                "The report carries the slider position, the numbers there, the sensitivity table, the assumptions and the acknowledgment. The CSV is the sensitivity table for a spreadsheet."
            ),
            mo.hstack(
                [
                    mo.download(
                        data=report_md.encode("utf-8"),
                        filename=f"bac-antenna-visualizer-{_slug}-{_now:%Y-%m-%d}.md",
                        mimetype="text/markdown",
                        label="Download report (.md)",
                    ),
                    mo.download(
                        data=sens_csv.encode("utf-8"),
                        filename=f"bac-antenna-visualizer-{_slug}-sensitivity-{_now:%Y-%m-%d}.csv",
                        mimetype="text/csv",
                        label="Download sensitivity (.csv)",
                    ),
                ],
                justify="start",
                gap=1,
            ),
        ]
    )
    return


@app.cell
def _(mo):
    ASSUMPTIONS_MD = """
    ## Assumptions

    **Cases.** Every case in a pack is one simulation of the antenna with
    [openEMS](https://cubesat-resources.space/references/glossary/#fdtd) through
    bac-antenna-optimizer: full-wave, one parameter changed from the nominal design, the others
    held. The pack's notes say at which mesh and end criterion it was run; the optimizer's
    handoff documents the mesh-convergence and run-to-run error bars.

    **Interpolation.** Between two simulated levels of one axis every number and every curve is a
    straight-line blend of the two cases. Along the axes swept for the S-band patch that is accurate
    to the simulation's own noise, because [resonance](https://cubesat-resources.space/references/glossary/#resonance),
    load, gain and [axial ratio](https://cubesat-resources.space/references/glossary/#axial-ratio) move
    nearly linearly over these ranges; the sensitivity table's "worst deviation" column shows where
    they do not. With several sliders off nominal the numbers add the single-axis changes and the
    interaction between parameters is not modeled; the charts then follow the axis moved furthest.

    **Feed network.** The two probes are simulated one at a time and combined afterwards as an
    ideal 90° [hybrid coupler](https://cubesat-resources.space/references/glossary/#hybrid-coupler)
    would; the power the probes reflect goes to the hybrid's load and is what the cards call the
    feed-network load. [Realized gain](https://cubesat-resources.space/references/glossary/#realized-gain)
    includes that loss and the dielectric and copper losses.

    **Geometry.** The 3D geometry is rebuilt from the optimizer's own model at every slider
    position, so it is exact at any value, including between simulated levels; the numbers and
    curves are not.

    **Fields.** The field planes are the solver's frequency-domain dumps at band centre, combined
    through the feed network and resampled to a coarse grid for the pack, each plane normalized to
    its own maximum. They are drawn only for cases that were run with dumps.

    ## Limitations

    Not modeled: anything outside the swept ranges; interactions between parameters; a stowed or
    deployed state of anything; the spacecraft body beyond what the pack's config includes. Nothing
    here has been measured – the FR4 prototype and a chamber measurement are what will tell whether
    the model and the copper agree.

    Linked terms go to the [CubeSat Resources glossary](https://cubesat-resources.space/references/glossary/).
    Source and issues: [bac-utils](https://github.com/buildacubesat/bac-utils).
    """
    mo.md(ASSUMPTIONS_MD)
    return (ASSUMPTIONS_MD,)


@app.cell
def _(mo):
    ACKNOWLEDGMENT_MD = """
    ## Acknowledgment

    Simulations by openEMS, the open-source FDTD solver by Thorsten Liebig (GPL), driven by
    bac-antenna-optimizer. Chart conventions shared with the BAC notebook family.

    Code MIT, text and figures CC BY-SA 4.0.
    """
    mo.md(ACKNOWLEDGMENT_MD)
    return (ACKNOWLEDGMENT_MD,)


@app.cell
def _(mo):
    mo.md("""
    ## Revision History

    | Version | Date | Change |
    |---|---|---|
    | 0.3.1 | 2026-10-02 | Conventions pass in bac-utils (SPDX header, ruff, tests under the workspace pytest); no change to what it shows. |
    | 0.3.0 | 2026-09-28 | Runs locally only: the WebAssembly (molab) code paths, the GitHub fallback and the wheel are gone. Packs are discovered in `BAC_ANTENNA_PACKS`, the notebook's `packs/` folder and the antenna folders of a bac-hardware checkout next to bac-utils; a path, URL or upload of a pack folder or pack zip works too. Geometry is always rebuilt live from the optimizer. The status line names the pack's source and release when the pack carries them. |
    | 0.2.3 | 2026-09-25 | Fixes: the band strip no longer pulls the frequency axis down to zero; the pattern cuts keep their legend and full colors (the opposite-hand layer has its own color scale). |
    | 0.2.2 | 2026-09-25 | Smith chart centered beside a table of the probe impedance at the band edges and centre (R + jX, return loss, VSWR). Hover on the 3D pattern gives the direction, both hands' gain and the axial ratio; on the 3D field the position and the level. Pattern cuts in the four most distinct family colors with a marker shape per plane, the opposite hand thin, dashed and lighter. The band is a light yellow strip behind the frequency charts instead of two dotted rules. |
    | 0.2.1 | 2026-09-25 | Pack discovery for molab: the loader reads index.json and the packs from the first place that answers – the file system next to the notebook, the URL next to it, or the folder in bac-utils on GitHub – so the notebook works when only the .py is uploaded. The shipped list no longer falls back to the placeholder's name. |
    | 0.2.0 | 2026-09-24 | Family conventions: the siblings' style and chart-conventions cells, two-column panel with the sidebar switch, headline cards in two rows of three with the callouts judging, export section, assumptions and acknowledgment. Explainer text under every section with glossary links. Smith chart of one probe, 3D electric field on the dumped planes, 3D pattern kept; the sensitivity table reports how straight each axis is. Packs carry complex probe S-parameters and resampled field planes. |
    | 0.1.0 | 2026-09-24 | First version: pack loader (shipped, upload, URL), one-axis interpolation, first-order estimate across axes, S-parameter, gain/AR and cut charts, 3D pattern, live or nearest-case geometry, sensitivity table, exports. |
    """)
    return


if __name__ == "__main__":
    app.run()
