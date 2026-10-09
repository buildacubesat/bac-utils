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

__generated_with = "0.25.0"
app = marimo.App(width="medium", auto_download=["html"])


@app.cell
def _(mo):
    mo.vstack(
        [
            mo.md("""
    # BAC Link Budget

    Estimate link margin and usable data volume between a satellite in low
    Earth orbit and one ground station. Set the orbit, station, radios and
    modes, or load a mission profile. Optical Payload and Power Budget
    profiles supply compatible settings.

    Compare each mode's margin at the lowest elevation you will work, the
    data that comes down per pass and per day, and which line of the budget
    costs the margin.

    This tool is published at [bac.page/molab-link-budget](https://bac.page/molab-link-budget);
    its siblings are the [Optical Payload](https://bac.page/molab-optical-payload)
    and [Power Budget](https://bac.page/molab-power-budget) tools. All three
    belong to the [Build a CubeSat](https://buildacubesat.space) project and
    their source is in [bac-utils](https://github.com/buildacubesat/bac-utils).
    """),
            mo.callout(
                mo.md(
                    "Every number here is a planning input, not a measurement. The model is "
                    "simple on purpose: a circular orbit over a spherical Earth, free-space loss "
                    "with allowances, no antenna patterns. Use it to compare options and find the "
                    "dominant term, not to schedule a pass."
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
      --text-muted: #6C6B67;
    }

    /* Track marimo's own light/dark setting rather than the operating system.
       marimo sets color-scheme from that setting and light-dark() follows it. */
    :root {
      --text: light-dark(#3F3F3F, #efefed);
      --bg:   light-dark(#efefed, #201e1c);
      --text-muted: light-dark(#6C6B67, #A3A29C);
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
    import tomllib  # stdlib from 3.11; profiles are read here and written by hand

    import altair as alt
    import marimo as mo
    import numpy as np
    import pandas as pd

    return alt, dt, mo, np, pd, tomllib


@app.cell
def _(np):
    # Constants, reference data and the small set of formulas everything uses.

    TOOL_VERSION = "0.7.4"

    R_EARTH_KM = 6371.0
    MU_KM3_S2 = 398600.4418
    OMEGA_EARTH = 7.2921159e-5  # rad/s
    K_BOLTZMANN_DBW = -228.6  # dBW/(K·Hz)
    T0_K = 290.0

    # Modulation library. Each entry is (kind, threshold_db, code_rate, ref_bw_hz).
    #   fsk  – threshold is a required Eb/N0 per information bit, from the
    #          AMSAT/IARU Link Model Rev 2.5.5, Modulation-Demodulation worksheet,
    #          cells F6:F23, BER 1e-5 unless the entry says otherwise. The mode
    #          row supplies the channel bit rate; information rate is that times
    #          the code rate, so a coded entry's gain and its throughput cost
    #          come from the same line.
    #   lora – threshold is a demodulator SNR in the row's bandwidth, SX1276
    #          datasheet Rev 5, Table 13, p. 27; the SX126x and LR11xx families
    #          publish the same values. The bit rate comes from SF and bandwidth
    #          and already includes the 4/5 code rate.
    #   snr  – threshold is an SNR in ref_bw_hz, for modes with no bit rate. The
    #          row's bandwidth overrides ref_bw_hz when set.
    # The two GFSK h=1 entries are King's coherent and non-coherent FSK numbers
    # under a name that matches the SatNOGS-COMMS UHF waveform: at a modulation
    # index of 1 the two tones are orthogonal, so the Gaussian shaping changes the
    # spectrum and not the threshold. Which of the two applies is a property of
    # the ground demodulator. AX.100 Mode 5 is filed under both "FSK" and "MSK"
    # in the SatNOGS census; the GMSK threshold is used, which is the optimistic
    # reading of that ambiguity.
    # CW: -3.6 dB in 100 Hz for a trained operator copying random text at
    # 10 wpm, about -6.6 dB when the text is known (W2RS, "The Human Ear as an
    # SSB/CW Receiver", Central States VHF Society 2002). The random-text figure
    # is used; a beacon's content is known, so it errs on the safe side.
    MODULATIONS = {
        "AFSK/FM": ("fsk", 23.2, 1.0, None),
        "G3RUH FSK": ("fsk", 18.0, 1.0, None),
        "FSK, non-coherent": ("fsk", 13.8, 1.0, None),
        "FSK, coherent": ("fsk", 11.9, 1.0, None),
        "GMSK": ("fsk", 9.6, 1.0, None),
        "AX.100 Mode 5": ("fsk", 9.6, 1.0, None),
        "GFSK h=1, coherent": ("fsk", 11.9, 1.0, None),
        "GFSK h=1, non-coherent": ("fsk", 13.8, 1.0, None),
        "GFSK h=0.5, discriminator": ("fsk", None, 1.0, None),
        "GFSK h=1 + conv K=4 R=1/2 (native)": ("fsk", 12.3, 0.5, None),
        "GFSK h=1 + RS(255,223) (MCU)": ("fsk", 11.8, 223 / 255, None),
        "BPSK": ("fsk", 9.6, 1.0, None),
        "QPSK": ("fsk", 9.6, 1.0, None),
        "BPSK + conv R=1/2 K=7": ("fsk", 4.8, 0.5, None),
        "BPSK + conv + RS(255,223)": ("fsk", 2.5, 0.5 * 223 / 255, None),
        "LoRa SF7": ("lora", -7.5, 1.0, None),
        "LoRa SF8": ("lora", -10.0, 1.0, None),
        "LoRa SF9": ("lora", -12.5, 1.0, None),
        "LoRa SF10": ("lora", -15.0, 1.0, None),
        "LoRa SF11": ("lora", -17.5, 1.0, None),
        "LoRa SF12": ("lora", -20.0, 1.0, None),
        "CW, aural": ("snr", -3.6, 1.0, 100.0),
        "CW, detector spec": ("snr", 10.0, 1.0, 100.0),
        "Custom": ("fsk", None, 1.0, None),
    }

    # Entries whose threshold has never been measured for the receiver they name.
    # King's table entries are not marked: they are the validation reference. The
    # notebook says on its face when the featured mode uses one of these.
    PROVISIONAL = {
        "GFSK h=1, coherent",
        "GFSK h=1, non-coherent",
        "GFSK h=0.5, discriminator",
        "GFSK h=1 + conv K=4 R=1/2 (native)",
        "GFSK h=1 + RS(255,223) (MCU)",
        "CW, aural",
        "CW, detector spec",
    }
    # Entries whose figure sits on the ideal non-coherent orthogonal FSK curve,
    # P_b = ½·exp(−Eb/N0 / 2). For these the tool can convert between bit error
    # rate, frame length and frame error rate; for everything else it cannot.
    IDEAL_NCFSK = {"FSK, non-coherent", "GFSK h=1, non-coherent"}
    LIBRARY_NOTES = {
        "GFSK h=1, coherent": "Optimistic reference bound only. The SatNOGS ground chain is a discriminator, so this is not the default.",
        "GFSK h=1, non-coherent": "SatNOGS-COMMS native UHF waveform through the SatNOGS discriminator chain. King's ideal non-coherent FSK figure stands in until the chain is swept.",
        "GFSK h=0.5, discriminator": "SatNOGS-COMMS native S-band waveform. No defensible figure exists: at h = 0.5 the tones are not orthogonal for a non-coherent detector, so it takes the Custom Eb/N0 below and you own the number.",
        "GFSK h=1 + conv K=4 R=1/2 (native)": "The AT86RF215's own MR-FSK convolutional code (datasheet §6.10.2.2). Halves the information rate: 25 kbit/s at 50 ksym/s. The 1.5 dB gain is an estimate for hard-decision Viterbi behind a discriminator; no ground decoder for this code exists yet.",
        "GFSK h=1 + RS(255,223) (MCU)": "Reed–Solomon in SatNOGS-COMMS MCU software, the configuration Libre Space measured the −117 dBm reference with. Costs 12.5% of throughput. The 2 dB gain is an estimate; discriminator errors are bursty, so the textbook figure is optimistic. gr-satnogs has RS decoder blocks to adapt.",
        "CW, aural": "W2RS, random text at 10 wpm by ear; about 3 dB better for known text.",
        "CW, detector spec": "BAC CW planning baseline: on/off keyed carrier, 10 WPM PARIS, non-coherent tone and envelope detection, 100 Hz equivalent noise bandwidth after frequency correction. Morse timing per ITU-R M.1677; carrier generation with the FPGA off per AT86RF215 datasheet §13.1.2 and Table 13-2, pp. 221–222.",
    }

    # Mode-table columns and the profile keys they serialise to, plus what an
    # unspecified cell falls back to when a profile names only some of them.
    MODE_KEYS = {
        "Mode": "mode",
        "Modulation": "modulation",
        "Bit rate (bps)": "bitrate_bps",
        "Bandwidth (Hz)": "bandwidth_hz",
        "Spacecraft TX (dBm)": "tx_dbm",
        "Downlink": "downlink",
        "Uplink": "uplink",
        "Featured": "featured",
    }
    MODE_BLANK = {
        "Mode": "",
        "Modulation": "GMSK",
        "Bit rate (bps)": 0,
        "Bandwidth (Hz)": None,
        "Spacecraft TX (dBm)": 32.0,
        "Downlink": True,
        "Uplink": False,
        "Featured": False,
    }

    # Three profiles ship with the tool. The BAC UHF one is what the panel starts
    # from, written out so the mission and the tool are separable; the BAC S-band
    # one is its sibling, because a band changes the whole ground station and not
    # only a frequency; the generic one is a different mission entirely, and
    # exists to show that the tool is not the mission.
    PROFILE_BAC = """
    # Build a CubeSat demo mission, UHF, as of 2026-10-06 (planning orbit 500 km).
    # Sibling: "Build a CubeSat demo mission, S-band" – same orbit, station and
    # policy; only the band, antennas and modes differ. Change both together.
    name = "Build a CubeSat demo mission"

    [mission]
    # What this link is for the payload: the optical payload tool puts the
    # usable volume in its low-rate or high-rate slot by this key.
    link_role = "low rate"

    [orbit]
    altitude_km = 500
    inclination_deg = 97.4
    min_elevation_deg = 10
    target_margin_db = 3
    downlink_mhz = 436.0
    uplink_mhz = 436.0

    [ground_station]
    station = "Bern, Switzerland"
    antenna = "WiMo X-Quad 70 cm"
    rotator = true
    tx_power_w = 25

    [spacecraft]
    antenna_gain_dbi = 0
    receiver_nf_db = 1.5
    # One radio and one antenna serve both directions on one frequency, so
    # the pass is shared by the downlink share under Link Allowances.
    duplex = "half"

    # The beacon ladder of 2026-09-14 maps onto these rows: tier 0 is the CW
    # row (radio node, commissioning and deep safe mode); tiers 1 and 2 ride
    # the native 50k profile (6.5 and 26 ms messages, safe mode and
    # commissioning); the backstop is the LoRa SF12 row (function board,
    # degraded phase). The power budget prices them.
    [[modes]]
    mode = "50k GFSK"
    modulation = "GFSK h=1, non-coherent"
    bitrate_bps = 50000
    tx_dbm = 32.0
    downlink = true
    uplink = true
    featured = true

    [[modes]]
    mode = "CW beacon"
    modulation = "CW, detector spec"
    bandwidth_hz = 100
    tx_dbm = 32.0
    downlink = true

    [[modes]]
    mode = "LoRa SF7"
    modulation = "LoRa SF7"
    bandwidth_hz = 125000
    tx_dbm = 22.0
    downlink = true
    uplink = true

    [[modes]]
    mode = "LoRa SF12"
    modulation = "LoRa SF12"
    bandwidth_hz = 125000
    tx_dbm = 22.0
    downlink = true
    uplink = true
    """

    PROFILE_SBAND = """
    # Build a CubeSat demo mission, S-band downlink, as of 2026-10-06 (planning orbit 500 km).
    # Sibling: "Build a CubeSat demo mission" (UHF) – same orbit, station and
    # policy; only the band, antennas and modes differ. Change both together.
    #
    # Placeholders, stated so nobody mistakes them for measurements: 2'445 MHz
    # is a planning channel inside the amateur allocation and inside the patch's
    # AR < 3 dB range (2'443–2'457 MHz), pending IARU coordination; the feed and
    # LNA for 2.4 GHz are not owned yet, so feed loss, noise figure and antenna
    # temperature are the tool's defaults; the spacecraft gain is the simulated
    # RHCP boresight value of the ICDT/Inatel patch at 2'450 MHz, not a measured
    # installed figure; and the h = 0.5 discriminator threshold is unverified, so
    # custom_ebn0_db carries the h = 1 figure as a pessimistic bracket with a
    # coherent-bound row alongside. Rows are downlink only: the dish has no
    # transmit path, and commanding stays on UHF.
    name = "Build a CubeSat demo mission, S-band"

    [mission]
    # The payload data link: the optical payload tool takes this profile's
    # usable volume as its high-rate figure.
    link_role = "high rate"

    [orbit]
    altitude_km = 500
    inclination_deg = 97.4
    min_elevation_deg = 10
    target_margin_db = 3
    downlink_mhz = 2445.0
    # Uplink stays on UHF, so the two directions are cross-band and the downlink
    # gets the whole pass. No uplink row exists for the dish to receive through.
    uplink_mhz = 436.0

    [ground_station]
    station = "Bern, Switzerland"
    antenna = "Discovery Dish 70 cm"
    rotator = true
    # 5° on a 12.2° beam costs about 2 dB; the same 5° on the X-Quad costs 0.2 dB.
    tracking_error_deg = 5

    [spacecraft]
    antenna_gain_dbi = 7.4
    cable_loss_db = 1.0
    # About 0.1 dB of that is the simulated patch loss at a 5° ADCS error; the
    # rest covers mounting, alignment and jitter that nobody has measured.
    pointing_allowance_db = 0.5
    receiver_nf_db = 1.5
    reference_rx_level_dbm = -108
    reference_rx_rate_bps = 100000
    # Full duplex is a hardware claim, not a frequency one: the AT86RF215's
    # 2.4 GHz transmitter and sub-GHz receiver run at the same time and the
    # dish and the UHF station are separate chains. Accepted as a design
    # assumption on 2026-09-14; set "half" to price the pessimistic case.
    duplex = "full"

    [allowances]
    custom_ebn0_db = 13.8

    [[modes]]
    mode = "100k GFSK"
    modulation = "GFSK h=0.5, discriminator"
    bitrate_bps = 100000
    tx_dbm = 31.0
    downlink = true
    uplink = false
    featured = true

    [[modes]]
    mode = "400k GFSK"
    modulation = "GFSK h=0.5, discriminator"
    bitrate_bps = 400000
    tx_dbm = 31.0
    downlink = true
    uplink = false

    [[modes]]
    mode = "100k, coherent bound"
    modulation = "GMSK"
    bitrate_bps = 100000
    tx_dbm = 31.0
    downlink = true
    uplink = false
    """

    PROFILE_GENERIC = """
    # A different mission: an amateur 1U on a community ground station.
    # No sibling – this is here to show the tool is not the mission.
    name = "Generic amateur 1U"

    [orbit]
    altitude_km = 550
    inclination_deg = 53.0
    min_elevation_deg = 5
    target_margin_db = 3
    downlink_mhz = 436.5
    uplink_mhz = 145.9

    [ground_station]
    station = "Custom"
    latitude_deg = 51.5
    longitude_deg = -0.13
    antenna = "Turnstile, no rotator"
    rotator = false
    tx_power_w = 50

    [spacecraft]
    antenna_gain_dbi = 0
    receiver_nf_db = 4.0
    # VHF up and UHF down, but one transceiver: it does not receive while it
    # transmits, so the pass is still shared.
    duplex = "half"

    [[modes]]
    mode = "9k6 GMSK"
    modulation = "GMSK"
    bitrate_bps = 9600
    tx_dbm = 30.0
    downlink = true
    uplink = true
    featured = true

    [[modes]]
    mode = "1k2 AFSK"
    modulation = "AFSK/FM"
    bitrate_bps = 1200
    tx_dbm = 30.0
    downlink = true
    uplink = true
    """

    # Ground antennas: gain in dBi, half-power beamwidth in degrees, circular.
    # Beamwidths and gains are consistent with each other through the practical
    # G = 31000 / (beamwidth squared) relation rather than the lossless constant
    # manufacturers tend to quote. Keep the names short: the dropdown is a native
    # select whose width is its longest option, and a long one overflows the column.
    GS_ANTENNAS = {
        "WiMo X-Quad 70 cm": (13.5, 36.0, True),
        "Yagi 70 cm, 7 element": (12.0, 44.0, False),
        "Turnstile, no rotator": (5.0, 100.0, True),
        "Discovery Dish 70 cm": (22.0, 12.2, True),
        "Helix S-band, 16 turn": (16.5, 26.0, True),
        "Dish S-band, 1.2 m": (26.8, 7.8, True),
        "Custom": (None, None, None),
    }

    # Ground stations: latitude and longitude in degrees.
    STATIONS = {
        "Bern, Switzerland": (46.950, 7.450),
        "San Marcos, Texas": (29.879, -97.939),
        "Farroupilha, Brazil": (-29.233, -51.350),
        "Nairobi, Kenya": (-1.286, 36.817),
        "Custom": None,
    }

    # Loss through atmospheric gases against elevation, interpolated from
    # Ippolito, Radiowave Propagation in Satellite Communications, 1986,
    # pp. 33-34, Tables 3-3a-c, as tabulated by King. Valid below 2 GHz.
    _ATMOS_EL = [0.0, 2.5, 5.0, 10.0, 30.0, 45.0, 90.0]
    _ATMOS_DB = [10.2, 4.6, 2.1, 1.1, 0.4, 0.3, 0.0]

    # Mean ionospheric loss against frequency, King's table: 0.7 dB at 146 MHz,
    # 0.4 dB at 438 MHz, 0.1 dB at 2410 MHz. Interpolated in log frequency.
    _IONO_F = np.log10([146.0, 438.0, 2410.0])
    _IONO_DB = [0.7, 0.4, 0.1]

    def _shell_airmass(el_deg, h_km):
        # Path length through a shell of thickness h over a spherical Earth,
        # relative to the zenith path. Equals 1/sin(el) at high elevation and
        # stays finite at the horizon.
        _s = R_EARTH_KM * np.sin(np.radians(el_deg))
        return (np.sqrt(_s**2 + 2 * R_EARTH_KM * h_km + h_km**2) - _s) / h_km

    def gaseous_zenith_db(f_mhz):
        # ITU-R P.676 Annex 2 simplified: oxygen and water vapor specific
        # attenuation at 1013.25 hPa, 15 °C, 7.5 g/m³, times the equivalent
        # heights. Returns (oxygen zenith dB, oxygen height km, vapor zenith dB,
        # vapor height km). Below about 1 GHz the expressions extrapolate; they
        # are tiny there anyway.
        f = f_mhz / 1000.0
        rp = rt = 1.0
        g_o = (
            (7.2 * rt**2.8 / (f**2 + 0.34 * rp**2 * rt**1.6) + 0.62 / ((54 - f) ** 1.16 + 0.83)) * f**2 * rp**2 * 1e-3
            if f < 54
            else 0.0
        )
        rho = 7.5
        eta1 = 0.955 * rp * rt**0.68 + 0.006 * rho
        eta2 = 0.735 * rp * rt**0.5 + 0.0353 * rt**4 * rho

        def g(fi):
            return 1 + ((f - fi) / (f + fi)) ** 2

        g_w = (
            (
                3.98 * eta1 / ((f - 22.235) ** 2 + 9.42 * eta1**2) * g(22)
                + 11.96 * eta1 / ((f - 183.31) ** 2 + 11.14 * eta1**2)
                + 0.081 * eta1 / ((f - 321.226) ** 2 + 6.29 * eta1**2)
                + 3.66 * eta1 / ((f - 325.153) ** 2 + 9.22 * eta1**2)
                + 25.37 * eta1 / (f - 380) ** 2
                + 17.4 * eta1 / (f - 448) ** 2
                + 844.6 * eta1 / (f - 557) ** 2 * g(557)
                + 290 * eta1 / (f - 752) ** 2 * g(752)
                + 8.3328e4 * eta2 / (f - 1780) ** 2 * g(1780)
            )
            * f**2
            * rt**2.5
            * rho
            * 1e-4
        )
        t1 = 4.64 / (1 + 0.066 * rp**-2.3) * np.exp(-(((f - 59.7) / (2.87 + 12.4 * np.exp(-7.9 * rp))) ** 2))
        t2 = 0.14 * np.exp(2.12 * rp) / ((f - 118.75) ** 2 + 0.031 * np.exp(2.2 * rp))
        t3 = (
            0.0114
            / (1 + 0.14 * rp**-2.6)
            * f
            * (-0.0247 + 0.0001 * f + 1.61e-6 * f**2)
            / (1 - 0.0169 * f + 4.1e-5 * f**2 + 3.2e-7 * f**3)
        )
        h_o = 6.1 / (1 + 0.17 * rp**-1.1) * (1 + t1 + t2 + t3)
        sw = 1.013 / (1 + np.exp(-8.6 * (rp - 0.57)))
        h_w = 1.66 * (
            1
            + 1.39 * sw / ((f - 22.235) ** 2 + 2.56 * sw)
            + 3.37 * sw / ((f - 183.31) ** 2 + 4.69 * sw)
            + 1.58 * sw / ((f - 325.1) ** 2 + 2.89 * sw)
        )
        return g_o * h_o, h_o, g_w * h_w, h_w

    def gaseous_loss_db(el_deg, f_mhz):
        a_o, h_o, a_w, h_w = gaseous_zenith_db(f_mhz)
        return a_o * _shell_airmass(el_deg, h_o) + a_w * _shell_airmass(el_deg, h_w)

    def atmospheric_loss_db(el_deg, f_mhz):
        # King's elevation table is an empirical allowance for everything the
        # troposphere does near the horizon, and exceeds gaseous absorption at
        # every frequency below about 10 GHz except at zenith, where it is zero.
        # The physical P.676 term takes over wherever it is larger, so the model
        # is continuous in frequency and never below physics.
        return np.maximum(
            np.interp(el_deg, _ATMOS_EL, _ATMOS_DB),
            gaseous_loss_db(el_deg, f_mhz),
        )

    def ionospheric_loss_db(f_mhz):
        return float(np.interp(np.log10(f_mhz), _IONO_F, _IONO_DB))

    def pointing_loss_db(error_deg, hpbw_deg):
        return 12.0 * (error_deg / hpbw_deg) ** 2

    def slant_range_km(el_deg, h_km):
        el = np.radians(el_deg)
        re = R_EARTH_KM
        return -re * np.sin(el) + np.sqrt((re * np.sin(el)) ** 2 + h_km**2 + 2 * re * h_km)

    def fspl_db(d_km, f_mhz):
        return 20 * np.log10(d_km) + 20 * np.log10(f_mhz) + 32.44

    def noise_density_dbm_hz(t_ant_k, feed_loss_db, nf_db):
        # System temperature referenced to the LNA input: the antenna
        # temperature attenuated by the feeder, the feeder's own thermal noise,
        # and the receiver. The signal is referenced to the same plane.
        _l = 10 ** (feed_loss_db / 10)
        t_sys = t_ant_k / _l + (1 - 1 / _l) * T0_K + T0_K * (10 ** (nf_db / 10) - 1)
        return K_BOLTZMANN_DBW + 30 + 10 * np.log10(t_sys), t_sys

    def polarization_loss_db(ar1_db, ar2_db, worst_case):
        # Polarization loss factor between two elliptically polarized antennas
        # of the same sense, from their axial ratios. The angle between the
        # ellipses' major axes is unknown for a tumbling spacecraft: worst case
        # sets them crossed, average takes the mean over that angle.
        r1, r2 = 10 ** (ar1_db / 20), 10 ** (ar2_db / 20)
        cos2 = -1.0 if worst_case else 0.0
        plf = 0.5 + (4 * r1 * r2 + (r1**2 - 1) * (r2**2 - 1) * cos2) / (2 * (r1**2 + 1) * (r2**2 + 1))
        return -10 * np.log10(plf)

    def ncfsk_ebn0_for_fer_db(fer, n_bits):
        # Ideal non-coherent orthogonal FSK, P_b = ½·exp(−γ/2), independent bit
        # errors: the Eb/N0 at which a frame of n_bits fails with probability fer.
        _pb = 1 - (1 - fer) ** (1.0 / n_bits)
        return 10 * np.log10(-2 * np.log(2 * _pb))

    def ncfsk_fer_at_ebn0(ebn0_db, n_bits):
        _pb = 0.5 * np.exp(-(10 ** (ebn0_db / 10)) / 2)
        return 1 - (1 - _pb) ** n_bits

    def lora_bitrate_bps(sf, bw_hz, cr_num=4, cr_den=5):
        return sf * bw_hz / (2**sf) * (cr_num / cr_den)

    def lora_packet_s(sf, bw_hz, payload_bytes, preamble_symbols, cr=1, crc=True, explicit_header=True):
        # Packet time on air, SX1276 datasheet Rev 5 §4.1.1.7, p. 31. The
        # symbol time is 2^SF / BW; the preamble carries 4.25 symbols of sync;
        # low-data-rate optimization is on when the symbol lasts more than
        # 16 ms, which at 125 kHz means SF11 and SF12. CR 1 is 4/5.
        _t_sym = 2.0**sf / bw_hz
        _de = 1 if _t_sym > 0.016 else 0
        _num = 8 * payload_bytes - 4 * sf + 28 + (16 if crc else 0) - (0 if explicit_header else 20)
        _n_payload = 8 + max(int(np.ceil(_num / (4 * (sf - 2 * _de)))) * (cr + 4), 0)
        return (preamble_symbols + 4.25 + _n_payload) * _t_sym

    def fmt_int(n):
        if n != n:  # NaN
            return "–"
        return f"{n:,.0f}".replace(",", "'")

    def fmt_num(n, digits=1):
        if n != n:
            return "–"
        return f"{n:,.{digits}f}".replace(",", "'")

    return (
        GS_ANTENNAS,
        IDEAL_NCFSK,
        LIBRARY_NOTES,
        MODE_BLANK,
        MODE_KEYS,
        MODULATIONS,
        MU_KM3_S2,
        OMEGA_EARTH,
        PROFILE_BAC,
        PROFILE_GENERIC,
        PROFILE_SBAND,
        PROVISIONAL,
        R_EARTH_KM,
        STATIONS,
        TOOL_VERSION,
        atmospheric_loss_db,
        fmt_int,
        fmt_num,
        fspl_db,
        ionospheric_loss_db,
        lora_bitrate_bps,
        lora_packet_s,
        ncfsk_ebn0_for_fer_db,
        ncfsk_fer_at_ebn0,
        noise_density_dbm_hz,
        pointing_loss_db,
        polarization_loss_db,
        slant_range_km,
    )


@app.cell
def _(mo):
    # Profile loader. Separate from the control panel because the panel reads the
    # parsed profile to set its starting values, and marimo does not propagate a
    # UI element's value inside the cell that defines it.
    ui_profile = mo.ui.file(
        kind="button",
        filetypes=[".toml"],
        label="Load mission profile (.toml)",
    )
    return (ui_profile,)


@app.cell
def _(tomllib, ui_profile):
    # Parse the uploaded profile into the defaults every input starts from.
    # Anything the file does not name keeps the tool's own default, so a partial
    # profile is valid and a profile from an older version still loads.
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
    # rather than breaking the panel; a float survives an integer default,
    # so 7.4 dBi is not 7 dBi.
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

    profile_modes = _doc.get("modes") or None
    # Which tool wrote the profile: its own key from 0.7.0 on, otherwise a
    # signature table. The optical payload has [sensor], the power budget
    # [storage], and this tool [[modes]].
    _tool = _doc.get("tool")
    if not _tool:
        _tool = (
            "bac_optical_payload"
            if "sensor" in _doc
            else ("bac_power_budget" if "storage" in _doc else "bac_link_budget")
        )
    profile_tool = str(_tool)
    return (
        P,
        PH,
        profile_error,
        profile_modes,
        profile_name,
        profile_tool,
        profile_warnings,
    )


@app.cell
def _(
    PROFILE_BAC,
    PROFILE_GENERIC,
    PROFILE_SBAND,
    mo,
    profile_error,
    profile_name,
    profile_tool,
    ui_profile,
):
    # Loading a profile resets every input, including the mode table, because the
    # panel is rebuilt from it. Saving one is in the export section at the bottom.
    _foreign = {
        "bac_optical_payload": "Optical payload profile loaded: **{n}**. Its orbit and its target as the station are taken; everything else is this tool's default.",
        "bac_power_budget": "Power budget profile loaded: **{n}**. Its orbit, station, minimum elevation and downlink share are taken; everything else is this tool's default.",
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
            filename=f"bac-link-budget-{slug}.toml",
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
                                "Download one, then load it with the button above. The BAC UHF "
                                "profile is what this notebook starts from. The BAC S-band profile "
                                "is its sibling: same orbit and station, different band, antennas "
                                "and modes – a band changes the whole ground station, which is why "
                                "it is a second profile and not a column. The generic one is a "
                                "different mission, and is here to show the tool is not the mission."
                            ),
                            mo.hstack(
                                [
                                    _shipped(
                                        "Build a CubeSat demo mission, UHF",
                                        PROFILE_BAC,
                                        "profile-bac-uhf",
                                    ),
                                    _shipped(
                                        "Build a CubeSat demo mission, S-band",
                                        PROFILE_SBAND,
                                        "profile-bac-sband",
                                    ),
                                    _shipped(
                                        "Generic amateur 1U",
                                        PROFILE_GENERIC,
                                        "profile-generic",
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
def _(
    GS_ANTENNAS,
    LIBRARY_NOTES,
    MODE_BLANK,
    MODE_KEYS,
    MODULATIONS,
    P,
    PH,
    PROVISIONAL,
    STATIONS,
    mo,
    pd,
    profile_modes,
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

    # Orbit and targets. The minimum elevation is read from either table the
    # siblings keep it in; a sibling's 30-day span is clamped to the slider.
    ui_altitude = S(
        start=300,
        stop=1200,
        step=10,
        value=P("orbit", "altitude_km", 500),
        show_value=True,
        label="Orbit altitude (km)",
    )
    ui_inclination = N(
        start=0, stop=180, step=0.1, value=P("orbit", "inclination_deg", 97.4), label="Inclination (deg)"
    )
    ui_min_el = S(
        start=0,
        stop=30,
        step=1,
        value=P("orbit", "min_elevation_deg", P("ground_station", "min_elevation_deg", 10)),
        show_value=True,
        label="Minimum usable elevation (deg)",
    )
    ui_target_margin = S(
        start=0,
        stop=12,
        step=0.5,
        value=P("orbit", "target_margin_db", 3),
        show_value=True,
        label="Target link margin (dB)",
    )
    ui_sim_days = S(
        start=1,
        stop=14,
        step=1,
        value=P("orbit", "sim_days", 7),
        show_value=True,
        label="Days to simulate per orbit phase",
    )
    ui_role = mo.ui.dropdown(
        options=["low rate", "high rate"],
        value=P("mission", "link_role", "low rate"),
        label="Role of this link for the payload",
    )

    # Ground station. An optical payload or power budget profile names a
    # [target] instead of a station: the preset whose city matches is taken,
    # otherwise its coordinates become the custom station.
    _sname = str(P("ground_station", "station", ""))
    if not _sname and PH("target", "name"):
        _city = str(P("target", "name", "")).split(",")[0].strip()
        _sname = next(
            (_k for _k in STATIONS if _k.split(",")[0] == _city),
            "Custom" if PH("target", "latitude_deg") else "Bern, Switzerland",
        )
    if _sname not in STATIONS:
        _sname = "Custom" if PH("ground_station", "latitude_deg") else "Bern, Switzerland"
    ui_station = mo.ui.dropdown(options=list(STATIONS), value=_sname, label="Station")
    ui_lat = N(
        start=-90,
        stop=90,
        step=0.01,
        value=P("ground_station", "latitude_deg", P("target", "latitude_deg", 46.95)),
        label="Custom latitude (deg N)",
    )
    ui_lon = N(
        start=-180,
        stop=180,
        step=0.01,
        value=P("ground_station", "longitude_deg", P("target", "longitude_deg", 7.45)),
        label="Custom longitude (deg E)",
    )
    ui_gs_antenna = mo.ui.dropdown(
        options=list(GS_ANTENNAS),
        value=P("ground_station", "antenna", "WiMo X-Quad 70 cm"),
        label="Antenna",
    )
    ui_rotator = mo.ui.switch(value=P("ground_station", "rotator", True), label="Antenna is on a tracking rotator")
    ui_track_err = S(
        start=0,
        stop=20,
        step=0.5,
        value=P("ground_station", "tracking_error_deg", 5),
        show_value=True,
        label="Tracking error (deg)",
    )
    ui_gs_feed_loss = N(
        start=0,
        stop=6,
        step=0.1,
        value=P("ground_station", "feed_loss_db", 1.0),
        label="Feed loss ahead of the LNA (dB)",
    )
    ui_gs_nf = N(
        start=0.3, stop=10, step=0.1, value=P("ground_station", "lna_nf_db", 1.0), label="LNA noise figure (dB)"
    )
    ui_gs_tant = N(
        start=50,
        stop=1000,
        step=10,
        value=P("ground_station", "antenna_temp_k", 300),
        label="Antenna noise temperature (K)",
    )
    ui_gs_tx_w = N(
        start=1, stop=500, step=1, value=P("ground_station", "tx_power_w", 25), label="Transmitter power (W)"
    )
    ui_gs_ar = N(
        start=0,
        stop=40,
        step=0.5,
        value=P("ground_station", "axial_ratio_db", 3.0),
        label="Axial ratio (dB), circular antennas",
    )

    # Spacecraft. Duplex is a hardware statement: half means one radio and
    # one antenna serve both directions and the pass is shared; full means
    # separate transmit and receive chains and each direction gets the whole
    # pass. A frequency difference alone does not make a link full duplex.
    ui_sat_gain = N(
        start=-10, stop=20, step=0.5, value=P("spacecraft", "antenna_gain_dbi", 0), label="Antenna gain (dBi)"
    )
    ui_sat_loss = N(
        start=0, stop=6, step=0.1, value=P("spacecraft", "cable_loss_db", 1.0), label="Cable and switch loss (dB)"
    )
    ui_sat_point_loss = N(
        start=0,
        stop=6,
        step=0.1,
        value=P("spacecraft", "pointing_allowance_db", 0.5),
        label="Antenna pointing allowance (dB)",
    )
    ui_sat_ar = N(
        start=0, stop=40, step=0.5, value=P("spacecraft", "axial_ratio_db", 3.0), label="Antenna axial ratio (dB)"
    )
    ui_sat_nf = N(
        start=0.5, stop=12, step=0.1, value=P("spacecraft", "receiver_nf_db", 1.5), label="Receiver noise figure (dB)"
    )
    ui_sat_sens = N(
        start=-140,
        stop=-80,
        step=1,
        value=P("spacecraft", "reference_rx_level_dbm", -117),
        label="Reference receive level (dBm)",
    )
    ui_sat_sens_rate = N(
        start=100,
        stop=1000000,
        step=100,
        value=P("spacecraft", "reference_rx_rate_bps", 50000),
        label="…reported at (bps)",
    )
    _duplex_options = {
        "Half – one radio, the pass is shared": "half",
        "Full – separate chains, each direction gets the whole pass": "full",
    }
    _duplex = str(P("spacecraft", "duplex", "half")).strip().lower()
    ui_duplex = mo.ui.dropdown(
        options=_duplex_options,
        value=next((_l for _l, _v in _duplex_options.items() if _v == _duplex), list(_duplex_options)[0]),
        label="Duplex",
    )

    # Frequencies
    ui_freq_down = N(
        start=30, stop=30000, step=0.1, value=P("orbit", "downlink_mhz", 436.0), label="Downlink frequency (MHz)"
    )
    ui_freq_up = N(
        start=30, stop=30000, step=0.1, value=P("orbit", "uplink_mhz", 436.0), label="Uplink frequency (MHz)"
    )

    # Link allowances and modulation – rarely touched, so folded away.
    ui_impl_loss = N(
        start=0,
        stop=8,
        step=0.5,
        value=P("allowances", "implementation_loss_db", 2.0),
        label="Implementation loss (dB)",
    )
    ui_custom_ebn0 = N(
        start=-25,
        stop=30,
        step=0.1,
        value=P("allowances", "custom_ebn0_db", 13.8),
        label="Required Eb/N0 for the Custom modulation (dB)",
    )
    # Coding cost is carried by the library's code rate, so this is framing
    # only, and it does not apply to LoRa rows, whose packet airtime already
    # carries preamble, header and CRC.
    ui_overhead = S(
        start=0,
        stop=50,
        step=5,
        value=P("allowances", "framing_overhead_pct", 20),
        show_value=True,
        label="Framing overhead, Eb/N0 modes (%)",
    )
    ui_duty = S(
        start=10,
        stop=100,
        step=5,
        value=P("allowances", "downlink_share_pct", P("radio", "downlink_share_pct", 80)),
        show_value=True,
        label="Downlink share of a half-duplex pass (%)",
    )
    ui_pol_case = mo.ui.dropdown(
        options=["worst case", "average"],
        value=P("allowances", "polarization_case", "worst case"),
        label="Polarization ellipse alignment",
    )
    ui_excess_loss = N(
        start=0,
        stop=30,
        step=0.1,
        value=P("allowances", "excess_loss_db", 0.0),
        label="Rain and other excess loss (dB)",
    )
    ui_frame_bytes = N(
        start=8,
        stop=65536,
        step=1,
        value=P("allowances", "frame_bytes", 448),
        label="Frame length on air, Eb/N0 modes (bytes)",
    )
    ui_fer_pct = N(
        start=0.01,
        stop=50,
        step=0.01,
        value=P("allowances", "target_fer_pct", 1.0),
        label="Target frame error rate (%)",
    )
    ui_lora_payload = N(
        start=1,
        stop=255,
        step=1,
        value=P("allowances", "lora_payload_bytes", 32),
        label="LoRa payload per packet (bytes)",
    )
    ui_lora_preamble = N(
        start=6,
        stop=65535,
        step=1,
        value=P("allowances", "lora_preamble_symbols", 8),
        label="LoRa programmed preamble (symbols)",
    )
    ui_gs_gain = N(
        start=-5,
        stop=45,
        step=0.5,
        value=P("ground_station", "custom_gain_dbi", 13.5),
        label="Custom antenna gain (dBi)",
    )
    ui_gs_hpbw = N(
        start=1,
        stop=180,
        step=0.5,
        value=P("ground_station", "custom_hpbw_deg", 36.0),
        label="Custom antenna beamwidth (deg)",
    )
    ui_gs_circular = mo.ui.switch(
        value=P("ground_station", "custom_circular", True), label="Custom antenna is circular"
    )

    # Map. The optical payload keeps the same three keys under [map]; profiles
    # from before its 0.7.0 kept them under [target].
    ui_tiles = mo.ui.switch(value=P("map", "tiles", P("target", "map_tiles", True)), label="Map tiles from CARTO")
    ui_map_zoom = S(
        start=2,
        stop=9,
        step=1,
        value=P("map", "zoom", P("target", "map_zoom", 4)),
        show_value=True,
        label="Map zoom (tile level)",
    )
    # CARTO basemaps need a key since August 2026; a free one comes from
    # carto.com/basemaps/apikey. The shipped key is BAC's; it is visible to
    # anyone running the notebook, which CARTO expects for browser use.
    ui_tile_key = mo.ui.text(
        value=P("map", "key", P("target", "map_key", "cb1_3hdr_1_de5c1c882378bcd2934e6ba2")),
        label="CARTO basemap key (free)",
    )

    # Layout. Off, everything sits in one panel at the top; on, the knobs move to
    # a sidebar so a chart and the control that changes it are in view together.
    ui_sidebar = mo.ui.switch(value=False, label="Controls in a sidebar")

    # Modes. The first row marked Featured drives the headline numbers and the
    # line-item budget; Downlink and Uplink say which directions to evaluate.
    # Bandwidth is per row so LoRa modes at different bandwidths, and
    # bandwidth-referenced modes such as CW, can share one table.
    _default_modes = [
        {
            "Mode": "50k GFSK",
            "Modulation": "GFSK h=1, non-coherent",
            "Bit rate (bps)": 50000,
            "Bandwidth (Hz)": None,
            "Spacecraft TX (dBm)": 32.0,
            "Downlink": True,
            "Uplink": True,
            "Featured": True,
        },
        {
            "Mode": "CW beacon",
            "Modulation": "CW, detector spec",
            "Bit rate (bps)": 0,
            "Bandwidth (Hz)": 100,
            "Spacecraft TX (dBm)": 32.0,
            "Downlink": True,
            "Uplink": False,
            "Featured": False,
        },
        {
            "Mode": "LoRa SF7",
            "Modulation": "LoRa SF7",
            "Bit rate (bps)": 0,
            "Bandwidth (Hz)": 125000,
            "Spacecraft TX (dBm)": 22.0,
            "Downlink": True,
            "Uplink": True,
            "Featured": False,
        },
        {
            "Mode": "LoRa SF12",
            "Modulation": "LoRa SF12",
            "Bit rate (bps)": 0,
            "Bandwidth (Hz)": 125000,
            "Spacecraft TX (dBm)": 22.0,
            "Downlink": True,
            "Uplink": True,
            "Featured": False,
        },
    ]
    _cols = list(MODE_KEYS)
    if profile_modes:
        _rows_in = [
            {_c: _m.get(_k, MODE_BLANK[_c]) for _c, _k in MODE_KEYS.items()}
            for _m in profile_modes
            if isinstance(_m, dict)
        ] or _default_modes
    else:
        _rows_in = _default_modes
    ui_modes = mo.ui.data_editor(pd.DataFrame(_rows_in, columns=_cols), label="")

    _threshold_is = {
        "fsk": "Eb/N0",
        "lora": "SNR in the row's bandwidth",
        "snr": "SNR in the reference bandwidth",
    }
    _library = pd.DataFrame(
        [
            {
                "Modulation": _k,
                "Threshold is": _threshold_is[_v[0]],
                "Value (dB)": "set below" if _v[1] is None else _v[1],
                "Code rate": round(_v[2], 3),
                "Reference bandwidth (Hz)": _v[3],
                "Status": "! provisional"
                if _k in PROVISIONAL
                else ("your figure" if _v[1] is None else "King's table"),
                "Note": LIBRARY_NOTES.get(_k, ""),
            }
            for _k, _v in MODULATIONS.items()
        ]
    )

    mode_block = mo.vstack(
        [
            mo.md(
                "One row per mode, each with its own name. **Modulation** is a name from the "
                "library below. **Bit rate** is the channel rate – required for Eb/N0 modes, "
                "derived for LoRa (whose volume uses the packet airtime), unused for CW. "
                "**Bandwidth** is required for LoRa and optional for CW, where it overrides the "
                "library's 100 Hz. **Spacecraft TX** is the downlink power; the uplink uses the "
                "ground transmitter. The first **Featured** row drives the headline numbers and "
                "the breakdown. Rows missing a required value, holding a value that is not a "
                "finite number, or repeating an earlier row's name are skipped and reported."
            ),
            ui_modes,
            mo.accordion({"Modulation Library": mo.ui.table(_library, selection=None, show_column_summaries=False)}),
        ]
    )
    return (
        mode_block,
        ui_altitude,
        ui_custom_ebn0,
        ui_duplex,
        ui_duty,
        ui_excess_loss,
        ui_fer_pct,
        ui_frame_bytes,
        ui_freq_down,
        ui_freq_up,
        ui_gs_antenna,
        ui_gs_ar,
        ui_gs_circular,
        ui_gs_feed_loss,
        ui_gs_gain,
        ui_gs_hpbw,
        ui_gs_nf,
        ui_gs_tant,
        ui_gs_tx_w,
        ui_impl_loss,
        ui_inclination,
        ui_lat,
        ui_lon,
        ui_lora_payload,
        ui_lora_preamble,
        ui_map_zoom,
        ui_min_el,
        ui_modes,
        ui_overhead,
        ui_pol_case,
        ui_role,
        ui_rotator,
        ui_sat_ar,
        ui_sat_gain,
        ui_sat_loss,
        ui_sat_nf,
        ui_sat_point_loss,
        ui_sat_sens,
        ui_sat_sens_rate,
        ui_sidebar,
        ui_sim_days,
        ui_station,
        ui_target_margin,
        ui_tile_key,
        ui_tiles,
        ui_track_err,
    )


@app.cell
def _(
    half_duplex,
    mo,
    ui_altitude,
    ui_custom_ebn0,
    ui_duplex,
    ui_duty,
    ui_excess_loss,
    ui_fer_pct,
    ui_frame_bytes,
    ui_freq_down,
    ui_freq_up,
    ui_gs_antenna,
    ui_gs_ar,
    ui_gs_circular,
    ui_gs_feed_loss,
    ui_gs_gain,
    ui_gs_hpbw,
    ui_gs_nf,
    ui_gs_tant,
    ui_gs_tx_w,
    ui_impl_loss,
    ui_inclination,
    ui_lat,
    ui_lon,
    ui_lora_payload,
    ui_lora_preamble,
    ui_map_zoom,
    ui_min_el,
    ui_overhead,
    ui_pol_case,
    ui_role,
    ui_rotator,
    ui_sat_ar,
    ui_sat_gain,
    ui_sat_loss,
    ui_sat_nf,
    ui_sat_point_loss,
    ui_sat_sens,
    ui_sat_sens_rate,
    ui_sim_days,
    ui_station,
    ui_target_margin,
    ui_tile_key,
    ui_tiles,
    ui_track_err,
):
    # The panel in pieces, so the render cells below can lay the same elements
    # out two ways. The scalar inputs are the knobs you turn while watching a
    # chart, so those are what the sidebar takes; the mode table is a setup step
    # and stays in the flow, where eight editable columns have room. Two
    # columns, as in the siblings: what the mission is on the left, what the
    # spacecraft does on the right. Its own cell, apart from the elements,
    # because the duplex note under the dropdown reads that dropdown and a cell
    # cannot read a control it defines.
    _duplex_note = (
        "Half duplex: the downlink share under Orbit and Targets sets the split of each pass "
        "and the uplink takes the rest."
        if half_duplex
        else "Full duplex: each direction gets the whole pass and the downlink share is ignored. "
        "That is a statement about the hardware at both ends, not about the frequencies."
    )
    _left = [
        mo.md("**Orbit and Targets**"),
        ui_altitude,
        ui_inclination,
        ui_min_el,
        ui_target_margin,
        ui_sim_days,
        ui_freq_down,
        ui_freq_up,
        ui_duty,
        ui_role,
        mo.md("The role names the slot the Optical Payload tool puts this link's usable volume in."),
        mo.md("**Ground Station**"),
        ui_station,
        mo.accordion({"Custom station": mo.vstack([ui_lat, ui_lon])}),
        ui_gs_antenna,
        mo.accordion({"Custom antenna": mo.vstack([ui_gs_gain, ui_gs_hpbw, ui_gs_circular])}),
        ui_gs_ar,
        ui_rotator,
        ui_track_err,
        ui_gs_feed_loss,
        ui_gs_nf,
        ui_gs_tant,
        ui_gs_tx_w,
        mo.md("**Map**"),
        ui_tiles,
        ui_map_zoom,
        ui_tile_key,
    ]
    _right = [
        mo.md("**Spacecraft**"),
        ui_sat_gain,
        ui_sat_ar,
        ui_sat_loss,
        ui_sat_point_loss,
        ui_sat_nf,
        ui_sat_sens,
        ui_sat_sens_rate,
        ui_duplex,
        mo.md(_duplex_note),
        mo.md("**Link Allowances**"),
        ui_impl_loss,
        ui_custom_ebn0,
        ui_overhead,
        ui_excess_loss,
        ui_pol_case,
        mo.accordion(
            {
                "Frame errors and LoRa packets": mo.vstack(
                    [
                        mo.md(
                            "Frame length and target error rate feed the FER view of the ideal FSK curve; the LoRa payload and preamble set the packet airtime that LoRa volumes use."
                        ),
                        ui_frame_bytes,
                        ui_fer_pct,
                        ui_lora_payload,
                        ui_lora_preamble,
                    ]
                )
            }
        ),
    ]
    knobs_wide = mo.hstack(
        [mo.vstack(_left, gap=0.5), mo.vstack(_right, gap=0.5)], justify="start", gap=2, wrap=True, widths="equal"
    )
    knobs_tall = mo.vstack(_left + _right, gap=0.5)
    return knobs_tall, knobs_wide


@app.cell
def _(knobs_tall, mo, ui_sidebar):
    # mo.sidebar has to be the last expression of its own cell, so the sidebar
    # and the in-flow panel below cannot come from the same cell.
    mo.sidebar([mo.md("### Control Panel"), knobs_tall], width="360px") if ui_sidebar.value else None
    return


@app.cell
def _(
    half_duplex,
    knobs_wide,
    mo,
    mode_block,
    profile_block,
    ui_freq_down,
    ui_freq_up,
    ui_sidebar,
):
    # The switch renders once, here, so it is reachable whether or not the
    # sidebar is open: a collapsed sidebar holding its own toggle would trap you.
    _band = (
        [
            mo.callout(
                mo.md(
                    "Above 10 GHz rain sets availability, and this tool only takes it as the "
                    "excess-loss input under Link Allowances. Look up the rain attenuation for "
                    "your site and availability (ITU-R P.618 and P.838) and enter it."
                ),
                kind="warn",
                title="Rain Is Not Computed at This Frequency",
            )
        ]
        if max(ui_freq_down.value, ui_freq_up.value) > 10000
        else []
    )
    if not half_duplex and ui_freq_down.value == ui_freq_up.value:
        _band.append(
            mo.callout(
                mo.md(
                    "Full duplex on one frequency needs a duplexer or two antennas with enough "
                    "isolation, which a CubeSat rarely has. Check the hardware, or set half duplex."
                ),
                kind="warn",
                title="Full Duplex on a Single Frequency",
            )
        )
    mo.vstack(
        [
            mo.md("## Control Panel"),
            profile_block,
            ui_sidebar,
            mo.md("The knobs are in the sidebar. Turn this off to bring them back here.")
            if ui_sidebar.value
            else knobs_wide,
            *_band,
            mo.md("### Modes"),
            mode_block,
        ]
    )
    return


@app.cell
def _(
    GS_ANTENNAS,
    IDEAL_NCFSK,
    MODULATIONS,
    STATIONS,
    lora_bitrate_bps,
    lora_packet_s,
    ncfsk_ebn0_for_fer_db,
    ncfsk_fer_at_ebn0,
    pd,
    pointing_loss_db,
    polarization_loss_db,
    ui_custom_ebn0,
    ui_duplex,
    ui_fer_pct,
    ui_frame_bytes,
    ui_gs_antenna,
    ui_gs_ar,
    ui_gs_circular,
    ui_gs_gain,
    ui_gs_hpbw,
    ui_lat,
    ui_lon,
    ui_lora_payload,
    ui_lora_preamble,
    ui_modes,
    ui_pol_case,
    ui_rotator,
    ui_sat_ar,
    ui_station,
    ui_track_err,
):
    # Resolve the presets and the mode table into the numbers the model uses.

    # Duplex is the hardware setting, not a frequency test: half means one
    # radio and one antenna serve both directions and the pass is shared;
    # full means separate chains and each direction has the whole pass.
    half_duplex = ui_duplex.value != "full"

    _st = STATIONS[ui_station.value]
    station_name = "Custom" if _st is None else ui_station.value.split(",")[0]
    lat_deg = ui_lat.value if _st is None else _st[0]
    lon_deg = ui_lon.value if _st is None else _st[1]

    _ant = GS_ANTENNAS[ui_gs_antenna.value]
    gs_gain_dbi = ui_gs_gain.value if _ant[0] is None else _ant[0]
    gs_hpbw_deg = ui_gs_hpbw.value if _ant[1] is None else _ant[1]
    gs_circular = ui_gs_circular.value if _ant[2] is None else _ant[2]

    # A linear ground antenna is an axial ratio of 40 dB for this purpose.
    gs_ar_db = ui_gs_ar.value if gs_circular else 40.0
    pol_loss_db = float(polarization_loss_db(gs_ar_db, ui_sat_ar.value, ui_pol_case.value == "worst case"))
    gs_point_loss_db = pointing_loss_db(ui_track_err.value, gs_hpbw_deg) if ui_rotator.value else 0.0

    def _num(v):
        # A finite number or NaN; an empty cell, text, or infinity is NaN.
        try:
            v = float(v)
        except (TypeError, ValueError):
            return float("nan")
        return v if v == v and v not in (float("inf"), float("-inf")) else float("nan")

    def _flag(v):
        # A checkbox column may hold a bool, a string, or nothing at all on a
        # freshly added row; nothing means off.
        if isinstance(v, str):
            return v.strip().lower() in ("true", "yes", "1")
        try:
            return bool(v) if v == v else False
        except (TypeError, ValueError):
            return False

    # Per kind: fsk rows need a channel bit rate, lora rows a bandwidth, snr rows
    # neither (the library's reference bandwidth applies unless the row sets one).
    # A missing or unreadable value drops the row loudly rather than inventing
    # one, and a name that repeats an earlier row's is dropped too, because
    # every curve, table and card looks a mode up by its name.
    _rows = []
    _seen = set()
    unknown_modulations = []
    dropped_modes = []
    invalid_modes = []
    duplicate_modes = []
    for _, _r in ui_modes.value.iterrows():
        _name = str(_r["Mode"]).strip()
        _mod = str(_r["Modulation"]).strip()
        if not _name or _name.lower() == "nan":
            continue
        if _name in _seen:
            duplicate_modes.append(_name)
            continue
        if _mod not in MODULATIONS:
            unknown_modulations.append(_mod)
            continue
        _kind, _req, _code_rate, _ref_bw = MODULATIONS[_mod]
        if _req is None:
            _req = ui_custom_ebn0.value
        _tx = _num(_r["Spacecraft TX (dBm)"])
        if _tx != _tx:
            invalid_modes.append(f"{_name} (spacecraft TX)")
            continue
        # Frame-error view, only where the library figure sits on a known curve.
        _n_bits = 8 * ui_frame_bytes.value
        if _mod in IDEAL_NCFSK:
            _ideal_req = float(ncfsk_ebn0_for_fer_db(ui_fer_pct.value / 100.0, _n_bits))
            _fer_at_req = 100 * float(ncfsk_fer_at_ebn0(_req, _n_bits))
        else:
            _ideal_req = _fer_at_req = float("nan")
        _bw = _num(_r["Bandwidth (Hz)"])
        _rate = _num(_r["Bit rate (bps)"])
        _overhead_applies = True
        _airtime_s = float("nan")
        if _kind == "lora":
            if not _bw > 0:
                dropped_modes.append(_name)
                continue
            _sf = int(_mod.rsplit("SF", 1)[1])
            _rate = lora_bitrate_bps(_sf, _bw)
            # The nominal rate says what a symbol carries; what a packet
            # delivers is the payload over its time on air, preamble, header,
            # CRC and symbol rounding included. That is the rate volumes use,
            # and the framing slider does not apply on top of it.
            _airtime_s = float(lora_packet_s(_sf, _bw, int(ui_lora_payload.value), int(ui_lora_preamble.value)))
            _info = 8.0 * int(ui_lora_payload.value) / _airtime_s
            _overhead_applies = False
        elif _kind == "snr":
            _sf = None
            _rate = float("nan")
            _info = float("nan")
            if not _bw > 0:
                _bw = float(_ref_bw)
        else:
            _sf = None
            _bw = float("nan")
            if not _rate > 0:
                dropped_modes.append(_name)
                continue
            _info = _rate * _code_rate
        _seen.add(_name)
        _rows.append(
            {
                "mode": _name,
                "modulation": _mod,
                "kind": _kind,
                "sf": _sf,
                "bitrate_bps": _rate,
                "code_rate": float(_code_rate),
                "info_rate_bps": _info,
                "packet_airtime_s": _airtime_s,
                "overhead_applies": _overhead_applies,
                "bandwidth_hz": _bw,
                "required_db": float(_req),
                "ideal_ebn0_for_fer_db": _ideal_req,
                "fer_at_threshold_pct": _fer_at_req,
                "tx_dbm": _tx,
                "downlink": _flag(_r["Downlink"]),
                "uplink": _flag(_r["Uplink"]),
                "featured": _flag(_r["Featured"]),
            }
        )
    # Columns are named even when no row survives, so downstream lookups on an
    # empty frame do not raise.
    modes = pd.DataFrame(
        _rows,
        columns=[
            "mode",
            "modulation",
            "kind",
            "sf",
            "bitrate_bps",
            "code_rate",
            "info_rate_bps",
            "packet_airtime_s",
            "overhead_applies",
            "bandwidth_hz",
            "required_db",
            "ideal_ebn0_for_fer_db",
            "fer_at_threshold_pct",
            "tx_dbm",
            "downlink",
            "uplink",
            "featured",
        ],
    )

    # The first Featured row drives every headline it can. Downlink headlines
    # fall back to the first downlink row; the uplink headline falls back to the
    # best uplink mode (decided where the volumes are known) when that row has
    # no uplink.
    _dn = modes[modes["downlink"]] if len(modes) else modes
    _feat = _dn[_dn["featured"]] if len(_dn) else _dn
    if len(_feat):
        featured_mode = str(_feat.iloc[0]["mode"])
    elif len(_dn):
        featured_mode = str(_dn.iloc[0]["mode"])
    else:
        featured_mode = ""
    _feat_any = modes[modes["featured"]] if len(modes) else modes
    featured_uplink_mode = (
        str(_feat_any.iloc[0]["mode"]) if len(_feat_any) and bool(_feat_any.iloc[0]["uplink"]) else ""
    )
    return (
        dropped_modes,
        duplicate_modes,
        featured_mode,
        featured_uplink_mode,
        gs_ar_db,
        gs_circular,
        gs_gain_dbi,
        gs_hpbw_deg,
        gs_point_loss_db,
        half_duplex,
        invalid_modes,
        lat_deg,
        lon_deg,
        modes,
        pol_loss_db,
        station_name,
        unknown_modulations,
    )


@app.cell
def _(
    MU_KM3_S2,
    OMEGA_EARTH,
    R_EARTH_KM,
    lat_deg,
    lon_deg,
    np,
    pd,
    ui_altitude,
    ui_inclination,
    ui_min_el,
    ui_sim_days,
):
    # Pass simulation – circular orbit propagated numerically over a rotating
    # spherical Earth, sampled every DT_S seconds. The number of passes in a
    # short window depends on where the orbit plane starts relative to the
    # station, so the run is repeated for N_PHASES equally spaced RAAN values
    # and every per-day figure is averaged over them.

    DT_S = 10.0
    N_PHASES = 8
    _a = R_EARTH_KM + ui_altitude.value
    _n = np.sqrt(MU_KM3_S2 / _a**3)
    _inc = np.radians(ui_inclination.value)

    _t = np.arange(0.0, ui_sim_days.value * 86400.0, DT_S)
    _u = _n * _t
    _xo, _yo = _a * np.cos(_u), _a * np.sin(_u)
    _theta = OMEGA_EARTH * _t

    _lat, _lon = np.radians(lat_deg), np.radians(lon_deg)
    _up = np.array(
        [
            np.cos(_lat) * np.cos(_lon),
            np.cos(_lat) * np.sin(_lon),
            np.sin(_lat),
        ]
    )
    _sta = R_EARTH_KM * _up

    _frames = []
    _next_id = 1
    track_day1 = None
    for _k in range(N_PHASES):
        _raan = 2 * np.pi * _k / N_PHASES
        _x = _xo * np.cos(_raan) - _yo * np.cos(_inc) * np.sin(_raan)
        _y = _xo * np.sin(_raan) + _yo * np.cos(_inc) * np.cos(_raan)
        _z = _yo * np.sin(_inc)
        _xe = _x * np.cos(_theta) + _y * np.sin(_theta)
        _ye = -_x * np.sin(_theta) + _y * np.cos(_theta)
        _rx, _ry, _rz = _xe - _sta[0], _ye - _sta[1], _z - _sta[2]
        _range = np.sqrt(_rx**2 + _ry**2 + _rz**2)
        _el = np.degrees(np.arcsin((_rx * _up[0] + _ry * _up[1] + _rz * _up[2]) / _range))
        _visible = _el >= ui_min_el.value
        _edges = np.diff(_visible.astype(int), prepend=0)
        _pass_id = np.cumsum(_edges == 1) * _visible
        _keep = _pass_id > 0
        _frames.append(
            pd.DataFrame(
                {
                    "phase": _k + 1,
                    "pass_id": _pass_id[_keep] + _next_id - 1,
                    "t_s": _t[_keep],
                    "elevation_deg": _el[_keep],
                    "range_km": _range[_keep],
                }
            )
        )
        _next_id += int(_pass_id.max())
        if _k == 0:
            # The first phase's first day, one point a minute, for the map:
            # sub-satellite point in the Earth-fixed frame, with the samples
            # in view flagged. Altair's default transformer caps at 5'000
            # rows, so the 10 s samples are thinned before charting.
            _every = max(int(60 / DT_S), 1)
            _day = _t < 86400.0
            _idx = np.arange(len(_t))[_day][::_every]
            track_day1 = pd.DataFrame(
                {
                    "t_s": _t[_idx],
                    "lat": np.degrees(np.arcsin(_z[_idx] / _a)),
                    "lon": (np.degrees(np.arctan2(_ye[_idx], _xe[_idx])) + 180) % 360 - 180,
                    "visible": _visible[_idx],
                    "elevation_deg": _el[_idx],
                }
            )

    samples = pd.concat(_frames, ignore_index=True)
    passes = (
        samples.groupby("pass_id")
        .agg(
            phase=("phase", "first"),
            start_s=("t_s", "min"),
            duration_min=("t_s", lambda s: (s.max() - s.min() + DT_S) / 60.0),
            max_elevation_deg=("elevation_deg", "max"),
        )
        .reset_index()
    )
    sim_days_total = ui_sim_days.value * N_PHASES
    orbital_period_min = 2 * np.pi / _n / 60.0

    # How far the station sees at the minimum elevation: the Earth-central
    # angle psi = arccos(R/(R+h) · cos e) − e, and a circle of that angular
    # radius around the station for the map.
    _e = np.radians(ui_min_el.value)
    vis_psi_rad = float(np.arccos(R_EARTH_KM / _a * np.cos(_e)) - _e)
    vis_radius_km = R_EARTH_KM * vis_psi_rad
    _az = np.radians(np.arange(0, 361, 3))
    _clat = np.arcsin(np.sin(_lat) * np.cos(vis_psi_rad) + np.cos(_lat) * np.sin(vis_psi_rad) * np.cos(_az))
    _clon = _lon + np.arctan2(
        np.sin(_az) * np.sin(vis_psi_rad) * np.cos(_lat), np.cos(vis_psi_rad) - np.sin(_lat) * np.sin(_clat)
    )
    vis_circle = pd.DataFrame(
        {"lat": np.degrees(_clat), "lon": (np.degrees(_clon) + 180) % 360 - 180, "order": range(len(_az))}
    )
    return (
        DT_S,
        N_PHASES,
        orbital_period_min,
        passes,
        samples,
        sim_days_total,
        track_day1,
        vis_circle,
        vis_radius_km,
    )


@app.cell
def _(
    atmospheric_loss_db,
    fspl_db,
    gs_gain_dbi,
    gs_point_loss_db,
    ionospheric_loss_db,
    noise_density_dbm_hz,
    np,
    pol_loss_db,
    ui_excess_loss,
    ui_freq_down,
    ui_freq_up,
    ui_gs_feed_loss,
    ui_gs_nf,
    ui_gs_tant,
    ui_gs_tx_w,
    ui_impl_loss,
    ui_sat_gain,
    ui_sat_loss,
    ui_sat_nf,
    ui_sat_point_loss,
):
    # Link budget primitives. Both directions share the path; the two ends swap
    # roles and each direction carries its own frequency.

    n0_gs_dbm_hz, t_sys_gs_k = noise_density_dbm_hz(ui_gs_tant.value, ui_gs_feed_loss.value, ui_gs_nf.value)
    # Spacecraft antenna: Earth fills about a third of its sky at 500 km, the
    # rest is cold; 290 K is the conservative end of that. The cable loss ahead
    # of the receiver plays the feeder's role.
    n0_sat_dbm_hz, t_sys_sat_k = noise_density_dbm_hz(290.0, ui_sat_loss.value, ui_sat_nf.value)
    gs_tx_dbm = 10 * np.log10(ui_gs_tx_w.value * 1000.0)
    iono_down_db = ionospheric_loss_db(ui_freq_down.value)
    iono_up_db = ionospheric_loss_db(ui_freq_up.value)

    def path_loss_db(el_deg, range_km, f_mhz, iono_db):
        return (
            fspl_db(range_km, f_mhz)
            + atmospheric_loss_db(el_deg, f_mhz)
            + iono_db
            + ui_excess_loss.value
            + pol_loss_db
            + gs_point_loss_db
            + ui_sat_point_loss.value
        )

    def downlink_prx_dbm(el_deg, range_km, tx_dbm):
        return (
            tx_dbm
            + ui_sat_gain.value
            - ui_sat_loss.value
            - path_loss_db(el_deg, range_km, ui_freq_down.value, iono_down_db)
            + gs_gain_dbi
            - ui_gs_feed_loss.value
        )

    def uplink_prx_dbm(el_deg, range_km):
        return (
            gs_tx_dbm
            + gs_gain_dbi
            - ui_gs_feed_loss.value
            - path_loss_db(el_deg, range_km, ui_freq_up.value, iono_up_db)
            + ui_sat_gain.value
            - ui_sat_loss.value
        )

    def margin_db(prx_dbm, n0_dbm_hz, mode):
        # mode is a row of `modes`. Eb/N0 modes reference the information rate;
        # bandwidth modes reference the row's bandwidth.
        cn0 = prx_dbm - n0_dbm_hz
        if mode["kind"] == "fsk":
            ratio = cn0 - 10 * np.log10(mode["info_rate_bps"])
        else:
            ratio = cn0 - 10 * np.log10(mode["bandwidth_hz"])
        return ratio - mode["required_db"] - ui_impl_loss.value

    return (
        downlink_prx_dbm,
        gs_tx_dbm,
        iono_down_db,
        iono_up_db,
        margin_db,
        n0_gs_dbm_hz,
        n0_sat_dbm_hz,
        t_sys_gs_k,
        t_sys_sat_k,
        uplink_prx_dbm,
    )


@app.cell
def _(
    downlink_prx_dbm,
    margin_db,
    modes,
    n0_gs_dbm_hz,
    n0_sat_dbm_hz,
    np,
    pd,
    slant_range_km,
    ui_altitude,
    uplink_prx_dbm,
):
    # Margin versus elevation, both directions, every mode that asks for it.

    _el = np.arange(0.0, 90.5, 1.0)
    _rng = slant_range_km(_el, ui_altitude.value)
    _prx_up = uplink_prx_dbm(_el, _rng)

    _frames = []
    for _, _m in modes.iterrows():
        if _m["downlink"]:
            _frames.append(
                pd.DataFrame(
                    {
                        "elevation_deg": _el,
                        "margin_db": margin_db(
                            downlink_prx_dbm(_el, _rng, _m["tx_dbm"]),
                            n0_gs_dbm_hz,
                            _m,
                        ),
                        "mode": _m["mode"],
                        "direction": "downlink",
                    }
                )
            )
        if _m["uplink"]:
            _frames.append(
                pd.DataFrame(
                    {
                        "elevation_deg": _el,
                        "margin_db": margin_db(_prx_up, n0_sat_dbm_hz, _m),
                        "mode": _m["mode"],
                        "direction": "uplink",
                    }
                )
            )
    margin_vs_el = (
        pd.concat(_frames, ignore_index=True)
        if _frames
        else pd.DataFrame(columns=["elevation_deg", "margin_db", "mode", "direction"])
    )
    uplink_prx_vs_el = pd.DataFrame({"elevation_deg": _el, "prx_dbm": _prx_up})
    return margin_vs_el, uplink_prx_vs_el


@app.cell
def _(
    DT_S,
    N_PHASES,
    downlink_prx_dbm,
    featured_uplink_mode,
    half_duplex,
    margin_db,
    margin_vs_el,
    modes,
    n0_gs_dbm_hz,
    n0_sat_dbm_hz,
    np,
    passes,
    pd,
    samples,
    sim_days_total,
    ui_duty,
    ui_min_el,
    ui_overhead,
    ui_sim_days,
    ui_target_margin,
    uplink_prx_dbm,
):
    # Bytes per pass: integrate the information rate (channel rate times code
    # rate for Eb/N0 modes, packet payload over airtime for LoRa) over every
    # sample of every pass where the margin meets the target, scaled by the
    # framing overhead where it applies and the share of the pass given to that
    # direction. Modes with no bit rate get a margin and no volume. The margin
    # columns come from the elevation sweep so the tables and the charts cannot
    # disagree.

    _frame = 1 - ui_overhead.value / 100.0
    _share_dn = ui_duty.value / 100.0 if half_duplex else 1.0
    _share_up = 1 - ui_duty.value / 100.0 if half_duplex else 1.0
    _el = samples["elevation_deg"].to_numpy()
    _rng = samples["range_km"].to_numpy()
    _prx_up = uplink_prx_dbm(_el, _rng)
    _n_passes = max(len(passes), 1)
    # Every simulated station-day, including the ones without a pass, so the
    # low-percentile day is a day and not a day-with-passes.
    _day_index = pd.MultiIndex.from_product(
        [range(1, N_PHASES + 1), range(int(ui_sim_days.value))], names=["phase", "day"]
    )
    _day_keys = [samples["phase"].to_numpy(), (samples["t_s"] // 86400).astype(int).to_numpy()]

    def _sweep_at(mode, direction, el):
        _s = margin_vs_el[(margin_vs_el["mode"] == mode) & (margin_vs_el["direction"] == direction)]
        if not len(_s):
            return float("nan")
        return float(np.interp(el, _s["elevation_deg"], _s["margin_db"]))

    _rows = []
    for _, _m in modes.iterrows():
        _has_rate = _m["info_rate_bps"] > 0
        _eta_dn = (_frame if _m["overhead_applies"] else 1.0) * _share_dn
        _eta_up = (_frame if _m["overhead_applies"] else 1.0) * _share_up
        _row = {
            "mode": _m["mode"],
            "modulation": _m["modulation"],
            "bitrate_bps": round(float(_m["bitrate_bps"])) if _has_rate else np.nan,
            "info_rate_bps": round(float(_m["info_rate_bps"])) if _has_rate else np.nan,
            "packet_airtime_ms": float(_m["packet_airtime_s"]) * 1000.0,
            "bandwidth_hz": float(_m["bandwidth_hz"]),
            "required_db": float(_m["required_db"]),
            "ideal_ebn0_for_fer_db": float(_m["ideal_ebn0_for_fer_db"]),
            "fer_at_threshold_pct": float(_m["fer_at_threshold_pct"]),
            "tx_dbm": float(_m["tx_dbm"]),
            "margin_at_min_el_db": np.nan,
            "margin_at_zenith_db": np.nan,
            "kB_per_avg_pass": np.nan,
            "kB_per_day": np.nan,
            "kB_per_avg_pass_0db": np.nan,
            "kB_per_day_if_only_closing": np.nan,
            "kB_per_day_p10": np.nan,
            "uplink_margin_at_min_el_db": np.nan,
            "uplink_kB_per_day": np.nan,
        }
        if _m["downlink"]:
            _row["margin_at_min_el_db"] = round(_sweep_at(_m["mode"], "downlink", ui_min_el.value), 1)
            _row["margin_at_zenith_db"] = round(_sweep_at(_m["mode"], "downlink", 90.0), 1)
            if _has_rate:
                _mg = margin_db(downlink_prx_dbm(_el, _rng, _m["tx_dbm"]), n0_gs_dbm_hz, _m)
                _bps = _m["info_rate_bps"] * DT_S / 8.0 * _eta_dn
                _at_target = (_mg >= ui_target_margin.value) * _bps
                _row["kB_per_avg_pass"] = float(_at_target.sum()) / _n_passes / 1000.0
                _row["kB_per_day"] = float(_at_target.sum()) / sim_days_total / 1000.0
                _row["kB_per_avg_pass_0db"] = float(((_mg >= 0.0) * _bps).sum()) / _n_passes / 1000.0
                _row["kB_per_day_if_only_closing"] = float(((_mg >= 0.0) * _bps).sum()) / sim_days_total / 1000.0
                # Daily totals over every simulated station-day, at the
                # target margin, with the days that saw no pass counted as 0.
                _day = pd.Series(_at_target).groupby(_day_keys).sum().reindex(_day_index, fill_value=0.0)
                _row["kB_per_day_p10"] = float(_day.quantile(0.10)) / 1000.0
        if _m["uplink"]:
            _row["uplink_margin_at_min_el_db"] = round(_sweep_at(_m["mode"], "uplink", ui_min_el.value), 1)
            if _has_rate:
                _mg = margin_db(_prx_up, n0_sat_dbm_hz, _m)
                _bps = _m["info_rate_bps"] * DT_S / 8.0 * _eta_up
                _row["uplink_kB_per_day"] = (
                    float(((_mg >= ui_target_margin.value) * _bps).sum()) / sim_days_total / 1000.0
                )
        _rows.append(_row)
    mode_summary = pd.DataFrame(
        _rows,
        columns=[
            "mode",
            "modulation",
            "bitrate_bps",
            "info_rate_bps",
            "packet_airtime_ms",
            "bandwidth_hz",
            "required_db",
            "ideal_ebn0_for_fer_db",
            "fer_at_threshold_pct",
            "tx_dbm",
            "margin_at_min_el_db",
            "margin_at_zenith_db",
            "kB_per_avg_pass",
            "kB_per_day",
            "kB_per_avg_pass_0db",
            "kB_per_day_if_only_closing",
            "kB_per_day_p10",
            "uplink_margin_at_min_el_db",
            "uplink_kB_per_day",
        ],
    )

    # One rule for which uplink mode the headline card, the reference-level line and
    # the export report: the Featured row when it has an uplink, otherwise the
    # uplink mode carrying the most data. The caption says which it was.
    _up = mode_summary.dropna(subset=["uplink_margin_at_min_el_db"]) if len(mode_summary) else mode_summary
    _fu = _up[_up["mode"] == featured_uplink_mode] if len(_up) else _up
    if len(_fu):
        uplink_headline = (_fu.iloc[0], "the featured mode")
    elif len(_up):
        _any_featured = bool(modes["featured"].any()) if len(modes) else False
        uplink_headline = (
            _up.sort_values("uplink_kB_per_day", ascending=False).iloc[0],
            "the best of the uplink modes"
            + ("; the featured row has no uplink" if _any_featured else "; no row is featured"),
        )
    else:
        uplink_headline = (None, "")

    passes_per_day = len(passes) / sim_days_total
    mean_pass_min = float(passes["duration_min"].mean()) if len(passes) else 0.0
    contact_min_per_day = float(passes["duration_min"].sum()) / sim_days_total
    # Longest wait between the end of one pass and the start of the next, within
    # any one orbit phase. A daily mean says nothing about this.
    _gaps = []
    for _, _g in passes.sort_values(["phase", "start_s"]).groupby("phase"):
        _end = (_g["start_s"] + _g["duration_min"] * 60.0).to_numpy()
        _gaps.extend((_g["start_s"].to_numpy()[1:] - _end[:-1]) / 3600.0)
    longest_gap_h = float(max(_gaps)) if _gaps else float("nan")
    return (
        contact_min_per_day,
        longest_gap_h,
        mean_pass_min,
        mode_summary,
        passes_per_day,
        uplink_headline,
    )


@app.cell
def _(alt, mo, modes):
    # Chart conventions from the Interface Design Guide §8: series in the nebula
    # order, shape markers so color is never the only channel, dashed for
    # targets, dotted for reference lines. On a dark surface the two dark series
    # use lighter derived tints to keep 3:1 graphical contrast. Beyond five
    # series the palette repeats in progressively lighter tints.

    IS_DARK = mo.app_meta().theme == "dark"
    MUTED = "#A3A29C" if IS_DARK else "#6C6B67"
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

    SERIES_ORDER = [str(_m) for _m in modes["mode"]] if len(modes) else []

    def series_lines(data, order, y_field, y_title, y_tip):
        _cols, _shp = series_style(order)
        _color = alt.Color(
            "mode:N",
            title="Mode",
            sort=order,
            scale=alt.Scale(domain=order, range=_cols),
        )
        _tip = [
            alt.Tooltip("mode:N", title="Mode"),
            alt.Tooltip("elevation_deg:Q", title="Elevation (deg)"),
            alt.Tooltip(f"{y_field}:Q", title=y_tip, format=".1f"),
        ]
        _lines = (
            alt.Chart(data)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X(
                    "elevation_deg:Q",
                    title="Elevation (deg)",
                    scale=alt.Scale(domain=[0, 90]),
                ),
                y=alt.Y(f"{y_field}:Q", title=y_title),
                color=_color,
                tooltip=_tip,
            )
        )
        _marks = (
            alt.Chart(data[data["elevation_deg"] % 10 == 0])
            .mark_point(filled=True, size=70)
            .encode(
                x="elevation_deg:Q",
                y=f"{y_field}:Q",
                color=_color,
                shape=alt.Shape(
                    "mode:N",
                    title="Mode",
                    sort=order,
                    scale=alt.Scale(domain=order, range=_shp),
                ),
                tooltip=_tip,
            )
        )
        return _lines + _marks

    def rule_y(value, dashed):
        return (
            alt.Chart(alt.Data(values=[{"y": value}]))
            .mark_rule(strokeDash=[6, 4] if dashed else [2, 2], color=MUTED)
            .encode(y="y:Q")
        )

    def rule_x(value):
        return alt.Chart(alt.Data(values=[{"x": value}])).mark_rule(strokeDash=[2, 2], color=MUTED).encode(x="x:Q")

    def rule_label(value, text):
        return (
            alt.Chart(alt.Data(values=[{"x": 90, "y": value, "label": text}]))
            .mark_text(
                align="right",
                dx=-2,
                dy=-7,
                color=MUTED,
                font=FONT,
                fontSize=11,
            )
            .encode(x="x:Q", y="y:Q", text="label:N")
        )

    def style_chart(chart):
        return (
            chart.configure(font=FONT, background="transparent")
            .configure_axis(
                grid=False,
                labelColor=TEXT,
                titleColor=TEXT,
                domainColor=MUTED,
                tickColor=MUTED,
            )
            .configure_legend(labelColor=TEXT, titleColor=TEXT)
            .configure_title(color=TEXT, anchor="start", fontWeight="normal")
            .configure_view(strokeWidth=0)
        )

    def chart_title(text, *notes):
        """A short title with the reading notes as subtitle lines – Altair never wraps a title, so a long one is clipped."""
        return alt.Title(text, subtitle=list(notes), subtitleColor=MUTED, subtitleFontSize=11) if notes else text

    return (
        IS_DARK,
        MUTED,
        PALETTE,
        SERIES_ORDER,
        TEXT,
        chart_title,
        rule_label,
        rule_x,
        rule_y,
        series_lines,
        style_chart,
    )


@app.cell
def _(
    P,
    PH,
    contact_min_per_day,
    featured_mode,
    fmt_int,
    fmt_num,
    mean_pass_min,
    mo,
    mode_summary,
    modes,
    passes_per_day,
    station_name,
    ui_min_el,
    uplink_headline,
):
    def _stat(value, label, caption):
        return mo.stat(value=value, label=label, caption=caption, bordered=True)

    _rows = mode_summary[mode_summary["mode"] == featured_mode]
    _feat = _rows.iloc[0] if len(_rows) else None
    _up_row, _up_caption = uplink_headline
    _el = f"{ui_min_el.value:g}°"

    # Which mode each card describes is said once, above the row. A caption long
    # enough to name a mode makes its card wider than the rest: mo.stat cards get
    # flex: 1 but their content still sets the minimum width, so the captions
    # here stay short and box-specific.
    _any_featured = bool(modes["featured"].any()) if len(modes) else False
    _up_name = None if _up_row is None else str(_up_row["mode"])
    if _feat is None and _up_row is None:
        _which = "No modes to report. Mark at least one row in the mode table."
    elif _feat is None:
        _which = f"No downlink mode is selected. Uplink is {_up_name}, {_up_caption}."
    elif _up_name == featured_mode:
        _which = (
            f"Both directions are {featured_mode}, the featured mode."
            if _any_featured
            else f"Both directions are {featured_mode}. No row is featured, so this is the "
            "first downlink row and the uplink mode carrying the most data."
        )
    else:
        _dn_why = "the featured mode" if _any_featured else "the first downlink row, since no row is featured"
        _which = f"Downlink is {featured_mode}, {_dn_why}."
        _which += f" Uplink is {_up_name}, {_up_caption}." if _up_name else " No mode has an uplink."

    # Demand against capacity, when a sibling's profile carried its results:
    # the optical payload's frames against this link's volume, the power
    # budget's affordable pass minutes against the minutes the station offers.
    _loops = []
    if (
        _feat is not None
        and PH("results.optical_payload", "compressed_frame_kb")
        and PH("results.optical_payload", "frames_per_day")
    ):
        _demand = float(P("results.optical_payload", "compressed_frame_kb", 0.0)) * float(
            P("results.optical_payload", "frames_per_day", 0.0)
        )
        _cap = float(_feat["kB_per_day"])
        _pct = _cap / _demand * 100 if _demand > 0 else float("inf")
        _text = (
            f"The optical payload profile plans {fmt_int(_demand)} kB/day of compressed frames; "
            f"{featured_mode} carries {fmt_int(_cap)} kB/day at the target margin, "
            + ("all of it and more." if _pct == float("inf") else f"{_pct:.0f}% of it.")
        )
        _loops.append(
            mo.callout(mo.md(_text), kind="warn" if _pct < 100 else "info", title="Payload Demand Against This Link")
        )
    if PH("results.power_budget", "sustainable_pass_min_per_day"):
        _afford = float(P("results.power_budget", "sustainable_pass_min_per_day", 0.0))
        _text = (
            f"The power budget profile affords {fmt_num(_afford, 0)} pass minutes a day; "
            f"this station offers {fmt_num(contact_min_per_day, 1)}."
            + (" Not every pass can transmit." if _afford < contact_min_per_day else "")
        )
        _loops.append(
            mo.callout(
                mo.md(_text),
                kind="warn" if _afford < contact_min_per_day else "info",
                title="Pass Minutes Against the Power Budget",
            )
        )

    mo.vstack(
        [
            mo.md(f"## Headline Numbers · {station_name}"),
            mo.md(_which),
            mo.hstack(
                [
                    _stat(
                        f"{passes_per_day:.1f}",
                        "Passes per Day",
                        f"above {_el}",
                    ),
                    _stat(
                        f"{mean_pass_min:.1f} min",
                        "Mean Pass",
                        f"{contact_min_per_day:.0f} min contact per day",
                    ),
                    _stat(
                        "–" if _feat is None else f"{_feat['margin_at_min_el_db']:.1f} dB",
                        f"Margin at {_el}",
                        "–" if _feat is None else f"{_feat['margin_at_zenith_db']:.1f} dB at zenith",
                    ),
                ],
                widths="equal",
            ),
            mo.hstack(
                [
                    _stat(
                        "–" if _feat is None else f"{fmt_int(_feat['kB_per_day'])} kB",
                        "Downlink per Day",
                        "–" if _feat is None else f"more than {fmt_int(_feat['kB_per_day_p10'])} kB on 90% of days",
                    ),
                    _stat(
                        "–" if _feat is None else f"{fmt_int(_feat['kB_per_day_if_only_closing'])} kB",
                        "At 0 dB Margin",
                        "–"
                        if _feat is None
                        else f"{fmt_int(_feat['kB_per_avg_pass_0db'])} kB per pass; {fmt_int(_feat['kB_per_avg_pass'])} at target",
                    ),
                    _stat(
                        "–"
                        if _up_row is None or _up_row["uplink_kB_per_day"] != _up_row["uplink_kB_per_day"]
                        else f"{fmt_int(_up_row['uplink_kB_per_day'])} kB",
                        "Uplink per Day",
                        "no uplink mode"
                        if _up_row is None
                        else f"{_up_row['uplink_margin_at_min_el_db']:.1f} dB at {_el}",
                    ),
                ],
                widths="equal",
            ),
            *_loops,
        ]
    )
    return


@app.cell
def _(
    PROVISIONAL,
    dropped_modes,
    duplicate_modes,
    featured_mode,
    gs_gain_dbi,
    invalid_modes,
    mo,
    mode_summary,
    profile_warnings,
    ui_freq_down,
    ui_freq_up,
    ui_min_el,
    ui_rotator,
    ui_target_margin,
    unknown_modulations,
):
    _rows = mode_summary[mode_summary["mode"] == featured_mode]
    _feat = _rows.iloc[0] if len(_rows) else None
    featured_provisional = _feat is not None and str(_feat["modulation"]) in PROVISIONAL
    # Every enabled direction of every row is checked against the target,
    # not only the downlinks.
    _dn = mode_summary.dropna(subset=["margin_at_min_el_db"])
    _up = mode_summary.dropna(subset=["uplink_margin_at_min_el_db"])
    _short = _dn[_dn["margin_at_min_el_db"] < ui_target_margin.value]["mode"].tolist()
    _short += [
        f"{_m} (uplink)" for _m in _up[_up["uplink_margin_at_min_el_db"] < ui_target_margin.value]["mode"].tolist()
    ]
    _target = f"{ui_target_margin.value:g} dB target at {ui_min_el.value}°"

    if _feat is None:
        _out = mo.callout(
            mo.md("Mark at least one row in the mode table as Downlink."),
            kind="warn",
            title="No Downlink Mode",
        )
    elif _feat["margin_at_min_el_db"] < 0:
        _out = mo.callout(
            mo.md(
                "The link opens later in the pass. The usable data figure above already "
                "accounts for that, but a beacon at this rate is missed near the horizon."
            ),
            kind="warn",
            title=f"{featured_mode} Does Not Close at {ui_min_el.value}°",
        )
    elif _short:
        _out = mo.callout(
            mo.md(
                "Below target at the minimum elevation: **"
                + ", ".join(_short)
                + "**. Downlinks are listed by name, uplinks with the direction."
            ),
            kind="warn",
            title=f"Directions in the Table Below the {_target}",
        )
    else:
        _out = mo.callout(
            mo.md(f"Every enabled direction of every mode meets the {_target}."),
            kind="success",
            title="All Modes at Target",
        )

    if featured_provisional:
        _out = mo.vstack(
            [
                _out,
                mo.callout(
                    mo.md(
                        f"{_feat['required_db']:g} dB is a theoretical figure for {featured_mode}. "
                        "The margin and volume are to be confirmed."
                    ),
                    kind="warn",
                    title="Provisional Threshold",
                ),
            ]
        )

    _notes = []
    if max(ui_freq_down.value, ui_freq_up.value) > 10000:
        _notes.append(
            "Above 10 GHz rain sets availability and is not computed; enter it as excess loss under Link Allowances."
        )
    if not ui_rotator.value and gs_gain_dbi > 8:
        _notes.append(
            f"A {gs_gain_dbi:.1f} dBi antenna without a rotator will not see the satellite "
            "for most of a pass. Either add a rotator or pick an antenna that does not need "
            "one; the fixed-antenna case is not modeled."
        )
    if unknown_modulations:
        _notes.append(
            "Skipped rows with an unknown modulation: "
            + ", ".join(sorted(set(unknown_modulations)))
            + ". Use a name from the modulation library."
        )
    if dropped_modes:
        _notes.append(
            "Skipped rows missing a required value: "
            + ", ".join(dropped_modes)
            + ". Eb/N0 rows need a bit rate in bps and LoRa rows need a bandwidth in Hz."
        )
    if invalid_modes:
        _notes.append("Skipped rows whose value is not a finite number: " + ", ".join(invalid_modes) + ".")
    if duplicate_modes:
        _notes.append(
            "Skipped rows whose name repeats an earlier row: "
            + ", ".join(sorted(set(duplicate_modes)))
            + ". Give every mode its own name."
        )
    if profile_warnings:
        _notes.append(
            "These profile values were not numbers and fell back to the defaults: "
            + ", ".join(profile_warnings[:8])
            + (" and more." if len(profile_warnings) > 8 else ".")
        )
    if _notes:
        _out = mo.vstack(
            [
                _out,
                mo.callout(
                    mo.md("\n\n".join(_notes)),
                    kind="warn",
                    title="Check the Model",
                ),
            ]
        )
    _out
    return (featured_provisional,)


@app.cell
def _(
    IS_DARK,
    MUTED,
    PALETTE,
    TEXT,
    alt,
    chart_title,
    fmt_int,
    lat_deg,
    lon_deg,
    mo,
    np,
    pd,
    station_name,
    style_chart,
    track_day1,
    ui_map_zoom,
    ui_min_el,
    ui_tile_key,
    ui_tiles,
    vis_circle,
    vis_radius_km,
):
    # Station map: grayscale CARTO basemap tiles (OpenStreetMap data, light or
    # dark to match the notebook theme, no labels) under a Natural Earth
    # coastline, the station, the circle it sees at the minimum elevation, the
    # first phase's first day of ground track, and the samples in view. The
    # mechanics are the optical payload tool's: tiles are Web Mercator images
    # placed in pixel space under a mercator projection with the same scale,
    # every layer clipped to the view; without tiles the coastline still
    # carries the picture.
    _w, _h, _z = 960, 540, int(ui_map_zoom.value)
    _world_px = 256 * 2**_z
    _scale = _world_px / (2 * np.pi)
    _cx = (lon_deg + 180) / 360 * _world_px
    _lat_r = np.radians(np.clip(lat_deg, -85, 85))
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
    _proj = alt.Projection(
        type="mercator", center=[float(lon_deg), float(lat_deg)], scale=_scale, clipExtent=[[0, 0], [_w, _h]]
    )
    _layers = []
    if ui_tiles.value and _tiles:
        _layers.append(
            alt.Chart(pd.DataFrame(_tiles))
            .mark_image(width=256, height=256, align="left", baseline="top", clip=True)
            .encode(x=alt.X("x:Q").scale(None).axis(None), y=alt.Y("y:Q").scale(None).axis(None), url="url:N")
        )
    _world = alt.topo_feature("https://cdn.jsdelivr.net/npm/vega-datasets@v1.29.0/data/world-110m.json", "countries")
    _layers.append(
        alt.Chart(_world).mark_geoshape(
            fill="transparent", stroke=MUTED, strokeWidth=0.8, opacity=0.5 if ui_tiles.value else 1, clip=True
        )
    )
    # The visibility circle, split where it crosses the date line.
    _circle = vis_circle.copy()
    _circle["seg"] = (np.abs(np.diff(_circle["lon"], prepend=_circle["lon"].iloc[0])) > 180).cumsum()
    _circle["what"] = "Visibility circle"
    _track = track_day1.copy()
    _track["orbit"] = (
        np.abs(np.diff(_track["lon"], prepend=_track["lon"].iloc[0])) > 180
    ).cumsum()  # split at the date line either way
    _track["i"] = range(len(_track))
    _track["hours"] = _track["t_s"] / 3600
    _track["what"] = "Ground track, one day"
    _seen = _track[_track["visible"]].copy()
    _seen["what"] = "In view of the station"
    _order = ["Visibility circle", "Ground track, one day", "In view of the station"]
    _color = alt.Color(
        "what:N",
        title=None,
        sort=_order,
        scale=alt.Scale(domain=_order, range=[PALETTE[0], TEXT, PALETTE[2]]),
        legend=alt.Legend(orient="bottom", direction="horizontal"),
    )
    _layers.append(
        alt.Chart(_circle)
        .mark_line(strokeWidth=2.5, clip=True)
        .encode(longitude="lon:Q", latitude="lat:Q", detail="seg:N", order="order:O", color=_color)
    )
    _layers.append(
        alt.Chart(_track)
        .mark_line(strokeWidth=1, opacity=0.55, clip=True)
        .encode(longitude="lon:Q", latitude="lat:Q", detail="orbit:N", order="i:O", color=_color)
    )
    _layers.append(
        alt.Chart(_seen)
        .mark_point(size=40, filled=True, clip=True)
        .encode(
            longitude="lon:Q",
            latitude="lat:Q",
            color=_color,
            tooltip=[
                alt.Tooltip("hours:Q", title="Hours from start", format=".2f"),
                alt.Tooltip("elevation_deg:Q", title="Elevation (deg)", format=".0f"),
            ],
        )
    )
    _layers.append(
        alt.Chart(pd.DataFrame({"lon": [lon_deg], "lat": [lat_deg]}))
        .mark_point(color=PALETTE[2], size=110, filled=True, stroke=TEXT, strokeWidth=1, clip=True)
        .encode(longitude="lon:Q", latitude="lat:Q")
    )
    _map = style_chart(
        alt.layer(*_layers).properties(
            width=_w,
            height=_h,
            projection=_proj,
            title=chart_title(
                f"Around {station_name}",
                f"The circle the station sees above {ui_min_el.value:g}°, one day of ground track from the first orbit phase,",
                "and the samples in view",
            ),
        )
    )
    _credit = (
        "Map tiles © OpenStreetMap contributors, © CARTO. Coastline: Natural Earth via vega-datasets."
        if ui_tiles.value
        else "Coastline: Natural Earth via vega-datasets."
    )
    mo.vstack(
        [
            mo.md("## Map"),
            mo.md(
                f"The station sees a circle of {fmt_int(vis_radius_km)} km ground radius above {ui_min_el.value:g}° elevation "
                "at this altitude; a pass is the track crossing it. The track is one day of the first of the eight orbit "
                "phases the statistics average over, so the picture is one phase and the numbers are all eight. "
                "The base map is grayscale on purpose, so the overlays carry the color. If the tiles do not load, "
                "the coastline alone still shows the geometry; turn the tiles off in the control panel to work "
                "offline; the zoom slider there sets the tile level."
            ),
            _map,  # geoshapes are not selectable in mo.ui.altair_chart, so the chart renders directly
            mo.md(f"<small>{_credit}</small>"),
        ]
    )
    return


@app.cell
def _(
    SERIES_ORDER,
    margin_vs_el,
    mo,
    rule_label,
    rule_x,
    rule_y,
    series_lines,
    style_chart,
    ui_min_el,
    ui_target_margin,
):
    _dn = margin_vs_el[margin_vs_el["direction"] == "downlink"]
    _order = [_m for _m in SERIES_ORDER if _m in set(_dn["mode"])]
    if len(_dn):
        _chart = (
            series_lines(_dn, _order, "margin_db", "Link margin (dB)", "Margin (dB)")
            + rule_y(ui_target_margin.value, dashed=True)
            + rule_y(0.0, dashed=False)
            + rule_x(ui_min_el.value)
            + rule_label(ui_target_margin.value, "target margin")
            + rule_label(0.0, "link closes")
        ).properties(
            title="Downlink margin versus elevation",
            width="container",
            height=320,
        )
        _out = mo.ui.altair_chart(style_chart(_chart))
    else:
        _out = mo.md("No downlink modes selected.")
    mo.vstack([mo.md("## Downlink"), _out])
    return


@app.cell
def _(
    SERIES_ORDER,
    alt,
    margin_vs_el,
    mo,
    np,
    rule_label,
    rule_x,
    rule_y,
    series_lines,
    style_chart,
    ui_min_el,
    ui_sat_sens,
    ui_sat_sens_rate,
    ui_target_margin,
    uplink_headline,
    uplink_prx_vs_el,
):
    # Uplink: margin for every uplink mode, plus received power against the
    # published reference receive level scaled to the headline uplink mode's bit
    # rate as an independent check. That level is a reported figure, not a
    # guaranteed sensitivity – see the assumptions.

    _up = margin_vs_el[margin_vs_el["direction"] == "uplink"]
    _order = [_m for _m in SERIES_ORDER if _m in set(_up["mode"])]
    if len(_up):
        _margin = (
            series_lines(_up, _order, "margin_db", "Link margin (dB)", "Margin (dB)")
            + rule_y(ui_target_margin.value, dashed=True)
            + rule_y(0.0, dashed=False)
            + rule_x(ui_min_el.value)
            + rule_label(ui_target_margin.value, "target margin")
        ).properties(
            title="Uplink margin versus elevation",
            width="container",
            height=260,
        )

        _up_row, _ = uplink_headline
        _has_rate = _up_row is not None and _up_row["bitrate_bps"] > 0
        _rate = float(_up_row["bitrate_bps"]) if _has_rate else ui_sat_sens_rate.value
        _sens = ui_sat_sens.value + 10 * np.log10(_rate / ui_sat_sens_rate.value)
        _lo = min(_sens, float(uplink_prx_vs_el["prx_dbm"].min())) - 5
        _hi = max(_sens, float(uplink_prx_vs_el["prx_dbm"].max())) + 5
        _prx = (
            alt.Chart(uplink_prx_vs_el)
            .mark_line(strokeWidth=2, color="#087C9B")
            .encode(
                x=alt.X(
                    "elevation_deg:Q",
                    title="Elevation (deg)",
                    scale=alt.Scale(domain=[0, 90]),
                ),
                y=alt.Y(
                    "prx_dbm:Q",
                    title="Received power (dBm)",
                    scale=alt.Scale(domain=[_lo, _hi]),
                ),
                tooltip=[
                    alt.Tooltip("elevation_deg:Q", title="Elevation (deg)"),
                    alt.Tooltip("prx_dbm:Q", title="Prx (dBm)", format=".1f"),
                ],
            )
        )
        _power = (
            _prx
            + rule_y(_sens, dashed=True)
            + rule_label(
                _sens,
                f"reference level at {_rate:,.0f} bps".replace(",", "'")
                + (f", {_up_row['mode']}" if _has_rate else ""),
            )
        ).properties(
            title="Uplink received power at the spacecraft",
            width="container",
            height=220,
        )
        _out = [
            mo.ui.altair_chart(style_chart(_margin)),
            mo.ui.altair_chart(style_chart(_power)),
        ]
    else:
        _out = [mo.md("No uplink modes selected.")]
    mo.vstack([mo.md("## Uplink")] + _out)
    return


@app.cell
def _(fmt_int, mo, mode_summary):
    _tbl = mode_summary.rename(
        columns={
            "mode": "Mode",
            "modulation": "Modulation",
            "bitrate_bps": "Bit rate (bps)",
            "info_rate_bps": "Information rate (bps)",
            "packet_airtime_ms": "LoRa packet airtime (ms)",
            "bandwidth_hz": "Bandwidth (Hz)",
            "required_db": "Threshold (dB)",
            "ideal_ebn0_for_fer_db": "Ideal Eb/N0 for target FER (dB)",
            "fer_at_threshold_pct": "FER at threshold (%)",
            "tx_dbm": "TX power (dBm)",
            "margin_at_min_el_db": "Margin, min elevation (dB)",
            "margin_at_zenith_db": "Margin, zenith (dB)",
            "kB_per_avg_pass": "kB per average pass",
            "kB_per_day": "kB per day at target",
            "kB_per_avg_pass_0db": "kB per average pass at 0 dB",
            "kB_per_day_if_only_closing": "kB per day at 0 dB margin",
            "kB_per_day_p10": "kB per day, 10th percentile",
            "uplink_margin_at_min_el_db": "Uplink margin, min el (dB)",
            "uplink_kB_per_day": "Uplink kB per day",
        }
    )
    _kb = {
        _c: fmt_int
        for _c in (
            "Bit rate (bps)",
            "Information rate (bps)",
            "LoRa packet airtime (ms)",
            "Bandwidth (Hz)",
            "kB per average pass",
            "kB per day at target",
            "kB per average pass at 0 dB",
            "kB per day at 0 dB margin",
            "kB per day, 10th percentile",
            "Uplink kB per day",
        )
    }
    _kb["Ideal Eb/N0 for target FER (dB)"] = "{:.2f}"
    _kb["FER at threshold (%)"] = "{:.1f}"
    mo.vstack(
        [
            mo.md("## Per-Mode Summary"),
            mo.md(
                "Volume counts the seconds of each pass where the margin meets the target, at "
                "the information rate, less framing overhead and the direction's share of a "
                "half-duplex pass. For LoRa rows the information rate is the packet payload over "
                "its time on air – preamble, header, CRC and symbol rounding included – and the "
                "framing overhead does not apply on top. *At 0 dB margin* counts any positive "
                "margin instead. The 10th percentile is the daily total on a low-volume day, "
                "days without a pass counted as zero. Modes without a bit rate, such as CW, get "
                "a margin only. The two FER columns are filled only for entries on the ideal "
                "non-coherent FSK curve."
            ),
            mo.ui.table(
                _tbl,
                selection=None,
                format_mapping=_kb,
                show_column_summaries=False,
            ),
        ]
    )
    return


@app.cell
def _(
    atmospheric_loss_db,
    featured_mode,
    fspl_db,
    gs_gain_dbi,
    gs_point_loss_db,
    gs_tx_dbm,
    iono_down_db,
    mo,
    modes,
    n0_gs_dbm_hz,
    np,
    pd,
    pol_loss_db,
    slant_range_km,
    t_sys_gs_k,
    ui_altitude,
    ui_excess_loss,
    ui_fer_pct,
    ui_frame_bytes,
    ui_freq_down,
    ui_gs_feed_loss,
    ui_gs_nf,
    ui_gs_tant,
    ui_impl_loss,
    ui_min_el,
    ui_sat_gain,
    ui_sat_loss,
    ui_sat_point_loss,
):
    # The downlink budget line by line for the featured mode, at the minimum
    # elevation and at zenith. Rows starting with = are running subtotals in the
    # AMSAT/IARU layout: EIRP, isotropic level, received power, C/N0, Eb/N0, margin.
    # The noise rows show how T_sys is built at the LNA input, so the reference
    # plane is on the page rather than in a comment.
    _l = 10 ** (ui_gs_feed_loss.value / 10)
    _t_ant = ui_gs_tant.value / _l
    _t_feed = (1 - 1 / _l) * 290.0
    _t_rx = 290.0 * (10 ** (ui_gs_nf.value / 10) - 1)

    _rows = modes[modes["mode"] == featured_mode]
    if len(_rows):
        _m = _rows.iloc[0]
        _is_fsk = _m["kind"] == "fsk"
        _coded = _is_fsk and _m["code_rate"] < 1.0
        _rate_db = 10 * np.log10(_m["info_rate_bps"] if _is_fsk else _m["bandwidth_hz"])
        _rate_label = (
            ("Information rate, 10·log10(Rb·R)" if _coded else "Bit rate, 10·log10(Rb)")
            if _is_fsk
            else "Bandwidth, 10·log10(BW)"
        )
        _cols = {}
        for _label, _el in (
            ("at min elevation", ui_min_el.value),
            ("at zenith", 90.0),
        ):
            _rng = float(slant_range_km(_el, ui_altitude.value))
            _fspl = float(fspl_db(_rng, ui_freq_down.value))
            _atm = float(atmospheric_loss_db(_el, ui_freq_down.value))
            _eirp = _m["tx_dbm"] + ui_sat_gain.value - ui_sat_loss.value
            _iso = (
                _eirp
                - _fspl
                - _atm
                - iono_down_db
                - ui_excess_loss.value
                - pol_loss_db
                - ui_sat_point_loss.value
                - gs_point_loss_db
            )
            _prx = _iso + gs_gain_dbi - ui_gs_feed_loss.value
            _cn0 = _prx - n0_gs_dbm_hz
            _ebn0 = _cn0 - _rate_db
            _cols[f"{_label}, {_rng:.0f} km"] = [
                _m["tx_dbm"],
                ui_sat_gain.value,
                -ui_sat_loss.value,
                _eirp,
                -_fspl,
                -_atm,
                -iono_down_db,
                -ui_excess_loss.value,
                -pol_loss_db,
                -ui_sat_point_loss.value,
                -gs_point_loss_db,
                _iso,
                gs_gain_dbi,
                -ui_gs_feed_loss.value,
                _prx,
                _t_ant,
                _t_feed,
                _t_rx,
                t_sys_gs_k,
                n0_gs_dbm_hz,
                _cn0,
                -_rate_db,
                _ebn0,
                -float(_m["required_db"]),
                -ui_impl_loss.value,
                _ebn0 - float(_m["required_db"]) - ui_impl_loss.value,
            ]
        _items = [
            ("Transmit power", "dBm"),
            ("Spacecraft antenna gain", "dBi"),
            ("Spacecraft cable and switch loss", "dB"),
            ("= EIRP", "dBm"),
            ("Free-space path loss", "dB"),
            ("Atmospheric loss", "dB"),
            ("Ionospheric loss", "dB"),
            ("Rain and other excess loss", "dB"),
            ("Polarization loss", "dB"),
            ("Spacecraft pointing allowance", "dB"),
            ("Ground pointing loss", "dB"),
            ("= Isotropic level at the ground", "dBm"),
            ("Ground antenna gain", "dBi"),
            ("Ground feed loss", "dB"),
            ("= Received power at the LNA input", "dBm"),
            ("Antenna noise after the feeder", "K"),
            ("Feeder noise", "K"),
            ("Receiver noise", "K"),
            ("= System noise temperature at the LNA input", "K"),
            ("Noise density N0", "dBm/Hz"),
            ("= C/N0", "dBHz"),
            (_rate_label, "dBHz"),
            ("= Eb/N0" if _is_fsk else "= SNR in the bandwidth", "dB"),
            (
                "Required Eb/N0" if _is_fsk else "Demodulator SNR threshold",
                "dB",
            ),
            ("Implementation loss", "dB"),
            ("= Margin", "dB"),
        ]
        budget_table = pd.DataFrame(
            {
                "Line item": [_i[0] for _i in _items],
                "Unit": [_i[1] for _i in _items],
            }
            | _cols
        )
        _fer_note = ""
        if _m["ideal_ebn0_for_fer_db"] == _m["ideal_ebn0_for_fer_db"]:
            _fer_note = (
                f" On the ideal non-coherent FSK curve the {_m['required_db']:g} dB threshold "
                f"gives about {_m['fer_at_threshold_pct']:.1f}% frame loss at "
                f"{ui_frame_bytes.value:g} bytes; {ui_fer_pct.value:g}% would need "
                f"{_m['ideal_ebn0_for_fer_db']:.2f} dB."
            )
        _out = mo.vstack(
            [
                mo.md(
                    "Free-space and atmospheric loss move with elevation; every other line is "
                    "an input. Signal and noise are both referenced to the LNA input, so a hand "
                    "check must carry every loss line here, not only path loss." + _fer_note
                ),
                mo.ui.table(
                    budget_table,
                    selection=None,
                    page_size=30,
                    show_column_summaries=False,
                    format_mapping={_c: "{:.1f}" for _c in _cols},
                ),
                mo.accordion(
                    {"Ground Transmitter in dBm": mo.md(f"{gs_tx_dbm:.1f} dBm from the transmitter power you set.")}
                ),
            ]
        )
    else:
        budget_table = pd.DataFrame()
        _out = mo.md("No downlink mode to break down.")
    mo.vstack([mo.md(f"## Link Budget Breakdown · {featured_mode}"), _out])
    return (budget_table,)


@app.cell
def _(
    N_PHASES,
    longest_gap_h,
    mo,
    orbital_period_min,
    passes,
    passes_per_day,
    pd,
    sim_days_total,
    station_name,
    ui_min_el,
    ui_sim_days,
):
    # Pass statistics – how the passes split by peak elevation, which decides
    # how much of each pass is usable.

    _bands = [("below 20°", 0, 20), ("20–45°", 20, 45), ("above 45°", 45, 91)]
    _rows = []
    _total_min = float(passes["duration_min"].sum()) or 1.0
    for _name, _lo, _hi in _bands:
        _sel = passes[(passes["max_elevation_deg"] >= _lo) & (passes["max_elevation_deg"] < _hi)]
        if len(_sel):
            _rows.append(
                {
                    "Peak elevation": _name,
                    "Passes per day": len(_sel) / sim_days_total,
                    "Mean duration (min)": float(_sel["duration_min"].mean()),
                    "Share of contact time (%)": 100 * float(_sel["duration_min"].sum()) / _total_min,
                }
            )
    band_table = pd.DataFrame(_rows)
    _pass_list = passes.assign(
        start_h=(passes["start_s"] / 3600.0).round(2),
        duration_min=passes["duration_min"].round(1),
        max_elevation_deg=passes["max_elevation_deg"].round(1),
    )[["phase", "pass_id", "start_h", "duration_min", "max_elevation_deg"]]
    mo.vstack(
        [
            mo.md(f"## Pass Statistics · {station_name}"),
            mo.md(
                f"Orbital period {orbital_period_min:.1f} min. {len(passes)} passes above "
                f"{ui_min_el.value}° in {ui_sim_days.value} simulated days for each of "
                f"{N_PHASES} orbit phases, {passes_per_day:.1f} per day on average; the longest "
                f"wait between passes is {longest_gap_h:.1f} h. Most passes are low, and a "
                f"low pass spends most of its time near the minimum elevation where the "
                f"margin is worst."
            ),
            mo.ui.table(
                band_table,
                selection=None,
                show_column_summaries=False,
                format_mapping={
                    "Passes per day": "{:.2f}",
                    "Mean duration (min)": "{:.1f}",
                    "Share of contact time (%)": "{:.0f}",
                },
            ),
            mo.accordion({"Simulated Pass List": mo.ui.table(_pass_list, selection=None, show_column_summaries=False)}),
        ]
    )
    return (band_table,)


@app.cell
def _(
    ACKNOWLEDGMENT_MD,
    ASSUMPTIONS_MD,
    MODE_KEYS,
    N_PHASES,
    TOOL_VERSION,
    band_table,
    budget_table,
    contact_min_per_day,
    dropped_modes,
    dt,
    featured_mode,
    featured_provisional,
    fmt_int,
    gs_ar_db,
    gs_circular,
    gs_gain_dbi,
    gs_hpbw_deg,
    gs_point_loss_db,
    gs_tx_dbm,
    half_duplex,
    iono_down_db,
    iono_up_db,
    lat_deg,
    lon_deg,
    longest_gap_h,
    mean_pass_min,
    mo,
    mode_summary,
    modes,
    orbital_period_min,
    passes,
    passes_per_day,
    pol_loss_db,
    profile_name,
    sim_days_total,
    station_name,
    t_sys_gs_k,
    t_sys_sat_k,
    ui_altitude,
    ui_custom_ebn0,
    ui_duplex,
    ui_duty,
    ui_excess_loss,
    ui_fer_pct,
    ui_frame_bytes,
    ui_freq_down,
    ui_freq_up,
    ui_gs_antenna,
    ui_gs_ar,
    ui_gs_circular,
    ui_gs_feed_loss,
    ui_gs_gain,
    ui_gs_hpbw,
    ui_gs_nf,
    ui_gs_tant,
    ui_gs_tx_w,
    ui_impl_loss,
    ui_inclination,
    ui_lora_payload,
    ui_lora_preamble,
    ui_map_zoom,
    ui_min_el,
    ui_modes,
    ui_overhead,
    ui_pol_case,
    ui_role,
    ui_rotator,
    ui_sat_ar,
    ui_sat_gain,
    ui_sat_loss,
    ui_sat_nf,
    ui_sat_point_loss,
    ui_sat_sens,
    ui_sat_sens_rate,
    ui_sim_days,
    ui_station,
    ui_target_margin,
    ui_tile_key,
    ui_tiles,
    ui_track_err,
    unknown_modulations,
    uplink_headline,
):
    # Export – every setting and every finding as one markdown file, so a run can
    # go into a technical note, an issue or an email without being retyped.

    def _dedent(text):
        return "\n".join(_l[4:] if _l.startswith("    ") else _l for _l in text.strip("\n").splitlines())

    def _val(v, places=1):
        if hasattr(v, "item"):
            v = v.item()
        if isinstance(v, bool):
            return "yes" if v else "no"
        if isinstance(v, float):
            return "" if v != v else f"{v:,.{places}f}".replace(",", "'")
        if isinstance(v, int):
            return f"{v:,}".replace(",", "'")
        return str(v)

    def _table(df, places=1):
        if df is None or not len(df):
            return "_None._"
        _cols = [str(_c) for _c in df.columns]
        _out = [
            "| " + " | ".join(_cols) + " |",
            "|" + "|".join("---" for _ in _cols) + "|",
        ]
        for _, _r in df.iterrows():
            _out.append("| " + " | ".join(_val(_v, places) for _v in _r) + " |")
        return "\n".join(_out)

    def _pairs(rows):
        return "\n".join(["| Setting | Value |", "|---|---|"] + [f"| {_k} | {_v} |" for _k, _v in rows])

    _now = dt.datetime.now(dt.timezone.utc)
    _feat_rows = mode_summary[mode_summary["mode"] == featured_mode]
    _feat = _feat_rows.iloc[0] if len(_feat_rows) else None
    _up_row, _up_caption = uplink_headline

    _mode_cols = {
        "mode": "Mode",
        "modulation": "Modulation",
        "bitrate_bps": "Bit rate (bps)",
        "code_rate": "Code rate",
        "bandwidth_hz": "Bandwidth (Hz)",
        "required_db": "Threshold (dB)",
        "tx_dbm": "Spacecraft TX (dBm)",
        "downlink": "Downlink",
        "uplink": "Uplink",
        "featured": "Featured",
    }

    def _hz(v):  # whole numbers with the Swiss apostrophe, blank when absent
        return "" if v != v else fmt_int(v)

    if len(modes):
        _modes_out = modes.copy()
        for _c in ("bitrate_bps", "bandwidth_hz"):
            _modes_out[_c] = _modes_out[_c].map(_hz)
        _modes_out["code_rate"] = _modes_out["code_rate"].round(3)
        _modes_md = _table(_modes_out.rename(columns=_mode_cols)[list(_mode_cols.values())])
    else:
        _modes_md = "_No modes defined._"
    _summary_cols = {
        "mode": "Mode",
        "bitrate_bps": "Bit rate (bps)",
        "info_rate_bps": "Information rate (bps)",
        "packet_airtime_ms": "LoRa packet airtime (ms)",
        "bandwidth_hz": "Bandwidth (Hz)",
        "required_db": "Threshold (dB)",
        "ideal_ebn0_for_fer_db": "Ideal Eb/N0 for target FER (dB)",
        "fer_at_threshold_pct": "FER at threshold (%)",
        "margin_at_min_el_db": "Margin, min el (dB)",
        "margin_at_zenith_db": "Margin, zenith (dB)",
        "kB_per_avg_pass": "kB per pass",
        "kB_per_day": "kB per day",
        "kB_per_day_if_only_closing": "kB per day at 0 dB margin",
        "kB_per_day_p10": "kB per day, 10th pct",
        "uplink_margin_at_min_el_db": "Uplink margin (dB)",
        "uplink_kB_per_day": "Uplink kB per day",
    }
    if len(mode_summary):
        _summary_out = mode_summary.copy()
        for _c in ("bitrate_bps", "info_rate_bps", "packet_airtime_ms", "bandwidth_hz"):
            _summary_out[_c] = _summary_out[_c].map(_hz)
        _summary_md = _table(_summary_out.rename(columns=_summary_cols)[list(_summary_cols.values())])
    else:
        _summary_md = "_No modes defined._"

    _sections = [
        f"# BAC Link Budget · {station_name}",
        f"Generated {_now:%Y-%m-%d %H:%M} UTC (Unix {int(_now.timestamp())}) with "
        f"BAC Link Budget {TOOL_VERSION}, bac.page/molab-link-budget."
        + (f" Profile: {profile_name}." if profile_name else "")
        + " Every value below is a planning input or a result derived from one; nothing here "
        "is measured. Enter the settings into the tool to reproduce it.",
        "## Settings",
        "### Orbit and Targets",
        _pairs(
            [
                ("Orbit altitude (km)", _val(ui_altitude.value, 0)),
                ("Inclination (deg)", _val(ui_inclination.value)),
                ("Minimum usable elevation (deg)", _val(ui_min_el.value, 0)),
                ("Target link margin (dB)", _val(ui_target_margin.value)),
                ("Days simulated per orbit phase", _val(ui_sim_days.value, 0)),
                ("Orbit phases averaged", _val(N_PHASES, 0)),
                ("Downlink frequency (MHz)", _val(ui_freq_down.value)),
                ("Uplink frequency (MHz)", _val(ui_freq_up.value)),
                ("Role of this link for the payload", ui_role.value),
            ]
        ),
        "### Ground Station",
        _pairs(
            [
                ("Station", station_name),
                ("Latitude (deg N)", _val(lat_deg, 3)),
                ("Longitude (deg E)", _val(lon_deg, 3)),
                ("Antenna", ui_gs_antenna.value),
                ("Antenna gain (dBi)", _val(gs_gain_dbi)),
                ("Half-power beamwidth (deg)", _val(gs_hpbw_deg)),
                ("Polarization", "circular" if gs_circular else "linear"),
                ("Axial ratio used (dB)", _val(gs_ar_db)),
                ("Tracking rotator", "yes" if ui_rotator.value else "no"),
                (
                    "Tracking error (deg)",
                    _val(ui_track_err.value) if ui_rotator.value else "n/a",
                ),
                ("Pointing loss (dB)", _val(gs_point_loss_db, 2)),
                (
                    "Feed loss ahead of the LNA (dB)",
                    _val(ui_gs_feed_loss.value),
                ),
                ("LNA noise figure (dB)", _val(ui_gs_nf.value)),
                ("Antenna noise temperature (K)", _val(ui_gs_tant.value, 0)),
                (
                    "System noise temperature at the LNA input (K)",
                    _val(t_sys_gs_k, 0),
                ),
                ("Transmitter power (W)", _val(ui_gs_tx_w.value, 0)),
                ("Transmitter power (dBm)", _val(gs_tx_dbm)),
            ]
        ),
        "### Spacecraft",
        _pairs(
            [
                ("Antenna gain (dBi)", _val(ui_sat_gain.value)),
                ("Antenna axial ratio (dB)", _val(ui_sat_ar.value)),
                ("Cable and switch loss (dB)", _val(ui_sat_loss.value)),
                (
                    "Antenna pointing allowance (dB)",
                    _val(ui_sat_point_loss.value),
                ),
                ("Receiver noise figure (dB)", _val(ui_sat_nf.value)),
                (
                    "System noise temperature at the receiver input (K)",
                    _val(t_sys_sat_k, 0),
                ),
                ("Reference receive level (dBm)", _val(ui_sat_sens.value, 0)),
                ("…reported at (bps)", _val(int(ui_sat_sens_rate.value))),
                ("Duplex", "half, one radio and one antenna" if half_duplex else "full, separate chains"),
            ]
        ),
        "### Link Allowances",
        _pairs(
            [
                (
                    "Atmospheric loss (dB)",
                    "max of King's elevation table and ITU-R P.676 gases at each frequency",
                ),
                ("Ionospheric loss, downlink (dB)", _val(iono_down_db, 2)),
                ("Ionospheric loss, uplink (dB)", _val(iono_up_db, 2)),
                (
                    "Rain and other excess loss (dB)",
                    _val(ui_excess_loss.value),
                ),
                (
                    f"Polarization loss, {ui_pol_case.value} (dB)",
                    _val(pol_loss_db, 2),
                ),
                ("Implementation loss (dB)", _val(ui_impl_loss.value)),
                (
                    "Required Eb/N0 for the Custom modulation (dB)",
                    _val(ui_custom_ebn0.value),
                ),
                ("Framing overhead (%)", _val(ui_overhead.value, 0)),
                (
                    "Frame length on air (bytes)",
                    _val(int(ui_frame_bytes.value)),
                ),
                ("Target frame error rate (%)", _val(ui_fer_pct.value, 2)),
                ("LoRa payload per packet (bytes)", _val(int(ui_lora_payload.value))),
                ("LoRa programmed preamble (symbols)", _val(int(ui_lora_preamble.value))),
                (
                    "Downlink share of a half-duplex pass (%)",
                    _val(ui_duty.value, 0) if half_duplex else "n/a, full duplex",
                ),
            ]
        ),
        "### Modes",
        _modes_md,
        "## Findings",
        "### Headline",
        _pairs(
            [
                ("Passes per day", _val(passes_per_day)),
                ("Mean pass duration (min)", _val(mean_pass_min)),
                ("Contact time per day (min)", _val(contact_min_per_day, 0)),
                ("Longest gap between passes (h)", _val(longest_gap_h)),
                ("Orbital period (min)", _val(orbital_period_min)),
                (
                    "Passes simulated",
                    f"{_val(len(passes), 0)} over {_val(sim_days_total, 0)} station-days",
                ),
                ("Featured mode", featured_mode or "none"),
                (
                    "Margin at minimum elevation (dB)",
                    "n/a" if _feat is None else _val(_feat["margin_at_min_el_db"]),
                ),
                (
                    "Downlink per day (kB)",
                    "n/a" if _feat is None else fmt_int(_feat["kB_per_day"]),
                ),
                (
                    "Downlink per day at 0 dB margin (kB)",
                    "n/a" if _feat is None else fmt_int(_feat["kB_per_day_if_only_closing"]),
                ),
                (
                    "Downlink per day, 10th percentile (kB)",
                    "n/a" if _feat is None else fmt_int(_feat["kB_per_day_p10"]),
                ),
                (
                    "Uplink mode",
                    "none" if _up_row is None else f"{_up_row['mode']} ({_up_caption})",
                ),
                (
                    "Uplink margin at minimum elevation (dB)",
                    "n/a" if _up_row is None else _val(_up_row["uplink_margin_at_min_el_db"]),
                ),
                (
                    "Uplink per day (kB)",
                    "n/a" if _up_row is None else fmt_int(_up_row["uplink_kB_per_day"]),
                ),
            ]
        ),
        "### Per Mode",
        _summary_md,
        "### Passes by Peak Elevation",
        _table(band_table, 2),
        f"### Link Budget Breakdown · {featured_mode}" if featured_mode else "### Link Budget Breakdown",
        _table(budget_table),
        _dedent(ASSUMPTIONS_MD),
        _dedent(ACKNOWLEDGMENT_MD),
    ]
    _skipped = []
    if featured_provisional:
        _skipped.append(
            f"! The featured mode's threshold ({_feat['modulation']}) is provisional: "
            "it has never been measured for the receiver it names."
        )
    if unknown_modulations:
        _skipped.append(
            "! Rows with an unknown modulation were skipped: " + ", ".join(sorted(set(unknown_modulations))) + "."
        )
    if dropped_modes:
        _skipped.append("! Rows missing a required value were skipped: " + ", ".join(dropped_modes) + ".")
    for _line in reversed(_skipped):
        _sections.insert(1, _line)
    report_md = "\n\n".join(_sections) + "\n"

    # Mission profile. Hand-rolled TOML so nothing new has to be installed: the
    # values are strings, numbers and booleans, which is the easy corner of the
    # format. Reading it back uses stdlib tomllib.
    def _toml(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if hasattr(v, "item"):
            v = v.item()
        if isinstance(v, (int, float)):
            return (
                "" if v != v or v in (float("inf"), float("-inf")) else repr(round(v, 6) if isinstance(v, float) else v)
            )
        _s = (
            str(v)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return '"' + _s + '"'

    def _section(title, rows):
        _out = [f"[{title}]"]
        for _k, _v in rows:
            _s = _toml(_v)
            if _s:  # a missing value is left out rather than written as an empty key
                _out.append(f"{_k} = {_s}")
        return "\n".join(_out)

    _profile_sections = [
        f"# Saved from BAC Link Budget {TOOL_VERSION} on {_now:%Y-%m-%d}. Load it with the button at the\n"
        "# top of the notebook. Any key you leave out keeps the tool's default. [results.link_budget]\n"
        "# is what this tool hands to its siblings and is ignored when loaded back.\n"
        f'name = "{station_name} {_now:%Y-%m-%d}"\n'
        'tool = "bac_link_budget"\n'
        f'tool_version = "{TOOL_VERSION}"',
        _section("mission", [("link_role", ui_role.value)]),
        _section(
            "orbit",
            [
                ("altitude_km", ui_altitude.value),
                ("inclination_deg", ui_inclination.value),
                ("min_elevation_deg", ui_min_el.value),
                ("target_margin_db", ui_target_margin.value),
                ("sim_days", ui_sim_days.value),
                ("downlink_mhz", ui_freq_down.value),
                ("uplink_mhz", ui_freq_up.value),
            ],
        ),
        _section(
            "ground_station",
            [
                ("station", ui_station.value),
                ("latitude_deg", lat_deg),
                ("longitude_deg", lon_deg),
                ("min_elevation_deg", ui_min_el.value),
                ("antenna", ui_gs_antenna.value),
                ("custom_gain_dbi", ui_gs_gain.value),
                ("custom_hpbw_deg", ui_gs_hpbw.value),
                ("custom_circular", ui_gs_circular.value),
                ("rotator", ui_rotator.value),
                ("tracking_error_deg", ui_track_err.value),
                ("feed_loss_db", ui_gs_feed_loss.value),
                ("lna_nf_db", ui_gs_nf.value),
                ("antenna_temp_k", ui_gs_tant.value),
                ("axial_ratio_db", ui_gs_ar.value),
                ("tx_power_w", ui_gs_tx_w.value),
            ],
        ),
        _section(
            "spacecraft",
            [
                ("antenna_gain_dbi", ui_sat_gain.value),
                ("axial_ratio_db", ui_sat_ar.value),
                ("cable_loss_db", ui_sat_loss.value),
                ("pointing_allowance_db", ui_sat_point_loss.value),
                ("receiver_nf_db", ui_sat_nf.value),
                ("reference_rx_level_dbm", ui_sat_sens.value),
                ("reference_rx_rate_bps", ui_sat_sens_rate.value),
                ("duplex", ui_duplex.value),
            ],
        ),
        _section(
            "allowances",
            [
                ("implementation_loss_db", ui_impl_loss.value),
                ("custom_ebn0_db", ui_custom_ebn0.value),
                ("framing_overhead_pct", ui_overhead.value),
                ("downlink_share_pct", ui_duty.value),
                ("excess_loss_db", ui_excess_loss.value),
                ("polarization_case", ui_pol_case.value),
                ("frame_bytes", int(ui_frame_bytes.value)),
                ("target_fer_pct", ui_fer_pct.value),
                ("lora_payload_bytes", int(ui_lora_payload.value)),
                ("lora_preamble_symbols", int(ui_lora_preamble.value)),
            ],
        ),
        _section("map", [("tiles", ui_tiles.value), ("zoom", ui_map_zoom.value), ("key", ui_tile_key.value)]),
    ]
    for _, _r in ui_modes.value.iterrows():
        _profile_sections.append(_section("[modes]", [(_k, _r[_c]) for _c, _k in MODE_KEYS.items()]))
    # Headline figures for the sibling tools, under a table named after this
    # tool so a profile can carry several tools' results without collision.
    _profile_sections.append(
        _section(
            "results.link_budget",
            [
                ("role", ui_role.value),
                ("featured_mode", featured_mode),
                ("usable_kb_per_day", float("nan") if _feat is None else float(_feat["kB_per_day"])),
                ("usable_kb_per_day_p10", float("nan") if _feat is None else float(_feat["kB_per_day_p10"])),
                (
                    "usable_kb_per_day_0db",
                    float("nan") if _feat is None else float(_feat["kB_per_day_if_only_closing"]),
                ),
                ("margin_at_min_el_db", float("nan") if _feat is None else float(_feat["margin_at_min_el_db"])),
                ("uplink_kb_per_day", float("nan") if _up_row is None else float(_up_row["uplink_kB_per_day"])),
                ("passes_per_day", passes_per_day),
                ("mean_pass_min", mean_pass_min),
                ("contact_min_per_day", contact_min_per_day),
                ("longest_gap_h", longest_gap_h),
                ("min_elevation_deg", ui_min_el.value),
                ("target_margin_db", ui_target_margin.value),
                ("downlink_share_pct", ui_duty.value if half_duplex else 100),
                ("duplex", ui_duplex.value),
                ("downlink_frequency_mhz", ui_freq_down.value),
                ("uplink_frequency_mhz", ui_freq_up.value),
                ("orbital_period_min", orbital_period_min),
            ],
        )
    )
    # One table per mode, so a sibling can match its beacon tiers to rows by
    # name or modulation: the power budget takes the LoRa backstop's packet
    # airtime from the SF12 row, and the tier rows' channel rate is here for
    # whoever converts a message length into milliseconds.
    for _, _r in mode_summary.iterrows():
        _profile_sections.append(
            _section(
                "[results.link_budget.modes]",
                [
                    ("mode", _r["mode"]),
                    ("modulation", _r["modulation"]),
                    ("bitrate_bps", float(_r["bitrate_bps"])),
                    ("info_rate_bps", float(_r["info_rate_bps"])),
                    ("packet_airtime_ms", float(_r["packet_airtime_ms"])),
                    ("tx_dbm", float(_r["tx_dbm"])),
                    ("margin_at_min_el_db", float(_r["margin_at_min_el_db"])),
                    ("uplink_margin_at_min_el_db", float(_r["uplink_margin_at_min_el_db"])),
                    ("kb_per_day", float(_r["kB_per_day"])),
                    ("uplink_kb_per_day", float(_r["uplink_kB_per_day"])),
                ],
            )
        )
    profile_toml = "\n\n".join(_profile_sections) + "\n"

    _slug = "".join(_c if _c.isalnum() else "-" for _c in station_name.lower()).strip("-")
    summary_csv = (
        mode_summary.rename(columns=_summary_cols)[list(_summary_cols.values())].to_csv(index=False)
        if len(mode_summary)
        else "Mode\n"
    )
    mo.vstack(
        [
            mo.md("## Export"),
            mo.md(
                "The report carries every setting and finding, the assumptions and the acknowledgment. "
                "The profile carries every input, the mode table and a `[results.link_budget]` table "
                "for the sibling tools; it loads back into the control panel. The CSV is the per-mode "
                "summary for a spreadsheet."
            ),
            mo.hstack(
                [
                    mo.download(
                        data=report_md.encode("utf-8"),
                        filename=f"bac-link-budget-{_slug}-{_now:%Y-%m-%d}.md",
                        mimetype="text/markdown",
                        label="Download report (.md)",
                    ),
                    mo.download(
                        data=profile_toml.encode("utf-8"),
                        filename=f"bac-link-budget-profile-{_now:%Y-%m-%d}.toml",
                        mimetype="application/toml",
                        label="Download profile (.toml)",
                    ),
                    mo.download(
                        data=summary_csv.encode("utf-8"),
                        filename=f"bac-link-budget-{_slug}-{_now:%Y-%m-%d}.csv",
                        mimetype="text/csv",
                        label="Download per-mode summary (.csv)",
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

    **Orbit.** Circular, two-body, over a spherical Earth, no [J2](https://cubesat-resources.space/references/glossary/#j2). Averaged over
    orbit phase the pass counts and durations match
    [SGP4](https://cubesat-resources.space/references/glossary/#sgp4) within 2%
    between 400 and 600 km. Good enough to plan a mission, not to point an antenna
    – for that you want a [TLE](https://cubesat-resources.space/references/glossary/#tle).

    **Antennas.** The spacecraft antenna is one gain in every direction, and any
    second radio on board shares it and the receiver. Ground pointing loss comes
    from the [beamwidth](https://cubesat-resources.space/references/glossary/#beamwidth-hpbw) and your tracking error and needs a [rotator](https://cubesat-resources.space/references/glossary/#rotator); a fixed
    antenna is not modeled, so pick one that does not need a rotator and set its
    gain accordingly. [Polarization](https://cubesat-resources.space/references/glossary/#polarization-loss)
    loss comes from the two [axial ratios](https://cubesat-resources.space/references/glossary/#axial-ratio) – a linear ground antenna counts as
    40 dB – with the ellipses either crossed (worst case) or averaged over their
    angle. A [tumbling](https://cubesat-resources.space/references/glossary/#tumbling) spacecraft earns the worst case.

    **Losses.** [Free-space path loss](https://cubesat-resources.space/references/glossary/#free-space-path-loss) per direction at its own frequency. The
    atmospheric line is the larger of King's elevation table – an empirical
    allowance for what the troposphere does near the horizon – and ITU-R P.676
    gaseous absorption at the frequency in use (1013 hPa, 15 °C, 7.5 g/m³, along
    a spherical-shell path), so it is continuous in frequency and never below
    physics. Ionospheric loss is King's mean value against frequency. Rain is the
    excess-loss input: at 2.4 GHz it is a fraction of a decibel, above 10 GHz it
    sets availability and the panel says so.

    **Noise.** Signal and noise are both referenced to the [LNA](https://cubesat-resources.space/references/glossary/#lna) input: the antenna
    temperature attenuated by the feeder, plus the feeder's own noise, plus the
    receiver's [noise figure](https://cubesat-resources.space/references/glossary/#noise-figure) as a temperature; together they are the [system noise temperature](https://cubesat-resources.space/references/glossary/#system-noise-temperature). The breakdown shows the three terms. The spacecraft sees 290 K of
    antenna noise, the conservative end of an Earth-filled sky.

    **Thresholds.** Library figures are King's table at a
    [bit error rate](https://cubesat-resources.space/references/glossary/#bit-error-rate-ber)
    of 1e-5, before [FEC](https://cubesat-resources.space/references/glossary/#fec)
    unless the entry names a code. Entries marked provisional name a receiver
    nobody has measured; a callout and a line in the report say so when the
    featured mode uses one. For entries on the ideal non-coherent FSK curve the
    tool also shows the [frame error rate](https://cubesat-resources.space/references/glossary/#frame-error-rate-fer) the figure implies at your frame length,
    and the [Eb/N0](https://cubesat-resources.space/references/glossary/#ebn0) your target FER would need, assuming independent bit errors –
    shown beside the library figure, never substituted for it. For a coded entry
    the bit rate you enter is the channel rate and the [code rate](https://cubesat-resources.space/references/glossary/#code-rate) turns it into the
    information rate; Eb/N0 is per information bit and
    volume counts information bits, so coding gain and its throughput cost come
    from one line. The [framing overhead](https://cubesat-resources.space/references/glossary/#framing-overhead) slider covers sync, headers and idle
    only. CW entries carry an [SNR](https://cubesat-resources.space/references/glossary/#snr) in the bandwidth the receiver integrates over
    and no data figure. The BAC CW specification asks for a 3 dB [implementation
    loss](https://cubesat-resources.space/references/glossary/#implementation-loss) allowance and 3 dB of [link margin](https://cubesat-resources.space/references/glossary/#link-margin); the tool's global 2 dB allowance and target
    apply instead, which at CW's margins changes no answer.

    **Modulation names describe demodulators.** [GMSK](https://cubesat-resources.space/references/glossary/#gmsk), GFSK, MSK and [FSK](https://cubesat-resources.space/references/glossary/#fsk) are one
    continuous-phase family; the 4.2 dB between the GMSK entry and non-coherent
    FSK is [coherent detection against a discriminator](https://cubesat-resources.space/references/glossary/#coherent-non-coherent-detection). Pick the entry that
    matches the receiver you will fly, not the transmitter's brochure. The GFSK entry at
    [modulation index](https://cubesat-resources.space/references/glossary/#modulation-index-h) h = 0.5 has no defensible figure and takes the Custom Eb/N0 input.

    **Reference receive level.** A published input level from Doppler tests under
    a Reed–Solomon-coded configuration, with no error rate attached. It draws a
    reference line on the uplink chart and nothing else.

    **Duplex.** A hardware setting, not a frequency test. [Half duplex](https://cubesat-resources.space/references/glossary/#duplex-half-full) means one
    radio and one antenna serve both directions, so the pass is split by the
    downlink share; full duplex means separate transmit and receive chains at
    both ends and each direction gets the whole pass. A frequency difference
    alone proves nothing, and full duplex on one frequency is flagged.

    **Bands are profiles.** A band changes the ground antenna, feed, LNA, antenna
    temperature and spacecraft antenna, not only a number, so there is no per-mode
    frequency column. The shipped BAC profiles name each other so drift is visible.

    **Volume.** Information rate × time × (1 − overhead) × direction share, over
    the seconds of each [pass](https://cubesat-resources.space/references/glossary/#pass)
    where the margin meets the target. For [LoRa](https://cubesat-resources.space/references/glossary/#lora)
    rows the information rate is the packet payload over its [time on air](https://cubesat-resources.space/references/glossary/#time-on-air) –
    programmed preamble plus 4.25 sync symbols, explicit header, CRC, the
    symbol rounding of the SX1276 datasheet Rev 5 §4.1.1.7 (p. 31) and
    low-data-rate optimization above 16 ms per symbol – so the framing
    overhead does not apply on top. The 10th percentile is over every
    simulated station-day, the days without a pass counted as zero. The saved
    profile carries the headline figures under `[results.link_budget]` and one
    `[[results.link_budget.modes]]` table per mode, with the LoRa packet
    airtime, for the sibling tools.

    **Station map.** The circle is the ground the station sees above the
    minimum [elevation angle](https://cubesat-resources.space/references/glossary/#elevation-angle),
    Earth-central angle arccos(R/(R+h)·cos ε) − ε. The
    [ground track](https://cubesat-resources.space/references/glossary/#ground-track)
    is one day of the first of the eight orbit phases the statistics average
    over; the map shows one phase, the numbers all eight.

    **Validation of the mode table.** A row is skipped and reported when its
    modulation is unknown, a required value is missing, a number is not finite,
    or its name repeats an earlier row's, because every curve and card looks a
    mode up by name. Profile values outside a control's range are clamped;
    profile values that are not numbers fall back to the default and are
    reported.

    ## Limitations

    Not modeled: [antenna patterns](https://cubesat-resources.space/references/glossary/#radiation-pattern) at either end, so nulls, tumble fades and
    partial deployment are invisible; [Doppler](https://cubesat-resources.space/references/glossary/#doppler-shift)
    (about ±11 kHz at 436 MHz and ±62 kHz at 2.45 GHz, plus 436 Hz or 2.45 kHz
    per ppm of oscillator error) and acquisition, assumed tracked; interference;
    transmit duty and power limits; a network of stations – this tool models one
    station holding a link at policy margin, and a network figure needs a station
    population, which is a study rather than a feature; a transmit schedule –
    volume assumes the spacecraft transmits whenever the link closes. Bit errors
    are independent in the FER view; fades and interference correlate them.

    Linked terms go to the CubeSat Resources glossary, [bac.page/glossary](https://bac.page/glossary).
    The sibling tools are the [Optical Payload](https://bac.page/molab-optical-payload)
    and the [Power Budget](https://bac.page/molab-power-budget); a profile saved
    from either loads here, and this tool's profile loads there. Source and
    issues: [bac-utils](https://github.com/buildacubesat/bac-utils).

    ## Validation

    For the same inputs this notebook agrees with the AMSAT/IARU Link Model
    Rev 2.5.5 within 0.03 dB below 2 GHz, once its noise is referenced to the
    same plane and its polarization loss set from the same axial ratios. Where
    the defaults differ it is in the allowances, not the physics.
    """
    mo.md(ASSUMPTIONS_MD)
    return (ASSUMPTIONS_MD,)


@app.cell
def _(mo):
    ACKNOWLEDGMENT_MD = """
    ## Acknowledgment

    The budget chain follows the AMSAT/IARU Annotated Link Model System by Jan
    King, W3GEY. Version 2.5.5 validated this notebook and the modulation library
    is his table. Gaseous absorption follows ITU-R P.676.

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
    | 0.7.4 | 2026-10-09 | Glossary links added on first use for J2, beamwidth, rotator, tumbling, noise figure, frame error rate, code rate, framing overhead, SNR, coherent detection, modulation index, duplex, time on air and radiation pattern; the noise and coded-entry sentences say what the receiver and the code rate contribute. The muted gray of chart subtitles, rules, axis lines and ticks takes the AA values of the shared tokens (#6C6B67 light, #A3A29C dark) instead of #888884. No change to the numbers. |
    | 0.7.3 | 2026-10-06 | The bac.page links point at the molab short links (`bac.page/molab-<tool>`); no other change. |
    | 0.7.2 | 2026-10-06 | Chart titles that Altair clipped at the chart width are split into a short title and a subtitle with the reading note (`chart_title` in the chart-conventions cell). No change to the numbers. |
    | 0.7.1 | 2026-10-06 | The BAC planning orbit is 500 km (was 450 km): both BAC profiles and the panel default move to 500 km; the sun-synchronous inclination for 500 km is 97.4° (the 450 km profiles carried that value already, computed for 500 km). Every result of the UHF and S-band profiles moves with the altitude. First edit made in the bac-utils repository; the molab copy is taken from here. |
    | 0.7.0 | 2026-09-14 | Review fixes: duplex is an explicit hardware setting under Spacecraft (half or full) and no longer inferred from a frequency difference, with a callout for full duplex on one frequency; the 10th-percentile day counts every simulated station-day, the ones without a pass as zero, and sits under the card whose margin it uses; a mode name that repeats an earlier row's is skipped and reported, since every curve and card looks a mode up by name; LoRa volumes use the packet payload over its time on air (SX1276 datasheet §4.1.1.7) from new payload and preamble inputs instead of the nominal rate less framing overhead; the target check covers every enabled direction, uplinks named as such; mode-table numbers must be finite or the row is skipped and reported; profile export escapes newlines, tabs and carriage returns. Follow-up round, mirroring the optical payload: dependencies as minimum bounds; profile names its tool and writes `[results.link_budget]` with the usable volume, its role, pass statistics and frequencies; a role dropdown (low rate / high rate); optical payload and power budget profiles load with their orbit and target or station, and their `[results]` tables feed two callouts – payload demand against this link and affordable pass minutes against the station's; two-column control panel with the custom station and custom antenna in accordions, in its own cell so the duplex note can sit under its dropdown and change with it; a station map with the visibility circle, one day of ground track and the samples in view; profile values clamped to control ranges and reported when unreadable; `fmt_num`; one `[[results.link_budget.modes]]` table per mode in the profile, so the power budget can take the LoRa backstop's airtime from the SF12 row. Homogenization: intro at the siblings' length with the tool's URL, its siblings, the project and the repository; the preliminary warning as a callout; export labels and profile file name as in the siblings; the "At 0 dB Margin" card captioned with its own per-pass figure. |
    | 0.6.0 | 2026-09-10 | Target margin policy 3 dB. Noise referenced to the LNA input: the antenna temperature is attenuated by the feeder and the feeder's own noise added, at both ends, with the three terms shown in the breakdown. Atmospheric loss is now the larger of King's elevation table and ITU-R P.676 gaseous absorption at the frequency in use, so S-band no longer borrows a UHF table; rain and other excess loss is an input. Polarization loss from the two axial ratios, worst case or average, replacing the 0.5 / 3 dB switch. Frame length and target frame error rate inputs: for entries on the ideal non-coherent FSK curve the tool shows the FER the library figure implies and the Eb/N0 the target needs, beside the library figure. Two provisional FEC entries for the native waveform: the AT86RF215 convolutional code and MCU Reed–Solomon; the provisional-threshold callout reworded to state the figure is theoretical rather than "unmeasured". A sixth headline card, "At 0 dB Margin", captioned with the 10th-percentile day as "more than … kB on 90% of days"; the headline cards now sit on two rows of three; longest gap between passes. Per-mode summary as CSV. Downlink share moved beside the frequencies. Profile status on its own line. Text tightened, assumptions split from limitations, US spelling, title-case headings, and "Link Budget Breakdown" for the line-item table. |
    | 0.5.2 | 2026-09-10 | Fix: a profile value with a decimal part under a key whose default is a whole number was truncated on load, so 7.4 dBi arrived as 7 dBi. Library entries carry a status: the GFSK and CW entries are marked provisional because their thresholds have never been measured for the receiver they name, and a callout and a line in the export say so when the featured mode uses one. A second CW entry at the BAC detector specification, 10 dB in 100 Hz, beside the aural one; the shipped mode table uses it. A GFSK h = 0.5 discriminator entry for the native S-band waveform, wired to the Custom Eb/N0 input because no defensible figure exists. The coherent GFSK entry is demoted to an optimistic reference bound. The 4k8 row leaves the default table and the BAC profile. Discovery Dish 70 cm ground-antenna preset, 22 dBi and 12.2° beamwidth. A third shipped profile for the BAC S-band downlink at 2'445 MHz, downlink rows only, naming its UHF sibling; a control-panel callout whenever a frequency above 2 GHz is set. |
    | 0.5.1 | 2026-09-10 | Mission profiles in TOML: load one to set the whole panel including the mode table, save the current settings from the export section, and two examples ship with the tool. Uplink and downlink at different frequencies are now treated as cross-band, where each direction gets the whole pass; the downlink share applies only when the two frequencies are equal. Library entries for GFSK at modulation index 1, coherent and non-coherent, and AX.100 Mode 5. Default altitude 450 km and a default mode table matching the SatNOGS-COMMS native waveform. Receiver sensitivity renamed to reference receive level, since the published figures are neither guaranteed nor uncoded. |
    | 0.5.0 | 2026-09-09 | Bandwidth is a column of the mode table, so LoRa rows at different bandwidths share one table and the global LoRa bandwidth dropdown is gone. Library entries carry a code rate: the entered bit rate is the channel rate, Eb/N0 and data volume use the information rate, and the overhead slider covers framing only. A third library kind for bandwidth-referenced modes without a bit rate, with a CW entry at −3.6 dB in 100 Hz (W2RS). Empty mode tables no longer raise. |
    | 0.4.3 | 2026-09-09 | Optional sidebar for the controls, so a chart and the control that changes it can be in view together. Headline cards name the minimum elevation in degrees. |
    | 0.4.2 | 2026-09-09 | Headline cards say which mode they describe once, above the row, so no caption is long enough to stretch its card. |
    | 0.4.1 | 2026-09-09 | The first Featured row now drives the uplink card, the sensitivity reference line and the export as well as the downlink headlines; the best uplink mode is used only when that row has no uplink, and the caption says so. Mode rows without a bit rate are reported instead of vanishing. Shorter ground-antenna preset names so the dropdown fits its column. Glossary links point at the canonical URLs; the export names the tool's link; a note on library names describing demodulators, not waveforms. |
    | 0.4.0 | 2026-09-08 | Settings and findings download as one markdown file, assumptions attached. Polarization spelled to match the CubeSat Resources glossary, with that term and bit error rate linked. |
    | 0.3.0 | 2026-09-08 | General-purpose release. Editable mode table with a modulation library (AFSK/FM, G3RUH FSK, coherent and non-coherent FSK, GMSK, BPSK, QPSK, coded BPSK, LoRa SF7–SF12). Separate uplink and downlink frequency, 30 MHz to 30 GHz. Elevation-dependent atmospheric loss and frequency-dependent ionospheric loss from King's tables. Uplink evaluated for every mode that asks for it, including LoRa. Station and ground-antenna presets, rotator switch with pointing loss derived from beamwidth and tracking error. Uplink capacity added to the headline. Default modulation changed to GMSK and spacecraft noise figure to the published 1.5 dB, which together move 9k6 at 10° by about 6 dB. |
    | 0.2.0 | 2026-09-08 | Separate transmit power for the LoRa modes. Pass statistics averaged over eight orbit phases. Line-item budget in the AMSAT/IARU subtotal layout. Charts: solid series with shape markers, dark-surface tints. |
    | 0.1.0 | 2026-09-08 | Initial version. Downlink and uplink margin versus elevation, numerical pass simulation, usable data per pass and per day, line-item budget. |
    """)
    return


if __name__ == "__main__":
    app.run()
