# bac-orbital-lifetime v0.2.5

Build a CubeSat – the order-of-magnitude lifetime of a CubeSat in a circular low Earth orbit, as a marimo notebook. The orbit decays under drag at −√(μa)·ρ·F/B until 120 km; the density is NRLMSIS 2.1 averaged along the orbit and embedded as a table, and the solar activity that drives it comes from the observed F10.7 and Ap record, the NOAA SWPC Cycle 25 prediction with its 75 % band, and a climatology of past cycles for whatever lies past the forecast. Ten scenarios run through the same spacecraft – NOAA nominal, low and high, six replays of past cycles, one constant-flux case – and the band they span is the answer; callouts judge it against the mission and the 5-year and 25-year disposal rules. Size, mass, deployables (which may deploy at end of mission, as a drag sail would) and an attitude switch at end of mission set the ballistic coefficient; a launch-date sweep shows where in the solar cycle a mission starts.

Published at [bac.page/molab-orbital-lifetime](https://bac.page/molab-orbital-lifetime). It is the fourth sibling of the [Link Budget](../bac-link-budget/), [Optical Payload](../bac-optical-payload/) and [Power Budget](../bac-power-budget/) notebooks and reads the orbit from their profiles.

## 1. Run

```sh
uvx marimo edit --sandbox notebooks/bac-orbital-lifetime/bac_orbital_lifetime.py
uv run --no-sync marimo edit notebooks/bac-orbital-lifetime/bac_orbital_lifetime.py
```

The file is about 175 kB because the density table and the solar snapshot are embedded as a few long data lines; the code itself is about 2'300 lines after the repository's formatter. It runs on [molab](https://molab.marimo.io) unchanged. With the NOAA switch on it fetches the current prediction (`urllib` on CPython, `pyodide.http` in the browser); otherwise it uses the embedded snapshot and says so.

## 2. Data tables and their builders

`scripts/build_density_table.py` builds the orbit-averaged NRLMSIS 2.1 table (altitude × F10.7 × Ap × inclination) with `pymsis`; `scripts/build_solar_snapshot.py` assembles the observed record and the NOAA prediction, with `scripts/noaa_predicted_f107_2026-09-17.txt` as the snapshot it was built from. Both run as `uv run scripts/<name>.py` and print the string the notebook's data cell carries; the data cell is pasted from them, never edited by hand.

## 3. Numbers at the defaults

BAC demo mission, 500 km SSO, 2.0 kg, four tape antennas, launch 2027-06, NOAA snapshot: 5.90 years in the NOAA nominal case, 4.90 years in the shortest and 7.14 years in the longest scenario, 478.2 km at end of mission, ballistic coefficient 38.5 kg/m², 0.0236 m² drag area before and after the attitude switch, 4.89 min/yr local-time drift at start; the 5-year rule is met in the nominal case and missed in the longest, the 25-year rule is met throughout. These are the regression figures `tests/test_orbital_lifetime.py` holds, from the 0.2.1 edit. At 450 km (0.2.0) they were 2.39 / 1.47 / 4.21 years, 350.6 km and 2.45 min/yr – the 50 km lift more than doubles the lifetime, which is what moves the five-year rule from comfortable to marginal.

## 4. Profiles

The panel starts from the BAC demo mission (1.5U, 2.0 kg placeholder, 500 km SSO, launch 2027-06 placeholder, four tape antennas). `examples/` holds the two shipped profiles: `bac-orbital-lifetime-profile-bac-demo-500km-sso.toml` and `bac-orbital-lifetime-profile-generic-3u-500km-sso.toml` (two deployed wings, Z face into the flow during the mission, tumbling after). The export carries `[results.orbital_lifetime]` with the lifetime band and every scenario. A sibling's profile loads its `[orbit]` only; a `[spacecraft]` table shared with the power budget is proposed for the Tooling Guide.

## 5. Tests

```sh
uv run --no-sync pytest notebooks/bac-orbital-lifetime
```

Sixteen checks through `notebooks/notebook_harness.py`: the regression figures above, plausible defaults, the drag-area geometry, the density table against `pymsis` recomputed along the orbit, the propagator against `scipy`'s integrator on the same rate function, monotonic sweeps, the decay-rate sign and scale, the profile round trip, the generic profile, a sibling's profile taking the orbit only, out-of-range and bad values clamped and reported, the analog scenarios bracketing the band, the small LTDN drift of an SSO, the launch-date sweep's shape, deployment at end of mission, and that `examples/` matches the shipped profile strings. `pymsis` and `scipy` are test dependencies only.

## 6. Open items

From the 0.2.0 handoff: validate against flown CubeSats' TLE histories and against DAS; eccentric orbits, propulsion and re-entry date prediction are out of scope by decision; the BAC placeholders (antenna geometry, launch date, delivered inclination). Since 0.2.1 the style cell is the siblings' byte-identical one and the chart-conventions cell follows their shape (palette list, `style_chart(chart)`, `rule_x`/`rule_y`) plus this tool's scenario map.

## 7. Version history

The notebook's revision-history cell has the full text of every row.

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.2.5 | 2026-10-09 | The LTDN glossary link fixed (`#ltdn` does not exist); first-use links added for the drag, solar and disposal terms; closing line linked as in the siblings; the muted gray on the AA values of the shared tokens (#6C6B67 light, #A3A29C dark); numbers unchanged. |
| 0.2.4 | 2026-10-06 | bac.page links point at the molab short links. |
| 0.2.3 | 2026-10-06 | The "Solar Activity Assumed" chart was empty in the browser (a dot in the data column name, which Vega-Lite reads as nested access); fixed, numbers unchanged. |
| 0.2.2 | 2026-10-06 | Every chart title split into a short title and a subtitle with the reading note; the decay title no longer repeats the legend; numbers unchanged. |
| 0.2.1 | 2026-10-06 | The BAC planning orbit moves to 500 km (was 450 km) with the 97.4° inclination; the siblings' style cell and chart-conventions shape replace the reconstructed ones (nebula series colors); the regression figures re-recorded. First edit made in the repository. |
| 0.2.0 | 2026-09-18 | Lifetime against launch date sweep (quarterly over eight years, three NOAA scenarios); deployables can deploy at end of mission; scenario sources in the CSV. Into bac-utils on 2026-10-02 as a byte-identical copy with its scripts and tests. |
| 0.1.0 | 2026-09-17 | First version: NRLMSIS 2.1 table, NOAA prediction with band, six analog cycles, constant case, deployables, attitude switch, local time drift, sensitivity sweeps, profile contract with `[results.orbital_lifetime]`. |
