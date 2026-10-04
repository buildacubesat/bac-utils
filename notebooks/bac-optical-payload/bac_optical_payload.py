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
    # BAC Optical Payload

    Estimate what a camera on a small satellite produces. Set the sensor, lens
    and orbit, pick a camera preset that sets sensor and lens together, or
    load a mission profile. Link Budget and Power Budget profiles supply
    compatible settings.

    Compare ground sample distance and swath, whether the optics or the
    detector limit the image, smear, frame size and downlink time, and access
    over a target. In boom mode the same sensor and lens look back at the
    spacecraft from a deployable boom. The sensor library follows the modules
    offered for the [CHC5 open machine vision camera](https://www.kickstarter.com/projects/circuitvalley/chc5-open-machine-vision-programmable-industrial-camera),
    plus the Raspberry Pi cameras and a few consumer cameras for scale; a
    sensor or lens not in the libraries goes in through the Custom fields.

    This tool is published at [bac.page/optical-payload-tool](https://bac.page/optical-payload-tool);
    its siblings are the [Link Budget](https://bac.page/link-budget-tool)
    and [Power Budget](https://bac.page/power-budget-tool) tools. All three
    belong to the [Build a CubeSat](https://buildacubesat.space) project and
    their source is in [bac-utils](https://github.com/buildacubesat/bac-utils).
    """),
            mo.callout(
                mo.md(
                    "Every number here is a planning input, not a measurement. The model is "
                    "simple on purpose: nadir pointing over a spherical Earth, a pinhole camera, "
                    "Rayleigh diffraction and no radiometry. Use it to compare options and find "
                    "the limiting term, not to specify an instrument."
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
def _(np):
    # Constants, reference data and the formulas everything uses.

    TOOL_VERSION = "0.7.0"

    R_EARTH_KM = 6371.0
    MU_KM3_S2 = 398600.4418

    # Sensor library. Columns: width and height in pixels, pixel pitch in µm,
    # bit depth, shutter, color, status, note. Status "reference" means the
    # figures are the module maker's published ones (Raspberry Pi); "provisional"
    # means they are from memory of the sensor family and want checking against
    # the Sony or OmniVision datasheet before a decision rests on them. Bit depth
    # is the sensor's maximum RAW depth, not what a JPEG carries.
    SENSOR_KEYS = [
        "Sensor",
        "Width (px)",
        "Height (px)",
        "Pitch (µm)",
        "Bits",
        "Shutter",
        "Color",
        "Status",
        "Note",
    ]
    SENSORS = {
        "IMX477": (4056, 3040, 1.55, 12, "rolling", "RGB", "reference", "1/2.3\", Raspberry Pi HQ camera; CHC5 module"),
        "IMX500": (4056, 3040, 1.55, 12, "rolling", "RGB", "reference", "1/2.3\", Raspberry Pi AI camera, inference on the sensor"),
        "IMX708": (4608, 2592, 1.40, 10, "rolling", "RGB", "reference", "1/2.43\", Raspberry Pi camera module 3"),
        "IMX219": (3280, 2464, 1.12, 10, "rolling", "RGB", "reference", "1/4\", Raspberry Pi camera module 2"),
        # The Raspberry Pi Global Shutter Camera carries the color IMX296LQR-C
        # with an integrated IR-cut filter (raspberrypi.com product page); the
        # mono IMX296LLR is a different part, kept as its own row.
        "IMX296": (1456, 1088, 3.45, 10, "global", "RGB", "reference", "1/2.9\", Raspberry Pi Global Shutter Camera; color IMX296LQR-C with IR-cut filter"),
        "IMX296 mono": (1456, 1088, 3.45, 10, "global", "mono", "provisional", "1/2.9\", monochrome IMX296LLR as used in industrial modules; not the Raspberry Pi camera"),
        "IMX678": (3840, 2160, 2.00, 12, "rolling", "RGB", "provisional", "1/1.8\", Starvis 2; CHC5 module"),
        "IMX585": (3840, 2160, 2.90, 12, "rolling", "RGB", "provisional", "1/1.2\", Starvis 2; CHC5 module"),
        "IMX585 mono": (3840, 2160, 2.90, 12, "rolling", "mono", "provisional", "1/1.2\", Starvis 2; CHC5 module"),
        "IMX283": (5472, 3648, 2.40, 12, "rolling", "RGB", "provisional", "1\", Exmor R; CHC5 module"),
        "IMX565": (4128, 3008, 2.74, 12, "global", "RGB", "provisional", "1/1.1\", Pregius S; CHC5 module, global shutter option B"),
        "IMX568": (2472, 2064, 2.74, 12, "global", "RGB", "provisional", "2/3\", Pregius S; CHC5 module, global shutter option A"),
        "IMX294": (3792, 2824, 4.63, 14, "rolling", "RGB", "provisional", "4/3\", Exmor R; CHC5 module"),
        "OX08B40": (3840, 2160, 2.10, 12, "rolling", "RGB", "provisional", "1/1.8\", automotive HDR; CHC5 module"),
        "OV5640": (2592, 1944, 1.40, 10, "rolling", "RGB", "provisional", "1/4\", parallel DVP output; STM32 DCMI candidate"),
        # Consumer action cameras, for a sense of scale rather than as candidates.
        # Pitches are derived from the published sensor format and pixel count.
        "GoPro Hero 13 Black": (5568, 4872, 1.27, 10, "rolling", "RGB", "provisional", "1/1.9\", 27 MP 8:7 sensor; consumer action camera, for scale"),
        "DJI Osmo Action 4": (3840, 2880, 2.40, 10, "rolling", "RGB", "provisional", "1/1.3\", 4:3 video frame at the 2.4 µm binned pitch; consumer action camera, for scale"),
        "RunCam Thumb Pro (IMX577)": (4056, 3040, 1.55, 10, "rolling", "RGB", "provisional", "1/2.3\", 16 g FPV camera, 155° lens; for scale"),
        "RunCam 5 Orange (IMX377)": (4000, 3000, 1.55, 12, "rolling", "RGB", "provisional", "1/2.3\", 56 g cube action camera, 145° lens; for scale"),
        # DJI's current FPV air units (O4 series, dji.com/o4-air-unit/specs):
        # DJI publishes the format and the 3840 × 2880 4:3 video frame but no
        # pixel count or pitch, so the pitch is the format width over the
        # frame width and the rows are provisional. The 8.2 g unit is a boom
        # camera candidate by mass; the Pro is the one FPV builders mean.
        "DJI O4 Air Unit": (3840, 2880, 1.67, 10, "rolling", "RGB", "provisional", "1/2\", 4:3 video frame at a pitch derived from the format; 8.2 g air unit with camera, 13.4 × 12.4 × 16.5 mm camera module"),
        "DJI O4 Air Unit Pro": (3840, 2880, 2.40, 10, "rolling", "RGB", "provisional", "1/1.3\", 4:3 video frame at the same derived pitch as the Osmo Action 4; 32 g air unit with camera, 25.6 × 20 × 23.3 mm camera module"),
        # A current phone, for the same reason. The main camera is a 48 MP
        # quad-pixel sensor that bins to 12 MP at 2.44 µm in normal use; the
        # row carries the individual pixel so the 48 MP frame is what is priced.
        "iPhone 18 Pro main": (8064, 6048, 1.22, 12, "rolling", "RGB", "provisional", "1/1.28\", 48 MP quad-pixel, 2.44 µm binned in normal use; current phone, for scale"),
    }

    # The sensor dropdown shows the product a sensor ships in beside its part
    # number; the library key stays the bare part number so profiles do not
    # change. Sensors without an entry here are shown by key alone.
    SENSOR_PRODUCT = {
        "IMX477": "Raspberry Pi HQ Camera, CHC5 module",
        "IMX500": "Raspberry Pi AI Camera",
        "IMX708": "Raspberry Pi Camera Module 3",
        "IMX219": "Raspberry Pi Camera Module 2",
        "IMX296": "Raspberry Pi Global Shutter Camera",
        "IMX296 mono": "industrial modules",
        "IMX678": "CHC5 module",
        "IMX585": "CHC5 module",
        "IMX585 mono": "CHC5 module",
        "IMX283": "CHC5 module",
        "IMX565": "CHC5 module",
        "IMX568": "CHC5 module",
        "IMX294": "CHC5 module",
        "OX08B40": "CHC5 module",
        "OV5640": "STM32 DCMI candidate",
    }
    SENSOR_LABELS = {(f"{_k} – {SENSOR_PRODUCT[_k]}" if _k in SENSOR_PRODUCT else _k): _k for _k in SENSORS}

    # Lens library. Columns: focal length in mm, f-number, mount, image circle
    # diameter in mm. Image circles are the nominal format the lens is sold for
    # and are provisional throughout; a lens that covers a larger format than
    # the sensor is fine, the reverse vignettes.
    LENS_KEYS = ["Lens", "Focal (mm)", "f-number", "Mount", "Image circle (mm)", "Note"]
    LENSES = {
        "S-mount 4 mm f/2.0": (4.0, 2.0, "S (M12)", 7.7, "1/2.3\" board lens"),
        "S-mount 8 mm f/2.0": (8.0, 2.0, "S (M12)", 7.7, "1/2.3\" board lens"),
        "S-mount 12 mm f/2.5": (12.0, 2.5, "S (M12)", 8.0, "1/2\" board lens"),
        "CS-mount 6 mm f/1.2": (6.0, 1.2, "CS", 8.0, "1/2\" format, Raspberry Pi wide-angle lens"),
        "C-mount 16 mm f/1.4": (16.0, 1.4, "C", 16.0, "1\" format, Raspberry Pi HQ lens"),
        "C-mount 25 mm f/1.4": (25.0, 1.4, "C", 16.0, "1\" format"),
        "C-mount 35 mm f/1.8": (35.0, 1.8, "C", 16.0, "1\" format"),
        "C-mount 50 mm f/2.8": (50.0, 2.8, "C", 16.0, "1\" format"),
        # A single fused-silica element sold for CubeSats; the image circle is
        # the 3.7° fully corrected field at 240 mm, and the mount is whatever
        # the buyer specifies. tinytelescope.com, product page, 2025.
        "Tiny Telescope TT240-40, 240 mm f/6": (240.0, 6.0, "custom", 15.5, "Single athermal element, 40 mm aperture, 147 g, 75.5 mm to the detector; fits a 1U along its axis"),
        "AI camera 4.8 mm f/1.8": (4.8, 1.8, "fixed", 7.7, "Raspberry Pi AI camera, fixed"),
        "Camera module 3, 4.7 mm f/1.8": (4.74, 1.8, "fixed", 7.4, "Raspberry Pi camera module 3, fixed"),
        # Action-camera lenses, provisional: focal lengths back-computed from the
        # published 35 mm equivalent, and all three are wide enough that the
        # rectilinear pinhole model overstates the edge of the field.
        "GoPro Hero 13 Black lens, 2.9 mm f/2.5": (2.9, 2.5, "fixed", 9.4, "Consumer action camera, fixed"),
        "DJI Osmo Action 4 lens, 3.5 mm f/2.8": (3.5, 2.8, "fixed", 12.0, "155° fisheye; consumer action camera, fixed"),
        "RunCam Thumb Pro lens, 2.5 mm f/2.8": (2.5, 2.8, "fixed", 7.9, "155° lens; f-number is a placeholder"),
        "RunCam 5 Orange lens, 3.0 mm f/2.8": (3.0, 2.8, "fixed", 7.9, "145° lens; focal length from the field of view and format, f-number a placeholder"),
        # DJI O4 lenses: f-numbers and 35 mm equivalents from the DJI spec page,
        # focal lengths from the equivalent over the format diagonal.
        "DJI O4 Air Unit lens, 2.6 mm f/2.8": (2.6, 2.8, "fixed", 8.1, "117.6° lens, 14 mm equivalent; focal length from the equivalent and the 1/2\" format"),
        "DJI O4 Air Unit Pro lens, 3.3 mm f/2.8": (3.3, 2.8, "fixed", 12.0, "155° fisheye, 12 mm equivalent; focal length from the equivalent and the 1/1.3\" format"),
        "iPhone 18 Pro main lens, 6.8 mm f/1.48": (6.8, 1.48, "fixed", 12.3, "24 mm equivalent, variable aperture to f/4.0; focal length from the equivalent"),
    }

    # Camera presets: a product sets its sensor and, where the lens is fixed,
    # its lens. Cameras with an interchangeable mount leave the lens dropdown
    # at whatever it was. Both dropdowns stay editable after a pick.
    CAMERAS = {
        "Raspberry Pi Camera Module 3": ("IMX708", "Camera module 3, 4.7 mm f/1.8"),
        "Raspberry Pi HQ Camera": ("IMX477", None),
        "Raspberry Pi AI Camera": ("IMX500", "AI camera 4.8 mm f/1.8"),
        "Raspberry Pi Global Shutter Camera": ("IMX296", None),
        "CHC5, IMX477 module": ("IMX477", None),
        "CHC5, IMX678 module": ("IMX678", None),
        "CHC5, IMX568 module (global shutter)": ("IMX568", None),
        "RunCam 5 Orange": ("RunCam 5 Orange (IMX377)", "RunCam 5 Orange lens, 3.0 mm f/2.8"),
        "RunCam Thumb Pro": ("RunCam Thumb Pro (IMX577)", "RunCam Thumb Pro lens, 2.5 mm f/2.8"),
        "GoPro Hero 13 Black": ("GoPro Hero 13 Black", "GoPro Hero 13 Black lens, 2.9 mm f/2.5"),
        "DJI Osmo Action 4": ("DJI Osmo Action 4", "DJI Osmo Action 4 lens, 3.5 mm f/2.8"),
        "DJI O4 Air Unit": ("DJI O4 Air Unit", "DJI O4 Air Unit lens, 2.6 mm f/2.8"),
        "DJI O4 Air Unit Pro": ("DJI O4 Air Unit Pro", "DJI O4 Air Unit Pro lens, 3.3 mm f/2.8"),
        "iPhone 18 Pro": ("iPhone 18 Pro main", "iPhone 18 Pro main lens, 6.8 mm f/1.48"),
    }

    # Target presets, degrees N and E. The link budget's four stations first,
    # then a spread of latitudes and longitudes so the illumination and access
    # behaviour can be seen from the equator to the Arctic.
    TARGETS = {
        "Bern": (46.95, 7.45),
        "San Marcos": (29.88, -97.94),
        "Farroupilha": (-29.22, -51.35),
        "Nairobi": (-1.29, 36.82),
        "Longyearbyen": (78.22, 15.63),
        "Reykjavik": (64.15, -21.94),
        "New York": (40.71, -74.01),
        "Chicago": (41.88, -87.63),
        "Tokyo": (35.68, 139.69),
        "Delhi": (28.61, 77.21),
        "Mexico City": (19.43, -99.13),
        "Singapore": (1.35, 103.82),
        "Sydney": (-33.87, 151.21),
        "Cape Town": (-33.93, 18.42),
    }

    # CubeSat envelopes in mm, X by Y by Z, per the CubeSat Design Specification.
    CUBESATS = {
        "1U": (100.0, 100.0, 113.5),
        "1.5U": (100.0, 100.0, 170.2),
        "2U": (100.0, 100.0, 227.0),
        "3U": (100.0, 100.0, 340.5),
        "4U": (100.0, 100.0, 454.0),
    }
    FACES = {
        "+Z": np.array([0.0, 0.0, 1.0]),
        "-Z": np.array([0.0, 0.0, -1.0]),
        "+X": np.array([1.0, 0.0, 0.0]),
        "-X": np.array([-1.0, 0.0, 0.0]),
        "+Y": np.array([0.0, 1.0, 0.0]),
        "-Y": np.array([0.0, -1.0, 0.0]),
    }

    def orbital_velocity_km_s(alt_km):
        return float(np.sqrt(MU_KM3_S2 / (R_EARTH_KM + alt_km)))

    def ground_speed_km_s(alt_km):
        # Sub-satellite point speed for a circular orbit, ignoring Earth rotation.
        return orbital_velocity_km_s(alt_km) * R_EARTH_KM / (R_EARTH_KM + alt_km)

    def ground_offset_km(angle_deg, alt_km):
        # Ground distance from the sub-satellite point to where a line of sight
        # at that off-nadir angle meets a spherical Earth: the incidence angle
        # from sin i = (R + h)/R · sin θ, the Earth-central angle i − θ. Past
        # the limb the answer is the horizon distance. The same geometry as
        # the off-nadir chart, so reach and chart agree.
        _t = np.radians(float(angle_deg))
        _sin_i = (R_EARTH_KM + alt_km) / R_EARTH_KM * np.sin(_t)
        if _sin_i >= 1.0:
            return R_EARTH_KM * float(np.arccos(R_EARTH_KM / (R_EARTH_KM + alt_km)))
        return R_EARTH_KM * float(np.arcsin(_sin_i) - _t)

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
        CAMERAS,
        CUBESATS,
        FACES,
        LENSES,
        LENS_KEYS,
        R_EARTH_KM,
        SENSORS,
        SENSOR_KEYS,
        SENSOR_LABELS,
        TARGETS,
        TOOL_VERSION,
        fmt_int,
        fmt_num,
        ground_offset_km,
        ground_speed_km_s,
    )


@app.cell
def _():
    # Three profiles ship with the tool. The BAC Earth observation one is what the
    # panel starts from; the BAC boom one is the engineering camera; the generic
    # one is a different mission and exists to show the tool is not the mission.
    PROFILE_BAC = """
    # Build a CubeSat demo mission, primary imager, as of 2026-09-10.
    # A candidate, not a decision: the sensor and lens are the January 2027
    # evaluation pair. Change them and the numbers follow.
    name = "Build a CubeSat demo mission, primary imager"

    [mission]
    mode = "Earth observation"

    [orbit]
    altitude_km = 450
    inclination_deg = 97.4
    ltdn_hours = 10.5
    epoch = "2027-06-21"
    sim_days = 30

    [target]
    name = "Bern"

    [sensor]
    name = "IMX477"

    [lens]
    name = "C-mount 16 mm f/1.4"

    [imaging]
    exposure_ms = 0.5
    readout_ms = 20
    attitude_rate_deg_s = 0.5
    pointing_error_deg = 5
    pointing_knowledge_deg = 5
    wavelength_nm = 550
    compression_ratio = 10
    frames_per_day = 4
    # From the link budget v0.6.0 at Bern, 450 km, 10°, 3 dB: the UHF 50k link
    # and the S-band 100k link as they stand today. S-band carries less because
    # it clears the margin target for about a minute per pass, not because it is
    # slower; a 2.4 GHz LNA and tracking under 2-3° take it to about 8'500.
    low_rate_kb_per_day = 3221
    high_rate_kb_per_day = 2539
    max_off_nadir_deg = 0
    min_sun_elevation_deg = 20
    """

    PROFILE_BOOM = """
    # Build a CubeSat demo mission, engineering camera on the boom, as of
    # 2026-09-10. The sensor is one of the secondary-imager candidates; the
    # boom geometry is a starting point for the mechanical issue.
    name = "Build a CubeSat demo mission, boom camera"

    [mission]
    mode = "Boom"

    [orbit]
    altitude_km = 450

    [sensor]
    name = "OV5640"

    [lens]
    name = "S-mount 8 mm f/2.0"

    [boom]
    cubesat = "1.5U"
    face = "+Z"
    offset_x_mm = 35
    offset_y_mm = 35
    length_mm = 500
    sweep_deg = 30
    sweep_dir_deg = 45
    aim_at_center = true
    pitch_deg = 15
    yaw_deg = 225
    focus_mm = 0
    """

    PROFILE_GENERIC = """
    # A generic 1U with a Raspberry Pi camera module 3 and its fixed lens.
    name = "Generic 1U, camera module 3"

    [camera]
    name = "Raspberry Pi Camera Module 3"

    [mission]
    mode = "Earth observation"

    [orbit]
    altitude_km = 500

    [sensor]
    name = "IMX708"

    [lens]
    name = "Camera module 3, 4.7 mm f/1.8"

    [imaging]
    exposure_ms = 1
    readout_ms = 30
    attitude_rate_deg_s = 1
    pointing_error_deg = 10
    pointing_knowledge_deg = 10
    wavelength_nm = 550
    compression_ratio = 10
    frames_per_day = 2
    # One amateur UHF radio and no second link.
    low_rate_kb_per_day = 500
    high_rate_kb_per_day = 0
    """
    return PROFILE_BAC, PROFILE_BOOM, PROFILE_GENERIC


@app.cell
def _(mo):
    # Profile loader. Separate from the control panel because the panel reads
    # the parsed profile to set its starting values.
    ui_profile = mo.ui.file(
        kind="button",
        filetypes=[".toml"],
        label="Load mission profile (.toml)",
    )
    return (ui_profile,)


@app.cell
def _(tomllib, ui_profile):
    # Parse the uploaded profile into the defaults every input starts from.
    # Anything the file does not name keeps the tool's own default.
    _raw = ui_profile.contents()
    profile_error = ""
    profile_name = ""
    _doc = {}
    if _raw:
        try:
            _doc = tomllib.loads(_raw.decode("utf-8"))
            profile_name = str(_doc.get("name") or ui_profile.name() or "unnamed")
        except Exception as _e:  # a bad file must not take the notebook down
            profile_error = f"{type(_e).__name__}: {_e}"
            _doc = {}

    # Dotted sections read the [results.<tool>] tables the siblings write. A
    # number the profile got wrong falls back to the default and is reported
    # rather than breaking the panel.
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
        # Whether the profile carries the key at all.
        _v = _doc
        for _part in section.split("."):
            _v = _v.get(_part, {}) if isinstance(_v, dict) else {}
        return isinstance(_v, dict) and key in _v

    # Which tool wrote the profile: its own key from the 0.7.0 generation on,
    # otherwise a signature table. The link budget has [[modes]], the power
    # budget [storage], this tool [sensor].
    _tool = _doc.get("tool")
    if not _tool:
        _tool = "bac_link_budget" if "modes" in _doc else ("bac_power_budget" if "storage" in _doc else "bac_optical_payload")
    profile_tool = str(_tool)
    return P, PH, profile_error, profile_name, profile_tool, profile_warnings


@app.cell
def _(
    P,
    PH,
    PROFILE_BAC,
    PROFILE_BOOM,
    PROFILE_GENERIC,
    mo,
    profile_error,
    profile_name,
    profile_tool,
    ui_profile,
):
    if profile_error:
        _status = mo.callout(
            mo.md(
                f"That file could not be read as TOML, so the defaults are unchanged. {profile_error}"
            ),
            kind="warn",
            title="Profile Not Loaded",
        )
    elif profile_name and profile_tool == "bac_link_budget":
        if PH("results.link_budget", "usable_kb_per_day"):
            _status = mo.md(
                f"Link budget profile loaded: **{profile_name}**. Its orbit, its station as the "
                f"target and its usable data per day ({P('results.link_budget', 'role', 'low rate')} slot) "
                "are taken; everything else is this tool's default."
            )
        else:
            _status = mo.callout(
                mo.md(
                    f"Link budget profile loaded: **{profile_name}**. Its orbit and its station as the "
                    "target are taken. It carries no `[results.link_budget]` table – the link budget "
                    "writes one from its 0.7.0 – so the downlink volumes keep their defaults; "
                    "re-export the profile from a current link budget or type the figure."
                ),
                kind="warn",
                title="Link Budget Profile Without Results",
            )
    elif profile_name and profile_tool == "bac_power_budget":
        _status = mo.md(
            f"Power budget profile loaded: **{profile_name}**. Its orbit, its activation location "
            "as the target and its planned activations per day as frames are taken; everything "
            "else is this tool's default."
        )
    elif profile_name:
        _status = mo.md(f"Profile loaded: **{profile_name}**.")
    else:
        _status = mo.md(
            "No profile loaded – the tool's own defaults are in use, which are the BAC demo "
            "mission's. Save the current settings as a profile from the export section below."
        )

    def _dedent_toml(text):
        return (
            "\n".join(
                _l[4:] if _l.startswith("    ") else _l
                for _l in text.strip("\n").splitlines()
            )
            + "\n"
        )

    def _shipped(label, text, slug):
        return mo.download(
            data=_dedent_toml(text).encode("utf-8"),
            filename=f"bac-optical-payload-{slug}.toml",
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
                                "Download one, then load it with the button above. The BAC "
                                "primary imager profile is what this notebook starts from and is a "
                                "candidate, not a decision. The boom profile is the engineering "
                                "camera looking back at the spacecraft. The generic one is a "
                                "different mission, and is here to show the tool is not the mission."
                            ),
                            mo.hstack(
                                [
                                    _shipped(
                                        "BAC primary imager", PROFILE_BAC, "profile-bac-primary"
                                    ),
                                    _shipped(
                                        "BAC boom camera", PROFILE_BOOM, "profile-bac-boom"
                                    ),
                                    _shipped(
                                        "Generic 1U", PROFILE_GENERIC, "profile-generic"
                                    ),
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
def _(CAMERAS, P, mo):
    # Camera preset. Its own cell, ahead of the sensor and lens dropdowns,
    # because those read it to pick their starting value.
    ui_camera = mo.ui.dropdown(
        options=["None"] + list(CAMERAS),
        value=P("camera", "name", "None"),
        label="Camera",
    )
    return (ui_camera,)


@app.cell
def _(CAMERAS, LENSES, P, PH, SENSOR_LABELS, mo, ui_camera):
    # Sensor and lens, apart from the rest of the panel so that changing the
    # camera rebuilds only these two dropdowns. Applying a preset is what a
    # change of the camera dropdown does: while it still shows what the profile
    # (or the default, "None") said, the profile's explicit sensor and lens
    # win, so a saved pair that departs from its preset survives a reload; pick
    # a different camera and its sensor and, where fixed, its lens are set.
    # "Custom" reads the fields beside the dropdown.
    _cam = CAMERAS.get(ui_camera.value)
    _as_loaded = ui_camera.value == P("camera", "name", "None")
    if _as_loaded and PH("sensor", "name"):
        _sensor_key = P("sensor", "name", "IMX477")
    else:
        _sensor_key = _cam[0] if _cam else P("sensor", "name", "IMX477")
    if _as_loaded and PH("lens", "name"):
        _lens_key = P("lens", "name", "C-mount 16 mm f/1.4")
    else:
        _lens_key = _cam[1] if _cam and _cam[1] else P("lens", "name", "C-mount 16 mm f/1.4")
    _sensor_options = {**SENSOR_LABELS, "Custom": "Custom"}
    _sensor_label = next((_l for _l, _k in _sensor_options.items() if _k == _sensor_key), "Custom")
    ui_sensor = mo.ui.dropdown(options=_sensor_options, value=_sensor_label, label="Sensor")
    ui_lens = mo.ui.dropdown(
        options=list(LENSES) + ["Custom"],
        value=_lens_key if _lens_key in LENSES else "Custom",
        label="Lens",
    )
    return ui_lens, ui_sensor


@app.cell
def _(
    CUBESATS,
    FACES,
    LENSES,
    LENS_KEYS,
    P,
    PH,
    SENSORS,
    SENSOR_KEYS,
    TARGETS,
    mo,
    pd,
):
    # Control panel – the only place inputs live. Every starting value comes
    # through P(), so a loaded profile sets the whole panel. A value a profile
    # puts outside an element's range is clamped rather than refused.
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

    _mode = P("mission", "mode", "Earth observation")
    ui_mode = mo.ui.dropdown(
        options=["Earth observation", "Boom"],
        value="Earth observation" if _mode == "Earth-looking" else _mode,  # pre-0.5.0 profiles
        label="Mode",
    )
    ui_altitude = S(start=300, stop=1200, step=10, value=P("orbit", "altitude_km", 450), show_value=True, label="Orbit altitude (km)")

    # Custom sensor and lens fields; the dropdowns are in the cell above.
    ui_sensor_w = N(start=64, stop=20000, step=1, value=P("sensor", "width_px", 4056), label="Custom width (px)")
    ui_sensor_h = N(start=64, stop=20000, step=1, value=P("sensor", "height_px", 3040), label="Custom height (px)")
    ui_sensor_pitch = N(start=0.5, stop=20, step=0.01, value=P("sensor", "pitch_um", 1.55), label="Custom pitch (µm)")
    ui_sensor_bits = N(start=8, stop=16, step=1, value=P("sensor", "bits", 12), label="Custom bit depth")
    ui_sensor_global = mo.ui.switch(value=P("sensor", "global_shutter", False), label="Custom sensor has a global shutter")
    ui_focal = N(start=1, stop=1000, step=0.1, value=P("lens", "focal_mm", 16.0), label="Custom focal length (mm)")
    ui_fnum = N(start=0.8, stop=32, step=0.1, value=P("lens", "f_number", 1.4), label="Custom f-number")
    ui_circle = N(start=1, stop=100, step=0.1, value=P("lens", "image_circle_mm", 16.0), label="Custom image circle (mm)")

    # Earth observation
    ui_exposure = S(start=0.05, stop=20, step=0.05, value=P("imaging", "exposure_ms", 0.5), show_value=True, include_input=True, label="Exposure (ms)")
    ui_readout = N(start=0.1, stop=200, step=0.1, value=P("imaging", "readout_ms", 20.0), label="Rolling-shutter readout (ms)")
    ui_att_rate = N(start=0, stop=10, step=0.01, value=P("imaging", "attitude_rate_deg_s", 0.5), label="Attitude rate (deg/s)")
    ui_point_err = N(start=0, stop=45, step=0.1, value=P("imaging", "pointing_error_deg", 5.0), label="Pointing error (deg)")
    ui_point_know = N(start=0, stop=45, step=0.01, value=P("imaging", "pointing_knowledge_deg", 5.0), label="Pointing knowledge (deg)")
    ui_wavelength = N(start=300, stop=1100, step=10, value=P("imaging", "wavelength_nm", 550), label="Wavelength (nm)")
    ui_compression = N(start=1, stop=100, step=0.5, value=P("imaging", "compression_ratio", 10.0), label="Compression ratio (n:1)")
    # A power budget profile plans its activations as a per-day cap, or, with
    # no cap, as whatever its triggers scheduled; either is the frames per day
    # here. What its energy affords is a callout, not an input.
    _pb_cap = P("payload", "cap_per_day", 0)
    _pb_sched = P("results.power_budget", "activations_scheduled_per_day", 0)
    _frames_default = int(round(_pb_cap)) if _pb_cap > 0 else (int(round(_pb_sched)) if _pb_sched > 0 else 4)
    ui_frames_day = N(start=0, stop=1000, step=1, value=P("imaging", "frames_per_day", _frames_default), label="Frames per day")
    # A link budget profile carries one usable-data figure under
    # [results.link_budget]; it lands in the slot its "role" key names, low
    # rate by default. This tool's own [imaging] keys win when present. A
    # profile without the table leaves the defaults and says so above.
    _lb_kb = P("results.link_budget", "usable_kb_per_day", None)
    _lb_role = str(P("results.link_budget", "role", "low rate")).lower()
    _low_default = _lb_kb if _lb_kb is not None and _lb_role != "high rate" else 1000
    _high_default = _lb_kb if _lb_kb is not None and _lb_role == "high rate" else 10000
    ui_low_rate = N(start=0, stop=1_000_000, step=1, value=P("imaging", "low_rate_kb_per_day", _low_default), label="Low-rate downlink (kB/day)")
    ui_high_rate = N(start=0, stop=10_000_000, step=1, value=P("imaging", "high_rate_kb_per_day", _high_default), label="High-rate downlink (kB/day)")

    # Boom
    ui_cubesat = mo.ui.dropdown(options=list(CUBESATS), value=P("boom", "cubesat", "1.5U"), label="CubeSat size")
    ui_face = mo.ui.dropdown(options=list(FACES), value=P("boom", "face", "+Z"), label="Deploying face")
    ui_off_x = N(start=-200, stop=200, step=1, value=P("boom", "offset_x_mm", 35.0), label="Root offset, first face axis (mm)")
    ui_off_y = N(start=-200, stop=200, step=1, value=P("boom", "offset_y_mm", 35.0), label="Root offset, second face axis (mm)")
    ui_boom_len = S(start=50, stop=2000, step=10, value=P("boom", "length_mm", 500), show_value=True, include_input=True, label="Boom length (mm)")
    ui_sweep = N(start=0, stop=90, step=1, value=P("boom", "sweep_deg", 0.0), label="Boom sweep from the face normal (deg)")
    ui_sweep_dir = N(start=0, stop=360, step=1, value=P("boom", "sweep_dir_deg", 45.0), label="Sweep direction in the face plane (deg)")
    ui_aim = mo.ui.switch(value=P("boom", "aim_at_center", True), label="Aim the boresight at the spacecraft center")
    ui_pitch = N(start=0, stop=90, step=0.5, value=P("boom", "pitch_deg", 15.0), label="Camera pitch from the boom axis (deg)")
    ui_yaw = N(start=0, stop=360, step=1, value=P("boom", "yaw_deg", 225.0), label="Pitch direction in the face plane (deg)")
    ui_focus = N(start=0, stop=5000, step=1, value=P("boom", "focus_mm", 0.0), label="Focus distance (mm, 0 = at the center)")
    ui_show_focus = mo.ui.switch(value=P("boom", "show_focus", False), label="Show depth of field in the views")

    # Target, access and illumination. A preset city or "Custom" with the
    # fields below it; a profile that names coordinates but no preset is Custom.
    # A link budget profile has no [target]; its ground station stands in,
    # matched by the part before the comma ("Bern, Switzerland" -> "Bern") or
    # taken as custom coordinates. A power budget profile has both; its
    # [target] is the activation location, which is the station unless it
    # says otherwise.
    _station = str(P("ground_station", "station", "")).split(",")[0].strip()
    if P("payload", "target_is_station", False) and PH("ground_station", "station"):
        _tname = _station if _station in TARGETS else "Custom"
        _tlat = P("ground_station", "latitude_deg", 46.95)
        _tlon = P("ground_station", "longitude_deg", 7.45)
    else:
        _tname = P("target", "name", _station if _station in TARGETS else ("Custom" if _station else ""))
        _tlat = P("target", "latitude_deg", P("ground_station", "latitude_deg", 46.95))
        _tlon = P("target", "longitude_deg", P("ground_station", "longitude_deg", 7.45))
    if _tname not in TARGETS:
        _tname = "Custom" if _tname == "Custom" or PH("target", "latitude_deg") else "Bern"
    ui_target = mo.ui.dropdown(options=list(TARGETS) + ["Custom"], value=_tname, label="Target")
    ui_target_lat = N(start=-90, stop=90, step=0.01, value=_tlat, label="Custom target latitude (deg N)")
    ui_target_lon = N(start=-180, stop=180, step=0.01, value=_tlon, label="Custom target longitude (deg E)")
    ui_inclination = N(start=0, stop=180, step=0.1, value=P("orbit", "inclination_deg", 97.4), label="Inclination (deg)")
    ui_ltdn = N(start=0, stop=24, step=0.25, value=P("orbit", "ltdn_hours", 10.5), label="Local time of descending node (h)")
    ui_epoch = mo.ui.text(value=str(P("orbit", "epoch", "2027-06-21")), label="Epoch (YYYY-MM-DD)")
    ui_sim_days = S(start=1, stop=60, step=1, value=P("orbit", "sim_days", 30), show_value=True, label="Days to simulate")
    ui_off_nadir = N(start=0, stop=60, step=1, value=P("imaging", "max_off_nadir_deg", 0), label="Maximum off-nadir angle for targeting (deg)")
    ui_min_sun = N(start=-10, stop=90, step=1, value=P("imaging", "min_sun_elevation_deg", P("payload", "min_sun_elevation_deg", 20)), label="Minimum Sun elevation at the target (deg)")

    # Map. The three keys live under [map], shared with the link budget;
    # profiles from before 0.7.0 kept them under [target].
    ui_tiles = mo.ui.switch(value=P("map", "tiles", P("target", "map_tiles", True)), label="Map tiles from CARTO")
    ui_map_zoom = S(start=2, stop=9, step=1, value=P("map", "zoom", P("target", "map_zoom", 5)), show_value=True, label="Map zoom (tile level)")
    # CARTO basemaps need a key since August 2026; a free one comes from
    # carto.com/basemaps/apikey. Without it the tiles still load, watermarked.
    # The shipped key is BAC's; it is visible to anyone running the notebook,
    # which CARTO expects for browser use.
    ui_tile_key = mo.ui.text(value=str(P("map", "key", P("target", "map_key", "cb1_3hdr_1_de5c1c882378bcd2934e6ba2"))), label="CARTO basemap key (free)")

    ui_sidebar = mo.ui.switch(value=False, label="Controls in a sidebar")

    # The libraries as tables, for reference; a sensor or lens that is not in
    # them goes in through the Custom fields.
    sensor_table = mo.ui.table(
        pd.DataFrame(
            [[_k, *_v] for _k, _v in SENSORS.items()], columns=SENSOR_KEYS
        ),
        selection=None,
        show_column_summaries=False,
        pagination=False,
        label="Sensor library",
    )
    lens_table = mo.ui.table(
        pd.DataFrame([[_k, *_v] for _k, _v in LENSES.items()], columns=LENS_KEYS),
        selection=None,
        show_column_summaries=False,
        pagination=False,
        label="Lens library",
    )
    return (
        lens_table,
        sensor_table,
        ui_aim,
        ui_altitude,
        ui_att_rate,
        ui_boom_len,
        ui_circle,
        ui_compression,
        ui_cubesat,
        ui_epoch,
        ui_exposure,
        ui_face,
        ui_fnum,
        ui_focal,
        ui_focus,
        ui_frames_day,
        ui_high_rate,
        ui_inclination,
        ui_low_rate,
        ui_ltdn,
        ui_map_zoom,
        ui_min_sun,
        ui_mode,
        ui_off_nadir,
        ui_off_x,
        ui_off_y,
        ui_pitch,
        ui_point_err,
        ui_point_know,
        ui_readout,
        ui_sensor_bits,
        ui_sensor_global,
        ui_sensor_h,
        ui_sensor_pitch,
        ui_sensor_w,
        ui_show_focus,
        ui_sidebar,
        ui_sim_days,
        ui_sweep,
        ui_sweep_dir,
        ui_target,
        ui_target_lat,
        ui_target_lon,
        ui_tile_key,
        ui_tiles,
        ui_wavelength,
        ui_yaw,
    )


@app.cell
def _(
    lens_table,
    mo,
    sensor_table,
    ui_aim,
    ui_altitude,
    ui_att_rate,
    ui_boom_len,
    ui_camera,
    ui_circle,
    ui_compression,
    ui_cubesat,
    ui_epoch,
    ui_exposure,
    ui_face,
    ui_fnum,
    ui_focal,
    ui_focus,
    ui_frames_day,
    ui_high_rate,
    ui_inclination,
    ui_lens,
    ui_low_rate,
    ui_ltdn,
    ui_map_zoom,
    ui_min_sun,
    ui_mode,
    ui_off_nadir,
    ui_off_x,
    ui_off_y,
    ui_pitch,
    ui_point_err,
    ui_point_know,
    ui_readout,
    ui_sensor,
    ui_sensor_bits,
    ui_sensor_global,
    ui_sensor_h,
    ui_sensor_pitch,
    ui_sensor_w,
    ui_show_focus,
    ui_sim_days,
    ui_sweep,
    ui_sweep_dir,
    ui_target,
    ui_target_lat,
    ui_target_lon,
    ui_tile_key,
    ui_tiles,
    ui_wavelength,
    ui_yaw,
):
    # Panel layout lives apart from the element definitions so it can read the
    # mode: the left column is common, the right column is whichever mode is
    # selected. A cell cannot read a control it defines.
    _left = mo.vstack(
        [
            mo.md("**Mission**"),
            ui_mode,
            ui_altitude,
            mo.md("**Camera**"),
            ui_camera,
            mo.md("Sets the sensor and, for a fixed lens, the lens; both stay editable. A loaded profile's own sensor and lens win until the camera is changed."),
            mo.md("**Sensor**"),
            ui_sensor,
            mo.accordion(
                {
                    "Custom sensor": mo.vstack(
                        [ui_sensor_w, ui_sensor_h, ui_sensor_pitch, ui_sensor_bits, ui_sensor_global]
                    )
                }
            ),
            mo.md("**Lens**"),
            ui_lens,
            mo.accordion({"Custom lens": mo.vstack([ui_focal, ui_fnum, ui_circle])}),
            mo.md("**Data and link**"),
            ui_compression,
            ui_frames_day,
            ui_low_rate,
            ui_high_rate,
        ]
    )
    if ui_mode.value == "Earth observation":
        _right = mo.vstack(
            [
                mo.md("**Earth observation**"),
                ui_exposure,
                ui_readout,
                ui_att_rate,
                ui_point_err,
                ui_point_know,
                ui_wavelength,
                mo.md("**Target, access and illumination**"),
                ui_target,
                mo.accordion({"Custom target": mo.vstack([ui_target_lat, ui_target_lon])}),
                ui_inclination,
                ui_ltdn,
                ui_epoch,
                ui_sim_days,
                ui_off_nadir,
                ui_min_sun,
                mo.md("**Map**"),
                ui_tiles,
                ui_map_zoom,
                ui_tile_key,
            ]
        )
    else:
        _right = mo.vstack(
            [
                mo.md("**Boom**"),
                ui_cubesat,
                ui_face,
                ui_off_x,
                ui_off_y,
                ui_boom_len,
                ui_sweep,
                ui_sweep_dir,
                ui_aim,
                ui_pitch,
                ui_yaw,
                ui_focus,
                ui_show_focus,
            ]
        )
    knobs_wide = mo.hstack([_left, _right], justify="start", gap=2, wrap=True, widths="equal")
    knobs_tall = mo.vstack([_left, _right])
    library_block = mo.accordion({"Sensor and Lens Libraries": mo.vstack([sensor_table, lens_table])})
    return knobs_tall, knobs_wide, library_block


@app.cell
def _(knobs_tall, mo, ui_sidebar):
    # mo.sidebar has to be the last expression of its own cell.
    mo.sidebar([mo.md("### Control Panel"), knobs_tall], width="360px") if ui_sidebar.value else None
    return


@app.cell
def _(knobs_wide, library_block, mo, profile_block, ui_sidebar):
    mo.vstack(
        [
            mo.md("## Control Panel"),
            profile_block,
            ui_sidebar,
            mo.md("The knobs are in the sidebar. Turn this off to bring them back here.")
            if ui_sidebar.value
            else knobs_wide,
            library_block,
        ]
    )
    return


@app.cell
def _(
    LENSES,
    SENSORS,
    TARGETS,
    ui_circle,
    ui_fnum,
    ui_focal,
    ui_lens,
    ui_sensor,
    ui_sensor_bits,
    ui_sensor_global,
    ui_sensor_h,
    ui_sensor_pitch,
    ui_sensor_w,
    ui_target,
    ui_target_lat,
    ui_target_lon,
):
    # Resolve the target: a preset or the custom fields.
    target_name = ui_target.value
    target_lat, target_lon = (
        TARGETS[target_name] if target_name in TARGETS else (float(ui_target_lat.value), float(ui_target_lon.value))
    )

    # Resolve the sensor and lens into the numbers the model uses.
    if ui_sensor.value == "Custom":
        sensor = dict(
            name="Custom",
            w=int(ui_sensor_w.value),
            h=int(ui_sensor_h.value),
            pitch_um=float(ui_sensor_pitch.value),
            bits=int(ui_sensor_bits.value),
            shutter="global" if ui_sensor_global.value else "rolling",
            color="RGB",
            status="custom",
        )
    else:
        _w, _h, _p, _b, _sh, _c, _st, _note = SENSORS[ui_sensor.value]
        sensor = dict(name=ui_sensor.value, w=_w, h=_h, pitch_um=_p, bits=_b, shutter=_sh, color=_c, status=_st)

    if ui_lens.value == "Custom":
        lens = dict(
            name="Custom",
            f_mm=float(ui_focal.value),
            n=float(ui_fnum.value),
            mount="custom",
            circle_mm=float(ui_circle.value),
        )
    else:
        _f, _n, _m, _ic, _ln = LENSES[ui_lens.value]
        lens = dict(name=ui_lens.value, f_mm=_f, n=_n, mount=_m, circle_mm=_ic)

    sensor["width_mm"] = sensor["w"] * sensor["pitch_um"] / 1000
    sensor["height_mm"] = sensor["h"] * sensor["pitch_um"] / 1000
    sensor["diag_mm"] = (sensor["width_mm"] ** 2 + sensor["height_mm"] ** 2) ** 0.5
    sensor["mpix"] = sensor["w"] * sensor["h"] / 1e6
    lens["aperture_mm"] = lens["f_mm"] / lens["n"]
    return lens, sensor, target_lat, target_lon, target_name


@app.cell
def _(
    R_EARTH_KM,
    ground_offset_km,
    ground_speed_km_s,
    lens,
    np,
    sensor,
    ui_altitude,
    ui_att_rate,
    ui_exposure,
    ui_point_err,
    ui_point_know,
    ui_readout,
    ui_wavelength,
):
    # Earth observation geometry at nadir, plus the three reality checks.
    h_km = float(ui_altitude.value)
    f_mm = lens["f_mm"]
    pitch_um = sensor["pitch_um"]

    gsd_m = pitch_um * h_km / f_mm  # µm·km/mm = m
    swath_x_km = gsd_m * sensor["w"] / 1000
    swath_y_km = gsd_m * sensor["h"] / 1000
    fov_x_deg = float(np.degrees(2 * np.arctan(sensor["width_mm"] / (2 * f_mm))))
    fov_y_deg = float(np.degrees(2 * np.arctan(sensor["height_mm"] / (2 * f_mm))))
    ifov_arcsec = float(np.degrees(pitch_um / 1000 / f_mm) * 3600)

    # Diffraction: Rayleigh spot on the ground and the sampling factor Q.
    lam_um = float(ui_wavelength.value) / 1000
    rayleigh_ground_m = 1.22 * lam_um * h_km / lens["aperture_mm"]  # µm·km/mm = m
    q_factor = lam_um * lens["n"] / pitch_um

    # Motion smear from the sub-satellite point speed, and from attitude rate.
    v_ground_m_s = ground_speed_km_s(h_km) * 1000
    smear_m = v_ground_m_s * float(ui_exposure.value) / 1000
    smear_px = smear_m / gsd_m
    att_smear_px = (
        np.radians(float(ui_att_rate.value)) * float(ui_exposure.value) / 1000
        / (pitch_um / 1000 / f_mm)
    )
    skew_px = (
        v_ground_m_s * float(ui_readout.value) / 1000 / gsd_m
        if sensor["shutter"] == "rolling"
        else 0.0
    )

    # Pointing: error moves the footprint, knowledge limits geolocation. Both
    # use the spherical-Earth offset the off-nadir chart and the access reach
    # use, so every ground distance in the tool comes from one geometry.
    point_shift_km = ground_offset_km(ui_point_err.value, h_km)
    geoloc_km = ground_offset_km(ui_point_know.value, h_km)
    envelope_x_km = swath_x_km + 2 * point_shift_km
    envelope_y_km = swath_y_km + 2 * point_shift_km

    # Ground distance to the horizon, to say how far the frame could look.
    horizon_km = R_EARTH_KM * float(np.arccos(R_EARTH_KM / (R_EARTH_KM + h_km)))
    circle_ok = lens["circle_mm"] >= sensor["diag_mm"] - 1e-9
    diffraction_limited = rayleigh_ground_m > gsd_m
    return (
        att_smear_px,
        circle_ok,
        diffraction_limited,
        envelope_x_km,
        envelope_y_km,
        fov_x_deg,
        fov_y_deg,
        geoloc_km,
        gsd_m,
        h_km,
        horizon_km,
        ifov_arcsec,
        point_shift_km,
        q_factor,
        rayleigh_ground_m,
        skew_px,
        smear_m,
        smear_px,
        swath_x_km,
        swath_y_km,
        v_ground_m_s,
    )


@app.cell
def _(sensor, ui_compression, ui_frames_day, ui_high_rate, ui_low_rate):
    # Data volume: raw and compressed frames against the two links.
    raw_kb = sensor["w"] * sensor["h"] * sensor["bits"] / 8 / 1000
    comp_kb = raw_kb / max(float(ui_compression.value), 1.0)
    thumb_kb = raw_kb / 64 / max(float(ui_compression.value), 1.0)  # 8× binned
    per_day_kb = comp_kb * float(ui_frames_day.value)

    def _days(kb, rate):
        return float("inf") if rate <= 0 else kb / rate

    low_kb = float(ui_low_rate.value)
    high_kb = float(ui_high_rate.value)
    days_raw_low = _days(raw_kb, low_kb)
    days_comp_low = _days(comp_kb, low_kb)
    days_raw_high = _days(raw_kb, high_kb)
    days_comp_high = _days(comp_kb, high_kb)
    link_share_low = float("inf") if low_kb <= 0 else per_day_kb / low_kb
    return (
        comp_kb,
        days_comp_high,
        days_comp_low,
        days_raw_high,
        days_raw_low,
        high_kb,
        link_share_low,
        low_kb,
        per_day_kb,
        raw_kb,
        thumb_kb,
    )


@app.cell
def _(
    CUBESATS,
    FACES,
    lens,
    np,
    sensor,
    ui_aim,
    ui_boom_len,
    ui_cubesat,
    ui_face,
    ui_focus,
    ui_off_x,
    ui_off_y,
    ui_pitch,
    ui_sweep,
    ui_sweep_dir,
    ui_yaw,
):
    # Boom geometry. Body frame at the box center, axes along the box edges. The
    # boom leaves the chosen face along its normal from a root offset in the
    # two face axes, and the camera sits at its tip. Pitch tilts the boresight
    # away from looking straight back along the boom; yaw says in which
    # direction within the face plane, measured from the first face axis.
    dims = np.array(CUBESATS[ui_cubesat.value])
    normal = FACES[ui_face.value]
    _axis = int(np.argmax(np.abs(normal)))
    _others = [_i for _i in range(3) if _i != _axis]
    face_axes = (np.eye(3)[_others[0]], np.eye(3)[_others[1]])
    face_axis_names = ("XYZ"[_others[0]], "XYZ"[_others[1]])
    root = normal * dims[_axis] / 2 + face_axes[0] * ui_off_x.value + face_axes[1] * ui_off_y.value
    # The boom itself can be swept off the normal, which is what lets a camera
    # see a side face: from inside the face's own footprint it cannot.
    _sa, _sd = np.radians(float(ui_sweep.value)), np.radians(float(ui_sweep_dir.value))
    boom_dir = np.cos(_sa) * normal + np.sin(_sa) * (np.cos(_sd) * face_axes[0] + np.sin(_sd) * face_axes[1])

    _hx, _hy, _hz = dims / 2
    corners = np.array(
        [[sx * _hx, sy * _hy, sz * _hz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    )
    edges = [
        (a, b)
        for a in range(8)
        for b in range(a + 1, 8)
        if np.sum(corners[a] != corners[b]) == 1
    ]
    half_w, half_h = sensor["width_mm"] / 2, sensor["height_mm"] / 2

    def _hull(pts):
        pts = sorted(set(map(tuple, pts)))
        if len(pts) < 3:
            return pts

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        lower, upper = [], []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        return lower[:-1] + upper[:-1]

    def _clip(poly, hw, hh):
        # Sutherland–Hodgman against the frame rectangle.
        def clip_edge(poly, inside_fn, intersect_fn):
            out = []
            for i, cur in enumerate(poly):
                prev = poly[i - 1]
                if inside_fn(cur):
                    if not inside_fn(prev):
                        out.append(intersect_fn(prev, cur))
                    out.append(cur)
                elif inside_fn(prev):
                    out.append(intersect_fn(prev, cur))
            return out

        def lerp(p, q, t):
            return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)

        for axis, lim, sign in ((0, hw, 1), (0, -hw, -1), (1, hh, 1), (1, -hh, -1)):
            if not poly:
                break
            poly = clip_edge(
                poly,
                lambda p, a=axis, l=lim, s=sign: s * p[a] <= s * l,
                lambda p, q, a=axis, l=lim: lerp(p, q, (l - p[a]) / (q[a] - p[a])),
            )
        return poly

    def _area(poly):
        if len(poly) < 3:
            return 0.0
        return 0.5 * abs(
            sum(poly[i][0] * poly[i - 1][1] - poly[i - 1][0] * poly[i][1] for i in range(len(poly)))
        )

    def boom_view(length_mm):
        # Everything the frame contains for one boom length, with the aim and
        # tilt settings from the panel. Used for the current geometry and for
        # the boom-length sweep.
        cam = root + boom_dir * float(length_mm)
        if ui_aim.value:
            bore = -cam / np.linalg.norm(cam)
            pitch = float(np.degrees(np.arccos(np.clip(np.dot(bore, -normal), -1, 1))))
            inplane = bore - np.dot(bore, -normal) * (-normal)
            yaw = (
                float(np.degrees(np.arctan2(np.dot(inplane, face_axes[1]), np.dot(inplane, face_axes[0])))) % 360
                if np.linalg.norm(inplane) > 1e-9
                else 0.0
            )
        else:
            pitch, yaw = float(ui_pitch.value), float(ui_yaw.value)
            _p, _y = np.radians(pitch), np.radians(yaw)
            inplane = np.cos(_y) * face_axes[0] + np.sin(_y) * face_axes[1]
            bore = np.cos(_p) * (-normal) + np.sin(_p) * inplane
            bore = bore / np.linalg.norm(bore)
        # Image axes: "up" is the second face axis projected off the boresight,
        # so an untilted camera shows the face with its axes upright.
        up_ref = face_axes[1]
        up = up_ref - np.dot(up_ref, bore) * bore
        if np.linalg.norm(up) < 1e-6:
            up_ref = face_axes[0]
            up = up_ref - np.dot(up_ref, bore) * bore
        up = up / np.linalg.norm(up)
        right = np.cross(bore, up)
        v = corners - cam
        d = v @ bore
        px = np.where(d > 1e-9, lens["f_mm"] * (v @ right) / np.maximum(d, 1e-9), np.nan)
        py = np.where(d > 1e-9, lens["f_mm"] * (v @ up) / np.maximum(d, 1e-9), np.nan)
        inside = (np.abs(px) <= half_w) & (np.abs(py) <= half_h) & (d > 0)
        pts = [(float(x), float(y)) for x, y, dd in zip(px, py, d) if dd > 0]
        fill = _area(_clip(_hull(pts), half_w, half_h)) / (4 * half_w * half_h) if pts else 0.0
        return dict(
            cam=cam, bore=bore, up=up, right=right, pitch=pitch, yaw=yaw, depth=d,
            px=px, py=py, corners_in=int(inside.sum()), fill=fill,
        )

    _now = boom_view(ui_boom_len.value)
    cam, boresight, up, right = _now["cam"], _now["bore"], _now["up"], _now["right"]
    pitch_used, yaw_used = _now["pitch"], _now["yaw"]
    depth, proj_x, proj_y = _now["depth"], _now["px"], _now["py"]
    corners_in_frame, fill_fraction = _now["corners_in"], _now["fill"]

    # Face centers, for labels on the faces the camera can see.
    face_labels = []
    for _name, _n in FACES.items():
        _c = _n * dims[int(np.argmax(np.abs(_n)))] / 2
        _v = _c - cam
        _d = float(_v @ boresight)
        if _d > 1e-9 and float(np.dot(_n, -_v)) > 0:  # facing the camera
            face_labels.append(
                {"face": _name, "x": lens["f_mm"] * float(_v @ right) / _d, "y": lens["f_mm"] * float(_v @ up) / _d}
            )

    # Sweep of boom length at the same aim settings.
    sweep = [
        {"length_mm": _l, "fill_pct": boom_view(_l)["fill"] * 100, "corners_in": boom_view(_l)["corners_in"]}
        for _l in range(50, 2001, 25)
    ]

    dist_center_mm = float(np.linalg.norm(cam))
    dist_near_mm = float(depth[depth > 0].min()) if (depth > 0).any() else float("nan")
    dist_far_mm = float(depth.max())
    gsd_center_mm_px = sensor["pitch_um"] / 1000 * dist_center_mm / lens["f_mm"]

    # Depth of field with a circle of confusion of two pixels. A thin lens
    # cannot focus at or inside its focal length, so such a focus distance is
    # refused and the center distance used instead, with a callout; an object
    # at or inside the focal length has no image and gets no blur figure.
    coc_mm = 2 * sensor["pitch_um"] / 1000
    hyperfocal_mm = lens["f_mm"] ** 2 / (lens["n"] * coc_mm) + lens["f_mm"]
    _focus_asked = float(ui_focus.value)
    focus_invalid = 0 < _focus_asked <= lens["f_mm"]
    focus_mm = _focus_asked if _focus_asked > 0 and not focus_invalid else dist_center_mm
    focus_inside_f = focus_mm <= lens["f_mm"]  # the center itself inside the focal length
    if focus_inside_f:
        dof_near_mm = dof_far_mm = float("nan")
    else:
        dof_near_mm = focus_mm * hyperfocal_mm / (hyperfocal_mm + (focus_mm - lens["f_mm"]))
        dof_far_mm = (
            float("inf")
            if focus_mm >= hyperfocal_mm
            else focus_mm * hyperfocal_mm / (hyperfocal_mm - (focus_mm - lens["f_mm"]))
        )
    object_inside_f = bool(dist_near_mm <= lens["f_mm"]) if dist_near_mm == dist_near_mm else False
    box_in_focus = (not focus_inside_f) and (not object_inside_f) and dof_near_mm <= dist_near_mm and dof_far_mm >= dist_far_mm

    def blur_px(dist_mm):
        # Blur-circle diameter in pixels for a point at that distance along the
        # boresight, thin lens focused at focus_mm. The CoC above is 2 px, so
        # 2 px is "in focus" and 6 px is where this tool calls it out of focus.
        # NaN where no image forms: object or focus at or inside the focal length.
        _d = np.asarray(dist_mm, dtype=float)
        if focus_inside_f:
            return np.full_like(_d, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            _c = lens["f_mm"] ** 2 / lens["n"] * np.abs(_d - focus_mm) / (_d * (focus_mm - lens["f_mm"]))
        return np.where(_d > lens["f_mm"], _c / (sensor["pitch_um"] / 1000), np.nan)

    return (
        blur_px,
        boom_dir,
        boresight,
        box_in_focus,
        cam,
        corners,
        corners_in_frame,
        depth,
        dims,
        dist_center_mm,
        dist_far_mm,
        dist_near_mm,
        dof_far_mm,
        dof_near_mm,
        edges,
        face_axes,
        face_axis_names,
        face_labels,
        fill_fraction,
        focus_inside_f,
        focus_invalid,
        focus_mm,
        gsd_center_mm_px,
        half_h,
        half_w,
        hyperfocal_mm,
        normal,
        object_inside_f,
        pitch_used,
        right,
        root,
        sweep,
        up,
        yaw_used,
    )


@app.cell
def _(alt, mo):
    # Chart conventions shared by both modes.
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

    def rule_x(value, dashed=True):
        return (
            alt.Chart(alt.Data(values=[{"x": value}]))
            .mark_rule(strokeDash=[6, 4] if dashed else [2, 2], color=MUTED)
            .encode(x="x:Q")
        )

    return FONT, IS_DARK, MUTED, PALETTE, TEXT, rule_x, style_chart


@app.cell
def _(
    box_in_focus,
    comp_kb,
    corners_in_frame,
    days_comp_low,
    diffraction_limited,
    dist_center_mm,
    dof_far_mm,
    dof_near_mm,
    fill_fraction,
    fmt_int,
    fmt_num,
    fov_x_deg,
    fov_y_deg,
    gsd_center_mm_px,
    gsd_m,
    lens,
    low_kb,
    mo,
    raw_kb,
    rayleigh_ground_m,
    sensor,
    smear_px,
    swath_x_km,
    swath_y_km,
    ui_mode,
):
    def _stat(value, label, caption):
        return mo.stat(value=value, label=label, caption=caption, bordered=True)

    def _days(d):
        if d == float("inf"):
            return "no link"
        return f"{d:.1f} days" if d >= 1 else f"{d * 24:.1f} hours"

    _which = f"{sensor['name']}, {sensor['mpix']:.1f} MP, {lens['name']} – f/{lens['n']:g}, {lens['aperture_mm']:.1f} mm aperture."

    if ui_mode.value == "Earth observation":
        _row1 = mo.hstack(
            [
                _stat(f"{fmt_num(gsd_m, 1)} m", "GSD at Nadir", "meters per pixel"),
                _stat(f"{fmt_num(swath_x_km, 0)} × {fmt_num(swath_y_km, 0)} km", "Swath", f"{fov_x_deg:.1f}° × {fov_y_deg:.1f}° field of view"),
                _stat(
                    f"{fmt_num(rayleigh_ground_m, 1)} m",
                    "Rayleigh Spot",
                    "larger than the GSD – diffraction limited" if diffraction_limited else "smaller than the GSD – detector limited",
                ),
            ],
            widths="equal",
        )
        _row2 = mo.hstack(
            [
                _stat(f"{smear_px:.2f} px", "Motion Smear", "ground motion during the exposure"),
                _stat(f"{fmt_num(raw_kb / 1000, 1)} MB", "Raw Frame", f"{fmt_int(comp_kb)} kB compressed"),
                _stat(_days(days_comp_low), "Compressed Frame, Low Rate", f"at {fmt_int(low_kb)} kB/day"),
            ],
            widths="equal",
        )
    else:
        _row1 = mo.hstack(
            [
                _stat(f"{fmt_int(dist_center_mm)} mm", "Camera to Center", "boom tip to spacecraft center"),
                _stat(f"{fill_fraction * 100:.0f}%", "Frame Filled", f"{corners_in_frame} of 8 corners in the frame"),
                _stat(f"{fov_x_deg:.1f}° × {fov_y_deg:.1f}°", "Field of View", "at the boom camera"),
            ],
            widths="equal",
        )
        _row2 = mo.hstack(
            [
                _stat(f"{gsd_center_mm_px:.2f} mm", "Scale at Center", "millimeters per pixel"),
                _stat(
                    f"{fmt_int(dof_near_mm)} mm – {'∞' if dof_far_mm == float('inf') else fmt_int(dof_far_mm) + ' mm'}",
                    "Depth of Field",
                    "whole spacecraft sharp" if box_in_focus else "part of the spacecraft outside focus",
                ),
                _stat(f"{fmt_num(raw_kb / 1000, 1)} MB", "Raw Frame", f"{fmt_int(comp_kb)} kB compressed"),
            ],
            widths="equal",
        )
    mo.vstack([mo.md("## Headline Numbers"), mo.md(_which), _row1, _row2])
    return


@app.cell
def _(
    P,
    PH,
    att_smear_px,
    box_in_focus,
    circle_ok,
    corners_in_frame,
    diffraction_limited,
    fmt_num,
    focus_inside_f,
    focus_invalid,
    gsd_m,
    high_kb,
    lens,
    link_share_low,
    low_kb,
    mo,
    object_inside_f,
    profile_warnings,
    q_factor,
    rayleigh_ground_m,
    sensor,
    skew_px,
    smear_px,
    ui_focus,
    ui_frames_day,
    ui_mode,
):
    # Callouts: the things a first-time reader must not skip past.
    _items = []
    if sensor["status"] == "provisional":
        _items.append(
            mo.callout(
                mo.md(
                    f"The {sensor['name']} entry is provisional: its pixel count, pitch and bit depth "
                    "are from memory of the sensor family, not from the datasheet. Verify them "
                    "before a decision rests on these numbers."
                ),
                kind="warn",
                title="Provisional Sensor Entry",
            )
        )
    if not circle_ok:
        _items.append(
            mo.callout(
                mo.md(
                    f"The lens image circle ({lens['circle_mm']:.1f} mm) is smaller than the sensor "
                    f"diagonal ({sensor['diag_mm']:.1f} mm). The corners of the frame will vignette or "
                    "be dark. Choose a lens for a larger format, or a smaller sensor."
                ),
                kind="danger",
                title="Lens Does Not Cover the Sensor",
            )
        )
    if ui_mode.value == "Earth observation":
        if diffraction_limited:
            _items.append(
                mo.callout(
                    mo.md(
                        f"The Rayleigh spot on the ground ({fmt_num(rayleigh_ground_m, 1)} m) is larger than "
                        f"the GSD ({fmt_num(gsd_m, 1)} m), Q = {q_factor:.2f}. The aperture, not the pixel "
                        "count, sets the resolution. A longer lens at the same f-number shrinks spot and "
                        "GSD together and leaves Q where it is; a lower f-number or a coarser pitch is "
                        "what moves the system toward detector limited."
                    ),
                    kind="warn",
                    title="Diffraction Limited",
                )
            )
        elif q_factor < 0.5:
            _items.append(
                mo.callout(
                    mo.md(
                        f"Q = {q_factor:.2f}: the pixels are much coarser than the optics can deliver. The "
                        "GSD is the resolution, and the image will alias on sharp edges."
                    ),
                    kind="info",
                    title="Strongly Detector Limited",
                )
            )
        if smear_px > 1 or att_smear_px > 1:
            _items.append(
                mo.callout(
                    mo.md(
                        f"Ground motion smears {smear_px:.2f} px and the attitude rate {att_smear_px:.1f} px "
                        "during the exposure. Shorten the exposure, or accept that the effective "
                        "resolution is the smear, not the GSD."
                    ),
                    kind="warn",
                    title="Smear Exceeds One Pixel",
                )
            )
        if skew_px > 1:
            _items.append(
                mo.callout(
                    mo.md(
                        f"Rolling-shutter readout shears the frame by about {skew_px:.0f} px between its "
                        "first and last line. Geolocation has to correct for it, or the frame is "
                        "cropped to a band; a global shutter has none."
                    ),
                    kind="info",
                    title="Rolling-Shutter Skew",
                )
            )
        if 0 < high_kb < low_kb:
            _items.append(
                mo.callout(
                    mo.md(
                        f"The high-rate link carries {fmt_num(low_kb / high_kb, 1)}× less per day than the low-rate one. "
                        "That is usually margin rather than bit rate: a faster waveform needs more signal, so it "
                        "closes for a shorter part of each pass. The fix is on the ground – a better front end, "
                        "tighter tracking, a bigger antenna, or coherent demodulation – and the "
                        "[link budget](https://bac.page/link-budget-tool) is where those are traded."
                    ),
                    kind="info",
                    title="High Rate Below Low Rate",
                )
            )
        if link_share_low > 1:
            _items.append(
                mo.callout(
                    mo.md(
                        f"The planned frames per day need {link_share_low:.1f}× the low-rate daily volume. "
                        "Either fewer frames, more compression, thumbnails first, or the high-rate link."
                    ),
                    kind="danger",
                    title="Frames Exceed the Link",
                )
            )
        # Demand against energy, when a power budget profile carried its results.
        if PH("results.power_budget", "sustainable_activations_per_day"):
            _afford = float(P("results.power_budget", "sustainable_activations_per_day", 0.0))
            _planned = float(ui_frames_day.value)
            _items.append(
                mo.callout(
                    mo.md(
                        f"The power budget profile affords {'unlimited' if _afford == float('inf') else fmt_num(_afford, 1)} "
                        f"activations a day at its payload draw; {_planned:g} frames a day are planned here."
                        + (" The camera cannot run that often on that energy." if _afford < _planned else "")
                    ),
                    kind="warn" if _afford < _planned else "info",
                    title="Frames Against the Power Budget",
                )
            )
    else:
        if focus_invalid:
            _items.append(
                mo.callout(
                    mo.md(
                        f"A focus distance of {ui_focus.value:g} mm is at or inside the {lens['f_mm']:g} mm focal "
                        "length, where a thin lens forms no image. The views use the center distance instead."
                    ),
                    kind="warn",
                    title="Focus Distance Inside the Focal Length",
                )
            )
        if focus_inside_f or object_inside_f:
            _items.append(
                mo.callout(
                    mo.md(
                        f"Part of the spacecraft lies at or inside the {lens['f_mm']:g} mm focal length of the "
                        "camera, where a thin lens forms no image at all. Lengthen the boom or shorten the lens; "
                        "the depth-of-field figures are blank until then."
                    ),
                    kind="danger",
                    title="Spacecraft Inside the Focal Length",
                )
            )
        if corners_in_frame < 8:
            _items.append(
                mo.callout(
                    mo.md(
                        f"Only {corners_in_frame} of the 8 corners are in the frame. A longer boom, a "
                        "shorter lens or a different pitch brings the whole spacecraft into view."
                    ),
                    kind="warn",
                    title="Spacecraft Cut Off",
                )
            )
        if not box_in_focus and not (focus_inside_f or object_inside_f):
            _items.append(
                mo.callout(
                    mo.md(
                        "Part of the spacecraft lies outside the depth of field at this focus distance "
                        "and f-number. Stop the lens down, focus nearer the hyperfocal distance, or "
                        "accept soft corners."
                    ),
                    kind="warn",
                    title="Depth of Field Too Shallow",
                )
            )
    if profile_warnings:
        _items.append(
            mo.callout(
                mo.md("These profile values were not numbers and fell back to the defaults: " + ", ".join(profile_warnings[:8]) + (" and more." if len(profile_warnings) > 8 else ".")),
                kind="warn",
                title="Profile Values Ignored",
            )
        )
    mo.vstack(_items) if _items else mo.md("No callouts: nothing in the current settings needs a warning.")
    return


@app.cell
def _(
    IS_DARK,
    MUTED,
    PALETTE,
    TEXT,
    accesses,
    alt,
    envelope_x_km,
    envelope_y_km,
    mo,
    np,
    pd,
    step_s,
    style_chart,
    sub_lat,
    sub_lon,
    swath_x_km,
    swath_y_km,
    target_lat,
    target_lon,
    target_name,
    ui_map_zoom,
    ui_mode,
    ui_tile_key,
    ui_tiles,
):
    # Map: grayscale CARTO basemap tiles (OpenStreetMap data, light or dark to
    # match the notebook theme, no labels) under a Natural Earth coastline, the
    # target, the nadir footprint with its pointing envelope, the first day's
    # ground track, and the sub-satellite tracks of the accesses. The tiles are
    # Web Mercator images placed in pixel space under a mercator projection with
    # the same scale, so they line up with the projected layers, and they are
    # clipped to the view so the map stays the size of the chart. If they do
    # not load, the coastline still carries the picture; the switch turns them off.
    if ui_mode.value == "Earth observation":
        _tlat, _tlon = float(target_lat), float(target_lon)
        _w, _h, _z = 960, 540, int(ui_map_zoom.value)
        _world_px = 256 * 2**_z
        _scale = _world_px / (2 * np.pi)  # px per radian, mercator
        _cx = (_tlon + 180) / 360 * _world_px
        _lat_r = np.radians(np.clip(_tlat, -85, 85))
        _cy = (1 - np.log(np.tan(_lat_r) + 1 / np.cos(_lat_r)) / np.pi) / 2 * _world_px
        _x0, _y0 = _cx - _w / 2, _cy - _h / 2
        _style = "dark_nolabels" if IS_DARK else "light_nolabels"
        _key = f"?key={ui_tile_key.value.strip()}" if ui_tile_key.value.strip() else ""
        _tiles = [
            {
                "url": f"https://basemaps.cartocdn.com/rastertiles/{_style}/{_z}/{_tx % 2**_z}/{_ty}.png{_key}",
                "x": _tx * 256 - _x0,
                "y": _ty * 256 - _y0,
            }
            for _tx in range(int(np.floor(_x0 / 256)), int(np.floor((_x0 + _w) / 256)) + 1)
            for _ty in range(max(int(np.floor(_y0 / 256)), 0), min(int(np.floor((_y0 + _h) / 256)), 2**_z - 1) + 1)
        ]
        _kmlat = 111.2
        _kmlon = 111.2 * max(np.cos(np.radians(_tlat)), 0.05)

        def _rect(wx, wy, what):
            _dx, _dy = wx / 2 / _kmlon, wy / 2 / _kmlat
            return pd.DataFrame(
                {
                    "lon": [_tlon - _dx, _tlon + _dx, _tlon + _dx, _tlon - _dx, _tlon - _dx],
                    "lat": [_tlat - _dy, _tlat - _dy, _tlat + _dy, _tlat + _dy, _tlat - _dy],
                    "order": range(5),
                    "what": what,
                }
            )

        _boxes = pd.concat([_rect(swath_x_km, swath_y_km, "Footprint"), _rect(envelope_x_km, envelope_y_km, "Pointing envelope")])
        _n_day = int(86400 / step_s)
        _every = max(int(60 / step_s), 1)  # one point a minute is plenty for a line
        _track = pd.DataFrame({"lon": sub_lon[:_n_day:_every], "lat": sub_lat[:_n_day:_every]})
        _track["i"] = range(len(_track))
        _track["orbit"] = (np.abs(np.diff(_track["lon"], prepend=_track["lon"].iloc[0])) > 180).cumsum()  # split at the date line either way
        _acc_rows = []
        for _k, _a in enumerate(accesses[:12]):
            _i0 = int(_a["t_mid"] / step_s)
            _lo, _hi = max(_i0 - 60, 0), min(_i0 + 60, len(sub_lon))
            _acc_rows.append(pd.DataFrame({"lon": sub_lon[_lo:_hi], "lat": sub_lat[_lo:_hi], "i": range(_hi - _lo), "k": _k, "lit": "lit" if _a["lit"] else "dark"}))
        _acc = pd.concat(_acc_rows) if _acc_rows else pd.DataFrame(columns=["lon", "lat", "i", "k", "lit"])

        _proj = alt.Projection(type="mercator", center=[_tlon, _tlat], scale=_scale, clipExtent=[[0, 0], [_w, _h]])
        _layers = []
        if ui_tiles.value and _tiles:
            _layers.append(
                alt.Chart(pd.DataFrame(_tiles))
                .mark_image(width=256, height=256, align="left", baseline="top", clip=True)
                .encode(x=alt.X("x:Q").scale(None).axis(None), y=alt.Y("y:Q").scale(None).axis(None), url="url:N")
            )
        _world = alt.topo_feature("https://cdn.jsdelivr.net/npm/vega-datasets@v1.29.0/data/world-110m.json", "countries")
        _layers.append(alt.Chart(_world).mark_geoshape(fill="transparent", stroke=MUTED, strokeWidth=0.8, opacity=0.5 if ui_tiles.value else 1, clip=True))
        _layers.append(alt.Chart(_track).mark_line(color=TEXT, strokeWidth=1, opacity=0.55, clip=True).encode(longitude="lon:Q", latitude="lat:Q", detail="orbit:N", order="i:O"))
        _layers.append(
            alt.Chart(_acc)
            .mark_line(strokeWidth=3, clip=True)
            .encode(
                longitude="lon:Q",
                latitude="lat:Q",
                detail="k:N",
                order="i:O",
                color=alt.Color("lit:N", title="Access", scale=alt.Scale(domain=["lit", "dark"], range=[PALETTE[2], PALETTE[1]]), legend=alt.Legend(orient="bottom", direction="horizontal", titleOrient="left")),
            )
        )
        _layers.append(
            alt.Chart(_boxes)
            .mark_line(strokeWidth=3, clip=True)
            .encode(
                longitude="lon:Q",
                latitude="lat:Q",
                detail="what:N",
                order="order:O",
                strokeDash=alt.StrokeDash("what:N", title=None, scale=alt.Scale(domain=["Footprint", "Pointing envelope"], range=[[1, 0], [6, 4]]), legend=alt.Legend(orient="bottom", direction="horizontal")),
                color=alt.value(PALETTE[0]),
            )
        )
        _layers.append(alt.Chart(pd.DataFrame({"lon": [_tlon], "lat": [_tlat]})).mark_point(color=PALETTE[2], size=110, filled=True, stroke=TEXT, strokeWidth=1, clip=True).encode(longitude="lon:Q", latitude="lat:Q"))
        _map = style_chart(
            alt.layer(*_layers).properties(
                width=_w,
                height=_h,
                projection=_proj,
                title=f"Around {'the custom target' if target_name == 'Custom' else target_name} – nadir footprint, pointing envelope, one day of ground track, and up to twelve access passes",
            )
        )
        _credit = "Map tiles © OpenStreetMap contributors, © CARTO. Coastline: Natural Earth via vega-datasets." if ui_tiles.value else "Coastline: Natural Earth via vega-datasets."
        _out = mo.vstack(
            [
                mo.md("## Map"),
                mo.md(
                    "The footprint is the swath laid over the target at nadir; the envelope is where it "
                    "could land at the stated pointing error. The thin line is the first simulated day's "
                    "ground track, the colored segments are ten minutes of track around each access. "
                    "The base map is grayscale on purpose, so the overlays carry the color. "
                    "If the tiles do not load, the coastline alone still shows the geometry; turn the "
                    "tiles off in the control panel to work offline; the zoom slider there sets the tile level."
                ),
                _map,  # geoshapes are not selectable in mo.ui.altair_chart, so the chart renders directly
                mo.md(f"<small>{_credit}</small>"),
            ]
        )
    else:
        _out = None
    _out
    return


@app.cell
def _(
    acc_per_day,
    accesses,
    epoch_error,
    fmt_num,
    lit_acc,
    lit_per_day,
    max_lit_gap_h,
    mean_lit_gap_h,
    mo,
    pd,
    period_min,
    reach_eff_km,
    reach_km,
    target_lat,
    target_lon,
    target_name,
    ui_min_sun,
    ui_mode,
    ui_off_nadir,
    ui_sim_days,
):
    # Access and illumination report.
    if ui_mode.value == "Earth observation":
        def _gap(h):
            if h != h:
                return "–"
            return f"{h / 24:.1f} days" if h >= 48 else f"{h:.1f} hours"

        _stats = mo.hstack(
            [
                mo.stat(value=f"{acc_per_day:.2f}", label="Accesses per Day", caption="target inside the reach", bordered=True),
                mo.stat(value=f"{lit_per_day:.2f}", label="Lit Accesses per Day", caption=f"Sun above {ui_min_sun.value:g}° at the target", bordered=True),
                mo.stat(value=_gap(mean_lit_gap_h), label="Mean Gap, Lit", caption=f"longest {_gap(max_lit_gap_h)}", bordered=True),
            ],
            widths="equal",
        )
        _rows = [
            (
                a["start"].strftime("%Y-%m-%d %H:%M:%S"),
                f"{fmt_num(a['duration_s'], 1)} s",
                f"{fmt_num(a['min_psi_km'], 0)} km",
                f"{a['sun_el_deg']:.0f}°",
                "✓" if a["lit"] else "✗",
            )
            for a in accesses[:40]
        ]
        _table = mo.ui.table(
            pd.DataFrame(_rows, columns=["Start (UTC)", "Duration", "Closest approach", "Sun elevation", "Lit"]),
            selection=None,
            show_column_summaries=False,
            pagination=False,
        )
        _note = (
            f"Over {ui_sim_days.value:g} simulated days the target {target_name} at {target_lat:g}°, "
            f"{target_lon:g}° came within reach {len(accesses)} times, {len(lit_acc)} of them lit. "
            f"The reach is {fmt_num(reach_km, 0)} km from the sub-satellite point – half the cross-track swath "
            f"plus the ground the slew at {ui_off_nadir.value:g}° off nadir buys on a spherical Earth – less the "
            f"pointing error, {fmt_num(reach_eff_km, 0)} km net. Entry and exit are solved between the 10 s "
            f"samples, so an access shorter than a sample is found and timed. Orbital period {period_min:.1f} min. "
            "Illumination is the Sun's elevation at the target, not the scene radiance; a 20° floor "
            "avoids the long shadows and the low signal of a low Sun."
        )
        _items = [mo.md("## Access and Illumination"), mo.md(_note), _stats]
        if epoch_error:
            _items.append(mo.callout(mo.md(epoch_error), kind="warn", title="Epoch Not Parsed"))
        if not accesses:
            _items.append(
                mo.callout(
                    mo.md("No access in the simulated span. Widen the off-nadir angle, lengthen the simulation, or check the inclination against the target latitude."),
                    kind="warn",
                    title="No Access",
                )
            )
        elif not lit_acc:
            _items.append(
                mo.callout(
                    mo.md("Every access is on the night side. For a sun-synchronous orbit that usually means the local time of the descending node puts the daylit pass on the ascending side; try LTDN near 10:30 for a morning descending pass."),
                    kind="warn",
                    title="No Lit Access",
                )
            )
        _items.append(mo.accordion({f"Access list, first {min(len(accesses), 40)} of {len(accesses)}": _table}))
        _out = mo.vstack(_items)
    else:
        _out = None
    _out
    return


@app.cell
def _(
    MUTED,
    PALETTE,
    R_EARTH_KM,
    accesses,
    alt,
    fmt_num,
    h_km,
    lens,
    mo,
    np,
    pd,
    rule_x,
    sensor,
    step_s,
    style_chart,
    sun_el_deg,
    ui_min_sun,
    ui_mode,
    ui_off_nadir,
    ui_wavelength,
):
    # Earth observation charts. Sun elevation over the simulation with the accesses
    # on it; GSD against off-nadir angle, because revisit is bought with slew;
    # and GSD against focal length, where the Rayleigh curve says when longer
    # lenses stop paying.
    if ui_mode.value == "Earth observation":
        # 1. Illumination timeline. One point every ten minutes keeps it light.
        _every = max(int(600 / step_s), 1)
        _days = np.arange(len(sun_el_deg))[::_every] * step_s / 86400
        _sun = pd.DataFrame({"day": _days, "sun_el_deg": sun_el_deg[::_every]})
        _acc = pd.DataFrame(
            [{"day": a["t_mid"] / 86400, "sun_el_deg": a["sun_el_deg"], "lit": "lit" if a["lit"] else "dark"} for a in accesses],
            columns=["day", "sun_el_deg", "lit"],
        )
        _sun_line = alt.Chart(_sun).mark_line(color=MUTED, strokeWidth=1).encode(
            x=alt.X("day:Q", title="Days from the epoch"), y=alt.Y("sun_el_deg:Q", title="Sun elevation at the target (deg)")
        )
        _acc_pts = alt.Chart(_acc).mark_point(size=60, filled=True).encode(
            x="day:Q",
            y="sun_el_deg:Q",
            color=alt.Color("lit:N", title="Access", scale=alt.Scale(domain=["lit", "dark"], range=[PALETTE[2], PALETTE[1]])),
            tooltip=[alt.Tooltip("day:Q", title="Day", format=".2f"), alt.Tooltip("sun_el_deg:Q", title="Sun elevation", format=".0f")],
        )
        _floor = alt.Chart(alt.Data(values=[{"y": float(ui_min_sun.value)}])).mark_rule(strokeDash=[6, 4], color=MUTED).encode(y="y:Q")
        _timeline = style_chart(
            (_sun_line + _floor + _acc_pts).properties(width="container", height=240, title="Sun elevation at the target, with each access marked – dashed is the illumination floor")
        )

        # 2. GSD against off-nadir angle, spherical Earth. Along-track grows
        # with slant range, cross-track also with the incidence angle. Linear
        # axes: a log axis silently drops the whole chart when a series has a 0.
        _theta = np.radians(np.arange(0, 60.5, 0.5))
        _sin_i = (R_EARTH_KM + h_km) / R_EARTH_KM * np.sin(_theta)
        _ok = _sin_i < 1
        _theta, _sin_i = _theta[_ok], _sin_i[_ok]
        _inc = np.arcsin(_sin_i)
        _lam = _inc - _theta
        _slant = np.sqrt(R_EARTH_KM**2 + (R_EARTH_KM + h_km) ** 2 - 2 * R_EARTH_KM * (R_EARTH_KM + h_km) * np.cos(_lam))
        _gsd_along = sensor["pitch_um"] * _slant / lens["f_mm"]
        _gsd_cross = _gsd_along / np.cos(_inc)
        _ground_km = R_EARTH_KM * _lam
        _off = pd.concat(
            [
                pd.DataFrame({"off_nadir_deg": np.degrees(_theta), "meters": _gsd_along, "ground_km": _ground_km, "series": "Along-track GSD"}),
                pd.DataFrame({"off_nadir_deg": np.degrees(_theta), "meters": _gsd_cross, "ground_km": _ground_km, "series": "Cross-track GSD"}),
            ]
        )
        _order = ["Along-track GSD", "Cross-track GSD"]
        _off_chart = style_chart(
            (
                alt.Chart(_off)
                .mark_line(strokeWidth=2)
                .encode(
                    x=alt.X("off_nadir_deg:Q", title="Off-nadir angle (deg)"),
                    y=alt.Y("meters:Q", title="Meters per pixel"),
                    color=alt.Color("series:N", title=None, sort=_order, scale=alt.Scale(domain=_order, range=PALETTE[:2])),
                    tooltip=[
                        alt.Tooltip("series:N", title="Series"),
                        alt.Tooltip("off_nadir_deg:Q", title="Off nadir (deg)", format=".1f"),
                        alt.Tooltip("meters:Q", title="Meters per pixel", format=".1f"),
                        alt.Tooltip("ground_km:Q", title="Ground distance from nadir (km)", format=".0f"),
                    ],
                )
                + rule_x(float(ui_off_nadir.value))
            ).properties(width="container", height=280, title="Resolution against off-nadir angle – the dashed line is the targeting slew in use; hover for the ground distance")
        )

        # 3. GSD and Rayleigh spot against focal length.
        _f = np.geomspace(2, 200, 120)
        _lamu = float(ui_wavelength.value) / 1000
        _df = pd.concat(
            [
                pd.DataFrame({"focal_mm": _f, "meters": sensor["pitch_um"] * h_km / _f, "series": "GSD"}),
                pd.DataFrame({"focal_mm": _f, "meters": 1.22 * _lamu * h_km / (_f / lens["n"]), "series": f"Rayleigh spot at f/{lens['n']:g}"}),
            ]
        )
        _focal_chart = style_chart(
            (
                alt.Chart(_df)
                .mark_line(strokeWidth=2)
                .encode(
                    x=alt.X("focal_mm:Q", title="Focal length (mm)", scale=alt.Scale(type="log")),
                    y=alt.Y("meters:Q", title="Meters on the ground", scale=alt.Scale(type="log")),
                    color=alt.Color("series:N", title=None, scale=alt.Scale(range=PALETTE[:2])),
                    tooltip=[alt.Tooltip("series:N", title="Series"), alt.Tooltip("focal_mm:Q", title="Focal (mm)", format=".1f"), alt.Tooltip("meters:Q", title="Meters", format=".1f")],
                )
                + rule_x(lens["f_mm"])
            ).properties(width="container", height=280, title=f"{sensor['name']} at {fmt_num(h_km, 0)} km – the dashed line is the selected lens")
        )
        _out = mo.vstack(
            [
                mo.md("## Illumination Over the Simulation"),
                mo.ui.altair_chart(_timeline),
                mo.md("## Resolution"),
                mo.md(
                    "Against focal length, the GSD falls as 1/f and so does the Rayleigh spot at a fixed "
                    "f-number, since the aperture grows with the focal length. A longer lens at the same "
                    "f-number therefore resolves more in meters – both curves come down together – but "
                    "their ratio, Q, stays where it is, so it never turns a diffraction-limited system "
                    "into a detector-limited one. That takes a lower f-number, which lifts the aperture "
                    "alone, or a coarser pitch."
                ),
                mo.ui.altair_chart(_focal_chart),
                mo.md(
                    "Off nadir, the along-track GSD grows with slant range and the cross-track GSD "
                    "with the incidence angle as well, so a 30° slew costs about a quarter in "
                    "resolution and doubles it beyond 50°."
                ),
                mo.ui.altair_chart(_off_chart),
            ]
        )
    else:
        _out = None
    _out
    return


@app.cell
def _(
    FONT,
    MUTED,
    PALETTE,
    TEXT,
    alt,
    blur_px,
    boom_dir,
    boresight,
    cam,
    corners,
    corners_in_frame,
    depth,
    dof_far_mm,
    dof_near_mm,
    edges,
    face_axes,
    face_axis_names,
    face_labels,
    fill_fraction,
    fmt_int,
    focus_mm,
    fov_x_deg,
    fov_y_deg,
    half_h,
    half_w,
    lens,
    mo,
    normal,
    np,
    pd,
    pitch_used,
    right,
    root,
    sensor,
    style_chart,
    sweep,
    ui_aim,
    ui_boom_len,
    ui_cubesat,
    ui_face,
    ui_mode,
    ui_show_focus,
    up,
    yaw_used,
):
    # Boom visualization: the frame with the projected envelope, a side view of
    # the geometry that produced it, and how the fill changes with boom length.
    # The focus switch adds the depth-of-field reading to the first two: edges
    # colored by their blur circle, and the near and far limits in the side view.
    # It is off by default, because the plain wireframe reads more clearly; the
    # depth-of-field callout fires either way.
    if ui_mode.value == "Boom":
        _show_focus = bool(ui_show_focus.value)
        # 1. The frame. With focus shown, each edge is cut into short pieces so
        # the blur circle can be evaluated along it; a piece is in focus up to
        # the 2 px CoC, soft to 6 px, out of focus beyond. Without it, each edge
        # is one straight segment between its corners, as before.
        _focus_order = ["In focus", "Soft", "Out of focus"]

        def _focus_class(b):
            # NaN, where no image forms, counts as out of focus.
            return "In focus" if b <= 2 else ("Soft" if b <= 6 else "Out of focus")

        _rows = []
        _n_pieces = 12 if _show_focus else 1
        for _i, (_a, _b) in enumerate(edges):
            if depth[_a] > 0 and depth[_b] > 0:
                _t = np.linspace(0, 1, _n_pieces + 1)
                _pts = corners[_a] + np.outer(_t, corners[_b] - corners[_a])
                _v = _pts - cam
                _d = _v @ boresight
                _x = lens["f_mm"] * (_v @ right) / _d
                _y = lens["f_mm"] * (_v @ up) / _d
                _blur = blur_px(_d)
                for _k in range(_n_pieces):
                    _bmax = float(np.max([_blur[_k], _blur[_k + 1]]))
                    _seg = _i * 100 + _k
                    _rows.append({"seg": _seg, "order": 0, "x": _x[_k], "y": _y[_k], "focus": _focus_class(_bmax), "blur_px": _bmax, "depth_mm": float(_d[_k])})
                    _rows.append({"seg": _seg, "order": 1, "x": _x[_k + 1], "y": _y[_k + 1], "focus": _focus_class(_bmax), "blur_px": _bmax, "depth_mm": float(_d[_k + 1])})
        _df = pd.DataFrame(_rows, columns=["seg", "order", "x", "y", "focus", "blur_px", "depth_mm"])
        _frame = pd.DataFrame(
            {"x": [-half_w, half_w, half_w, -half_w, -half_w], "y": [-half_h, -half_h, half_h, half_h, -half_h], "order": range(5)}
        )
        _pad = 1.25
        _lim_x = alt.Scale(domain=[-half_w * _pad, half_w * _pad])
        _lim_y = alt.Scale(domain=[-half_h * _pad, half_h * _pad])
        _px_w = 560
        _px_h = int(_px_w * half_h / half_w)
        _frame_chart = (
            alt.Chart(_frame)
            .mark_line(color=MUTED, strokeDash=[6, 4])
            .encode(x=alt.X("x:Q", scale=_lim_x, title="Sensor width (mm)"), y=alt.Y("y:Q", scale=_lim_y, title="Sensor height (mm)"), order="order:O")
        )
        _box_base = alt.Chart(_df).mark_line(strokeWidth=2.5 if _show_focus else 2).encode(
            x=alt.X("x:Q", scale=_lim_x),
            y=alt.Y("y:Q", scale=_lim_y),
            detail="seg:N",
            order="order:O",
        )
        if _show_focus:
            _box_chart = _box_base.encode(
                color=alt.Color(
                    "focus:N",
                    title="Focus",
                    sort=_focus_order,
                    scale=alt.Scale(domain=_focus_order, range=[PALETTE[0], PALETTE[2], MUTED]),
                    legend=alt.Legend(orient="bottom", direction="horizontal", titleOrient="left"),
                ),
                strokeDash=alt.StrokeDash("focus:N", sort=_focus_order, scale=alt.Scale(domain=_focus_order, range=[[1, 0], [1, 0], [3, 3]]), legend=None),
                tooltip=[alt.Tooltip("blur_px:Q", title="Blur circle (px)", format=".1f"), alt.Tooltip("depth_mm:Q", title="Distance (mm)", format=".0f")],
            )
        else:
            _box_chart = _box_base.encode(color=alt.value(PALETTE[0]))
        _labels = (
            alt.Chart(pd.DataFrame(face_labels, columns=["face", "x", "y"]))
            .mark_text(font=FONT, fontSize=12, color=TEXT)
            .encode(x=alt.X("x:Q", scale=_lim_x), y=alt.Y("y:Q", scale=_lim_y), text="face:N")
        )
        _frame_view = style_chart(
            (_frame_chart + _box_chart + _labels).properties(
                width=_px_w,
                height=_px_h,
                title=(
                    f"The frame: {ui_cubesat.value} from a {fmt_int(ui_boom_len.value)} mm boom on {ui_face.value} – dashed is the sensor edge"
                    + ("; edges colored by focus" if _show_focus else "")
                ),
            )
        )

        # 2. Side view, in the plane spanned by the face normal and the tilt
        # direction (or the first face axis when there is no tilt). Horizontal
        # is distance along the face from the root, vertical is distance along
        # the normal from the face.
        _inplane = boresight - np.dot(boresight, -normal) * (-normal)
        _sweep_inplane = boom_dir - np.dot(boom_dir, normal) * normal
        if np.linalg.norm(_sweep_inplane) > 1e-9:
            _e1 = _sweep_inplane / np.linalg.norm(_sweep_inplane)
        elif np.linalg.norm(_inplane) > 1e-9:
            _e1 = _inplane / np.linalg.norm(_inplane)
        else:
            _e1 = face_axes[0]
        _e2 = normal

        def _to_plane(p):
            return float(np.dot(p, _e1)), float(np.dot(p, _e2))

        # The envelope's extent in that plane: project all corners.
        _cp = np.array([_to_plane(c) for c in corners])
        _hull_x = [_cp[:, 0].min(), _cp[:, 0].max(), _cp[:, 0].max(), _cp[:, 0].min(), _cp[:, 0].min()]
        _hull_y = [_cp[:, 1].min(), _cp[:, 1].min(), _cp[:, 1].max(), _cp[:, 1].max(), _cp[:, 1].min()]
        _cam2 = _to_plane(cam)
        _root2 = _to_plane(root)
        _bore2 = np.array([np.dot(boresight, _e1), np.dot(boresight, _e2)])
        _bore2 = _bore2 / np.linalg.norm(_bore2)
        # The diagonal half-angle bounds the field of view in any cutting plane.
        _half = np.arctan(np.hypot(half_w, half_h) / lens["f_mm"])
        _reach = float(np.linalg.norm(cam)) * 1.6
        _rot = lambda v, a: np.array([v[0] * np.cos(a) - v[1] * np.sin(a), v[0] * np.sin(a) + v[1] * np.cos(a)])
        _ray1 = _rot(_bore2, _half) * _reach
        _ray2 = _rot(_bore2, -_half) * _reach
        # Depth-of-field limits as lines across the field of view at the near
        # and far distance along the boresight; a far limit at infinity is drawn
        # at the edge of the plot.
        _perp2 = np.array([-_bore2[1], _bore2[0]])
        _dof_rows = []
        for _lim in ((dof_near_mm, dof_far_mm if np.isfinite(dof_far_mm) else _reach) if _show_focus and dof_near_mm == dof_near_mm else ()):
            _hw = _lim * np.tan(_half)
            _c = np.array(_cam2) + _bore2 * _lim
            _dof_rows.append(pd.DataFrame({"x": [_c[0] - _perp2[0] * _hw, _c[0] + _perp2[0] * _hw], "y": [_c[1] - _perp2[1] * _hw, _c[1] + _perp2[1] * _hw], "order": [0, 1], "what": "Depth of field", "lim": _lim}))
        _side = pd.concat(
            [
                pd.DataFrame({"x": _hull_x, "y": _hull_y, "order": range(5), "what": "Envelope"}),
                pd.DataFrame({"x": [_root2[0], _cam2[0]], "y": [_root2[1], _cam2[1]], "order": [0, 1], "what": "Boom"}),
                pd.DataFrame({"x": [_cam2[0], _cam2[0] + _bore2[0] * _reach], "y": [_cam2[1], _cam2[1] + _bore2[1] * _reach], "order": [0, 1], "what": "Boresight"}),
                pd.DataFrame({"x": [_cam2[0] + _ray1[0], _cam2[0], _cam2[0] + _ray2[0]], "y": [_cam2[1] + _ray1[1], _cam2[1], _cam2[1] + _ray2[1]], "order": [0, 1, 2], "what": "Diagonal field of view"}),
                *_dof_rows,
            ]
        )
        _order = ["Envelope", "Boom", "Boresight", "Diagonal field of view"] + (["Depth of field"] if _show_focus else [])
        _side_chart = style_chart(
            alt.Chart(_side)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X("x:Q", title="Along the face, from the root direction (mm)"),
                y=alt.Y("y:Q", title="Along the face normal (mm)"),
                color=alt.Color("what:N", title=None, sort=_order, scale=alt.Scale(domain=_order, range=[PALETTE[0], PALETTE[2], PALETTE[1], MUTED, PALETTE[4]][: len(_order)]), legend=alt.Legend(orient="bottom", direction="horizontal")),
                strokeDash=alt.StrokeDash("what:N", sort=_order, scale=alt.Scale(domain=_order, range=[[1, 0], [1, 0], [1, 0], [6, 4], [2, 2]][: len(_order)]), legend=None),
                order="order:O",
                detail=alt.Detail(["what:N", "lim:N"]),
            )
            .properties(
                width="container",
                height=340,
                title="Side view in the plane of the sweep (or the tilt); the envelope is its projection onto that plane"
                + (", green marks the depth-of-field limits" if _show_focus else ""),
            )
        )

        # 3. Fill against boom length.
        _sw = pd.DataFrame(sweep)
        _sweep_chart = style_chart(
            (
                alt.Chart(_sw)
                .mark_line(strokeWidth=2, color=PALETTE[0])
                .encode(
                    x=alt.X("length_mm:Q", title="Boom length (mm)"),
                    y=alt.Y("fill_pct:Q", title="Frame filled (%)"),
                    tooltip=[alt.Tooltip("length_mm:Q", title="Boom (mm)"), alt.Tooltip("fill_pct:Q", title="Fill (%)", format=".1f"), alt.Tooltip("corners_in:Q", title="Corners in frame")],
                )
                + alt.Chart(_sw[_sw["corners_in"] == 8])
                .mark_point(color=PALETTE[2], size=18, filled=True)
                .encode(x="length_mm:Q", y="fill_pct:Q")
                + alt.Chart(alt.Data(values=[{"x": float(ui_boom_len.value)}])).mark_rule(strokeDash=[6, 4], color=MUTED).encode(x="x:Q")
            ).properties(width="container", height=260, title="Fill against boom length at the same aim – copper marks where all eight corners are in the frame")
        )

        _aim = (
            f"Boresight aimed at the center: pitch {pitch_used:.1f}° from the boom axis, toward {yaw_used:.0f}° "
            f"in the {face_axis_names[0]}{face_axis_names[1]} face plane."
            if ui_aim.value
            else f"Manual boresight: pitch {pitch_used:.1f}°, direction {yaw_used:.0f}° in the {face_axis_names[0]}{face_axis_names[1]} face plane."
        )
        _out = mo.vstack(
            [
                mo.md("## Boom Visualization"),
                mo.md(
                    f"{_aim} The spacecraft fills {fill_fraction * 100:.0f}% of the {sensor['w']} × {sensor['h']} frame "
                    f"({fov_x_deg:.1f}° × {fov_y_deg:.1f}°) and {corners_in_frame} of its 8 corners are inside it. "
                    "The frame is drawn as seen through a pinhole, so the far face looks smaller; no lens "
                    "distortion is modeled. Labels sit on the faces the camera can see."
                    + (
                        " Edge color is the blur circle at that depth with focus at "
                        f"{fmt_int(focus_mm)} mm: in focus up to 2 px, soft to 6 px, dashed gray beyond; "
                        f"the depth of field runs {fmt_int(dof_near_mm)} to "
                        f"{'∞' if not np.isfinite(dof_far_mm) else fmt_int(dof_far_mm)} mm."
                        if _show_focus
                        else " Turn on the focus switch in the control panel to color the edges by depth of field."
                    )
                ),
                mo.ui.altair_chart(_frame_view),
                mo.ui.altair_chart(_side_chart),
                mo.ui.altair_chart(_sweep_chart),
            ]
        )
    else:
        _out = None
    _out
    return


@app.cell
def _(
    att_smear_px,
    comp_kb,
    days_comp_high,
    days_comp_low,
    days_raw_high,
    days_raw_low,
    envelope_x_km,
    envelope_y_km,
    fmt_int,
    fmt_num,
    fov_x_deg,
    fov_y_deg,
    geoloc_km,
    gsd_m,
    h_km,
    high_kb,
    horizon_km,
    ifov_arcsec,
    lens,
    low_kb,
    mo,
    pd,
    per_day_kb,
    point_shift_km,
    q_factor,
    raw_kb,
    rayleigh_ground_m,
    sensor,
    skew_px,
    smear_m,
    smear_px,
    swath_x_km,
    swath_y_km,
    thumb_kb,
    ui_compression,
    ui_frames_day,
    ui_mode,
    v_ground_m_s,
):
    # Line-item tables for Earth observation mode.
    def _d(x):
        if x == float("inf"):
            return "no link"
        return f"{x:.1f} days" if x >= 1 else f"{x * 24:.1f} hours"

    if ui_mode.value == "Earth observation":
        _geom = pd.DataFrame(
            [
                ("Altitude", f"{fmt_num(h_km, 0)} km"),
                ("Sensor", f"{sensor['name']}, {sensor['w']} × {sensor['h']} px, {sensor['pitch_um']:g} µm, {sensor['bits']} bit, {sensor['shutter']} shutter"),
                ("Lens", f"{lens['name']}, {lens['f_mm']:g} mm f/{lens['n']:g}, aperture {lens['aperture_mm']:.1f} mm"),
                ("GSD at nadir", f"{fmt_num(gsd_m, 1)} m"),
                ("Instantaneous field of view", f"{fmt_num(ifov_arcsec, 1)} arcsec per pixel"),
                ("Swath", f"{fmt_num(swath_x_km, 1)} × {fmt_num(swath_y_km, 1)} km"),
                ("Field of view", f"{fov_x_deg:.2f}° × {fov_y_deg:.2f}°"),
                ("Rayleigh spot on the ground", f"{fmt_num(rayleigh_ground_m, 1)} m"),
                ("Sampling factor Q", f"{q_factor:.2f}"),
                ("Ground speed", f"{fmt_num(v_ground_m_s / 1000, 2)} km/s – {fmt_num(v_ground_m_s / 1000, 1)} m per ms"),
                ("Motion smear", f"{fmt_num(smear_m, 1)} m, {smear_px:.2f} px"),
                ("Attitude-rate smear", f"{att_smear_px:.1f} px"),
                ("Rolling-shutter skew", f"{skew_px:.0f} px" if sensor["shutter"] == "rolling" else "none, global shutter"),
                ("Footprint shift at the pointing error", f"{fmt_num(point_shift_km, 1)} km"),
                ("Footprint envelope", f"{fmt_num(envelope_x_km, 0)} × {fmt_num(envelope_y_km, 0)} km"),
                ("Geolocation uncertainty from pointing knowledge", f"{fmt_num(geoloc_km, 1)} km"),
                ("Distance to the horizon", f"{fmt_num(horizon_km, 0)} km"),
            ],
            columns=["Quantity", "Value"],
        )
        _data = pd.DataFrame(
            [
                ("Raw frame", f"{fmt_int(raw_kb)} kB at {sensor['bits']} bit"),
                (f"Compressed frame, {ui_compression.value:g}:1", f"{fmt_int(comp_kb)} kB"),
                ("Thumbnail, 8× binned and compressed", f"{fmt_num(thumb_kb, 1)} kB"),
                (f"{ui_frames_day.value:g} frames per day", f"{fmt_int(per_day_kb)} kB/day"),
                ("Raw frame on the low-rate link", f"{_d(days_raw_low)} at {fmt_int(low_kb)} kB/day"),
                ("Compressed frame on the low-rate link", _d(days_comp_low)),
                ("Raw frame on the high-rate link", f"{_d(days_raw_high)} at {fmt_int(high_kb)} kB/day"),
                ("Compressed frame on the high-rate link", _d(days_comp_high)),
            ],
            columns=["Quantity", "Value"],
        )
        _out = mo.vstack(
            [
                mo.md("## Geometry and Resolution"),
                mo.ui.table(_geom, selection=None, show_column_summaries=False, pagination=False),
                mo.md("## Data Volume and Downlink"),
                mo.md(
                    "Frame sizes are pixels times bit depth; the compression ratio is an input because "
                    "it depends on the scene and the codec. The daily volumes come from the BAC Link "
                    "Budget at the stated profile and are inputs here, so a different link is a "
                    "different number, not a different tool."
                ),
                mo.ui.table(_data, selection=None, show_column_summaries=False, pagination=False),
            ]
        )
    else:
        _out = None
    _out
    return


@app.cell
def _(
    fmt_int,
    fmt_num,
    geoloc_km,
    gsd_m,
    mean_lit_gap_h,
    mo,
    pd,
    sensor,
    swath_x_km,
    swath_y_km,
    ui_mode,
    ui_off_nadir,
):
    # The parameters a licensing regime asks about, in one place. The tool
    # reports capability; the operator checks the threshold that applies.
    if ui_mode.value == "Earth observation":
        _bands = "RGB, Bayer, roughly 400–700 nm" if sensor["color"] == "RGB" else "panchromatic, roughly 400–1000 nm"
        _lic = pd.DataFrame(
            [
                ("Ground sample distance at nadir", f"{fmt_num(gsd_m, 1)} m"),
                ("Spectral bands", _bands),
                ("Radiometric resolution", f"{sensor['bits']} bit RAW at the sensor"),
                ("Swath", f"{fmt_int(swath_x_km)} × {fmt_int(swath_y_km)} km"),
                ("Revisit interval, lit", "no lit access in the simulated span" if mean_lit_gap_h != mean_lit_gap_h else f"{mean_lit_gap_h / 24:.1f} days mean, at the stated target and slew"),
                ("Off-nadir capability", f"{ui_off_nadir.value:g}° used for targeting; the platform's slew range decides"),
                ("Geolocation accuracy", f"{fmt_num(geoloc_km, 1)} km from pointing knowledge alone"),
                ("Imaging of objects other than the Earth", "possible whenever the attitude control permits it"),
            ],
            columns=["Parameter", "Value"],
        )
        _out = mo.vstack(
            [
                mo.md("## Licensing Parameters"),
                mo.md(
                    "Remote-sensing regimes differ by jurisdiction and change; this table states what "
                    "the payload can do so the numbers are to hand when a form asks. It does not say "
                    "whether a threshold applies – check the current text of the regime for the "
                    "operating entity. Germany's SatDSiG and the United States' NOAA licensing are the "
                    "usual quantitative examples; Switzerland has no dedicated remote-sensing statute "
                    "at the time of writing. Verify all three before relying on them."
                ),
                mo.ui.table(_lic, selection=None, show_column_summaries=False, pagination=False),
            ]
        )
    else:
        _out = None
    _out
    return


@app.cell
def _(
    boom_dir,
    boresight,
    cam,
    dims,
    dist_center_mm,
    dist_far_mm,
    dist_near_mm,
    dof_far_mm,
    dof_near_mm,
    face_axis_names,
    fmt_int,
    fmt_num,
    focus_mm,
    gsd_center_mm_px,
    hyperfocal_mm,
    lens,
    mo,
    pd,
    sensor,
    ui_mode,
    ui_sweep,
):
    # Line-item table for boom mode.
    if ui_mode.value == "Boom":
        _t = pd.DataFrame(
            [
                ("Spacecraft envelope", f"{dims[0]:g} × {dims[1]:g} × {dims[2]:g} mm"),
                ("Boom direction", f"({boom_dir[0]:.3f}, {boom_dir[1]:.3f}, {boom_dir[2]:.3f}), {ui_sweep.value:g}° off the normal"),
                ("Camera position in the body frame", f"({fmt_num(cam[0], 0)}, {fmt_num(cam[1], 0)}, {fmt_num(cam[2], 0)}) mm"),
                ("Boresight unit vector", f"({boresight[0]:.3f}, {boresight[1]:.3f}, {boresight[2]:.3f})"),
                ("Face axes in the image", f"{face_axis_names[0]} across, {face_axis_names[1]} up, before the tilt"),
                ("Distance to the center", f"{fmt_int(dist_center_mm)} mm"),
                ("Nearest and farthest corner", f"{fmt_int(dist_near_mm)} – {fmt_int(dist_far_mm)} mm along the boresight"),
                ("Scale at the center", f"{gsd_center_mm_px:.2f} mm per pixel"),
                ("Lens", f"{lens['name']}, {lens['f_mm']:g} mm f/{lens['n']:g}"),
                ("Circle of confusion", f"2 px = {2 * sensor['pitch_um'] / 1000:.4f} mm"),
                ("Hyperfocal distance", f"{fmt_int(hyperfocal_mm)} mm"),
                ("Focus distance", f"{fmt_int(focus_mm)} mm"),
                ("Depth of field", f"{fmt_int(dof_near_mm)} mm to {'infinity' if dof_far_mm == float('inf') else fmt_int(dof_far_mm) + ' mm'}"),
            ],
            columns=["Quantity", "Value"],
        )
        _out = mo.vstack(
            [
                mo.md("## Boom Geometry"),
                mo.md(
                    "The body frame sits at the geometric center of the envelope with axes along its "
                    "edges. The boom leaves the deploying face along the face normal from the root "
                    "offset, and the camera is at its tip. A focus distance of 0 focuses at the "
                    "spacecraft center."
                ),
                mo.ui.table(_t, selection=None, show_column_summaries=False, pagination=False),
            ]
        )
    else:
        _out = None
    _out
    return


@app.cell
def _(
    R_EARTH_KM,
    dt,
    ground_offset_km,
    h_km,
    np,
    point_shift_km,
    swath_x_km,
    target_lat,
    target_lon,
    ui_epoch,
    ui_inclination,
    ui_ltdn,
    ui_min_sun,
    ui_off_nadir,
    ui_sim_days,
):
    # Access and illumination. Two-body circular orbit with J2 nodal regression
    # so a sun-synchronous inclination stays sun-synchronous; the RAAN is set
    # from the local time of the descending node at the epoch. The Sun follows
    # the low-precision Astronomical Almanac algorithm (good to about 0.01°)
    # and Earth rotation uses GMST, so the Sun elevation at the target is
    # right to a fraction of a degree, which is all the illumination test needs.
    MU = 398600.4418
    J2 = 1.08263e-3
    _a = R_EARTH_KM + h_km
    _n = np.sqrt(MU / _a**3)  # rad/s
    _inc = np.radians(float(ui_inclination.value))
    _raan_dot = -1.5 * _n * J2 * (R_EARTH_KM / _a) ** 2 * np.cos(_inc)
    period_min = 2 * np.pi / _n / 60

    try:
        _epoch = dt.datetime.strptime(ui_epoch.value.strip(), "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        epoch_error = ""
    except ValueError:
        _epoch = dt.datetime(2027, 6, 21, tzinfo=dt.timezone.utc)
        epoch_error = f"Epoch \"{ui_epoch.value}\" is not YYYY-MM-DD; using 2027-06-21."

    def _jd(when):
        return 2440587.5 + when.timestamp() / 86400

    def sun_eci(jd):
        # Astronomical Almanac low-precision solar coordinates.
        _d = jd - 2451545.0
        _g = np.radians((357.529 + 0.98560028 * _d) % 360)
        _q = (280.459 + 0.98564736 * _d) % 360
        _lam = np.radians((_q + 1.915 * np.sin(_g) + 0.020 * np.sin(2 * _g)) % 360)
        _eps = np.radians(23.439 - 0.00000036 * _d)
        return np.stack([np.cos(_lam), np.cos(_eps) * np.sin(_lam), np.sin(_eps) * np.sin(_lam)], axis=-1)

    def gmst_rad(jd):
        _d = jd - 2451545.0
        return np.radians((280.46061837 + 360.98564736629 * _d) % 360)

    _jd0 = _jd(_epoch)
    _sun0 = sun_eci(_jd0)
    _ra_sun0 = np.arctan2(_sun0[1], _sun0[0])
    # Local time of the ascending node is the descending one plus 12 h; the
    # node's right ascension leads the Sun's by that offset from noon.
    _ltan_h = (float(ui_ltdn.value) + 12) % 24
    _raan0 = _ra_sun0 + np.radians((_ltan_h - 12) * 15)

    step_s = 10.0
    _t = np.arange(0, float(ui_sim_days.value) * 86400, step_s)
    _tlat, _tlon = np.radians(float(target_lat)), np.radians(float(target_lon))
    _tv = np.array([np.cos(_tlat) * np.cos(_tlon), np.cos(_tlat) * np.sin(_tlon), np.sin(_tlat)])

    def _sub_point(t):
        # Sub-satellite point at any time from the epoch, so the access edges
        # can be solved between samples: argument of latitude from the
        # ascending node at t = 0, the regressing node, GMST for the Earth.
        _u = _n * t
        _raan = _raan0 + _raan_dot * t
        _x = np.cos(_u) * np.cos(_raan) - np.sin(_u) * np.sin(_raan) * np.cos(_inc)
        _y = np.cos(_u) * np.sin(_raan) + np.sin(_u) * np.cos(_raan) * np.cos(_inc)
        _z = np.sin(_u) * np.sin(_inc)
        _g = gmst_rad(_jd0 + t / 86400)
        _lat = np.arcsin(_z)
        _lon = np.arctan2(_y, _x) - _g
        return _lat, _lon

    def _psi_at(t):
        # Earth-central angle between the sub-satellite point and the target.
        _lat, _lon = _sub_point(np.asarray(t, dtype=float))
        _sv = np.stack([np.cos(_lat) * np.cos(_lon), np.cos(_lat) * np.sin(_lon), np.sin(_lat)], axis=-1)
        return np.arccos(np.clip(_sv @ _tv, -1, 1))

    def _sun_el_at(t):
        # Sun elevation at the target, in the Earth-fixed frame.
        _jd = _jd0 + np.asarray(t, dtype=float) / 86400
        _sun = np.atleast_2d(sun_eci(_jd))
        _g = np.atleast_1d(gmst_rad(_jd))
        _cg, _sg = np.cos(_g), np.sin(_g)
        _sun_ecef = np.stack([_cg * _sun[:, 0] + _sg * _sun[:, 1], -_sg * _sun[:, 0] + _cg * _sun[:, 1], _sun[:, 2]], axis=-1)
        return np.degrees(np.arcsin(np.clip(_sun_ecef @ _tv, -1, 1)))

    _lat_s, _lon_s = _sub_point(_t)
    sub_lat = np.degrees(_lat_s)
    sub_lon = (np.degrees(_lon_s) + 180) % 360 - 180
    _psi = _psi_at(_t)
    sun_el_deg = _sun_el_at(_t)

    # The angular reach of the camera from the sub-satellite point: half the
    # cross-track swath plus the ground distance the slew buys on a spherical
    # Earth (the off-nadir chart's geometry, horizon limited), less the
    # pointing error, because an access the pointing error can lose is not an
    # access.
    reach_km = swath_x_km / 2 + ground_offset_km(ui_off_nadir.value, h_km)
    reach_eff_km = max(reach_km - point_shift_km, 0.0)
    _thr = reach_eff_km / R_EARTH_KM
    in_view = _psi <= _thr

    # Accesses. The samples say roughly when the target comes within reach;
    # an access narrower than a sample can fall between two of them, so every
    # local minimum of the angular distance that could dip under the reach is
    # refined: the closest approach on a fine grid, then the entry and exit
    # times by bisection, to a tenth of a second.
    _fine = 0.1
    _margin = _n * step_s  # the angle the sub-satellite point moves in one step
    _cand = list(np.where((_psi[1:-1] <= _psi[:-2]) & (_psi[1:-1] <= _psi[2:]) & (_psi[1:-1] <= _thr + _margin))[0] + 1)
    if len(_psi) > 1 and _psi[0] <= _psi[1] and _psi[0] <= _thr + _margin:
        _cand.insert(0, 0)
    if len(_psi) > 1 and _psi[-1] <= _psi[-2] and _psi[-1] <= _thr + _margin:
        _cand.append(len(_psi) - 1)
    _t_end = float(_t[-1]) + step_s

    def _edge(t_in, t_out):
        # Bisect between a time inside the reach and one outside.
        for _ in range(40):
            _tm = 0.5 * (t_in + t_out)
            if float(_psi_at(_tm)) <= _thr:
                t_in = _tm
            else:
                t_out = _tm
            if abs(t_out - t_in) < _fine / 4:
                break
        return 0.5 * (t_in + t_out)

    accesses = []
    _last_end = -1.0
    for _i in _cand:
        _tg = np.arange(max(float(_t[_i]) - step_s, 0.0), min(float(_t[_i]) + step_s, _t_end) + _fine / 2, _fine)
        _pg = _psi_at(_tg)
        _k = int(np.argmin(_pg))
        if _pg[_k] > _thr:
            continue
        _t_min = float(_tg[_k])
        if _t_min <= _last_end:
            continue  # the same access seen from a second sample minimum
        # Walk out in whole steps until outside the reach, then bisect.
        _a = _t_min
        while _a > 0.0 and float(_psi_at(_a)) <= _thr:
            _a = max(_a - step_s, 0.0)
        _t0 = _edge(_t_min, _a) if _a > 0.0 or float(_psi_at(0.0)) > _thr else 0.0
        _b = _t_min
        while _b < _t_end and float(_psi_at(_b)) <= _thr:
            _b = min(_b + step_s, _t_end)
        _t1 = _edge(_t_min, _b) if _b < _t_end or float(_psi_at(_t_end)) > _thr else _t_end
        _last_end = _t1
        _t_mid = 0.5 * (_t0 + _t1)
        _el = float(_sun_el_at(_t_mid)[0])
        _mlat, _mlon = _sub_point(_t_mid)
        accesses.append(
            dict(
                start=_epoch + dt.timedelta(seconds=_t0),
                t_start=_t0,
                t_end=_t1,
                duration_s=_t1 - _t0,
                min_psi_km=float(_pg[_k]) * R_EARTH_KM,
                sun_el_deg=_el,
                lit=_el >= float(ui_min_sun.value),
                sub_lat=float(np.degrees(_mlat)),
                sub_lon=float((np.degrees(_mlon) + 180) % 360 - 180),
                t_mid=_t_mid,
            )
        )
    sim_days = float(ui_sim_days.value)
    acc_per_day = len(accesses) / sim_days
    lit_acc = [a for a in accesses if a["lit"]]
    lit_per_day = len(lit_acc) / sim_days
    _lit_t = np.array([a["t_mid"] for a in lit_acc])
    lit_gaps_h = np.diff(_lit_t) / 3600 if len(_lit_t) > 1 else np.array([])
    mean_lit_gap_h = float(lit_gaps_h.mean()) if len(lit_gaps_h) else float("nan")
    max_lit_gap_h = float(lit_gaps_h.max()) if len(lit_gaps_h) else float("nan")
    return (
        acc_per_day,
        accesses,
        epoch_error,
        lit_acc,
        lit_per_day,
        max_lit_gap_h,
        mean_lit_gap_h,
        period_min,
        reach_eff_km,
        reach_km,
        step_s,
        sub_lat,
        sub_lon,
        sun_el_deg,
    )


@app.cell
def _(
    ACKNOWLEDGMENT_MD,
    ASSUMPTIONS_MD,
    TOOL_VERSION,
    acc_per_day,
    comp_kb,
    corners_in_frame,
    days_comp_high,
    days_comp_low,
    days_raw_high,
    days_raw_low,
    dist_center_mm,
    dof_far_mm,
    dof_near_mm,
    dt,
    fill_fraction,
    fmt_int,
    fmt_num,
    fov_x_deg,
    fov_y_deg,
    gsd_m,
    h_km,
    lens,
    lit_per_day,
    mean_lit_gap_h,
    mo,
    pitch_used,
    profile_name,
    q_factor,
    raw_kb,
    rayleigh_ground_m,
    reach_km,
    sensor,
    skew_px,
    smear_px,
    swath_x_km,
    swath_y_km,
    target_lat,
    target_lon,
    target_name,
    ui_aim,
    ui_altitude,
    ui_att_rate,
    ui_boom_len,
    ui_camera,
    ui_circle,
    ui_compression,
    ui_cubesat,
    ui_epoch,
    ui_exposure,
    ui_face,
    ui_fnum,
    ui_focal,
    ui_focus,
    ui_frames_day,
    ui_high_rate,
    ui_inclination,
    ui_lens,
    ui_low_rate,
    ui_ltdn,
    ui_map_zoom,
    ui_min_sun,
    ui_mode,
    ui_off_nadir,
    ui_off_x,
    ui_off_y,
    ui_pitch,
    ui_point_err,
    ui_point_know,
    ui_readout,
    ui_sensor,
    ui_sensor_bits,
    ui_sensor_global,
    ui_sensor_h,
    ui_sensor_pitch,
    ui_sensor_w,
    ui_show_focus,
    ui_sim_days,
    ui_sweep,
    ui_sweep_dir,
    ui_tile_key,
    ui_tiles,
    ui_wavelength,
    ui_yaw,
    yaw_used,
):
    # Export: a markdown report of the current settings and results, and the
    # settings as a profile that loads back into the panel.
    _now = dt.datetime.now(dt.timezone.utc)
    _today = _now.strftime("%Y-%m-%d")
    _slug = "boom" if ui_mode.value == "Boom" else "earth"

    def _d(x):
        if x == float("inf"):
            return "no link"
        return f"{x:.1f} days" if x >= 1 else f"{x * 24:.1f} hours"

    _head = [
        f"# BAC Optical Payload – {ui_mode.value} mode",
        "",
        f"Generated {_now:%Y-%m-%d %H:%M} UTC (Unix {int(_now.timestamp())}) with BAC Optical Payload {TOOL_VERSION}, bac.page/optical-payload-tool." + (f" Profile: {profile_name}." if profile_name else "") + " Every value below is a planning input or a result derived from one; nothing here is measured.",
        "",
        f"Sensor {sensor['name']}, {sensor['w']} × {sensor['h']} px, {sensor['pitch_um']:g} µm, {sensor['bits']} bit, {sensor['shutter']} shutter ({sensor['status']}). "
        f"Lens {lens['name']}, {lens['f_mm']:g} mm f/{lens['n']:g}. Field of view {fov_x_deg:.1f}° × {fov_y_deg:.1f}°.",
        "",
    ]
    if ui_mode.value == "Earth observation":
        _body = [
            f"Orbit {fmt_num(h_km, 0)} km, inclination {ui_inclination.value:g}°, LTDN {ui_ltdn.value:g} h, epoch {ui_epoch.value}.",
            "",
            "| Quantity | Value |",
            "|---|---|",
            f"| GSD at nadir | {fmt_num(gsd_m, 1)} m |",
            f"| Swath | {fmt_num(swath_x_km, 0)} × {fmt_num(swath_y_km, 0)} km |",
            f"| Rayleigh spot | {fmt_num(rayleigh_ground_m, 1)} m, Q = {q_factor:.2f} |",
            f"| Motion smear at {ui_exposure.value:g} ms | {smear_px:.2f} px |",
            f"| Rolling-shutter skew | {skew_px:.0f} px |",
            f"| Raw frame | {fmt_int(raw_kb)} kB |",
            f"| Compressed frame, {ui_compression.value:g}:1 | {fmt_int(comp_kb)} kB |",
            f"| Raw frame, low / high rate | {_d(days_raw_low)} / {_d(days_raw_high)} |",
            f"| Compressed frame, low / high rate | {_d(days_comp_low)} / {_d(days_comp_high)} |",
            f"| Accesses per day, target {target_name} {target_lat:g}°, {target_lon:g}° | {acc_per_day:.2f}, {lit_per_day:.2f} lit |",
            f"| Mean gap between lit accesses | {'–' if mean_lit_gap_h != mean_lit_gap_h else f'{mean_lit_gap_h / 24:.1f} days'} |",
            "",
        ]
    else:
        _body = [
            f"{ui_cubesat.value} envelope, boom on {ui_face.value} at ({ui_off_x.value:g}, {ui_off_y.value:g}) mm, {fmt_int(ui_boom_len.value)} mm long, swept {ui_sweep.value:g}° toward {ui_sweep_dir.value:g}°. "
            f"Boresight pitch {pitch_used:.1f}° toward {yaw_used:.0f}°" + (" (aimed at the center)." if ui_aim.value else " (manual)."),
            "",
            "| Quantity | Value |",
            "|---|---|",
            f"| Camera to center | {fmt_int(dist_center_mm)} mm |",
            f"| Frame filled | {fill_fraction * 100:.0f}%, {corners_in_frame} of 8 corners |",
            f"| Depth of field | {fmt_int(dof_near_mm)} mm to {'infinity' if dof_far_mm == float('inf') else fmt_int(dof_far_mm) + ' mm'} |",
            f"| Raw frame | {fmt_int(raw_kb)} kB, {fmt_int(comp_kb)} kB compressed |",
            "",
        ]
    report_md = "\n".join(_head + _body) + "\n" + "\n".join(_l[4:] if _l.startswith("    ") else _l for _l in ASSUMPTIONS_MD.strip("\n").splitlines()) + "\n\n" + "\n".join(_l[4:] if _l.startswith("    ") else _l for _l in ACKNOWLEDGMENT_MD.strip("\n").splitlines()) + "\n"

    # Hand-rolled TOML, the link budget's writer: strings escaped including
    # newlines, numpy scalars unwrapped, NaN and infinity left out rather than
    # written.
    def _t(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if hasattr(v, "item"):
            v = v.item()
        if isinstance(v, (int, float)):
            return "" if v != v or v in (float("inf"), float("-inf")) else repr(round(v, 6) if isinstance(v, float) else v)
        _s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return '"' + _s + '"'

    def _kv(key, v):
        _s = _t(v)
        return f"{key} = {_s}" if _s else f"# {key} not available"

    # Headline figures for the sibling tools, under a table named after this
    # tool so a profile can carry several tools' results without collision.
    if ui_mode.value == "Earth observation":
        _results = [
            "[results.optical_payload]",
            f"mode = {_t(ui_mode.value)}",
            _kv("gsd_m", gsd_m),
            _kv("swath_x_km", swath_x_km),
            _kv("swath_y_km", swath_y_km),
            _kv("fov_x_deg", fov_x_deg),
            _kv("fov_y_deg", fov_y_deg),
            _kv("raw_frame_kb", raw_kb),
            _kv("compressed_frame_kb", comp_kb),
            _kv("frames_per_day", ui_frames_day.value),
            _kv("exposure_ms", ui_exposure.value),
            _kv("readout_ms", ui_readout.value),
            _kv("accesses_per_day", acc_per_day),
            _kv("lit_accesses_per_day", lit_per_day),
            _kv("mean_lit_gap_h", mean_lit_gap_h),
            _kv("reach_km", reach_km),
        ]
    else:
        _results = [
            "[results.optical_payload]",
            f"mode = {_t(ui_mode.value)}",
            _kv("raw_frame_kb", raw_kb),
            _kv("compressed_frame_kb", comp_kb),
            _kv("fill_fraction", fill_fraction),
            _kv("corners_in_frame", corners_in_frame),
            _kv("distance_to_center_mm", dist_center_mm),
            _kv("dof_near_mm", dof_near_mm),
            _kv("dof_far_mm", dof_far_mm),
        ]

    profile_toml = "\n".join(
        [
            f"# Saved from BAC Optical Payload {TOOL_VERSION} on {_today}. Load it with the button at the",
            "# top of the notebook. Any key you leave out keeps the tool's default. [results.optical_payload]",
            "# is what this tool hands to its siblings and is ignored when loaded back.",
            f'name = "Saved settings, {_today}"',
            'tool = "bac_optical_payload"',
            f"tool_version = {_t(TOOL_VERSION)}",
            "",
            "[mission]",
            f"mode = {_t(ui_mode.value)}",
            "",
            "[orbit]",
            f"altitude_km = {_t(ui_altitude.value)}",
            f"inclination_deg = {_t(ui_inclination.value)}",
            f"ltdn_hours = {_t(ui_ltdn.value)}",
            f"epoch = {_t(ui_epoch.value)}",
            f"sim_days = {_t(ui_sim_days.value)}",
            "",
            "[camera]",
            f"name = {_t(ui_camera.value)}",
            "",
            "[sensor]",
            f"name = {_t(ui_sensor.value)}",
            f"width_px = {_t(ui_sensor_w.value)}",
            f"height_px = {_t(ui_sensor_h.value)}",
            f"pitch_um = {_t(ui_sensor_pitch.value)}",
            f"bits = {_t(ui_sensor_bits.value)}",
            f"global_shutter = {_t(ui_sensor_global.value)}",
            "",
            "[lens]",
            f"name = {_t(ui_lens.value)}",
            f"focal_mm = {_t(ui_focal.value)}",
            f"f_number = {_t(ui_fnum.value)}",
            f"image_circle_mm = {_t(ui_circle.value)}",
            "",
            "[imaging]",
            f"exposure_ms = {_t(ui_exposure.value)}",
            f"readout_ms = {_t(ui_readout.value)}",
            f"attitude_rate_deg_s = {_t(ui_att_rate.value)}",
            f"pointing_error_deg = {_t(ui_point_err.value)}",
            f"pointing_knowledge_deg = {_t(ui_point_know.value)}",
            f"wavelength_nm = {_t(ui_wavelength.value)}",
            f"compression_ratio = {_t(ui_compression.value)}",
            f"frames_per_day = {_t(ui_frames_day.value)}",
            f"low_rate_kb_per_day = {_t(ui_low_rate.value)}",
            f"high_rate_kb_per_day = {_t(ui_high_rate.value)}",
            f"max_off_nadir_deg = {_t(ui_off_nadir.value)}",
            f"min_sun_elevation_deg = {_t(ui_min_sun.value)}",
            "",
            "[target]",
            f"name = {_t(target_name)}",
            f"latitude_deg = {_t(target_lat)}",
            f"longitude_deg = {_t(target_lon)}",
            "",
            "[map]",
            f"tiles = {_t(ui_tiles.value)}",
            f"zoom = {_t(ui_map_zoom.value)}",
            f"key = {_t(ui_tile_key.value)}",
            "",
            "[boom]",
            f"cubesat = {_t(ui_cubesat.value)}",
            f"face = {_t(ui_face.value)}",
            f"offset_x_mm = {_t(ui_off_x.value)}",
            f"offset_y_mm = {_t(ui_off_y.value)}",
            f"length_mm = {_t(ui_boom_len.value)}",
            f"sweep_deg = {_t(ui_sweep.value)}",
            f"sweep_dir_deg = {_t(ui_sweep_dir.value)}",
            f"aim_at_center = {_t(ui_aim.value)}",
            f"pitch_deg = {_t(ui_pitch.value)}",
            f"yaw_deg = {_t(ui_yaw.value)}",
            f"focus_mm = {_t(ui_focus.value)}",
            f"show_focus = {_t(ui_show_focus.value)}",
            "",
            *_results,
            "",
        ]
    )
    mo.vstack(
        [
            mo.md("## Export"),
            mo.md(
                "The report carries the headline table, the assumptions and the acknowledgment. "
                "The profile carries every input and a `[results.optical_payload]` table for the "
                "sibling tools – frame size, frames per day, exposure, reach and access figures; "
                "it loads back into the control panel."
            ),
            mo.hstack(
                [
                    mo.download(data=report_md.encode("utf-8"), filename=f"bac-optical-payload-{_slug}-{_today}.md", mimetype="text/markdown", label="Download report (.md)"),
                    mo.download(data=profile_toml.encode("utf-8"), filename=f"bac-optical-payload-profile-{_today}.toml", mimetype="application/toml", label="Download profile (.toml)"),
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

    **Orbit.** Circular, two-body, over a spherical Earth of radius 6'371 km,
    with [J2](https://cubesat-resources.space/references/glossary/#j2) nodal regression so a
    [sun-synchronous](https://cubesat-resources.space/references/glossary/#sso) [inclination](https://cubesat-resources.space/references/glossary/#inclination)
    stays sun-synchronous; the [RAAN](https://cubesat-resources.space/references/glossary/#raan) follows from the
    [local time of the descending node](https://cubesat-resources.space/references/glossary/#local-time-of-descending-node-ltdn)
    at the [epoch](https://cubesat-resources.space/references/glossary/#epoch). Earth rotation is GMST; the Sun follows the
    Astronomical Almanac low-precision algorithm, good to about 0.01°. Ground
    speed is the sub-satellite point speed without Earth rotation, within 7% at
    any inclination. Good enough to plan, not to schedule – for that you want a
    [TLE](https://cubesat-resources.space/references/glossary/#tle) and [SGP4](https://cubesat-resources.space/references/glossary/#sgp4).

    **Geometry.** A pinhole camera pointed at [nadir](https://cubesat-resources.space/references/glossary/#nadir): no distortion,
    no vignetting, a rectilinear projection.
    [GSD](https://cubesat-resources.space/references/glossary/#ground-sample-distance-gsd) is pitch × altitude ÷ focal length,
    [swath](https://cubesat-resources.space/references/glossary/#swath) is GSD × pixel count, and the
    [field of view](https://cubesat-resources.space/references/glossary/#field-of-view-fov) follows from the sensor size. The
    image-circle check is a diameter comparison, not a measured illumination
    falloff. Every ground distance that depends on an angle – the reach a
    [slew](https://cubesat-resources.space/references/glossary/#slew) buys, the footprint shift at the pointing error, the
    geolocation uncertainty – comes from the same spherical-Earth geometry as
    the off-nadir chart, horizon limited, so the numbers agree with each other.

    **Resolution.** Diffraction as the Rayleigh criterion at a single
    wavelength, 1.22 λ h ÷ D, with Q = λ·N/pitch as the sampling factor: below
    about 0.5 strongly detector limited, above 1 the aperture governs, between
    the two both matter ([diffraction limit](https://cubesat-resources.space/references/glossary/#diffraction-limit)). At a fixed
    [f-number](https://cubesat-resources.space/references/glossary/#f-number) a longer lens shrinks GSD and spot together and
    leaves Q alone. [Smear](https://cubesat-resources.space/references/glossary/#image-smear) is the ground motion or the
    attitude motion during the exposure, whichever is asked; the two are not
    combined. [Rolling-shutter](https://cubesat-resources.space/references/glossary/#rolling-shutter-global-shutter) skew is the
    ground motion during the readout time you enter, across the whole frame.

    **Pointing.** The [pointing error](https://cubesat-resources.space/references/glossary/#pointing-accuracy-pointing-knowledge)
    moves the footprint on the ground without changing its shape and is
    subtracted from the access reach; pointing knowledge sets the geolocation
    uncertainty and nothing else.

    **Access and illumination.** An access is the target inside the reach of
    the sub-satellite point, the reach being half the cross-track swath (the
    sensor's long axis is taken as cross-track) plus the ground the slew buys,
    less the pointing error. The [ground track](https://cubesat-resources.space/references/glossary/#ground-track) is sampled
    every 10 s; every closest approach that could dip inside the reach is then
    refined on a fine grid and the entry and exit times solved by bisection to
    a tenth of a second, so an access shorter than a sample is found and timed
    rather than lost between two samples. The Sun's elevation at the target at
    the middle of the access decides lit or dark; illumination is the Sun's
    elevation, not the scene radiance.

    **Data volume.** Frame size is pixel count times RAW bit depth. The
    compression ratio is an input; typical JPEG at good quality is 8:1 to 12:1
    on Earth scenes. The thumbnail is 8× binned and compressed. Daily
    [downlink](https://cubesat-resources.space/references/glossary/#downlink-uplink) volumes are inputs: a low-rate and a
    high-rate link, in kB per day, with no assumption about their frequency
    bands. An empty panel starts at 1'000 and 10'000 kB/day, round figures an
    order of magnitude apart. The BAC profiles carry the
    [link budget](https://cubesat-resources.space/references/glossary/#link-budget)'s figures at Bern, 450 km, 10°, 3 dB:
    3'221 kB/day on UHF and 2'539 on S-band. The high-rate link carrying less
    is a margin result, not a bit-rate one, and a callout says so whenever it
    happens.

    **Boom.** The spacecraft is its envelope, a box with no deployables; the
    boom is a straight line from the root, drawn only in the side view. Depth
    of field uses a circle of confusion of two pixel pitches and the thin-lens
    formulas. A focus distance at or inside the focal length is refused and the
    center distance used instead; a part of the spacecraft at or inside the
    focal length has no image and no blur figure. With the focus switch on, the
    boom frame colors each edge by the blur circle at its depth – in focus up
    to 2 px, soft to 6 px, out of focus beyond – and the side view marks the
    near and far limits; with it off the views are plain geometry and the
    depth-of-field callout still fires.

    **Libraries and presets.** A camera preset chooses library rows. On load
    the profile's explicit sensor and lens win over its preset name, so a pair
    that departs from the preset survives a reload; changing the camera
    afterwards applies the new preset. The libraries are shown for reference;
    a sensor or lens that is not in them goes in through the Custom fields.
    The action cameras, the DJI air units and the phone are there for a sense
    of scale; their pitches and focal lengths are derived from published
    formats and 35 mm equivalents, and their wide lenses are outside what a
    rectilinear pinhole describes.

    **Profiles.** A link budget profile loads with its orbit, its station as
    the target and its `[results.link_budget]` usable data per day in the slot
    its `role` names; a profile without that table says so and keeps the
    defaults. A power budget profile loads with its orbit, its activation
    location as the target and its planned activations as frames per day, and
    its `[results.power_budget]` affordable activations feed a callout. Profile
    values outside a control's range are clamped; values that are not numbers
    fall back to the default and are reported.

    ## Limitations

    No radiometry: the tool says whether an image is sharp, not whether it is
    exposed; signal-to-noise, full well and read noise are a later version. No
    off-nadir geometry across the frame, no keystone, no GSD variation within a
    frame. Access is geometric, with no attitude scheduling, no cloud cover and
    no conflict with the downlink passes. Sensor entries marked provisional are
    from memory of the sensor family and want checking against the datasheet.
    The licensing table reports capability and names three regimes as examples;
    it does not state law.

    Linked terms go to the CubeSat Resources glossary, [bac.page/glossary](https://bac.page/glossary).
    The sibling tools are the [Link Budget](https://bac.page/link-budget-tool)
    and the [Power Budget](https://bac.page/power-budget-tool); a profile saved
    from either loads here, and this tool's profile loads there. Source and
    issues: [bac-utils](https://github.com/buildacubesat/bac-utils).
    """

    ACKNOWLEDGMENT_MD = """
    ## Acknowledgment

    The geometry follows the standard first-order optical payload relations; the
    Q sampling factor follows Fiete, "Image quality and λFN/p for remote sensing
    systems", Optical Engineering 38(7), 1999. Camera and sensor figures are from
    the makers' product pages where the library says so, otherwise derived and
    marked provisional.

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
    | 0.7.0 | 2026-09-14 | Review fixes: access entry and exit are solved between the 10 s samples – every closest approach that could dip inside the reach is refined on a fine grid and bisected to a tenth of a second – so an access shorter than a sample is found and timed, and the access list shows the closest approach; a saved profile's explicit sensor and lens win over its camera preset on load, and the preset applies only when the camera dropdown is changed; a link budget profile without `[results.link_budget]` says so in a callout instead of claiming an import; a focus distance at or inside the focal length is refused with a callout, and a spacecraft part inside the focal length gets no blur figure and its own callout; the focal-length advice and the diffraction callout now say what the equations say (a longer lens at constant f-number resolves more and leaves Q alone); every angle-to-ground distance – access reach, footprint shift, geolocation – uses the off-nadir chart's spherical geometry with the horizon limit; the Raspberry Pi Global Shutter Camera is the color IMX296LQR-C, with the mono IMX296 kept as its own provisional row; the libraries are described as reference tables, with the Custom fields as the way in. DJI O4 Air Unit and O4 Air Unit Pro as camera presets, sensor rows provisional. Interoperability: a power budget profile loads (orbit, activation location, planned activations as frames) and its affordable activations feed a callout; map settings move to a `[map]` table shared with the link budget, old `[target]` keys still load; `reach_km` in the results; profile values clamped to control ranges and reported when unreadable; newlines escaped in the profile. Homogenization: intro at the siblings' length with the tool's URL, its siblings, the project and the repository; the preliminary warning as a callout; "Headline Numbers"; assumptions as structured paragraphs with glossary links; equal-width panel columns. |
    | 0.6.0 | 2026-09-13 | Camera dropdown: a product sets its sensor and, where fixed, its lens (Raspberry Pi Camera Module 3, HQ Camera, AI Camera and Global Shutter Camera, the three CHC5 evaluation modules, the action cameras and the phone); the sensor dropdown names the product each sensor ships in. Tiny Telescope TT240-40 in the lens library. Interoperability: the saved profile names the tool and its version and carries a `[results.optical_payload]` table with the figures the siblings take; a link budget profile loads directly, its station standing in for the target and its `[results.link_budget]` figure for the downlink volume. Profile writer replaced with the link budget's. |
    | 0.5.3 | 2026-09-13 | Library additions: RunCam 5 and the iPhone 18 Pro main camera as scale references, each with its fixed lens; the RunCam Thumb Pro lens circle raised to cover its own sensor so the fixed pair no longer trips the image-circle callout; and the Raspberry Pi 6 mm CS-mount lens so the HQ and Global Shutter cameras have both of their official lenses to choose from. |
    | 0.5.2 | 2026-09-11 | Depth of field in the boom views is behind a switch, off by default: the frame is a plain wireframe and the side view plain geometry unless it is on. The depth-of-field callout is unchanged. |
    | 0.5.1 | 2026-09-11 | Downlink defaults revisited: an empty panel starts at 1'000 and 10'000 kB/day, the BAC profiles carry the link budget's 3'221 UHF and 2'539 S-band, and the generic 1U carries 500 with no second link. A callout when the high-rate link carries less per day than the low-rate one, because that is a margin result rather than a bit-rate one. |
    | 0.5.0 | 2026-09-11 | Earth mode renamed to Earth observation (old profiles still load). Target presets, thirteen cities with a custom option. Map at full content width with a zoom slider, a CARTO key field, and legends on one line. Boom frame edges colored by focus with the blur circle in the tooltip; depth-of-field limits drawn in the side view. GoPro Hero 13 Black, DJI Osmo Action 4 and RunCam Thumb Pro in the libraries for scale. |
    | 0.4.0 | 2026-09-11 | Map base switched to grayscale CARTO tiles, light or dark with the notebook theme, and every layer clipped to the chart so the overlays and legends stay inside the frame. Resolution charts reordered: focal length first, then off-nadir, which now draws (a log axis was dropping it on the zero at nadir). Downlink inputs renamed to low rate and high rate with 1'000 and 3'000 kB/day as shipped defaults, so the tool assumes nothing about frequency bands. |
    | 0.3.0 | 2026-09-11 | Map moved to the top of the Earth observation results and gains OpenStreetMap tiles under the coastline with a switch to turn them off. Two Earth observation charts added: Sun elevation over the simulation with the accesses marked, and GSD against off-nadir angle. Control panel mode line removed. CHC5 named as the source of the sensor library. |
    | 0.2.0 | 2026-09-11 | Control panel split into a common left column and a mode column. Boom mode gains a boom sweep angle, face labels, a side view of the geometry and a fill-against-boom-length sweep. Earth observation mode gains access and illumination over a target (two-body plus J2, LTDN-set RAAN, Almanac Sun), a regional map with footprint, envelope, ground track and access passes, and the revisit line in the licensing table. Report and profile export. |
    | 0.1.0 | 2026-09-10 | Initial version. Earth observation mode: GSD, swath, field of view, Rayleigh spot and Q, motion and attitude smear, rolling-shutter skew, pointing envelope and geolocation, frame size and days to downlink on two links, licensing parameters, resolution against focal length. Boom mode: pinhole projection of the CubeSat envelope into the frame, fill fraction, depth of field. Sensor and lens libraries, TOML profiles, three shipped. |
    """)
    return


if __name__ == "__main__":
    app.run()
