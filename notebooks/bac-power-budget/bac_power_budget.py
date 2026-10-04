# SPDX-License-Identifier: MIT
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo>=0.14",
#     "numpy>=2.0",
#     "pandas>=2.0",
#     "altair>=5.0",
#     "pyarrow>=15.0",
# ]
# ///

import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium", auto_download=["html"])


@app.cell
def _(mo):
    mo.vstack(
        [
            mo.md("""
    # BAC Power Budget

    Estimate generation, consumption and battery charge over a shared orbit
    timeline. Set the panels, battery, loads and payload schedule, or load a
    mission profile. Link Budget and Optical Payload profiles supply compatible
    settings.

    Compare the requested margin with the result after safe-mode load shedding.
    Pass and activation allowances are independent daily energy limits.

    This tool is published at [bac.page/power-budget-tool](https://bac.page/power-budget-tool);
    its siblings are the [Link Budget](https://bac.page/link-budget-tool)
    and [Optical Payload](https://bac.page/optical-payload-tool) tools. All three
    belong to the [Build a CubeSat](https://buildacubesat.space) project and
    their source is in [bac-utils](https://github.com/buildacubesat/bac-utils).
    """),
            mo.callout(
                mo.md(
                    "Most default loads are placeholders. The model uses a circular orbit, a "
                    "simple Earth shadow and fixed conversion efficiencies; it does not model "
                    "battery voltage, current limits or thermal behavior. Use it to see which "
                    "term decides the balance, not to size a battery."
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
    import tomllib

    import altair as alt
    import marimo as mo
    import numpy as np
    import pandas as pd

    return alt, dt, mo, np, pd, tomllib


@app.cell
def _():
    TOOL_VERSION = "0.5.0"
    R_EARTH_KM = 6371.0
    SOLAR_CONST_W_M2 = 1361.0  # AM0, mean Earth distance

    # Solar cell library. Columns: Vmpp (V), Impp (A), Voc (V), Isc (A),
    # efficiency (%), area (cm²), Pmpp temperature coefficient (%/K), rated
    # irradiance (W/m²), rated spectrum, status, note. Datasheet figures are
    # at 25°C under the rated irradiance and spectrum; space cells are rated
    # under AM0 already and get no irradiance or spectrum rescaling.
    SOLAR_CELLS = {
        # Anysolar IXOLAR SolarMD datasheet, electrical characteristics table
        # on p. 1: Voc 6.91 V, Isc 58.6 mA, Vmpp 5.58 V, Impp 55.1 mA, 25%.
        # The Pmpp coefficient is not on that page; –0.40 %/K is typical
        # crystalline silicon and provisional.
        "Anysolar SM141K10TF": (5.58, 0.0551, 6.91, 0.0586, 25.0, 16.1, -0.40, 1000.0, "AM1.5", "provisional", "10 monocrystalline junctions in series, 70 × 23 mm laminate; BAC panel module cell"),
        # AzurSpace 3G30C-Advanced, average BOL values from the datasheet
        # (AM0 WRC, 1367 W/m², 28°C). Provisional.
        "AzurSpace 3G30C-Advanced": (2.409, 0.5029, 2.700, 0.5196, 29.8, 30.18, -0.24, 1367.0, "AM0", "provisional", "Triple-junction GaAs, 80 × 40 mm; the common CubeSat cell"),
        # 4G32C-Advanced DB 0005979-01-00 p. 1: Voc 3451 mV, Isc 457.6 mA, 30.18 cm²;
        # Vmp and Imp are back-solved from the 32% class efficiency.
        "AzurSpace 4G32C-Advanced": (3.08, 0.431, 3.451, 0.4576, 32.0, 30.18, -0.22, 1367.0, "AM0", "provisional", "Quadruple-junction GaAs, 80 × 40 mm"),
        "Spectrolab XTJ Prime": (2.396, 0.456, 2.72, 0.473, 30.7, 26.62, -0.24, 1353.0, "AM0", "provisional", "Triple-junction GaAs, current from the datasheet's mA/cm² over the 26.62 cm² standard cell"),
        # Terrestrial silicon that low-cost CubeSats cut into strips; rated at AM1.5.
        "SunPower Maxeon C60 (Gen II)": (0.577, 5.93, 0.682, 6.24, 22.5, 153.0, -0.35, 1000.0, "AM1.5", "provisional", "125 mm back-contact silicon, usually cut into strips"),
        "Anysolar KXOB25-14X1F": (0.501, 0.0613, 0.63, 0.0654, 25.0, 1.2, -0.40, 1000.0, "AM1.5", "provisional", "Single junction, 23 × 8 mm; the small SolarBIT for sun sensors and demonstrators"),
    }
    SOLAR_KEYS = ["Cell", "Vmpp (V)", "Impp (A)", "Voc (V)", "Isc (A)", "Efficiency (%)", "Area (cm²)", "Pmpp TC (%/K)", "Rated (W/m²)", "Spectrum", "Status", "Note"]

    # Battery cell library. Columns: nominal V, capacity (Ah), max charge V,
    # discharge cutoff V, mass (g), status, note.
    BATTERY_CELLS = {
        # LG Chem product specification INR18650 MJ1, Rev 1 (2016-06-30),
        # §2.1 capacity 3'500 mAh nominal / 3'350 minimum, §2.2 average
        # 3.635 V, §2.4 charge 4.2 V, §2.6 cutoff 2.5 V, §2.7 max 10 A.
        "LG INR18650 MJ1": (3.635, 3.5, 4.2, 2.5, 49.0, "reference", "12.7 Wh, 10 A max discharge, charge 0–45°C only"),
        # The rows below are widely flown 18650s with figures from their
        # public specifications as usually quoted; provisional until the
        # datasheet page is on file.
        "Samsung INR18650-35E": (3.6, 3.5, 4.2, 2.65, 50.0, "provisional", "8 A max discharge; the MJ1's usual alternative"),
        "Panasonic NCR18650GA": (3.6, 3.45, 4.2, 2.5, 48.0, "provisional", "10 A max discharge"),
        "Panasonic NCR18650B": (3.6, 3.35, 4.2, 2.5, 48.5, "provisional", "The classic CubeSat cell; 6.8 A max"),
        "Murata VTC6": (3.6, 3.0, 4.2, 2.5, 46.6, "provisional", "15 A continuous; used where pulse current matters"),
        "Samsung INR18650-30Q": (3.6, 3.0, 4.2, 2.5, 48.0, "provisional", "15 A continuous"),
        "Molicel INR18650-P28A": (3.6, 2.8, 4.2, 2.5, 46.0, "provisional", "35 A continuous, wide temperature range"),
        "Generic 18650, 2.6 Ah": (3.6, 2.6, 4.2, 2.75, 46.0, "placeholder", "A conservative stand-in for any unspecified cell"),
    }
    # Open-circuit voltage against state of charge for a generic NMC 18650,
    # rested cell, per cell. Provisional; it turns the percentage sliders into
    # volts and nothing else depends on it.
    OCV_SOC = [(0.0, 3.00), (0.05, 3.35), (0.10, 3.45), (0.20, 3.55), (0.30, 3.62), (0.40, 3.67), (0.50, 3.72), (0.60, 3.80), (0.70, 3.88), (0.80, 3.96), (0.90, 4.06), (1.00, 4.18)]
    BATTERY_KEYS = ["Cell", "Nominal (V)", "Capacity (Ah)", "Charge (V)", "Cutoff (V)", "Mass (g)", "Status", "Note"]

    STATIONS = {
        "Bern, Switzerland": (46.950, 7.450),
        "San Marcos, Texas": (29.879, -97.939),
        "Farroupilha, Brazil": (-29.233, -51.350),
        "Nairobi, Kenya": (-1.286, 36.817),
        "Custom": None,
    }

    CUBESAT_UNITS = {"1U": 1, "1.5U": 1.5, "2U": 2, "3U": 3}

    PAYLOAD_MODES = [
        "Over a location",
        "Over a region",
        "Orbit position",
        "Fixed cadence",
        "Clock window",
        "During passes",
        "Eclipse or sunlight",
        "Listed",
        "Always",
        "Never",
    ]

    # Load table columns and their profile keys.
    LOAD_KEYS = {
        "Consumer": "consumer",
        "Node": "node",
        "Rail": "rail",
        "Peak (W)": "peak_w",
        "Safe (W)": "safe_w",
        "Nominal (W)": "nominal_w",
        "Pass (W)": "pass_w",
        "Payload (W)": "payload_w",
        "Degraded (W)": "degraded_w",
        "Status": "status",
        "Note": "note",
    }
    LOAD_BLANK = {"Consumer": "", "Node": "", "Rail": "VBAT", "Peak (W)": 0.0, "Safe (W)": 0.0, "Nominal (W)": 0.0, "Pass (W)": 0.0, "Payload (W)": 0.0, "Degraded (W)": 0.0, "Status": "placeholder", "Note": ""}
    RAILS = ("VBAT", "5V", "3V3")

    # Average watts per mode. A consumer that is switched off in a mode has 0
    # there. Pass and payload override nominal per consumer; safe and degraded
    # replace the whole row. Every value marked placeholder is a guess.
    DEFAULT_LOADS = [
        ("EPS main board (STM32F405, sensors, eFuses)", "small", "VBAT", 0.3, 0.15, 0.15, 0.15, 0.15, 0.15, "placeholder", "No bench figure yet; 150 mW is the working assumption"),
        ("Radio node (SatNOGS-COMMS respin)", "medium", "VBAT", 6.0, 0.4, 0.4, 4.9, 0.4, 0.0, "placeholder", "RX 0.4 W, TX 6 W at 32 dBm assumed; pass = 80% TX; only the 8 W S-band peak is published"),
        ("LoRa function board (LR1121, STM32U5)", "medium", "VBAT", 0.5, 0.03, 0.03, 0.03, 0.03, 0.03, "placeholder", "Sniffer and MCU idle; TX priced under Beacon"),
        ("CM5 on carrier (Yocto, F Prime)", "large", "5V", 7.0, 0.0, 2.5, 3.0, 5.0, 0.0, "placeholder", "Idle 2.5 W, pass 3 W, payload 5 W assumed; off in safe and degraded"),
        ("CHC5 primary imager (Zynq)", "large", "5V", 4.0, 0.0, 0.0, 0.0, 3.0, 0.0, "placeholder", "Unknown until the January 2027 hardware; 3 W while the pipeline is powered"),
        ("Boom camera node (STM32U5, OV5640)", "medium", "3V3", 0.6, 0.0, 0.0, 0.0, 0.4, 0.0, "placeholder", "Powered around each activation only"),
        ("Magnetorquer coils (4 × PCB) and driver", "small", "3V3", 0.8, 0.1, 0.2, 0.2, 0.3, 0.0, "placeholder", "About 20 mm PCB coils, one per side face; average over a detumble-and-hold duty"),
        ("Attitude sensors (IMU, magnetometer, sun sensors)", "small", "3V3", 0.1, 0.05, 0.05, 0.05, 0.05, 0.0, "placeholder", ""),
        ("Heaters", "–", "VBAT", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "placeholder", "Not decided; row kept so the table has somewhere to put it"),
    ]
    DEFAULT_LOADS_GENERIC = [
        ("On-board computer", "–", "3V3", 1.0, 0.3, 0.5, 0.5, 0.5, 0.3, "placeholder", ""),
        ("UHF transceiver", "–", "VBAT", 4.0, 0.2, 0.2, 3.2, 0.2, 0.2, "placeholder", "1 W RF class"),
        ("Camera", "–", "3V3", 1.0, 0.0, 0.0, 0.0, 0.8, 0.0, "placeholder", "Raspberry Pi camera on a microcontroller"),
        ("ADCS", "–", "3V3", 0.5, 0.1, 0.2, 0.2, 0.2, 0.0, "placeholder", ""),
    ]

    def fmt_int(n):
        if n != n:  # NaN
            return "–"
        return f"{n:,.0f}".replace(",", "'")

    def fmt_num(n, digits=1):
        if n != n:
            return "–"
        _s = f"{n:,.{digits}f}"
        return _s.replace(",", "'")

    return (
        BATTERY_CELLS,
        BATTERY_KEYS,
        CUBESAT_UNITS,
        DEFAULT_LOADS,
        LOAD_BLANK,
        LOAD_KEYS,
        OCV_SOC,
        PAYLOAD_MODES,
        RAILS,
        R_EARTH_KM,
        SOLAR_CELLS,
        SOLAR_CONST_W_M2,
        SOLAR_KEYS,
        STATIONS,
        TOOL_VERSION,
        fmt_num,
    )


@app.cell
def _():
    # Shipped profiles. Any key left out keeps the tool's default.
    PROFILE_BAC = """
    name = "Build a CubeSat demo mission, 1.5U"

    [orbit]
    altitude_km = 450
    inclination_deg = 97.4
    ltdn_hours = 10.5
    epoch = "2027-06-21"
    sim_days = 2

    [ground_station]
    station = "Bern, Switzerland"
    min_elevation_deg = 10

    [payload]
    mode = "Over a location"
    target_is_station = true
    reach_km = 88
    gate_lit = true
    min_sun_elevation_deg = 20
    cap_per_day = 4
    active_s = 60

    [radio]
    consumer = "Radio node (SatNOGS-COMMS respin)"

    [generation]
    cell = "Anysolar SM141K10TF"
    module_series = 2
    module_parallel = 2
    module_u = 0.5
    cubesat = "1.5U"
    faces_x = true
    faces_y = true
    faces_z = false
    modules_per_z_face = 0
    am0_factor = 0.9
    cell_temp_c = 50
    string_loss_pct = 5
    attitude = "Tumbling"

    [storage]
    cell = "LG INR18650 MJ1"
    series = 2
    parallel = 2
    dod_pct = 30
    initial_soc_pct = 80
    charger_eff_pct = 86
    rail_5v_eff_pct = 90
    rail_3v3_eff_pct = 87
    uvlo_v_per_cell = 3.5
    safe_enter_soc_pct = 40
    safe_exit_soc_pct = 60

    tx_w = 6.0
    rx_w = 0.4
    downlink_share_pct = 80

    # The beacon ladder of 2026-09-14. Tier 0: CW on the radio node, in
    # commissioning and deep safe mode, 300 s cadence, 12 s at 6 W (both
    # placeholders). Tiers 1 and 2: digital on the native 50k profile, radio
    # node, safe mode and commissioning only, silent in nominal and during
    # passes; tier 1 is identity and the radio node's state (6.5 ms), tier 2
    # adds EPS housekeeping over bacBus (26 ms) and degrades to tier 1 when the
    # EPS does not answer. Backstop: LoRa SF12 on the function board, degraded
    # phase only, 2.5 s at 0.5 W every 300 s (placeholder; a link budget
    # profile brings the SF12 packet airtime, 1.81 s for 32 bytes). Fallback
    # order tier 2 -> tier 1 -> tier 0 -> LoRa. Every length and power here is
    # a typed placeholder until measured.
    [beacon]
    policy = "Safe mode and commissioning"
    cw_message_s = 12
    cw_power_w = 6.0
    cw_cadence_s = 300
    tier1_on_air_ms = 6.5
    tier1_cadence_s = 60
    tier2_on_air_ms = 26
    tier2_cadence_s = 300
    lora_on_air_s = 2.5
    lora_power_w = 0.5
    lora_cadence_nominal_s = 0
    lora_cadence_degraded_s = 300

    [oneshot]
    hdrm_power_w = 5.0
    hdrm_duration_s = 30

    [schedule]
    scenario = "Nominal"
    """

    PROFILE_GENERIC = """
    name = "Generic 1U, one radio, one camera"

    [orbit]
    altitude_km = 500
    inclination_deg = 97.4
    ltdn_hours = 10.5
    sim_days = 2

    [ground_station]
    station = "Bern, Switzerland"

    [payload]
    mode = "Fixed cadence"
    cadence_min = 30
    cap_per_day = 0
    active_s = 30

    [radio]
    consumer = "UHF transceiver"

    [generation]
    cell = "AzurSpace 3G30C-Advanced"
    module_series = 2
    module_parallel = 1
    module_u = 1.0
    cubesat = "1U"
    cell_temp_c = 50
    attitude = "Tumbling"

    [storage]
    cell = "Generic 18650, 2.6 Ah"
    series = 2
    parallel = 1
    dod_pct = 30

    tx_w = 3.0
    rx_w = 0.2

    [beacon]
    cw_cadence_s = 0
    tier1_on_air_ms = 300
    tier1_cadence_s = 60
    tier2_cadence_s = 0
    lora_cadence_degraded_s = 0

    [oneshot]
    hdrm_duration_s = 0

    [[loads]]
    consumer = "On-board computer"
    rail = "3V3"
    peak_w = 1.0
    safe_w = 0.3
    nominal_w = 0.5
    pass_w = 0.5
    payload_w = 0.5
    degraded_w = 0.3

    [[loads]]
    consumer = "UHF transceiver"
    rail = "VBAT"
    peak_w = 4.0
    safe_w = 0.2
    nominal_w = 0.2
    pass_w = 3.2
    payload_w = 0.2
    degraded_w = 0.2
    note = "1 W RF class"

    [[loads]]
    consumer = "Camera"
    rail = "3V3"
    peak_w = 1.0
    payload_w = 0.8

    [[loads]]
    consumer = "ADCS"
    rail = "3V3"
    peak_w = 0.5
    safe_w = 0.1
    nominal_w = 0.2
    pass_w = 0.2
    payload_w = 0.2
    """
    return PROFILE_BAC, PROFILE_GENERIC


@app.cell
def _(mo):
    ui_profile = mo.ui.file(
        kind="button",
        filetypes=[".toml"],
        label="Load mission profile (.toml)",
    )
    return (ui_profile,)


@app.cell
def _(tomllib, ui_profile):
    # Parse the uploaded profile into the defaults every input starts from.
    _raw = ui_profile.contents()
    profile_error = ""
    profile_name = ""
    _doc = {}
    if _raw:
        try:
            _doc = tomllib.loads(_raw.decode("utf-8"))
            profile_name = str(_doc.get("name") or ui_profile.name() or "unnamed")
        except Exception as _e:
            profile_error = f"{type(_e).__name__}: {_e}"
            _doc = {}

    # Dotted sections read the [results.<tool>] tables the siblings write.
    profile_warnings = []

    def P(section, key, default):
        _v = _doc
        for _part in section.split("."):
            _v = _v.get(_part, {}) if isinstance(_v, dict) else {}
        if not isinstance(_v, dict) or key not in _v:
            return default
        _v = _v[key]
        if isinstance(default, bool):
            return bool(_v) if isinstance(_v, (bool, int, float)) else str(_v).strip().lower() in ("true", "yes", "1")
        if isinstance(default, (int, float)):
            # A number the profile got wrong falls back to the default and is
            # reported, rather than breaking the panel.
            try:
                _f = float(_v)
            except (TypeError, ValueError):
                _f = float("nan")
            if _f != _f or _f in (float("inf"), float("-inf")):
                profile_warnings.append(f"{section}.{key} = {_v!r}")
                return default
            return int(_f) if isinstance(default, int) and _f.is_integer() else _f
        return _v

    def PH(section, key):
        # Whether the profile carries the key at all (to tell "absent" from
        # "set to nothing").
        _v = _doc
        for _part in section.split("."):
            _v = _v.get(_part, {}) if isinstance(_v, dict) else {}
        return isinstance(_v, dict) and key in _v

    profile_loads = [_r for _r in _doc.get("loads", []) if isinstance(_r, dict)]
    # Which tool wrote the profile: its own key from the 0.7.0 generation on,
    # otherwise a signature table. The link budget has [[modes]], the optical
    # payload [sensor], this tool [storage].
    _tool = _doc.get("tool")
    if not _tool:
        _tool = "bac_link_budget" if "modes" in _doc else ("bac_optical_payload" if "sensor" in _doc else "bac_power_budget")
    profile_tool = str(_tool)
    return (
        P,
        PH,
        profile_error,
        profile_loads,
        profile_name,
        profile_tool,
        profile_warnings,
    )


@app.cell
def _(
    PROFILE_BAC,
    PROFILE_GENERIC,
    mo,
    profile_error,
    profile_name,
    profile_tool,
    ui_profile,
):
    _foreign = {
        "bac_link_budget": "Link budget profile loaded: **{n}**. Its orbit, station, minimum elevation and downlink share are taken, and the LoRa backstop's time on air when it carries a LoRa row; everything else is this tool's default.",
        "bac_optical_payload": "Optical payload profile loaded: **{n}**. Its orbit, target, frames per day as activations and half its swath as the reach are taken; everything else is this tool's default.",
    }
    if profile_error:
        _status = mo.callout(
            mo.md(f"That file could not be read as TOML, so the defaults are unchanged. {profile_error}"),
            kind="warn",
            title="Profile Not Loaded",
        )
    elif profile_name and profile_tool in _foreign:
        _status = mo.md(_foreign[profile_tool].format(n=profile_name))
    elif profile_name:
        _status = mo.md(f"Profile loaded: **{profile_name}**.")
    else:
        _status = mo.md(
            "No profile loaded – the tool's own defaults are in use, which are the BAC demo "
            "mission's. Save the current settings as a profile from the export section below."
        )

    def _dedent_toml(text):
        return "\n".join(_l[4:] if _l.startswith("    ") else _l for _l in text.strip("\n").splitlines()) + "\n"

    def _shipped(label, text, slug):
        return mo.download(
            data=_dedent_toml(text).encode("utf-8"),
            filename=f"bac-power-budget-{slug}.toml",
            mimetype="application/toml",
            label=label,
        )

    profile_block = mo.vstack(
        [
            ui_profile,
            _status,
            mo.accordion(
                {
                    "Example Profiles": mo.vstack(
                        [
                            mo.md(
                                "Download one, then load it with the button above. The BAC profile "
                                "is what this notebook starts from; nearly every consumer in it is a "
                                "placeholder. The generic 1U is a different spacecraft, and is here "
                                "to show the tool is not the mission."
                            ),
                            mo.hstack(
                                [
                                    _shipped("BAC demo mission, 1.5U", PROFILE_BAC, "profile-bac"),
                                    _shipped("Generic 1U", PROFILE_GENERIC, "profile-generic"),
                                ],
                                justify="start",
                                gap=1,
                            ),
                        ]
                    )
                }
            ),
        ]
    )
    return (profile_block,)


@app.cell
def _(
    BATTERY_CELLS,
    CUBESAT_UNITS,
    DEFAULT_LOADS,
    LOAD_BLANK,
    LOAD_KEYS,
    P,
    PAYLOAD_MODES,
    PH,
    SOLAR_CELLS,
    STATIONS,
    mo,
    pd,
    profile_loads,
):
    # Control panel elements. Every starting value comes through P(). A value a
    # profile puts outside an element's range is clamped rather than refused.
    def N(**kw):
        kw["value"] = min(max(float(kw["value"]), kw["start"]), kw["stop"])
        if float(kw.get("step", 1)) >= 1 and float(kw["step"]).is_integer():
            kw["value"] = int(round(kw["value"]))
        return mo.ui.number(**kw)

    def S(**kw):
        kw["value"] = min(max(float(kw["value"]), kw["start"]), kw["stop"])
        if float(kw["step"]).is_integer():
            kw["value"] = int(round(kw["value"]))
        return mo.ui.slider(**kw)

    ui_scenario = mo.ui.dropdown(
        options=["Nominal", "Safe", "Degraded"], value=P("schedule", "scenario", "Nominal"), label="Scenario"
    )

    # Orbit
    ui_altitude = S(
        start=300, stop=1200, step=10, value=P("orbit", "altitude_km", 450), show_value=True, label="Orbit altitude (km)"
    )
    ui_inclination = N(start=0, stop=180, step=0.1, value=P("orbit", "inclination_deg", 97.4), label="Inclination (deg)")
    ui_ltdn = N(start=0, stop=24, step=0.25, value=P("orbit", "ltdn_hours", 10.5), label="Local time of descending node (h)")
    ui_epoch = mo.ui.text(value=P("orbit", "epoch", "2027-06-21"), label="Epoch (YYYY-MM-DD)")
    # A sibling profile may carry a 30-day span; this tool integrates at most 7.
    ui_sim_days = S(start=1, stop=7, step=1, value=int(min(max(P("orbit", "sim_days", 2), 1), 7)), show_value=True, label="Days to simulate")

    # Ground station, also readable from a link budget profile.
    _sname = P("ground_station", "station", "Bern, Switzerland")
    if _sname not in STATIONS:
        _sname = "Custom" if P("ground_station", "latitude_deg", None) is not None else "Bern, Switzerland"
    ui_station = mo.ui.dropdown(options=list(STATIONS), value=_sname, label="Ground station")
    ui_lat = N(start=-90, stop=90, step=0.01, value=P("ground_station", "latitude_deg", 46.95), label="Custom station latitude (deg N)")
    ui_lon = N(start=-180, stop=180, step=0.01, value=P("ground_station", "longitude_deg", 7.45), label="Custom station longitude (deg E)")
    ui_min_el = N(start=0, stop=60, step=1, value=P("ground_station", "min_elevation_deg", P("orbit", "min_elevation_deg", 10)), label="Minimum elevation (deg)")

    # Payload activation location; an optical payload profile names it under
    # [target], and its old [imaging] keys are read as fallbacks.
    def _PP(key, imaging_key, default):
        return P("payload", key, P("imaging", imaging_key, P("payload", "activations_per_day", default) if key == "cap_per_day" else default))

    _t_is_station = _PP("target_is_station", "target_is_station", P("target", "name", None) is None)
    ui_target_same = mo.ui.switch(value=bool(_t_is_station), label="Activation location is the ground station")
    ui_target_lat = N(start=-90, stop=90, step=0.01, value=P("target", "latitude_deg", 46.95), label="Target latitude (deg N)")
    ui_target_lon = N(start=-180, stop=180, step=0.01, value=P("target", "longitude_deg", 7.45), label="Target longitude (deg E)")
    _mode = P("payload", "mode", "Over a location")
    # A 0.1.0–0.2.0 profile that said zero activations per day meant none;
    # the cap now reads 0 as no cap, so that profile lands on "Never".
    _legacy_zero = not PH("payload", "mode") and (PH("payload", "activations_per_day") or PH("imaging", "frames_per_day")) and P("payload", "activations_per_day", P("imaging", "frames_per_day", 1)) == 0
    if _legacy_zero:
        _mode = "Never"
    ui_pay_mode = mo.ui.dropdown(options=PAYLOAD_MODES, value=_mode if _mode in PAYLOAD_MODES else "Over a location", label="Activation trigger")
    ui_reach = N(
        start=1, stop=2000, step=1, value=_PP("reach_km", "reach_km", P("results.optical_payload", "swath_x_km", 176.0) / 2), label="Reach from the sub-satellite point (km)"
    )
    ui_region_s = N(start=-90, stop=90, step=0.1, value=P("payload", "region_south_deg", 35.0), label="Region south edge (deg N)")
    ui_region_n = N(start=-90, stop=90, step=0.1, value=P("payload", "region_north_deg", 60.0), label="Region north edge (deg N)")
    ui_region_w = N(start=-180, stop=180, step=0.1, value=P("payload", "region_west_deg", -10.0), label="Region west edge (deg E)")
    ui_region_e = N(start=-180, stop=180, step=0.1, value=P("payload", "region_east_deg", 30.0), label="Region east edge (deg E)")
    ui_orbit_u0 = N(start=0, stop=360, step=1, value=P("payload", "orbit_start_deg", 60.0), label="Orbit window start (deg)")
    ui_orbit_u1 = N(start=0, stop=360, step=1, value=P("payload", "orbit_end_deg", 120.0), label="Orbit window end (deg)")
    ui_orbit_nth = N(start=1, stop=100, step=1, value=P("payload", "every_nth_orbit", 1), label="Every Nth orbit")
    ui_cadence = N(start=1, stop=1440, step=1, value=P("payload", "cadence_min", 30), label="Cadence (min)")
    ui_clock_start = N(start=0, stop=24, step=0.25, value=P("payload", "clock_start_h", 8.0), label="Clock window start (h UTC)")
    ui_clock_end = N(start=0, stop=24, step=0.25, value=P("payload", "clock_end_h", 9.0), label="Clock window end (h UTC)")
    ui_pass_after = mo.ui.switch(value=bool(P("payload", "after_pass", False)), label="Start after the pass")
    ui_pass_offset = N(start=0, stop=3600, step=10, value=P("payload", "pass_offset_s", 0), label="Offset (s)")
    ui_eclipse_edge = mo.ui.dropdown(
        options=["Throughout eclipse", "Throughout sunlight", "At eclipse entry", "At eclipse exit"],
        value=P("payload", "eclipse_edge", "Throughout eclipse"),
        label="Eclipse or sunlight",
    )
    _listed = _doc_activations = P("payload", "listed", "3.5, 120\n15.0, 120")
    ui_listed = mo.ui.text_area(value=str(_listed), label="Hours from epoch, duration (s)", rows=4)
    ui_hold = mo.ui.switch(value=bool(P("payload", "hold_whole_window", False)), label="Hold for the whole trigger window")
    ui_window = N(start=1, stop=86400, step=1, value=_PP("active_s", "window_s", 60), label="Active time per activation (s)")
    ui_gate_lit = mo.ui.switch(value=bool(P("payload", "gate_lit", True)), label="Only when lit")
    ui_min_sun = N(start=-10, stop=90, step=1, value=_PP("min_sun_elevation_deg", "min_sun_elevation_deg", 20), label="Minimum Sun elevation at the location (deg)")
    ui_gate_nopass = mo.ui.switch(value=bool(P("payload", "gate_no_pass", False)), label="Not during passes")
    ui_cap_day = N(
        start=0, stop=1000, step=1, value=_PP("cap_per_day", "frames_per_day", P("results.optical_payload", "frames_per_day", 4)), label="Cap per day (0 = no cap)"
    )
    ui_cap_orbit = N(start=0, stop=100, step=1, value=P("payload", "cap_per_orbit", 0), label="Cap per orbit (0 = no cap)")

    # Generation
    ui_cell = mo.ui.dropdown(options=list(SOLAR_CELLS) + ["Custom"], value=P("generation", "cell", "Anysolar SM141K10TF"), label="Solar cell")
    ui_cell_vmpp = N(start=0.1, stop=100, step=0.01, value=P("generation", "custom_vmpp_v", 5.58), label="Custom Vmpp (V)")
    ui_cell_impp = N(start=0.001, stop=10, step=0.001, value=P("generation", "custom_impp_a", 0.0551), label="Custom Impp (A)")
    ui_cell_tc = N(start=-2, stop=0, step=0.01, value=P("generation", "custom_tc_pct_k", -0.4), label="Custom Pmpp coefficient (%/K)")
    ui_cell_rated = N(start=100, stop=2000, step=1, value=P("generation", "custom_rated_w_m2", 1000), label="Custom rated irradiance (W/m²)")
    ui_cell_spectrum = mo.ui.dropdown(options=["AM1.5", "AM0"], value=P("generation", "custom_spectrum", "AM1.5"), label="Custom rated spectrum")
    ui_cell_area = N(start=0.1, stop=1000, step=0.1, value=P("generation", "custom_area_cm2", 16.1), label="Custom cell area (cm²)")
    # A 0.1.0–0.2.0 profile's cells_per_module were all in series.
    _legacy_series = PH("generation", "cells_per_module") and not PH("generation", "module_series")
    ui_mod_series = N(start=1, stop=40, step=1, value=P("generation", "module_series", P("generation", "cells_per_module", 2)), label="Cells in series per string (S)")
    ui_mod_parallel = N(start=1, stop=40, step=1, value=P("generation", "module_parallel", 1 if _legacy_series else 2), label="Parallel strings per module (P)")
    _mod_u_options = {f"{_x:g}U": _x for _x in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0)}
    _mod_u = f"{P('generation', 'module_u', 0.5):g}U"
    ui_mod_u = mo.ui.dropdown(options=_mod_u_options, value=_mod_u if _mod_u in _mod_u_options else "0.5U", label="Module length along the face")
    ui_cubesat = mo.ui.dropdown(options=list(CUBESAT_UNITS), value=P("generation", "cubesat", "1.5U"), label="CubeSat size")
    ui_faces_x = mo.ui.switch(value=P("generation", "faces_x", True), label="Modules on +X and –X")
    ui_faces_y = mo.ui.switch(value=P("generation", "faces_y", True), label="Modules on +Y and –Y")
    ui_faces_z = mo.ui.switch(value=P("generation", "faces_z", False), label="Modules on +Z and –Z")
    ui_modules_z = N(start=0, stop=8, step=1, value=P("generation", "modules_per_z_face", 0), label="Modules per Z face")
    ui_am0 = N(start=0.5, stop=1.2, step=0.01, value=P("generation", "am0_factor", 0.9), label="AM0 factor (AM1.5-rated cells only)")
    ui_cell_temp = N(start=-60, stop=120, step=1, value=P("generation", "cell_temp_c", 50), label="Cell temperature in sunlight (°C)")
    ui_string_loss = N(start=0, stop=30, step=0.5, value=P("generation", "string_loss_pct", 5), label="Diode and mismatch loss (%)")
    ui_attitude = mo.ui.dropdown(
        options=["Tumbling", "Nadir-pointed", "Sun-pointed"], value=P("generation", "attitude", "Tumbling"), label="Attitude"
    )

    # Storage
    ui_batt = mo.ui.dropdown(options=list(BATTERY_CELLS) + ["Custom"], value=P("storage", "cell", "LG INR18650 MJ1"), label="Battery cell")
    ui_batt_v = N(start=1, stop=5, step=0.001, value=P("storage", "custom_nominal_v", 3.6), label="Custom nominal voltage (V)")
    ui_batt_ah = N(start=0.1, stop=50, step=0.01, value=P("storage", "custom_capacity_ah", 2.6), label="Custom capacity (Ah)")
    ui_series = N(start=1, stop=8, step=1, value=P("storage", "series", 2), label="Cells in series (S)")
    ui_parallel = N(start=1, stop=8, step=1, value=P("storage", "parallel", 2), label="Strings in parallel (P)")
    ui_dod = S(start=5, stop=90, step=5, value=P("storage", "dod_pct", 30), show_value=True, label="Allowed depth of discharge (%)")
    ui_soc0 = S(start=10, stop=100, step=5, value=P("storage", "initial_soc_pct", 80), show_value=True, label="Initial state of charge (%)")
    ui_eff_charge = N(start=50, stop=100, step=0.5, value=P("storage", "charger_eff_pct", 86), label="Charger efficiency (%)")
    ui_eff_5v = N(start=50, stop=100, step=0.5, value=P("storage", "rail_5v_eff_pct", 90), label="5 V rail efficiency (%)")
    ui_eff_3v3 = N(start=50, stop=100, step=0.5, value=P("storage", "rail_3v3_eff_pct", 87), label="3V3 rail efficiency (%)")
    ui_uvlo = N(start=2.5, stop=4.0, step=0.05, value=P("storage", "uvlo_v_per_cell", 3.5), label="EPS undervoltage lockout (V per cell)")
    ui_safe_enter = N(start=0, stop=100, step=1, value=P("storage", "safe_enter_soc_pct", 40), label="Enter safe mode below (% SoC)")
    ui_safe_exit = N(start=0, stop=100, step=1, value=P("storage", "safe_exit_soc_pct", 60), label="Leave safe mode above (% SoC)")

    # Radio and beacon
    ui_tx_w = N(start=0, stop=50, step=0.1, value=P("radio", "tx_w", 6.0), label="Radio transmit draw (W)")
    ui_rx_w = N(start=0, stop=50, step=0.01, value=P("radio", "rx_w", 0.4), label="Radio receive draw (W)")
    ui_share = S(
        start=0, stop=100, step=5, value=P("radio", "downlink_share_pct", P("results.link_budget", "downlink_share_pct", P("allowances", "downlink_share_pct", 80))), show_value=True, label="Downlink share of a pass (%)"
    )
    ui_beacon_policy = mo.ui.dropdown(
        options=["Safe mode and commissioning", "Always while the radio is up", "Off"],
        value=P("beacon", "policy", "Safe mode and commissioning"),
        label="CW and tier beacon policy",
    )
    ui_cw_s = N(start=0, stop=120, step=0.5, value=P("beacon", "cw_message_s", 12), label="CW message on air (s)")
    ui_cw_w = N(start=0, stop=50, step=0.1, value=P("beacon", "cw_power_w", 6.0), label="CW transmit draw (W)")
    ui_cw_cad = N(start=0, stop=3600, step=10, value=P("beacon", "cw_cadence_s", 300), label="CW cadence (s, 0 = off)")
    ui_t1_ms = N(start=0, stop=10000, step=0.5, value=P("beacon", "tier1_on_air_ms", 6.5), label="Tier 1 on air (ms)")
    ui_t1_cad = N(start=0, stop=3600, step=10, value=P("beacon", "tier1_cadence_s", 60), label="Tier 1 cadence (s, 0 = off)")
    ui_t2_ms = N(start=0, stop=10000, step=0.5, value=P("beacon", "tier2_on_air_ms", 26), label="Tier 2 on air (ms)")
    ui_t2_cad = N(start=0, stop=3600, step=10, value=P("beacon", "tier2_cadence_s", 300), label="Tier 2 cadence (s, 0 = off)")
    # The backstop's time on air comes from a link budget profile's per-mode
    # results when it carries a LoRa SF12 row (any LoRa row failing that);
    # this tool's own key wins when present.
    _lb_modes = [_m for _m in P("results.link_budget", "modes", []) if isinstance(_m, dict) and str(_m.get("modulation", "")).startswith("LoRa")]
    _lb_sf12 = next((_m for _m in _lb_modes if "SF12" in str(_m.get("modulation", ""))), _lb_modes[0] if _lb_modes else None)
    _lora_default = 2.5
    if _lb_sf12 is not None:
        try:
            _lora_default = float(_lb_sf12.get("packet_airtime_ms", float("nan"))) / 1000
        except (TypeError, ValueError):
            _lora_default = float("nan")
        _lora_default = 2.5 if _lora_default != _lora_default else round(_lora_default, 2)
    ui_lora_s = N(start=0, stop=30, step=0.1, value=P("beacon", "lora_on_air_s", _lora_default), label="LoRa backstop on air (s)")
    ui_lora_w = N(start=0, stop=5, step=0.01, value=P("beacon", "lora_power_w", 0.5), label="LoRa transmit draw (W)")
    ui_lora_cad_nom = N(start=0, stop=3600, step=10, value=P("beacon", "lora_cadence_nominal_s", 0), label="LoRa cadence, nominal (s, 0 = off)")
    ui_lora_cad_deg = N(start=0, stop=3600, step=10, value=P("beacon", "lora_cadence_degraded_s", 300), label="LoRa cadence, degraded (s, 0 = off)")

    # One-shot
    ui_hdrm_w = N(start=0, stop=50, step=0.1, value=P("oneshot", "hdrm_power_w", 5.0), label="Release mechanism draw (W)")
    ui_hdrm_s = N(start=0, stop=600, step=1, value=P("oneshot", "hdrm_duration_s", 30), label="Release duration (s)")

    # Loads table. Rows from the profile's [[loads]] or the shipped defaults.
    _cols = list(LOAD_KEYS)
    if profile_loads:
        _rows = [{_c: _r.get(_k, _r.get("imaging_w", LOAD_BLANK[_c]) if _k == "payload_w" else LOAD_BLANK[_c]) for _c, _k in LOAD_KEYS.items()} for _r in profile_loads]
    else:
        _rows = [dict(zip(_cols, _r)) for _r in DEFAULT_LOADS]
    ui_loads = mo.ui.data_editor(pd.DataFrame(_rows, columns=_cols), label="")

    ui_sidebar = mo.ui.switch(value=False, label="Controls in a sidebar")
    return (
        ui_altitude,
        ui_am0,
        ui_attitude,
        ui_batt,
        ui_batt_ah,
        ui_batt_v,
        ui_beacon_policy,
        ui_cadence,
        ui_cap_day,
        ui_cap_orbit,
        ui_cell,
        ui_cell_area,
        ui_cell_impp,
        ui_cell_rated,
        ui_cell_spectrum,
        ui_cell_tc,
        ui_cell_temp,
        ui_cell_vmpp,
        ui_clock_end,
        ui_clock_start,
        ui_cubesat,
        ui_cw_cad,
        ui_cw_s,
        ui_cw_w,
        ui_dod,
        ui_eclipse_edge,
        ui_eff_3v3,
        ui_eff_5v,
        ui_eff_charge,
        ui_epoch,
        ui_faces_x,
        ui_faces_y,
        ui_faces_z,
        ui_gate_lit,
        ui_gate_nopass,
        ui_hdrm_s,
        ui_hdrm_w,
        ui_hold,
        ui_inclination,
        ui_lat,
        ui_listed,
        ui_loads,
        ui_lon,
        ui_lora_cad_deg,
        ui_lora_cad_nom,
        ui_lora_s,
        ui_lora_w,
        ui_ltdn,
        ui_min_el,
        ui_min_sun,
        ui_mod_parallel,
        ui_mod_series,
        ui_mod_u,
        ui_modules_z,
        ui_orbit_nth,
        ui_orbit_u0,
        ui_orbit_u1,
        ui_parallel,
        ui_pass_after,
        ui_pass_offset,
        ui_pay_mode,
        ui_reach,
        ui_region_e,
        ui_region_n,
        ui_region_s,
        ui_region_w,
        ui_rx_w,
        ui_safe_enter,
        ui_safe_exit,
        ui_scenario,
        ui_series,
        ui_share,
        ui_sidebar,
        ui_sim_days,
        ui_soc0,
        ui_station,
        ui_string_loss,
        ui_t1_cad,
        ui_t1_ms,
        ui_t2_cad,
        ui_t2_ms,
        ui_target_lat,
        ui_target_lon,
        ui_target_same,
        ui_tx_w,
        ui_uvlo,
        ui_window,
    )


@app.cell
def _(P, PH, mo, ui_loads):
    # Which table row is the radio. Its pass value is computed from the radio
    # controls; this cell reads the table, so it lives apart from the elements.
    _names = [str(_n).strip() for _n in ui_loads.value["Consumer"].tolist() if str(_n).strip()]
    # The profile may name the row, say "None" outright, or say nothing; only
    # the last falls back to the first row that looks like a radio.
    _want = str(P("radio", "consumer", "")).strip()
    if not PH("radio", "consumer"):
        _want = next((_n for _n in _names if "radio" in _n.lower() or "transceiver" in _n.lower()), "None")
    elif _want not in _names:
        _want = "None"
    _options = {"None": "None"}
    for _i, _n in enumerate(_names, 1):
        _short = _n.split(" (")[0]
        _options[f"{_i}. {_short[:27].rstrip() + '…' if len(_short) > 30 else _short}"] = _n
    _label = next((_l for _l, _v in _options.items() if _v == _want), "None")
    ui_radio_row = mo.ui.dropdown(options=_options, value=_label, label="Radio consumer", full_width=True)
    return (ui_radio_row,)


@app.cell
def _(OCV_SOC, mo, np, ui_dod, ui_series, ui_soc0, ui_uvlo):
    # The percentage sliders in volts, per cell and per pack, off a generic
    # rested open-circuit curve. Its own cell so a slider move redraws only
    # this line.
    _soc = np.array([_p[0] for _p in OCV_SOC])
    _v = np.array([_p[1] for _p in OCV_SOC])

    def soc_to_v(soc):
        return float(np.interp(soc, _soc, _v))

    def v_to_soc(v):
        return float(np.interp(v, _v, _soc))

    _ns = int(ui_series.value)
    _floor = 1 - float(ui_dod.value) / 100
    _start = float(ui_soc0.value) / 100
    _uvlo_soc = v_to_soc(float(ui_uvlo.value))
    volts_line = mo.md(
        f"Floor {_floor * 100:.0f}% SoC ≈ {soc_to_v(_floor):.2f} V per cell, {soc_to_v(_floor) * _ns:.2f} V pack; "
        f"start {_start * 100:.0f}% ≈ {soc_to_v(_start):.2f} V per cell, {soc_to_v(_start) * _ns:.2f} V pack; "
        f"the {ui_uvlo.value:g} V lockout is about {_uvlo_soc * 100:.0f}% SoC. Rested open-circuit volts from a generic 18650 curve, provisional."
    )
    return (volts_line,)


@app.cell
def _(
    BATTERY_CELLS,
    BATTERY_KEYS,
    SOLAR_CELLS,
    SOLAR_KEYS,
    mo,
    pd,
    ui_altitude,
    ui_am0,
    ui_attitude,
    ui_batt,
    ui_batt_ah,
    ui_batt_v,
    ui_beacon_policy,
    ui_cadence,
    ui_cap_day,
    ui_cap_orbit,
    ui_cell,
    ui_cell_area,
    ui_cell_impp,
    ui_cell_rated,
    ui_cell_spectrum,
    ui_cell_tc,
    ui_cell_temp,
    ui_cell_vmpp,
    ui_clock_end,
    ui_clock_start,
    ui_cubesat,
    ui_cw_cad,
    ui_cw_s,
    ui_cw_w,
    ui_dod,
    ui_eclipse_edge,
    ui_eff_3v3,
    ui_eff_5v,
    ui_eff_charge,
    ui_epoch,
    ui_faces_x,
    ui_faces_y,
    ui_faces_z,
    ui_gate_lit,
    ui_gate_nopass,
    ui_hdrm_s,
    ui_hdrm_w,
    ui_hold,
    ui_inclination,
    ui_lat,
    ui_listed,
    ui_loads,
    ui_lon,
    ui_lora_cad_deg,
    ui_lora_cad_nom,
    ui_lora_s,
    ui_lora_w,
    ui_ltdn,
    ui_min_el,
    ui_min_sun,
    ui_mod_parallel,
    ui_mod_series,
    ui_mod_u,
    ui_modules_z,
    ui_orbit_nth,
    ui_orbit_u0,
    ui_orbit_u1,
    ui_parallel,
    ui_pass_after,
    ui_pass_offset,
    ui_pay_mode,
    ui_radio_row,
    ui_reach,
    ui_region_e,
    ui_region_n,
    ui_region_s,
    ui_region_w,
    ui_rx_w,
    ui_safe_enter,
    ui_safe_exit,
    ui_scenario,
    ui_series,
    ui_share,
    ui_sim_days,
    ui_soc0,
    ui_station,
    ui_string_loss,
    ui_t1_cad,
    ui_t1_ms,
    ui_t2_cad,
    ui_t2_ms,
    ui_target_lat,
    ui_target_lon,
    ui_target_same,
    ui_tx_w,
    ui_uvlo,
    ui_window,
    volts_line,
):
    # Panel layout apart from the elements so it can read them. Left: what the
    # spacecraft is. Right: what it does. Only the inputs of the chosen
    # activation trigger are shown.
    _mode_help = {
        "Over a location": "Fires when the location is within this ground radius of the sub-satellite point; for an imager, half the swath.",
        "Over a region": "Fires inside a latitude–longitude box; west above east crosses the date line.",
        "Orbit position": "Angle from the ascending node, optionally every Nth orbit only.",
        "Fixed cadence": "Starts every N minutes from the epoch.",
        "Clock window": "A daily UTC window; an end before the start crosses midnight.",
        "During passes": "Starts during a ground contact, or after it ends, with an offset.",
        "Eclipse or sunlight": "An illumination window, or an eclipse edge for the active time.",
        "Listed": "One activation per line: hours from the epoch, duration in seconds.",
        "Always": "The payload column all day, subject to the gates.",
        "Never": "The payload stays off.",
    }
    _mode_inputs = {
        "Over a location": [ui_target_same, mo.accordion({"Separate location": mo.vstack([ui_target_lat, ui_target_lon])}), ui_reach],
        "Over a region": [ui_region_s, ui_region_n, ui_region_w, ui_region_e],
        "Orbit position": [ui_orbit_u0, ui_orbit_u1, ui_orbit_nth],
        "Fixed cadence": [ui_cadence],
        "Clock window": [ui_clock_start, ui_clock_end],
        "During passes": [ui_pass_after, ui_pass_offset],
        "Eclipse or sunlight": [ui_eclipse_edge],
        "Listed": [ui_listed],
        "Always": [],
        "Never": [],
    }[ui_pay_mode.value]
    _mode_inputs = [mo.md(_mode_help[ui_pay_mode.value])] + _mode_inputs
    _left = mo.vstack(
        [
            mo.md("**Schedule**"),
            ui_scenario,
            mo.md("Nominal follows the timeline with a safe-mode fallback; Safe and Degraded hold their load column all day."),
            mo.md("**Orbit**"),
            ui_altitude,
            ui_inclination,
            ui_ltdn,
            ui_epoch,
            ui_sim_days,
            mo.md("**Generation**"),
            ui_cell,
            mo.accordion({"Custom cell": mo.vstack([ui_cell_vmpp, ui_cell_impp, ui_cell_tc, ui_cell_rated, ui_cell_spectrum, ui_cell_area])}),
            mo.md("A module is S cells per string and P parallel strings behind one diode. Its length sets how many fit along a side face."),
            ui_mod_series,
            ui_mod_parallel,
            ui_mod_u,
            ui_cubesat,
            ui_faces_x,
            ui_faces_y,
            ui_faces_z,
            ui_modules_z,
            ui_attitude,
            mo.accordion({"Environment and losses": mo.vstack([ui_am0, ui_cell_temp, ui_string_loss])}),
            mo.md("**Storage**"),
            ui_batt,
            mo.accordion({"Custom cell": mo.vstack([ui_batt_v, ui_batt_ah])}),
            ui_series,
            ui_parallel,
            ui_dod,
            ui_soc0,
            volts_line,
            mo.md("The initial charge starts the run; the allowed depth of discharge sets the floor."),
            mo.accordion({"Efficiencies and thresholds": mo.vstack([ui_eff_charge, ui_eff_5v, ui_eff_3v3, ui_uvlo, ui_safe_enter, ui_safe_exit])}),
        ],
        gap=0.5,
    )
    _right = mo.vstack(
        [
            mo.md("**Ground station**"),
            ui_station,
            mo.accordion({"Custom station": mo.vstack([ui_lat, ui_lon])}),
            ui_min_el,
            mo.md("**Payload**"),
            ui_pay_mode,
            *_mode_inputs,
            ui_hold,
            ui_window,
            ui_gate_lit,
            *([ui_min_sun] if ui_pay_mode.value == "Over a location" else []),
            ui_gate_nopass,
            ui_cap_day,
            ui_cap_orbit,
            mo.md("**Radio**"),
            ui_tx_w,
            ui_rx_w,
            ui_share,
            ui_radio_row,
            mo.md("Pass draw for the selected row = share × TX + (1 – share) × RX, replacing its table cell."),
            mo.md("**Beacon**"),
            ui_beacon_policy,
            mo.md("CW and the data tiers follow this policy; the LoRa backstop has its own cadences."),
            ui_cw_s,
            ui_cw_w,
            ui_cw_cad,
            mo.accordion({"Tiers 1 and 2, LoRa backstop": mo.vstack([ui_t1_ms, ui_t1_cad, ui_t2_ms, ui_t2_cad, ui_lora_s, ui_lora_w, ui_lora_cad_nom, ui_lora_cad_deg])}),
            mo.md("**One-shot**"),
            ui_hdrm_w,
            ui_hdrm_s,
        ],
        gap=0.5,
    )
    knobs_wide = mo.hstack([_left, _right], justify="start", gap=2, wrap=True, widths="equal")
    knobs_tall = mo.vstack([_left, _right], gap=0.5)

    loads_block = mo.vstack(
        [
            mo.md("**Loads** – average watts per mode. Pass and payload override nominal per consumer; safe and degraded replace the row. Rails: VBAT, 5V, 3V3."),
            ui_loads,
        ]
    )
    _cells = pd.DataFrame([[_k, *_v] for _k, _v in SOLAR_CELLS.items()], columns=SOLAR_KEYS)
    _batts = pd.DataFrame([[_k, *_v] for _k, _v in BATTERY_CELLS.items()], columns=BATTERY_KEYS)
    library_block = mo.accordion(
        {
            "Cell Libraries": mo.vstack(
                [
                    mo.ui.table(_cells, selection=None, show_column_summaries=False, pagination=False),
                    mo.ui.table(_batts, selection=None, show_column_summaries=False, pagination=False),
                ]
            )
        }
    )
    return knobs_tall, knobs_wide, library_block, loads_block


@app.cell
def _(knobs_tall, mo, ui_sidebar):
    mo.sidebar([mo.md("### Control Panel"), knobs_tall], width="360px") if ui_sidebar.value else None
    return


@app.cell
def _(knobs_wide, library_block, loads_block, mo, profile_block, ui_sidebar):
    mo.vstack(
        [
            mo.md("## Control Panel"),
            profile_block,
            ui_sidebar,
            mo.md("The knobs are in the sidebar. Turn this off to bring them back here.") if ui_sidebar.value else knobs_wide,
            loads_block,
            library_block,
        ]
    )
    return


@app.cell
def _(
    BATTERY_CELLS,
    CUBESAT_UNITS,
    P,
    SOLAR_CELLS,
    SOLAR_CONST_W_M2,
    STATIONS,
    ui_altitude,
    ui_am0,
    ui_batt,
    ui_batt_ah,
    ui_batt_v,
    ui_cell,
    ui_cell_area,
    ui_cell_impp,
    ui_cell_rated,
    ui_cell_spectrum,
    ui_cell_tc,
    ui_cell_temp,
    ui_cell_vmpp,
    ui_cubesat,
    ui_dod,
    ui_faces_x,
    ui_faces_y,
    ui_faces_z,
    ui_lat,
    ui_lon,
    ui_mod_parallel,
    ui_mod_series,
    ui_mod_u,
    ui_modules_z,
    ui_parallel,
    ui_series,
    ui_station,
    ui_string_loss,
    ui_target_lat,
    ui_target_lon,
    ui_target_same,
):
    # Resolve presets and custom fields into plain numbers.
    h_km = float(ui_altitude.value)

    if ui_cell.value == "Custom":
        cell = dict(name="Custom", vmpp=float(ui_cell_vmpp.value), impp=float(ui_cell_impp.value), tc=float(ui_cell_tc.value), rated=float(ui_cell_rated.value), spectrum=ui_cell_spectrum.value, area_cm2=float(ui_cell_area.value), status="custom")
    else:
        _c = SOLAR_CELLS[ui_cell.value]
        cell = dict(name=ui_cell.value, vmpp=_c[0], impp=_c[1], tc=_c[6], rated=_c[7], spectrum=_c[8], area_cm2=_c[5], status=_c[9])
    cell["pmpp_w"] = cell["vmpp"] * cell["impp"]
    # Rated power to a space power at the given temperature, per cell. A cell
    # rated under AM0 is only rescaled from its rated irradiance to the solar
    # constant; an AM1.5-rated cell also takes the spectral factor.
    _temp_factor = 1 + cell["tc"] / 100 * (float(ui_cell_temp.value) - 25)
    _spectral = float(ui_am0.value) if cell["spectrum"] != "AM0" else 1.0
    cell_space_w = cell["pmpp_w"] * SOLAR_CONST_W_M2 / cell["rated"] * _spectral * max(_temp_factor, 0.0) * (1 - float(ui_string_loss.value) / 100)
    mod_series, mod_parallel = int(ui_mod_series.value), int(ui_mod_parallel.value)
    cells_per_module = mod_series * mod_parallel
    module_w = cell_space_w * cells_per_module
    # Module MPP voltage, hot, for the charger headroom check; the voltage
    # coefficient is taken as the power coefficient, which is close for silicon.
    module_vmpp_hot = cell["vmpp"] * mod_series * max(_temp_factor, 0.0)
    module_u = float(ui_mod_u.value)
    module_area_cm2 = module_u * 100.0  # 10 cm wide face × module length
    cells_area_cm2 = cells_per_module * cell["area_cm2"]

    _u = CUBESAT_UNITS[ui_cubesat.value]
    _side_modules = int(_u / module_u + 1e-9)
    module_too_long = module_u > _u + 1e-9
    z_face_overfull = ui_faces_z.value and int(ui_modules_z.value) * module_area_cm2 > 100.0 + 1e-9
    # Face normals in the body frame with +Z zenith, +X along velocity when
    # nadir-pointed. –Z carries the imager, +Z the boom root.
    face_modules = {
        "+X": _side_modules if ui_faces_x.value else 0,
        "-X": _side_modules if ui_faces_x.value else 0,
        "+Y": _side_modules if ui_faces_y.value else 0,
        "-Y": _side_modules if ui_faces_y.value else 0,
        "+Z": int(ui_modules_z.value) if ui_faces_z.value else 0,
        "-Z": int(ui_modules_z.value) if ui_faces_z.value else 0,
    }
    face_normal_w = {_f: _n * module_w for _f, _n in face_modules.items()}
    total_normal_w = sum(face_normal_w.values())
    total_modules = sum(face_modules.values())

    if ui_batt.value == "Custom":
        batt = dict(name="Custom", v=float(ui_batt_v.value), ah=float(ui_batt_ah.value), vmax=4.2, status="custom")
    else:
        _b = BATTERY_CELLS[ui_batt.value]
        batt = dict(name=ui_batt.value, v=_b[0], ah=_b[1], vmax=_b[2], status=_b[5])
    n_series, n_parallel = int(ui_series.value), int(ui_parallel.value)
    pack_wh = batt["v"] * batt["ah"] * n_series * n_parallel
    pack_v = batt["v"] * n_series
    float_v = batt["vmax"] * n_series
    usable_wh = pack_wh * float(ui_dod.value) / 100

    _st = STATIONS[ui_station.value]
    station_name = "Custom" if _st is None else ui_station.value.split(",")[0]
    station_lat = float(ui_lat.value) if _st is None else _st[0]
    station_lon = float(ui_lon.value) if _st is None else _st[1]
    if ui_target_same.value:
        target_lat, target_lon, target_name = station_lat, station_lon, station_name
    else:
        target_lat, target_lon, target_name = float(ui_target_lat.value), float(ui_target_lon.value), str(P("target", "name", "Custom") or "Custom")
    return (
        batt,
        cell,
        cell_space_w,
        cells_area_cm2,
        cells_per_module,
        face_modules,
        face_normal_w,
        float_v,
        h_km,
        mod_parallel,
        mod_series,
        module_area_cm2,
        module_too_long,
        module_u,
        module_vmpp_hot,
        module_w,
        pack_v,
        pack_wh,
        station_lat,
        station_lon,
        station_name,
        target_lat,
        target_lon,
        total_modules,
        total_normal_w,
        usable_wh,
        z_face_overfull,
    )


@app.cell
def _(
    R_EARTH_KM,
    dt,
    face_normal_w,
    h_km,
    np,
    station_lat,
    station_lon,
    target_lat,
    target_lon,
    ui_attitude,
    ui_epoch,
    ui_inclination,
    ui_ltdn,
    ui_min_el,
    ui_reach,
    ui_sim_days,
):
    # One timeline for everything. Two-body circular orbit with J2 nodal
    # regression from an epoch, RAAN set from the LTDN, GMST for Earth
    # rotation and the Astronomical Almanac low-precision Sun, at 10 s steps:
    # the optical payload tool's propagator, plus the link budget's station
    # elevation test and a per-face illumination model.
    MU = 398600.4418
    J2 = 1.08263e-3
    _a = R_EARTH_KM + h_km
    _n = np.sqrt(MU / _a**3)
    _inc = np.radians(float(ui_inclination.value))
    _raan_dot = -1.5 * _n * J2 * (R_EARTH_KM / _a) ** 2 * np.cos(_inc)
    period_min = 2 * np.pi / _n / 60

    try:
        epoch = dt.datetime.strptime(ui_epoch.value.strip(), "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        epoch_error = ""
    except ValueError:
        epoch = dt.datetime(2027, 6, 21, tzinfo=dt.timezone.utc)
        epoch_error = f"Epoch \"{ui_epoch.value}\" is not YYYY-MM-DD; using 2027-06-21."

    def _jd(when):
        return 2440587.5 + when.timestamp() / 86400

    def _sun_eci(jd):
        _d = jd - 2451545.0
        _g = np.radians((357.529 + 0.98560028 * _d) % 360)
        _q = (280.459 + 0.98564736 * _d) % 360
        _lam = np.radians((_q + 1.915 * np.sin(_g) + 0.020 * np.sin(2 * _g)) % 360)
        _eps = np.radians(23.439 - 0.00000036 * _d)
        return np.stack([np.cos(_lam), np.cos(_eps) * np.sin(_lam), np.sin(_eps) * np.sin(_lam)], axis=-1)

    def _gmst_rad(jd):
        _d = jd - 2451545.0
        return np.radians((280.46061837 + 360.98564736629 * _d) % 360)

    _jd0 = _jd(epoch)
    _sun0 = _sun_eci(_jd0)
    _ltan_h = (float(ui_ltdn.value) + 12) % 24
    _raan0 = np.arctan2(_sun0[1], _sun0[0]) + np.radians((_ltan_h - 12) * 15)

    step_s = 10.0
    sim_days = float(ui_sim_days.value)
    t_s = np.arange(0, sim_days * 86400, step_s)
    _u = _n * t_s
    _raan = _raan0 + _raan_dot * t_s
    _cu, _su, _cr, _sr, _ci, _si = np.cos(_u), np.sin(_u), np.cos(_raan), np.sin(_raan), np.cos(_inc), np.sin(_inc)
    # Position and velocity directions in ECI.
    r_hat = np.stack([_cu * _cr - _su * _sr * _ci, _cu * _sr + _su * _cr * _ci, _su * _si], axis=-1)
    v_hat = np.stack([-_su * _cr - _cu * _sr * _ci, -_su * _sr + _cu * _cr * _ci, _cu * _si], axis=-1)
    _jdt = _jd0 + t_s / 86400
    _gmst = _gmst_rad(_jdt)
    sun = _sun_eci(_jdt)

    # Sunlit: on the Sun side, or outside the cylindrical shadow.
    _along = np.einsum("ij,ij->i", r_hat, sun) * _a
    _perp = np.linalg.norm(r_hat * _a - _along[:, None] * sun, axis=1)
    sunlit = (_along > 0) | (_perp > R_EARTH_KM)

    # Per-face illumination. Nadir-pointed: body Z = zenith, X = velocity,
    # Y completes. Tumbling: every face sees a quarter of the Sun on average.
    # Sun-pointed: the largest populated face is held at the Sun.
    _faces = list(face_normal_w)
    _normals = {"+Z": r_hat, "-Z": -r_hat, "+X": v_hat, "-X": -v_hat}
    _y = np.cross(r_hat, v_hat)
    _normals["+Y"], _normals["-Y"] = _y, -_y
    if ui_attitude.value == "Nadir-pointed":
        face_cos = {_f: np.clip(np.einsum("ij,ij->i", _normals[_f], sun), 0, None) for _f in _faces}
    elif ui_attitude.value == "Sun-pointed":
        _best = max(_faces, key=lambda _f: face_normal_w[_f])
        face_cos = {_f: (np.ones(len(t_s)) if _f == _best else np.zeros(len(t_s))) for _f in _faces}
    else:
        face_cos = {_f: np.full(len(t_s), 0.25) for _f in _faces}
    gen_w = sum(face_normal_w[_f] * face_cos[_f] for _f in _faces) * sunlit

    # Station elevation in the Earth-fixed frame.
    def _ecef_unit(lat, lon):
        _la, _lo = np.radians(lat), np.radians(lon)
        return np.array([np.cos(_la) * np.cos(_lo), np.cos(_la) * np.sin(_lo), np.sin(_la)])

    _cg, _sg = np.cos(_gmst), np.sin(_gmst)
    r_ecef = np.stack([_cg * r_hat[:, 0] + _sg * r_hat[:, 1], -_sg * r_hat[:, 0] + _cg * r_hat[:, 1], r_hat[:, 2]], axis=-1) * _a
    _sv = _ecef_unit(station_lat, station_lon)
    _range = r_ecef - _sv * R_EARTH_KM
    elevation_deg = np.degrees(np.arcsin(np.einsum("ij,j->i", _range, _sv) / np.linalg.norm(_range, axis=1)))
    in_pass = elevation_deg >= float(ui_min_el.value)

    # Imaging target: within reach of the sub-satellite point and lit.
    _tv = _ecef_unit(target_lat, target_lon)
    _psi = np.arccos(np.clip(np.einsum("ij,j->i", r_ecef / _a, _tv), -1, 1))
    in_reach = _psi <= float(ui_reach.value) / R_EARTH_KM
    sun_ecef = np.stack([_cg * sun[:, 0] + _sg * sun[:, 1], -_sg * sun[:, 0] + _cg * sun[:, 1], sun[:, 2]], axis=-1)
    target_sun_el = np.degrees(np.arcsin(np.clip(sun_ecef @ _tv, -1, 1)))

    def runs(mask):
        _e = np.diff(np.concatenate([[0], mask.astype(int), [0]]))
        return list(zip(np.where(_e == 1)[0], np.where(_e == -1)[0]))

    _runs = runs

    passes = [dict(start=epoch + dt.timedelta(seconds=float(t_s[s0])), t0=float(t_s[s0]), t1=float(t_s[min(e0, len(t_s) - 1)]), duration_min=(e0 - s0) * step_s / 60, max_el=float(elevation_deg[s0:e0].max())) for s0, e0 in _runs(in_pass)]
    # Sub-satellite point and orbit phase for the region and orbit triggers.
    sub_lat = np.degrees(np.arcsin(r_ecef[:, 2] / _a))
    sub_lon = np.degrees(np.arctan2(r_ecef[:, 1], r_ecef[:, 0]))
    arg_lat_deg = np.degrees(_u) % 360
    orbit_index = np.floor(_u / (2 * np.pi)).astype(int)
    eclipse_runs = [(float(t_s[s0]), float(t_s[min(e0, len(t_s) - 1)])) for s0, e0 in _runs(~sunlit)]
    eclipse_fraction = float(1 - sunlit.mean())
    passes_per_day = len(passes) / sim_days
    contact_min_per_day = sum(p["duration_min"] for p in passes) / sim_days
    return (
        arg_lat_deg,
        contact_min_per_day,
        eclipse_fraction,
        eclipse_runs,
        epoch,
        epoch_error,
        face_cos,
        gen_w,
        in_pass,
        in_reach,
        orbit_index,
        passes,
        passes_per_day,
        period_min,
        runs,
        sim_days,
        step_s,
        sub_lat,
        sub_lon,
        sunlit,
        t_s,
        target_sun_el,
    )


@app.cell
def _(
    RAILS,
    ui_beacon_policy,
    ui_cw_cad,
    ui_cw_s,
    ui_cw_w,
    ui_eff_3v3,
    ui_eff_5v,
    ui_hdrm_s,
    ui_hdrm_w,
    ui_loads,
    ui_lora_cad_deg,
    ui_lora_cad_nom,
    ui_lora_s,
    ui_lora_w,
    ui_radio_row,
    ui_rx_w,
    ui_share,
    ui_t1_cad,
    ui_t1_ms,
    ui_t2_cad,
    ui_t2_ms,
    ui_tx_w,
):
    # Loads per mode from the table, referred to the battery through the rail
    # efficiencies, plus the beacon lines and the one-shot release.
    rail_eff = {"VBAT": 1.0, "5V": float(ui_eff_5v.value) / 100, "3V3": float(ui_eff_3v3.value) / 100}
    MODES = ["Safe", "Nominal", "Pass", "Payload", "Degraded"]
    _mode_cols = {"Safe": "Safe (W)", "Nominal": "Nominal (W)", "Pass": "Pass (W)", "Payload": "Payload (W)", "Degraded": "Degraded (W)"}

    loads = []
    unknown_rails = []
    invalid_loads = []

    def _watts(name, col, v):
        # Finite and non-negative or it does not enter the balance.
        try:
            _f = float(v)
        except (TypeError, ValueError):
            _f = float("nan")
        if _f != _f or _f < 0 or _f in (float("inf"), float("-inf")):
            invalid_loads.append(f"{name}, {col}")
            return 0.0
        return _f

    _share = float(ui_share.value) / 100
    radio_pass_w = _share * float(ui_tx_w.value) + (1 - _share) * float(ui_rx_w.value)
    radio_name = ui_radio_row.value if ui_radio_row.value != "None" else ""
    for _, _r in ui_loads.value.iterrows():
        _name = str(_r["Consumer"]).strip()
        if not _name:
            continue
        _rail = str(_r["Rail"]).strip().upper()
        if _rail not in RAILS:
            unknown_rails.append(f"{_name}: {_rail}")
            _rail = "VBAT"
        _w = {_m: _watts(_name, _c, _r[_c]) for _m, _c in _mode_cols.items()}
        if _name == radio_name:
            _w["Pass"] = radio_pass_w
        loads.append(
            dict(
                name=_name,
                node=str(_r["Node"]),
                rail=_rail,
                peak_w=_watts(_name, "Peak (W)", _r["Peak (W)"]),
                status=str(_r["Status"]).strip().lower(),
                note=str(_r["Note"]),
                w=_w,
                batt_w={_m: _v / rail_eff[_rail] for _m, _v in _w.items()},
            )
        )
    placeholder_loads = [_l["name"] for _l in loads if _l["status"] == "placeholder"]

    # Beacon average draws. CW and the data tiers ride the radio node; the
    # policy decides in which modes they run. "Safe mode and commissioning"
    # keeps them to the safe column, which the nominal scenario only uses
    # while in the safe-mode fallback. The LoRa backstop has its own cadence
    # per state.
    def _avg(on_s, cadence_s, power_w):
        return power_w * on_s / cadence_s if cadence_s > 0 else 0.0

    cw_avg_w = _avg(float(ui_cw_s.value), float(ui_cw_cad.value), float(ui_cw_w.value))
    tier_avg_w = _avg(float(ui_t1_ms.value) / 1000, float(ui_t1_cad.value), float(ui_tx_w.value)) + _avg(float(ui_t2_ms.value) / 1000, float(ui_t2_cad.value), float(ui_tx_w.value))
    lora_nom_w = _avg(float(ui_lora_s.value), float(ui_lora_cad_nom.value), float(ui_lora_w.value))
    lora_deg_w = _avg(float(ui_lora_s.value), float(ui_lora_cad_deg.value), float(ui_lora_w.value))
    _policy = ui_beacon_policy.value
    _in_safe = 0.0 if _policy == "Off" else 1.0
    _in_nominal = 1.0 if _policy == "Always while the radio is up" else 0.0
    beacon_rows = [
        dict(name="Beacon, CW tier 0 (radio node)", rail="VBAT", w={"Safe": cw_avg_w * _in_safe, "Nominal": cw_avg_w * _in_nominal, "Pass": cw_avg_w * _in_nominal, "Payload": cw_avg_w * _in_nominal, "Degraded": 0.0}),
        dict(name="Beacon, tiers 1 and 2 (radio node)", rail="VBAT", w={"Safe": tier_avg_w * _in_safe, "Nominal": tier_avg_w * _in_nominal, "Pass": 0.0, "Payload": tier_avg_w * _in_nominal, "Degraded": 0.0}),
        dict(name="Beacon, LoRa backstop (function board)", rail="VBAT", w={"Safe": lora_nom_w, "Nominal": lora_nom_w, "Pass": lora_nom_w, "Payload": lora_nom_w, "Degraded": lora_deg_w}),
    ]
    for _b in beacon_rows:
        _b["batt_w"] = dict(_b["w"])
    # The CW card prices the beacon running all day, whatever the policy,
    # because that is the safe-mode and commissioning cost.
    cw_wh_day = cw_avg_w * 24

    # Mode totals at the battery. Pass and imaging are per-consumer overrides
    # of nominal, so their totals here are "everyone in that mode at once".
    def _total(mode, key="batt_w"):
        return sum(_l[key][mode] for _l in loads + beacon_rows)

    mode_total_w = {_m: _total(_m) for _m in MODES}
    # What a pass minute and an activation cost over nominal. A column is the
    # draw in that mode, so a consumer may also drop below nominal (the tier
    # beacons during a pass); the increments carry the sign.
    pass_increment_w = mode_total_w["Pass"] - mode_total_w["Nominal"]
    imaging_increment_w = mode_total_w["Payload"] - mode_total_w["Nominal"]
    hdrm_wh = float(ui_hdrm_w.value) * float(ui_hdrm_s.value) / 3600
    return (
        MODES,
        beacon_rows,
        cw_wh_day,
        hdrm_wh,
        imaging_increment_w,
        invalid_loads,
        loads,
        mode_total_w,
        pass_increment_w,
        placeholder_loads,
        radio_name,
        rail_eff,
        unknown_rails,
    )


@app.cell
def _(
    arg_lat_deg,
    dt,
    epoch,
    in_pass,
    in_reach,
    np,
    orbit_index,
    passes,
    runs,
    sim_days,
    step_s,
    sub_lat,
    sub_lon,
    sunlit,
    t_s,
    target_sun_el,
    ui_cadence,
    ui_cap_day,
    ui_cap_orbit,
    ui_clock_end,
    ui_clock_start,
    ui_eclipse_edge,
    ui_gate_lit,
    ui_gate_nopass,
    ui_hold,
    ui_listed,
    ui_min_sun,
    ui_orbit_nth,
    ui_orbit_u0,
    ui_orbit_u1,
    ui_pass_after,
    ui_pass_offset,
    ui_pay_mode,
    ui_region_e,
    ui_region_n,
    ui_region_s,
    ui_region_w,
    ui_window,
):
    # Payload activations. Every trigger yields candidate windows (start,
    # end) on the timeline; the gates and caps then decide which are taken,
    # and the taken ones become the activation mask the schedule consumes.
    _n = len(t_s)
    _mode = ui_pay_mode.value
    _active = float(ui_window.value)
    _hold = bool(ui_hold.value)
    listed_error = ""

    def _window_from_runs(mask, at="start"):
        # A run of the trigger becomes one window: the whole run when
        # holding, otherwise the active time from the run start (or centred).
        # A run over samples s0..e0-1 spans t[s0] to t[e0-1] + step.
        _out = []
        for s0, e0 in runs(mask):
            _t0, _t1 = float(t_s[s0]), float(t_s[e0 - 1]) + step_s
            if _hold:
                _out.append((_t0, _t1))
            elif at == "centre":
                _mid = (_t0 + _t1) / 2
                _out.append((_mid - _active / 2, _mid + _active / 2))
            else:
                _out.append((_t0, _t0 + _active))
        return _out

    if _mode == "Over a location":
        candidates = _window_from_runs(in_reach, at="centre")
    elif _mode == "Over a region":
        _lat_ok = (sub_lat >= float(ui_region_s.value)) & (sub_lat <= float(ui_region_n.value))
        _w, _e = float(ui_region_w.value), float(ui_region_e.value)
        _lon_ok = ((sub_lon >= _w) & (sub_lon <= _e)) if _w <= _e else ((sub_lon >= _w) | (sub_lon <= _e))
        candidates = _window_from_runs(_lat_ok & _lon_ok)
    elif _mode == "Orbit position":
        _u0, _u1 = float(ui_orbit_u0.value), float(ui_orbit_u1.value)
        _in = ((arg_lat_deg >= _u0) & (arg_lat_deg <= _u1)) if _u0 <= _u1 else ((arg_lat_deg >= _u0) | (arg_lat_deg <= _u1))
        _in &= orbit_index % int(ui_orbit_nth.value) == 0
        candidates = _window_from_runs(_in)
    elif _mode == "Fixed cadence":
        _p = float(ui_cadence.value) * 60
        candidates = [(_t, _t + _active) for _t in np.arange(0, sim_days * 86400, _p)]
    elif _mode == "Clock window":
        _h = (t_s + epoch.hour * 3600 + epoch.minute * 60) % 86400 / 3600
        _c0, _c1 = float(ui_clock_start.value), float(ui_clock_end.value)
        _in = ((_h >= _c0) & (_h < _c1)) if _c0 <= _c1 else ((_h >= _c0) | (_h < _c1))
        candidates = _window_from_runs(_in)
    elif _mode == "During passes":
        _off = float(ui_pass_offset.value)
        if ui_pass_after.value:
            candidates = [(_p["t1"] + _off, _p["t1"] + _off + _active) for _p in passes]
        elif _hold:
            candidates = [(_p["t0"] + _off, _p["t1"]) for _p in passes]
        else:
            candidates = [(_p["t0"] + _off, _p["t0"] + _off + _active) for _p in passes]
    elif _mode == "Eclipse or sunlight":
        _edge = ui_eclipse_edge.value
        if _edge == "Throughout eclipse":
            candidates = _window_from_runs(~sunlit)
        elif _edge == "Throughout sunlight":
            candidates = _window_from_runs(sunlit)
        else:
            _ecl = runs(~sunlit)
            _starts = [float(t_s[s0]) for s0, _ in _ecl] if _edge == "At eclipse entry" else [float(t_s[min(e0, _n - 1)]) for _, e0 in _ecl]
            candidates = [(_t, _t + _active) for _t in _starts]
    elif _mode == "Listed":
        candidates = []
        for _line in str(ui_listed.value).splitlines():
            _line = _line.strip()
            if not _line:
                continue
            try:
                _hh, _dd = [float(_x) for _x in _line.replace(";", ",").split(",")[:2]]
                if not (_hh == _hh and _dd == _dd) or _dd <= 0 or _hh < 0:
                    raise ValueError
                candidates.append((_hh * 3600, _hh * 3600 + _dd))
            except ValueError:
                listed_error = (listed_error + " " if listed_error else "") + f"Could not read \"{_line}\" as non-negative hours and a positive duration in seconds."
    elif _mode == "Always":
        candidates = [(0.0, sim_days * 86400)]
    else:  # Never
        candidates = []

    # Gates and caps, in order of the candidates.
    _gate_lit = bool(ui_gate_lit.value)
    _cap_day, _cap_orbit = int(ui_cap_day.value), int(ui_cap_orbit.value)
    _per_day, _per_orbit = {}, {}
    _pass_mask = in_pass
    # Coverage of each sample by an activation, as a fraction of the step, so
    # an activation shorter than a step costs what it lasts.
    act_frac = np.zeros(_n)
    activations = []
    _lit_mask = (target_sun_el >= float(ui_min_sun.value)) if _mode == "Over a location" else sunlit
    for _t0, _t1 in sorted(candidates):
        _t0 = max(_t0, 0.0)
        _t1 = min(_t1, sim_days * 86400)
        if _t1 <= _t0:
            continue
        # Samples touched: sample i covers [t_i, t_i + step).
        _i0 = int(np.searchsorted(t_s, _t0, side="right") - 1)
        _i1 = int(np.searchsorted(t_s, _t1, side="left"))
        _i0, _i1 = max(_i0, 0), max(min(_i1, _n), _i0 + 1)
        _cover = np.clip(np.minimum(t_s[_i0:_i1] + step_s, _t1) - np.maximum(t_s[_i0:_i1], _t0), 0, step_s) / step_s
        # Lit across the whole activation, not only at its start.
        _lit = bool(_lit_mask[_i0:_i1].all())
        _reason = ""
        _day, _orb = int(_t0 // 86400), int(orbit_index[_i0])
        if _gate_lit and not _lit:
            _reason = "not lit"
        elif bool(ui_gate_nopass.value) and _pass_mask[_i0:_i1].any():
            _reason = "overlaps a pass"
        elif _cap_day and _per_day.get(_day, 0) >= _cap_day:
            _reason = "day cap"
        elif _cap_orbit and _per_orbit.get(_orb, 0) >= _cap_orbit:
            _reason = "orbit cap"
        elif (act_frac[_i0:_i1] + _cover > 1 + 1e-9).any():
            _reason = "overlaps another"
        _taken = _reason == ""
        if _taken:
            _per_day[_day] = _per_day.get(_day, 0) + 1
            _per_orbit[_orb] = _per_orbit.get(_orb, 0) + 1
            act_frac[_i0:_i1] += _cover
        activations.append(dict(start=epoch + dt.timedelta(seconds=_t0), t0=_t0, t1=_t1, i0=_i0, i1=_i1, duration_s=_t1 - _t0, lit=_lit, taken=_taken, reason=_reason))
    act_frac = np.clip(act_frac, 0, 1)
    in_activation = act_frac > 0
    activations_scheduled = sum(1 for _a in activations if _a["taken"])
    active_min_per_day = float(act_frac.mean() * 24 * 60)
    _taken_durations = [_a["duration_s"] for _a in activations if _a["taken"]]
    # What one activation lasts, for pricing: the scheduled ones' mean, else
    # the active-time setting.
    activation_duration_s = float(np.mean(_taken_durations)) if _taken_durations else float(ui_window.value)
    return (
        act_frac,
        activation_duration_s,
        activations,
        activations_scheduled,
        active_min_per_day,
        in_activation,
        listed_error,
    )


@app.cell
def _(
    act_frac,
    activation_duration_s,
    activations,
    activations_scheduled,
    beacon_rows,
    gen_w,
    hdrm_wh,
    imaging_increment_w,
    in_activation,
    in_pass,
    loads,
    mode_total_w,
    np,
    pack_wh,
    pass_increment_w,
    sim_days,
    step_s,
    t_s,
    ui_dod,
    ui_eff_charge,
    ui_safe_enter,
    ui_safe_exit,
    ui_scenario,
    ui_soc0,
):
    # Schedule and state of charge. A column is the draw in that mode: pass
    # samples take the Pass column, activation samples the Payload column, the
    # larger of the two per consumer when both apply, everything else the
    # Nominal column. Safe and degraded scenarios hold their column all day.
    # In the nominal scenario a low state of charge drops the spacecraft into
    # safe mode until it recovers, with hysteresis.
    _n = len(t_s)
    _rows = loads + beacon_rows
    in_imaging = in_activation
    _nom = np.array([_l["batt_w"]["Nominal"] for _l in _rows])
    _pas = np.array([_l["batt_w"]["Pass"] for _l in _rows])
    _pay = np.array([_l["batt_w"]["Payload"] for _l in _rows])
    load_nominal_w = np.full(_n, _nom.sum())
    # Pass samples take the pass column; an activation adds its increment in
    # proportion to how much of the sample it covers.
    _pass_inc = (_pas - _nom).sum()
    _pay_inc_alone = (_pay - _nom).sum()
    _pay_inc_in_pass = (np.maximum(_pas, _pay) - _pas).sum()
    load_sched_w = load_nominal_w + in_pass * _pass_inc + act_frac * np.where(in_pass, _pay_inc_in_pass, _pay_inc_alone)
    safe_w = mode_total_w["Safe"]
    degraded_w = mode_total_w["Degraded"]

    _eta = float(ui_eff_charge.value) / 100
    gen_batt_w = gen_w * _eta
    _dt_h = step_s / 3600
    soc_floor = 1 - float(ui_dod.value) / 100
    _enter, _exit = float(ui_safe_enter.value) / 100, float(ui_safe_exit.value) / 100
    threshold_error = _enter >= _exit
    if threshold_error:
        _exit = min(_enter + 0.1, 1.0)

    scenario = ui_scenario.value
    if scenario == "Safe":
        load_used_w = np.full(_n, safe_w)
    elif scenario == "Degraded":
        load_used_w = np.full(_n, degraded_w)
    else:
        load_used_w = load_sched_w

    soc = np.empty(_n)
    _e = pack_wh * float(ui_soc0.value) / 100
    _in_safe = False
    in_safe = np.zeros(_n, dtype=bool)
    for _i in range(_n):
        _load = load_used_w[_i]
        if scenario == "Nominal":
            _s = _e / pack_wh
            if _in_safe and _s >= _exit:
                _in_safe = False
            elif not _in_safe and _s < _enter:
                _in_safe = True
            if _in_safe:
                _load = safe_w
                in_safe[_i] = True
        _e = min(max(_e + (gen_batt_w[_i] - _load) * _dt_h, 0.0), pack_wh)
        soc[_i] = _e / pack_wh
    load_actual_w = np.where(in_safe, safe_w, load_used_w)
    safe_hours = float(in_safe.sum() * step_s / 3600)

    # Activations completed: scheduled ones whose every sample ran in the
    # nominal scenario outside safe mode.
    for _a in activations:
        _a["completed"] = bool(_a["taken"] and scenario == "Nominal" and not in_safe[_a["i0"]:_a["i1"]].any())
    activations_completed = sum(1 for _a in activations if _a["completed"])
    frames_per_day_taken = activations_scheduled / sim_days
    completed_per_day = activations_completed / sim_days
    lit_accesses = sum(1 for _a in activations if _a["lit"])

    # Daily energies and the headline figures. The requested margin is the
    # scheduled day without load shedding; the run margin is what happened.
    gen_wh_day = float(gen_batt_w.mean() * 24)
    load_wh_day = float(load_actual_w.mean() * 24)
    sched_wh_day = float(load_sched_w.mean() * 24) if scenario == "Nominal" else float(load_used_w.mean() * 24)
    margin_w = float(gen_batt_w.mean() - load_actual_w.mean())
    requested_margin_w = float(gen_batt_w.mean() - sched_wh_day / 24)
    min_soc = float(soc.min())
    end_soc = float(soc[-1])
    below_floor = bool(min_soc < soc_floor)
    # What the battery can afford beyond a day at nominal watts. Each figure
    # spends the whole surplus, so they are independent maxima, not a pair.
    _base_wh_day = float(load_nominal_w.mean() * 24)
    _surplus_wh = gen_wh_day - _base_wh_day
    base_exceeds = _surplus_wh < 0
    if base_exceeds:
        sustainable_pass_min = 0.0
        sustainable_frames = 0.0
    else:
        sustainable_pass_min = float(_surplus_wh / pass_increment_w * 60) if pass_increment_w > 0 else float("inf")
        _frame_wh = imaging_increment_w * activation_duration_s / 3600
        sustainable_frames = float(_surplus_wh / _frame_wh) if _frame_wh > 0 else float("inf")
    imaging_min_per_day = float(act_frac.mean() * 24 * 60)
    degraded_margin_w = float(gen_batt_w.mean() - degraded_w)
    safe_margin_w = float(gen_batt_w.mean() - safe_w)
    hdrm_soc_pct = hdrm_wh / pack_wh * 100
    return (
        activations_completed,
        base_exceeds,
        below_floor,
        completed_per_day,
        degraded_margin_w,
        end_soc,
        frames_per_day_taken,
        gen_wh_day,
        hdrm_soc_pct,
        in_imaging,
        in_safe,
        load_actual_w,
        load_sched_w,
        load_wh_day,
        margin_w,
        min_soc,
        requested_margin_w,
        safe_hours,
        safe_margin_w,
        scenario,
        sched_wh_day,
        soc,
        soc_floor,
        sustainable_frames,
        sustainable_pass_min,
        threshold_error,
    )


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

    def style_chart(chart):
        return (
            chart.configure(font=FONT, background="transparent")
            .configure_axis(grid=False, labelColor=TEXT, titleColor=TEXT, domainColor=MUTED, tickColor=MUTED)
            .configure_legend(labelColor=TEXT, titleColor=TEXT)
            .configure_title(color=TEXT, anchor="start", fontWeight="normal")
            .configure_view(strokeWidth=0)
        )

    def rule_y(value, dashed=True):
        return alt.Chart(alt.Data(values=[{"y": value}])).mark_rule(strokeDash=[6, 4] if dashed else [2, 2], color=MUTED).encode(y="y:Q")

    return PALETTE, rule_y, style_chart


@app.cell
def _(
    P,
    PH,
    activation_duration_s,
    activations_completed,
    activations_scheduled,
    base_exceeds,
    below_floor,
    cell,
    cells_area_cm2,
    cells_per_module,
    completed_per_day,
    contact_min_per_day,
    cw_wh_day,
    degraded_margin_w,
    eclipse_fraction,
    epoch_error,
    float_v,
    fmt_num,
    frames_per_day_taken,
    gen_wh_day,
    hdrm_soc_pct,
    invalid_loads,
    listed_error,
    margin_w,
    min_soc,
    mo,
    module_area_cm2,
    module_too_long,
    module_u,
    module_vmpp_hot,
    pack_wh,
    passes_per_day,
    placeholder_loads,
    profile_warnings,
    radio_name,
    requested_margin_w,
    safe_hours,
    safe_margin_w,
    scenario,
    sched_wh_day,
    soc_floor,
    sustainable_frames,
    sustainable_pass_min,
    threshold_error,
    ui_cubesat,
    ui_modules_z,
    ui_pay_mode,
    unknown_rails,
    usable_wh,
    z_face_overfull,
):
    def _pm(x):
        return f"{'+' if x >= 0 else '–'}{fmt_num(abs(x), 2)} W"

    def _fin(x, digits=1):
        return "unlimited" if x == float("inf") else fmt_num(x, digits)

    _cards = [
        mo.stat(label="Requested margin", value=_pm(requested_margin_w), caption=f"{fmt_num(gen_wh_day, 1)} in / {fmt_num(sched_wh_day, 1)} Wh/day asked; after safe-mode shedding {_pm(margin_w)}", bordered=True),
        mo.stat(label="Worst state of charge", value=f"{min_soc * 100:.0f}%", caption=f"Floor {soc_floor * 100:.0f}%; pack {fmt_num(pack_wh, 1)} Wh, {fmt_num(usable_wh, 1)} Wh usable", bordered=True),
        mo.stat(label="Sustainable pass minutes", value=f"{_fin(sustainable_pass_min, 0)} /day", caption=f"{fmt_num(contact_min_per_day, 1)} min/day offered by {passes_per_day:.2f} passes", bordered=True),
        mo.stat(label="Sustainable activations", value=f"{_fin(sustainable_frames, 1)} /day", caption=f"{frames_per_day_taken:.2f} scheduled, {completed_per_day:.2f} completed per day; {fmt_num(activation_duration_s, 0)} s each", bordered=True),
        mo.stat(label="CW beacon, all day", value=f"{fmt_num(cw_wh_day, 2)} Wh/day", caption=f"{cw_wh_day / gen_wh_day * 100:.0f}% of generation" if gen_wh_day > 0 else "no generation", bordered=True),
        mo.stat(label="Degraded mode", value=_pm(degraded_margin_w), caption="closes" if degraded_margin_w >= 0 else "does not close", bordered=True),
    ]
    _items = [
        mo.md("## Headline Numbers"),
        mo.hstack(_cards[0:2], widths="equal", gap=1),
        mo.hstack(_cards[2:4], widths="equal", gap=1),
        mo.hstack(_cards[4:6], widths="equal", gap=1),
        mo.md("The pass and activation allowances each spend the whole nominal surplus; they are independent maxima."),
    ]

    _callouts = []
    # Cross-checks against a sibling's results, when its profile carried them:
    # the link budget's eight-phase pass statistics against this run's single
    # phase, and its usable volume against what the affordable pass minutes
    # would carry; the optical payload's accesses against the activations.
    if PH("results.link_budget", "passes_per_day"):
        _lb_p = float(P("results.link_budget", "passes_per_day", 0.0))
        _lb_m = float(P("results.link_budget", "contact_min_per_day", 0.0))
        _text = (
            f"The link budget profile averages {_lb_p:.2f} passes and {fmt_num(_lb_m, 1)} contact minutes a day over eight orbit phases; "
            f"this run's single phase gives {passes_per_day:.2f} and {fmt_num(contact_min_per_day, 1)}. "
        )
        if _lb_m > 0 and sustainable_pass_min != float("inf"):
            _text += f"The battery affords {_fin(sustainable_pass_min, 0)} of the link budget's {fmt_num(_lb_m, 0)} minutes" + (", so its usable volume cannot all be transmitted." if sustainable_pass_min < _lb_m else ".")
        _callouts.append(mo.callout(mo.md(_text), kind="warn" if _lb_m > 0 and sustainable_pass_min < _lb_m else "info", title="Passes Against the Link Budget"))
    if PH("results.optical_payload", "accesses_per_day"):
        _op_a = float(P("results.optical_payload", "accesses_per_day", 0.0))
        _op_l = float(P("results.optical_payload", "lit_accesses_per_day", _op_a))
        _callouts.append(
            mo.callout(
                mo.md(
                    f"The optical payload profile found {_op_a:.2f} accesses a day over its target, {_op_l:.2f} of them lit; "
                    f"this run schedules {frames_per_day_taken:.2f} activations a day and the battery affords {_fin(sustainable_frames, 1)}."
                ),
                kind="warn" if sustainable_frames < _op_l else "info",
                title="Accesses Against the Optical Payload",
            )
        )
    if epoch_error:
        _callouts.append(mo.callout(mo.md(epoch_error), kind="warn", title="Epoch"))
    if unknown_rails:
        _callouts.append(mo.callout(mo.md("Rails must be VBAT, 5V or 3V3; these rows were taken as VBAT: " + ", ".join(unknown_rails)), kind="warn", title="Unknown Rail"))
    if invalid_loads:
        _callouts.append(mo.callout(mo.md("Watts must be finite and not negative; these cells were taken as 0: " + ", ".join(invalid_loads[:8]) + (" and more" if len(invalid_loads) > 8 else "")), kind="warn", title="Invalid Load Values"))
    if threshold_error:
        _callouts.append(mo.callout(mo.md("Exit must exceed entry. This run uses entry + 10 points, capped at 100%."), kind="warn", title="Safe-Mode Thresholds"))
    if listed_error:
        _callouts.append(mo.callout(mo.md(listed_error), kind="warn", title="Listed Activations"))
    if profile_warnings:
        _callouts.append(mo.callout(mo.md("These profile values were not numbers and fell back to the defaults: " + ", ".join(profile_warnings[:8]) + (" and more" if len(profile_warnings) > 8 else "")), kind="warn", title="Profile Values Ignored"))
    if module_too_long:
        _callouts.append(mo.callout(mo.md(f"A {module_u:g}U module is longer than the {ui_cubesat.value} side face, so the side faces carry no modules."), kind="warn", title="Module Longer Than the Face"))
    if z_face_overfull:
        _callouts.append(mo.callout(mo.md(f"{int(ui_modules_z.value)} modules of {fmt_num(module_area_cm2, 0)} cm² do not fit a 100 cm² Z face."), kind="warn", title="Z Face Overfull"))
    if not radio_name:
        _callouts.append(mo.callout(mo.md("No radio row is selected; pass loads come from the table. TX draw still sets the data-tier beacon cost."), kind="info", title="No Radio Row"))
    if cells_area_cm2 > module_area_cm2:
        _callouts.append(mo.callout(mo.md(f"{cells_per_module} cells of {fmt_num(cell['area_cm2'], 1)} cm² need {fmt_num(cells_area_cm2, 0)} cm², but a {module_u:g}U module on a 10 cm face has {fmt_num(module_area_cm2, 0)} cm². The generation figure assumes they fit."), kind="warn", title="Cells Do Not Fit the Module"))
    if margin_w < 0:
        _callouts.append(mo.callout(mo.md(f"The {scenario.lower()} scenario draws {fmt_num(-margin_w, 2)} W more than the panels deliver on average; the loads table is where to look first."), kind="warn", title="Negative Energy Balance"))
    if below_floor:
        _callouts.append(mo.callout(mo.md(f"State of charge falls to {min_soc * 100:.0f}%, below the {soc_floor * 100:.0f}% floor."), kind="warn", title="Below the Discharge Floor"))
    if safe_hours > 0:
        _callouts.append(mo.callout(mo.md(f"Safe mode was entered for {fmt_num(safe_hours, 1)} h of the simulation on the state-of-charge threshold."), kind="warn" if safe_margin_w < 0 else "info", title="Safe Mode Entered"))
    if base_exceeds:
        _callouts.append(mo.callout(mo.md("Nominal loads exceed generation. No energy remains for extra passes or activations."), kind="warn", title="Nominal Load Exceeds Generation"))
    if frames_per_day_taken == 0 and ui_pay_mode.value != "Always":
        _callouts.append(mo.callout(mo.md("No activations passed the triggers and gates. The activation allowance still uses the payload load and the active-time setting."), kind="info", title="No Activation in the Span"))
    if activations_completed < activations_scheduled and scenario == "Nominal":
        _callouts.append(mo.callout(mo.md(f"{activations_scheduled - activations_completed} of {activations_scheduled} scheduled activations fell inside safe mode and did not complete."), kind="warn", title="Activations Lost to Safe Mode"))
    if sustainable_pass_min < contact_min_per_day:
        _callouts.append(mo.callout(mo.md(f"The battery affords {_fin(sustainable_pass_min, 0)} pass minutes a day; the station offers {fmt_num(contact_min_per_day, 1)}. Not every pass can transmit."), kind="warn", title="Passes Exceed the Budget"))
    if degraded_margin_w < 0:
        _callouts.append(mo.callout(mo.md("With the radio node dead and the LoRa board beaconing, loads still exceed generation; the backstop fails when it is needed."), kind="warn", title="Degraded Mode Does Not Close"))
    _headroom = float_v + 3.3
    if module_vmpp_hot < _headroom:
        _callouts.append(
            mo.callout(
                mo.md(
                    f"The panel modules deliver about {fmt_num(module_vmpp_hot, 1)} V at maximum power when hot, but the LTM8062 needs the input 3.3 V above the float voltage to start (datasheet Rev D p. 3, note 3, and Table 1 p. 11): {fmt_num(_headroom, 1)} V for a {fmt_num(float_v, 1)} V float. Check the series-cell count, the float voltage or the charger choice."
                ),
                kind="warn",
                title="Charger Input Headroom",
            )
        )
    if eclipse_fraction == 0:
        _callouts.append(mo.callout(mo.md("No eclipse in this run. Check other epochs for the worst season."), kind="info", title="No Eclipse"))
    if hdrm_soc_pct > 5:
        _callouts.append(mo.callout(mo.md(f"The release mechanism costs {hdrm_soc_pct:.1f}% of the pack in one pulse."), kind="info", title="Release Pulse"))
    if placeholder_loads or cell["status"] != "reference":
        _what = ", ".join(placeholder_loads[:4]) + (" and more" if len(placeholder_loads) > 4 else "")
        _callouts.append(mo.callout(mo.md(f"Placeholder figures in use: {_what if placeholder_loads else 'none in the loads'}; solar cell status {cell['status']}. Treat the margin as a shape, not a number."), kind="info", title="Placeholders"))
    mo.vstack(_items + _callouts)
    return


@app.cell
def _(
    PALETTE,
    alt,
    eclipse_runs,
    gen_w,
    in_imaging,
    in_pass,
    in_safe,
    load_actual_w,
    mo,
    np,
    pd,
    rule_y,
    runs,
    soc,
    soc_floor,
    step_s,
    style_chart,
    t_s,
    ui_safe_enter,
):
    # Day-in-the-life charts, downsampled to one point a minute (Altair's
    # default transformer refuses more than 5'000 rows).
    _k = max(int(60 / step_s), 1)
    _idx = np.arange(0, len(t_s), _k)
    _h = t_s[_idx] / 3600
    _first_day = _h <= 24
    _power = pd.DataFrame(
        {
            "Hours": np.concatenate([_h[_first_day], _h[_first_day]]),
            "W": np.concatenate([gen_w[_idx][_first_day], load_actual_w[_idx][_first_day]]),
            "Series": ["Generation at the panels"] * int(_first_day.sum()) + ["Load at the battery"] * int(_first_day.sum()),
        }
    )
    _ecl = pd.DataFrame([{"x": s / 3600, "x2": min(e, 86400) / 3600} for s, e in eclipse_runs if s < 86400])
    _shade = alt.Chart(_ecl).mark_rect(opacity=0.12, color="#888884").encode(x="x:Q", x2="x2:Q") if len(_ecl) else alt.Chart(pd.DataFrame({"x": []})).mark_rect()
    # Passes and activations as translucent bands over the first day, from
    # the runs of each mask, so short events stay visible.
    def _bands(mask, color):
        _r = [{"x": t_s[s0] / 3600, "x2": (t_s[e0 - 1] + step_s) / 3600} for s0, e0 in runs(mask) if t_s[s0] < 86400]
        return alt.Chart(pd.DataFrame(_r if _r else [{"x": 0, "x2": 0}])).mark_rect(opacity=0.25, color=color).encode(x="x:Q", x2="x2:Q")

    _band_pass = _bands(in_pass, PALETTE[2])
    _band_img = _bands(in_imaging, PALETTE[4])
    _lines = (
        alt.Chart(_power)
        .mark_line(interpolate="step-after", clip=True)
        .encode(
            x=alt.X("Hours:Q", title="Hours from the epoch (first day)", scale=alt.Scale(domain=[0, 24])),
            y=alt.Y("W:Q", title="W"),
            color=alt.Color("Series:N", scale=alt.Scale(range=[PALETTE[0], PALETTE[1]]), legend=alt.Legend(orient="bottom", title=None)),
            tooltip=[alt.Tooltip("Hours:Q", format=".2f"), alt.Tooltip("W:Q", format=".2f"), "Series:N"],
        )
    )
    power_chart = style_chart(
        alt.layer(_shade, _band_pass, _band_img, _lines).properties(width="container", height=260, title="Power over the first day – gray: eclipse; orange: passes; green: payload activations")
    )

    # The state-of-charge chart spans the whole run; thin it to stay under
    # the row cap on a seven-day span.
    _k2 = max(int(np.ceil(len(t_s) / 4000)), 1)
    _idx2 = np.arange(0, len(t_s), _k2)
    _socdf = pd.DataFrame({"Hours": t_s[_idx2] / 3600, "SoC": soc[_idx2] * 100, "Safe": in_safe[_idx2]})
    _soc_line = (
        alt.Chart(_socdf)
        .mark_line(color=PALETTE[0], clip=True)
        .encode(x=alt.X("Hours:Q", title="Hours from the epoch"), y=alt.Y("SoC:Q", title="State of charge (%)", scale=alt.Scale(domain=[0, 100])), tooltip=[alt.Tooltip("Hours:Q", format=".2f"), alt.Tooltip("SoC:Q", format=".1f")])
    )
    _safe_pts = alt.Chart(_socdf[_socdf["Safe"]]).mark_tick(color=PALETTE[2], thickness=2, size=8).encode(x="Hours:Q", y=alt.value(4))
    soc_chart = style_chart(
        alt.layer(_soc_line, rule_y(soc_floor * 100), rule_y(float(ui_safe_enter.value), dashed=False), _safe_pts).properties(
            width="container", height=240, title="State of charge – dashed: discharge floor; dotted: safe-mode entry; ticks: in safe mode"
        )
    )
    mo.vstack([mo.md("## Day in the Life"), power_chart, soc_chart])
    return


@app.cell
def _(
    MODES,
    beacon_rows,
    cell,
    cell_space_w,
    eclipse_fraction,
    face_cos,
    face_modules,
    face_normal_w,
    fmt_num,
    gen_w,
    hdrm_wh,
    load_sched_w,
    loads,
    mo,
    mod_parallel,
    mod_series,
    mode_total_w,
    module_u,
    module_w,
    np,
    pack_v,
    pack_wh,
    pd,
    period_min,
    rail_eff,
    sunlit,
    total_modules,
    total_normal_w,
    ui_attitude,
    usable_wh,
):
    # Power budget breakdown, per mode and per day in the nominal schedule.
    _rows = []
    for _l in loads + beacon_rows:
        _rows.append({"Consumer": _l["name"], "Rail": _l["rail"], **{f"{_m} (W)": round(_l["w"][_m], 3) for _m in MODES}})
    _rows.append({"Consumer": "Conversion loss (rails)", "Rail": "–", **{f"{_m} (W)": round(mode_total_w[_m] - sum(_l["w"][_m] for _l in loads + beacon_rows), 3) for _m in MODES}})
    _rows.append({"Consumer": "Total at the battery", "Rail": "–", **{f"{_m} (W)": round(mode_total_w[_m], 3) for _m in MODES}})
    _ledger = pd.DataFrame(_rows)

    _faces = pd.DataFrame(
        [
            {"Face": _f, "Modules": face_modules[_f], "Normal incidence (W)": round(face_normal_w[_f], 3), "Mean illumination in sunlight": round(float(np.mean(face_cos[_f][sunlit])) if sunlit.any() else 0.0, 3), "Orbit-average (W)": round(float(np.mean(face_normal_w[_f] * face_cos[_f] * sunlit)), 3)}
            for _f in face_normal_w
        ]
    )
    _gen_text = (
        f"{cell['name']}: {fmt_num(cell['pmpp_w'] * 1000, 0)} mW rated, {fmt_num(cell_space_w * 1000, 0)} mW in space at the set temperature and losses; "
        f"{fmt_num(module_w, 2)} W per {mod_series}S{mod_parallel}P module of {module_u:g}U, {total_modules} modules, {fmt_num(total_normal_w, 1)} W with every module at normal incidence. "
        f"{ui_attitude.value}: {fmt_num(float(gen_w.mean()), 2)} W orbit average at the panels; eclipse {eclipse_fraction * 100:.0f}% of the time, period {fmt_num(period_min, 1)} min."
    )
    _store_text = f"Pack {pack_v:.1f} V nominal, {fmt_num(pack_wh, 1)} Wh, {fmt_num(usable_wh, 1)} Wh usable; rails at {rail_eff['5V'] * 100:.0f}% (5V) and {rail_eff['3V3'] * 100:.0f}% (3V3); release pulse {fmt_num(hdrm_wh * 1000, 0)} mWh once."
    mo.vstack(
        [
            mo.md("## Power Budget Breakdown"),
            mo.md(_gen_text),
            mo.ui.table(_faces, selection=None, show_column_summaries=False, pagination=False),
            mo.md(_store_text),
            mo.md(f"Scheduled nominal-scenario load averages {fmt_num(float(load_sched_w.mean()), 2)} W at the battery. Per mode, with everyone in that mode at once:"),
            mo.ui.table(_ledger, selection=None, show_column_summaries=False, pagination=False),
        ]
    )
    return


@app.cell
def _(
    activations,
    activations_completed,
    activations_scheduled,
    fmt_num,
    mo,
    passes,
    pd,
    station_name,
    ui_pay_mode,
):
    _p = pd.DataFrame([{"Start (UTC)": p["start"].strftime("%Y-%m-%d %H:%M"), "Duration (min)": round(p["duration_min"], 1), "Max elevation (deg)": round(p["max_el"], 1)} for p in passes])
    _a = pd.DataFrame([{"Candidate (UTC)": a["start"].strftime("%Y-%m-%d %H:%M"), "Duration (s)": round(a["duration_s"]), "Lit": a["lit"], "Taken": a["taken"], "Completed": a.get("completed", False), "Dropped because": a["reason"]} for a in activations])
    mo.accordion(
        {
            f"Passes over {station_name} and payload activations ({ui_pay_mode.value.lower()})": mo.vstack(
                [
                    mo.md(f"{len(passes)} passes, {fmt_num(sum(p['duration_min'] for p in passes), 1)} minutes in total; {len(activations)} candidate activations, {activations_scheduled} scheduled, {activations_completed} completed."),
                    mo.ui.table(_p, selection=None, show_column_summaries=False, pagination=False) if len(_p) else mo.md("No passes in the span."),
                    mo.ui.table(_a, selection=None, show_column_summaries=False, pagination=len(_a) > 40) if len(_a) else mo.md("No candidate activations in the span."),
                ]
            )
        }
    )
    return


@app.cell
def _(
    ACKNOWLEDGMENT_MD,
    ASSUMPTIONS_MD,
    LOAD_KEYS,
    MODES,
    TOOL_VERSION,
    active_min_per_day,
    batt,
    beacon_rows,
    cell,
    completed_per_day,
    contact_min_per_day,
    cw_wh_day,
    degraded_margin_w,
    dt,
    eclipse_fraction,
    end_soc,
    fmt_num,
    frames_per_day_taken,
    gen_wh_day,
    load_wh_day,
    loads,
    margin_w,
    min_soc,
    mo,
    mode_total_w,
    pack_wh,
    passes_per_day,
    pd,
    profile_name,
    radio_name,
    requested_margin_w,
    scenario,
    sched_wh_day,
    station_name,
    sustainable_frames,
    sustainable_pass_min,
    ui_altitude,
    ui_am0,
    ui_attitude,
    ui_batt,
    ui_batt_ah,
    ui_batt_v,
    ui_beacon_policy,
    ui_cadence,
    ui_cap_day,
    ui_cap_orbit,
    ui_cell,
    ui_cell_area,
    ui_cell_impp,
    ui_cell_rated,
    ui_cell_spectrum,
    ui_cell_tc,
    ui_cell_temp,
    ui_cell_vmpp,
    ui_clock_end,
    ui_clock_start,
    ui_cubesat,
    ui_cw_cad,
    ui_cw_s,
    ui_cw_w,
    ui_dod,
    ui_eclipse_edge,
    ui_eff_3v3,
    ui_eff_5v,
    ui_eff_charge,
    ui_epoch,
    ui_faces_x,
    ui_faces_y,
    ui_faces_z,
    ui_gate_lit,
    ui_gate_nopass,
    ui_hdrm_s,
    ui_hdrm_w,
    ui_hold,
    ui_inclination,
    ui_lat,
    ui_listed,
    ui_loads,
    ui_lon,
    ui_lora_cad_deg,
    ui_lora_cad_nom,
    ui_lora_s,
    ui_lora_w,
    ui_ltdn,
    ui_min_el,
    ui_min_sun,
    ui_mod_parallel,
    ui_mod_series,
    ui_mod_u,
    ui_modules_z,
    ui_orbit_nth,
    ui_orbit_u0,
    ui_orbit_u1,
    ui_parallel,
    ui_pass_after,
    ui_pass_offset,
    ui_pay_mode,
    ui_reach,
    ui_region_e,
    ui_region_n,
    ui_region_s,
    ui_region_w,
    ui_rx_w,
    ui_safe_enter,
    ui_safe_exit,
    ui_scenario,
    ui_series,
    ui_share,
    ui_sim_days,
    ui_soc0,
    ui_station,
    ui_string_loss,
    ui_t1_cad,
    ui_t1_ms,
    ui_t2_cad,
    ui_t2_ms,
    ui_target_lat,
    ui_target_lon,
    ui_target_same,
    ui_tx_w,
    ui_uvlo,
    ui_window,
    usable_wh,
):
    _now = dt.datetime.now(dt.timezone.utc)
    _today = _now.strftime("%Y-%m-%d")

    def _fin(x, digits=1):
        return "unlimited" if x == float("inf") else fmt_num(x, digits)

    _head = [
        f"# BAC Power Budget – {scenario} scenario",
        "",
        f"Generated {_now:%Y-%m-%d %H:%M} UTC (Unix {int(_now.timestamp())}) with BAC Power Budget {TOOL_VERSION}, bac.page/power-budget-tool." + (f" Profile: {profile_name}." if profile_name else "") + " Every value below is a planning input or a result derived from one; nothing here is measured.",
        "",
        f"Orbit {fmt_num(float(ui_altitude.value), 0)} km, inclination {ui_inclination.value:g}°, LTDN {ui_ltdn.value:g} h, epoch {ui_epoch.value}, {ui_sim_days.value} day(s). "
        f"Station {station_name}, {ui_min_el.value:g}° minimum elevation. {cell['name']} cells, {ui_cubesat.value}, {ui_attitude.value.lower()}. "
        f"Pack {ui_series.value}S{ui_parallel.value}P {batt['name']}, {fmt_num(pack_wh, 1)} Wh, {fmt_num(usable_wh, 1)} Wh usable.",
        "",
        "| Quantity | Value |",
        "|---|---|",
        f"| Generation at the battery | {fmt_num(gen_wh_day, 1)} Wh/day |",
        f"| Consumption | {fmt_num(load_wh_day, 1)} Wh/day |",
        f"| Requested margin, no shedding | {fmt_num(requested_margin_w, 2)} W |",
        f"| Run margin, with safe-mode shedding | {fmt_num(margin_w, 2)} W |",
        f"| Eclipse fraction | {eclipse_fraction * 100:.0f}% |",
        f"| State of charge, minimum / end | {min_soc * 100:.0f}% / {end_soc * 100:.0f}% |",
        f"| Passes | {passes_per_day:.2f}/day, {fmt_num(contact_min_per_day, 1)} min/day |",
        f"| Sustainable pass minutes | {_fin(sustainable_pass_min, 0)}/day |",
        f"| Activations scheduled / completed / sustainable | {frames_per_day_taken:.2f} / {completed_per_day:.2f} / {_fin(sustainable_frames, 1)} per day ({ui_pay_mode.value.lower()}) |",
        f"| CW beacon, running all day | {fmt_num(cw_wh_day, 2)} Wh/day |",
        f"| Degraded-mode margin | {fmt_num(degraded_margin_w, 2)} W |",
        "",
        "| Consumer | Rail | " + " | ".join(f"{_m} (W)" for _m in MODES) + " |",
        "|---|---|" + "---|" * len(MODES),
    ]
    for _l in loads + beacon_rows:
        _head.append(f"| {_l['name']} | {_l['rail']} | " + " | ".join(f"{_l['w'][_m]:g}" for _m in MODES) + " |")
    _head.append("| Total at the battery | – | " + " | ".join(f"{mode_total_w[_m]:.2f}" for _m in MODES) + " |")
    _head.append("")

    def _strip(text):
        return "\n".join(_l[4:] if _l.startswith("    ") else _l for _l in text.strip("\n").splitlines())

    report_md = "\n".join(_head) + "\n" + _strip(ASSUMPTIONS_MD) + "\n\n" + _strip(ACKNOWLEDGMENT_MD) + "\n"

    def _t(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if hasattr(v, "item"):
            v = v.item()
        if isinstance(v, (int, float)):
            return "" if v != v or v in (float("inf"), float("-inf")) else repr(round(v, 6) if isinstance(v, float) else v)
        _t_s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return '"' + _t_s + '"'

    def _section(header, pairs):
        _lines = [header]
        for _k, _v in pairs:
            _s = _t(_v)
            if _s:
                _lines.append(f"{_k} = {_s}")
        return "\n".join(_lines)

    _sections = [
        f'# Saved from BAC Power Budget {TOOL_VERSION} on {_today}. Load it with the button at the\n# top of the notebook. Any key you leave out keeps the tool\'s default. [results.power_budget]\n# is what this tool hands to its siblings and is ignored when loaded back.\nname = "Saved settings, {_today}"\ntool = "bac_power_budget"\ntool_version = {_t(TOOL_VERSION)}',
        _section("[orbit]", [("altitude_km", ui_altitude.value), ("inclination_deg", ui_inclination.value), ("ltdn_hours", ui_ltdn.value), ("epoch", ui_epoch.value), ("sim_days", ui_sim_days.value)]),
        _section("[ground_station]", [("station", ui_station.value), ("latitude_deg", ui_lat.value), ("longitude_deg", ui_lon.value), ("min_elevation_deg", ui_min_el.value)]),
        _section("[target]", [("latitude_deg", ui_target_lat.value), ("longitude_deg", ui_target_lon.value)]),
        _section(
            "[payload]",
            [("mode", ui_pay_mode.value), ("target_is_station", ui_target_same.value), ("reach_km", ui_reach.value), ("region_south_deg", ui_region_s.value), ("region_north_deg", ui_region_n.value), ("region_west_deg", ui_region_w.value), ("region_east_deg", ui_region_e.value), ("orbit_start_deg", ui_orbit_u0.value), ("orbit_end_deg", ui_orbit_u1.value), ("every_nth_orbit", ui_orbit_nth.value), ("cadence_min", ui_cadence.value), ("clock_start_h", ui_clock_start.value), ("clock_end_h", ui_clock_end.value), ("after_pass", ui_pass_after.value), ("pass_offset_s", ui_pass_offset.value), ("eclipse_edge", ui_eclipse_edge.value), ("listed", ui_listed.value), ("hold_whole_window", ui_hold.value), ("active_s", ui_window.value), ("gate_lit", ui_gate_lit.value), ("min_sun_elevation_deg", ui_min_sun.value), ("gate_no_pass", ui_gate_nopass.value), ("cap_per_day", ui_cap_day.value), ("cap_per_orbit", ui_cap_orbit.value)],
        ),
        _section(
            "[generation]",
            [("cell", ui_cell.value), ("custom_vmpp_v", ui_cell_vmpp.value), ("custom_impp_a", ui_cell_impp.value), ("custom_tc_pct_k", ui_cell_tc.value), ("custom_rated_w_m2", ui_cell_rated.value), ("custom_spectrum", ui_cell_spectrum.value), ("custom_area_cm2", ui_cell_area.value), ("module_series", ui_mod_series.value), ("module_parallel", ui_mod_parallel.value), ("module_u", ui_mod_u.value), ("cubesat", ui_cubesat.value), ("faces_x", ui_faces_x.value), ("faces_y", ui_faces_y.value), ("faces_z", ui_faces_z.value), ("modules_per_z_face", ui_modules_z.value), ("am0_factor", ui_am0.value), ("cell_temp_c", ui_cell_temp.value), ("string_loss_pct", ui_string_loss.value), ("attitude", ui_attitude.value)],
        ),
        _section(
            "[storage]",
            [("cell", ui_batt.value), ("custom_nominal_v", ui_batt_v.value), ("custom_capacity_ah", ui_batt_ah.value), ("series", ui_series.value), ("parallel", ui_parallel.value), ("dod_pct", ui_dod.value), ("initial_soc_pct", ui_soc0.value), ("charger_eff_pct", ui_eff_charge.value), ("rail_5v_eff_pct", ui_eff_5v.value), ("rail_3v3_eff_pct", ui_eff_3v3.value), ("uvlo_v_per_cell", ui_uvlo.value), ("safe_enter_soc_pct", ui_safe_enter.value), ("safe_exit_soc_pct", ui_safe_exit.value)],
        ),
        _section("[radio]", [("consumer", radio_name), ("tx_w", ui_tx_w.value), ("rx_w", ui_rx_w.value), ("downlink_share_pct", ui_share.value)]),
        _section(
            "[beacon]",
            [("policy", ui_beacon_policy.value), ("cw_message_s", ui_cw_s.value), ("cw_power_w", ui_cw_w.value), ("cw_cadence_s", ui_cw_cad.value), ("tier1_on_air_ms", ui_t1_ms.value), ("tier1_cadence_s", ui_t1_cad.value), ("tier2_on_air_ms", ui_t2_ms.value), ("tier2_cadence_s", ui_t2_cad.value), ("lora_on_air_s", ui_lora_s.value), ("lora_power_w", ui_lora_w.value), ("lora_cadence_nominal_s", ui_lora_cad_nom.value), ("lora_cadence_degraded_s", ui_lora_cad_deg.value)],
        ),
        _section("[oneshot]", [("hdrm_power_w", ui_hdrm_w.value), ("hdrm_duration_s", ui_hdrm_s.value)]),
        _section("[schedule]", [("scenario", ui_scenario.value)]),
    ]
    for _, _r in ui_loads.value.iterrows():
        if str(_r["Consumer"]).strip():
            _sections.append(_section("[[loads]]", [(_k, _r[_c]) for _c, _k in LOAD_KEYS.items()]))
    _sections.append(
        _section(
            "[results.power_budget]",
            [("scenario", scenario), ("payload_mode", ui_pay_mode.value), ("generation_wh_day", gen_wh_day), ("consumption_wh_day", load_wh_day), ("requested_wh_day", sched_wh_day), ("requested_margin_w", requested_margin_w), ("margin_w", margin_w), ("min_soc", min_soc), ("eclipse_fraction", eclipse_fraction), ("passes_per_day", passes_per_day), ("contact_min_per_day", contact_min_per_day), ("sustainable_pass_min_per_day", sustainable_pass_min), ("sustainable_activations_per_day", sustainable_frames), ("activations_scheduled_per_day", frames_per_day_taken), ("activations_completed_per_day", completed_per_day), ("active_min_per_day", active_min_per_day), ("cw_beacon_wh_day_all_day", cw_wh_day), ("degraded_margin_w", degraded_margin_w)],
        )
    )
    profile_toml = "\n\n".join(_sections) + "\n"

    _csv_rows = [{"Consumer": _l["name"], "Rail": _l["rail"], **{f"{_m} (W)": _l["w"][_m] for _m in MODES}} for _l in loads + beacon_rows]
    ledger_csv = pd.DataFrame(_csv_rows).to_csv(index=False)
    _slug = scenario.lower()
    mo.vstack(
        [
            mo.md("## Export"),
            mo.md(
                "The report carries the headline table, the ledger, the assumptions and the acknowledgment. "
                "The profile carries every input, the loads table and a `[results.power_budget]` table for the "
                "sibling tools; it loads back into the control panel. The CSV is the ledger for a spreadsheet."
            ),
            mo.hstack(
                [
                    mo.download(data=report_md.encode("utf-8"), filename=f"bac-power-budget-{_slug}-{_today}.md", mimetype="text/markdown", label="Download report (.md)"),
                    mo.download(data=profile_toml.encode("utf-8"), filename=f"bac-power-budget-profile-{_today}.toml", mimetype="application/toml", label="Download profile (.toml)"),
                    mo.download(data=ledger_csv.encode("utf-8"), filename=f"bac-power-budget-ledger-{_today}.csv", mimetype="text/csv", label="Download ledger (.csv)"),
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

    **Orbit.** Circular, two-body, over a spherical Earth, with [J2](https://cubesat-resources.space/references/glossary/#j2)
    nodal regression, propagated at 10 s from the [epoch](https://cubesat-resources.space/references/glossary/#epoch); the
    [RAAN](https://cubesat-resources.space/references/glossary/#raan) follows from the
    [local time of the descending node](https://cubesat-resources.space/references/glossary/#local-time-of-descending-node-ltdn).
    Eclipse is the cylindrical shadow of the Earth, no penumbra, no atmosphere;
    the [eclipse fraction](https://cubesat-resources.space/references/glossary/#eclipse-fraction) is what one epoch gives, and
    the worst season for the orbit is not searched – move the epoch to find it
    (the [beta angle](https://cubesat-resources.space/references/glossary/#beta-angle) decides it).

    **Generation.** Each solar cell carries its rated irradiance and spectrum.
    A cell rated under [AM0](https://cubesat-resources.space/references/glossary/#am0) (the space cells) is rescaled only from
    its rated irradiance to the 1'361 W/m² [solar constant](https://cubesat-resources.space/references/glossary/#solar-constant);
    a cell rated under AM1.5 at 1'000 W/m² (the silicon cells) is rescaled to
    1'361 W/m² and multiplied by the AM0 spectral factor. Then a linear power
    loss per kelvin above 25°C at the set cell temperature, and a flat
    diode-and-mismatch loss. A module is S cells in series by P strings in
    parallel behind one diode, sized in [U](https://cubesat-resources.space/references/glossary/#u-cubesat-unit) along the face;
    a side face carries as many modules as fit in the CubeSat length. Every
    module on a face sees the same Sun. Nothing is said about degradation
    ([BOL/EOL](https://cubesat-resources.space/references/glossary/#bol-eol)), [albedo](https://cubesat-resources.space/references/glossary/#albedo) or [Earth infrared](https://cubesat-resources.space/references/glossary/#earth-ir).

    **Attitude.** Tumbling puts a quarter of the Sun on every face on average,
    the isotropic result for flat faces. Nadir-pointed holds +Z at zenith and
    +X along velocity; –Z carries the imager, +Z the boom root, so the Z faces
    carry no modules unless told otherwise. Sun-pointed holds the largest
    populated face at the Sun.

    **Storage.** All generation goes through the charger at its set efficiency
    into the battery, and every load is drawn from the battery through its
    [rail](https://cubesat-resources.space/references/glossary/#rail) at that rail's efficiency; the direct path from panel to
    load is not modeled, which is pessimistic by the charger loss.
    [State of charge](https://cubesat-resources.space/references/glossary/#state-of-charge-soc) is energy over nominal capacity
    with no voltage model; the [depth of discharge](https://cubesat-resources.space/references/glossary/#dod-battery) sets the
    floor and the [undervoltage lockout](https://cubesat-resources.space/references/glossary/#under-voltage-lockout-uvlo) is
    reported, not simulated. The volts shown beside the state-of-charge sliders
    come from a generic rested 18650 open-circuit curve; nothing in the balance
    depends on them.

    **Scenarios.** Nominal runs the timeline: the spacecraft sits at its
    nominal watts, passes raise the pass column and activations the payload
    column, and when the state of charge falls below the entry threshold the
    safe column is held until it climbs back above the exit threshold –
    [safe mode](https://cubesat-resources.space/references/glossary/#safe-mode) with hysteresis. Safe holds the safe column all
    day, the state after a fault or during
    [commissioning](https://cubesat-resources.space/references/glossary/#commissioning): radio listening and beaconing, payload
    off. Degraded holds the degraded column all day, the state with the radio
    node dead and only the EPS and the LoRa backstop alive. State of charge at
    the epoch is the pack's charge when the simulation starts.

    **Loads.** Average watts per mode from the table; a column is the draw in
    that mode, so a consumer may sit below nominal in a mode (the data-tier
    beacons during a pass). In the nominal scenario each consumer sits at its
    nominal value, takes its pass value during a [pass](https://cubesat-resources.space/references/glossary/#pass) and its payload
    value during an activation, the larger of the two when both apply. Watts
    that are negative or not numbers are taken as 0 and flagged. The selected
    radio row's pass value is share × transmit + (1 – share) × receive from the
    radio controls, written over the table cell. Peak watts are carried for
    rail sizing and not used yet.

    **Passes and activations.** Passes are station
    [elevation](https://cubesat-resources.space/references/glossary/#elevation-angle) at or above the minimum. The payload
    trigger yields candidate windows: over a location (within the reach of the
    sub-satellite point; centered), over a region (a latitude–longitude box),
    an orbit-position window (argument of latitude from the ascending node,
    every Nth orbit), a fixed cadence from the epoch, a daily clock window,
    during or after passes with an offset, throughout eclipse or sunlight or at
    an eclipse edge, a typed list, or always. Each candidate lasts the active
    time, or the whole trigger run when holding, and costs energy in proportion
    to the part of each 10 s sample it covers. Gates drop candidates that are
    not lit for their whole duration (the location's Sun elevation for the
    location trigger, the spacecraft's sunlight otherwise), that overlap a
    pass, that exceed the per-day or per-orbit cap, or that overlap an earlier
    activation. Scheduled activations that fall in safe mode, or in the Safe
    and Degraded scenarios, are counted as not completed.

    **Beacons.** Cadence arithmetic: CW and the data tiers on the radio node's
    transmit draw, the [LoRa](https://cubesat-resources.space/references/glossary/#lora) backstop on the function board's, each
    at its own cadence. The policy decides where the radio-node
    [beacons](https://cubesat-resources.space/references/glossary/#beacon) run: in safe mode and the Safe scenario only (the
    shipped policy, since the beacon is a commissioning and safe-mode
    function), in every mode the radio is up, or never. The card and the report
    price CW running all day regardless, which is its commissioning cost. Tiers
    1 and 2 are silent during passes. The release mechanism
    ([HDRM](https://cubesat-resources.space/references/glossary/#hdrm)) is a single energy pulse reported against the pack, not
    placed on the timeline.

    **Sustainable figures.** Sustainable pass minutes and activations are the
    day's generation minus a day at nominal watts, divided by the per-minute or
    per-activation increment; an activation is priced at the mean duration of
    the scheduled ones, or the active-time setting when none was scheduled.
    Each spends the whole surplus, so they are independent maxima, not a pair;
    both read 0 when nominal watts alone exceed generation. They are
    orbit-average figures and ignore where in the day the energy is. The
    requested margin is the scheduled day with no load shedding; the run margin
    is what the simulation did after dropping into safe mode.

    **Profiles.** A link budget profile loads with its orbit, station, minimum
    elevation and downlink share, and, from its per-mode results, the LoRa
    backstop's packet time on air (the SF12 row); its `[results.link_budget]`
    pass statistics feed a callout against this run's single phase. An optical
    payload profile loads with its orbit, its target as the activation
    location, half its swath as the reach and its frames per day as the cap,
    and its access count feeds a callout. Profile values outside a control's
    range are clamped; values that are not numbers fall back to the default and
    are reported.

    ## Limitations

    One epoch, so the worst eclipse season is not searched. No thermal model:
    the cell temperature is an input, and the battery's charge-temperature
    limit (0–45°C for the MJ1) is not checked. No voltage or current limits on
    the rails, no eFuse trip levels, no charger current limit (2 A for the
    LTM8062), no [MPPT](https://cubesat-resources.space/references/glossary/#mppt) tracking loss. Passes come from this
    propagator's single phase, not from the link budget's eight-phase average,
    and the optical payload's access count is a check, not the schedule.

    Linked terms go to the CubeSat Resources glossary, [bac.page/glossary](https://bac.page/glossary).
    The sibling tools are the [Link Budget](https://bac.page/link-budget-tool)
    and the [Optical Payload](https://bac.page/optical-payload-tool); a profile
    saved from either loads here, and this tool's profile loads there. Source
    and issues: [bac-utils](https://github.com/buildacubesat/bac-utils).
    """
    ACKNOWLEDGMENT_MD = """
    ## Acknowledgment

    Solar cell figures from the Anysolar, AzurSpace and Spectrolab datasheets
    where cited in the library, otherwise as publicly quoted; battery cell
    figures from the LG Chem INR18650 MJ1 product specification Rev 1; charger
    efficiency from the LTM8062 datasheet Rev D, p. 4. The propagator is the
    BAC Optical Payload tool's; the station elevation test is the BAC Link
    Budget tool's.

    Code MIT, text and figures CC BY-SA 4.0.
    """
    mo.md(ASSUMPTIONS_MD + "\n" + ACKNOWLEDGMENT_MD)
    return ACKNOWLEDGMENT_MD, ASSUMPTIONS_MD


@app.cell
def _(mo):
    mo.md("""
    ## Revision History

    | Version | Date | Change |
    |---|---|---|
    | 0.5.0 | 2026-09-14 | Homogenization with the siblings at their 0.7.0: intro names the tool's URL, its siblings, the project and the repository; the preliminary warning as a callout; "Headline Numbers" and title-case headings and callout titles throughout; assumptions as structured paragraphs with glossary links; report header and export text as in the siblings. Two cross-checks from the sibling profiles' results tables: the link budget's eight-phase pass statistics against this run's single phase, with the affordable pass minutes against its contact minutes, and the optical payload's accesses per day against the scheduled and affordable activations. Profile author detection by signature table as in the siblings. The LoRa backstop's time on air defaults to the SF12 row's packet airtime from a link budget 0.7.0 profile's per-mode results; the BAC profile documents the beacon ladder in its `[beacon]` comments. |
    | 0.4.1 | 2026-09-14 | Intro and callouts in the tighter wording; Schedule at the top of the left column; charts fill the width; passes and activations drawn as translucent bands instead of ticks. |
    | 0.4.0 | 2026-09-14 | Panel wording tightened, module controls named S and P, module length up to 4U, headline as three rows of two, radio row with short labels. Fixes from the GUI review: trigger windows no longer overrun by a step; the lit gate holds across the whole activation; an activation costs the fraction of each sample it covers; the activation allowance is priced at the scheduled mean duration; a "Never" trigger, which zero-activation profiles from before 0.3.0 land on; profiles from before 0.3.0 keep their cells all in series; malformed profile numbers fall back and are reported; an explicit "None" radio row survives a reload; face packing checked for the Z faces and for modules longer than the face. |
    | 0.3.0 | 2026-09-14 | Payload triggers: over a location, over a region, orbit position, fixed cadence, clock window, during or after passes, eclipse or sunlight, a typed list, always; hold-the-window switch; lit, not-during-pass, per-day and per-orbit gates; activations reported as scheduled and completed. Modules configurable as S × P cells and a size in U, with a fit check against the face. Review fixes: cells carry their rated irradiance and spectrum (space cells no longer rescaled from 1'000 W/m²); the radio controls set the selected radio row's pass value; a mode column is the draw in that mode, so the tier beacons do go silent during passes; loads validated finite and non-negative, thresholds ordered, profile values clamped to ranges; sustainable figures read 0 in a deficit and are labelled independent maxima; multiline notes survive the profile round trip; requested margin shown beside the run margin. Headline cards bordered again. |
    | 0.2.0 | 2026-09-13 | Imaging generalized to payload: activation location, reach, activations per day and active time per activation, with an explanation in the panel; old `[imaging]` keys and `imaging_w` still load. Beacon policy dropdown (safe mode and commissioning, always, off) – the radio-node beacons no longer run in nominal operation by default. Depth-of-discharge, start state of charge and lockout shown in volts off a generic open-circuit curve. Scenario and epoch explanations in the panel and the assumptions. Solar cell library gains the 4G32C-Advanced, XTJ Prime, Maxeon C60 and KXOB25; battery library gains six common 18650s. Where The Watts Go renamed Power Budget Breakdown. |
    | 0.1.0 | 2026-09-13 | Initial version. One timeline from the optical payload's propagator with the link budget's station test: sunlit state, passes, lit imaging accesses. Per-face generation with three attitude models, a solar cell and battery cell library, an editable loads table with average watts per mode, beacon cadence arithmetic, a one-shot release pulse, state of charge with a safe-mode fallback, three scenarios. Six headline cards, callouts including the charger input headroom check, day-in-the-life charts, the where-the-watts-go ledger, export with `[results.power_budget]`, and loading of link budget and optical payload profiles. |
    """)
    return


if __name__ == "__main__":
    app.run()