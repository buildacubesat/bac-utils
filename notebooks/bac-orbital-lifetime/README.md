# bac-orbital-lifetime v0.2.0

Build a CubeSat – the order-of-magnitude lifetime of a CubeSat in a circular low Earth orbit, as a marimo notebook. The orbit decays under drag at −√(μa)·ρ·F/B until 120 km; the density is NRLMSIS 2.1 averaged along the orbit and embedded as a table, and the solar activity that drives it comes from the observed F10.7 and Ap record, the NOAA SWPC Cycle 25 prediction with its 75 % band, and a climatology of past cycles for whatever lies past the forecast. Ten scenarios run through the same spacecraft – NOAA nominal, low and high, six replays of past cycles, one constant-flux case – and the band they span is the answer; callouts judge it against the mission and the 5-year and 25-year disposal rules. Size, mass, deployables (which may deploy at end of mission, as a drag sail would) and an attitude switch at end of mission set the ballistic coefficient; a launch-date sweep shows where in the solar cycle a mission starts.

Published at bac.page/orbital-lifetime-tool once the short link exists. It is the fourth sibling of the [Link Budget](../bac-link-budget/), [Optical Payload](../bac-optical-payload/) and [Power Budget](../bac-power-budget/) notebooks and reads the orbit from their profiles.

## 1. Run

```sh
uvx marimo edit --sandbox notebooks/bac-orbital-lifetime/bac_orbital_lifetime.py
uv run --no-sync marimo edit notebooks/bac-orbital-lifetime/bac_orbital_lifetime.py
```

The file is 168 kB because the density table and the solar snapshot are embedded as a few long data lines; the code itself is about 1'800 lines. It runs on [molab](https://molab.marimo.io) unchanged. With the NOAA switch on it fetches the current prediction (`urllib` on CPython, `pyodide.http` in the browser); otherwise it uses the embedded snapshot and says so.

## 2. Data tables and their builders

`scripts/build_density_table.py` builds the orbit-averaged NRLMSIS 2.1 table (altitude × F10.7 × Ap × inclination) with `pymsis`; `scripts/build_solar_snapshot.py` assembles the observed record and the NOAA prediction, with `scripts/noaa_predicted_f107_2026-09-17.txt` as the snapshot it was built from. Both run as `uv run scripts/<name>.py` and print the string the notebook's data cell carries; the data cell is pasted from them, never edited by hand.

## 3. Numbers at the defaults

BAC demo mission, 450 km SSO, 2.0 kg, four tape antennas, launch 2027-06, NOAA snapshot: 2.39 years in the NOAA nominal case, 1.47 years in the shortest and 4.21 years in the longest scenario, 350.6 km at end of mission, ballistic coefficient 38.5 kg/m², 0.0236 m² drag area before and after the attitude switch, 2.45 min/yr local-time drift at start; both the 5-year and the 25-year rule are met. These are the regression figures `tests/test_orbital_lifetime.py` holds; they move with step 5c's 500 km orbit.

## 4. Profiles

The panel starts from the BAC demo mission (1.5U, 2.0 kg placeholder, 450 km SSO, launch 2027-06 placeholder, four tape antennas). `examples/` holds the two shipped profiles: `bac-orbital-lifetime-profile-bac-demo-450km-sso.toml` and `bac-orbital-lifetime-profile-generic-3u-500km-sso.toml` (two deployed wings, Z face into the flow during the mission, tumbling after). The export carries `[results.orbital_lifetime]` with the lifetime band and every scenario. A sibling's profile loads its `[orbit]` only; a `[spacecraft]` table shared with the power budget is proposed for the Tooling Guide.

## 5. Tests

```sh
uv run --no-sync pytest notebooks/bac-orbital-lifetime
```

Sixteen checks through `notebooks/notebook_harness.py`: the regression figures above, plausible defaults, the drag-area geometry, the density table against `pymsis` recomputed along the orbit, the propagator against `scipy`'s integrator on the same rate function, monotonic sweeps, the decay-rate sign and scale, the profile round trip, the generic profile, a sibling's profile taking the orbit only, out-of-range and bad values clamped and reported, the analog scenarios bracketing the band, the small LTDN drift of an SSO, the launch-date sweep's shape, deployment at end of mission, and that `examples/` matches the shipped profile strings. `pymsis` and `scipy` are test dependencies only.

## 6. Open items

From the 0.2.0 handoff: validate against flown CubeSats' TLE histories and against DAS; eccentric orbits, propulsion and re-entry date prediction are out of scope by decision; the BAC placeholders (antenna geometry, launch date, delivered inclination). The chart-conventions cell was written from the guide's description without the siblings' source and differs from theirs in shape (a named-colour palette and a `height` argument that its charts use); aligning it is bundled with the next number-changing edit (the 500 km planning orbit, 0.2.1) rather than done on the byte-identical copy.

## 7. Version history

The notebook's revision-history cell has the full text of every row.

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.2.0 | 2026-09-18 | Lifetime against launch date sweep (quarterly over eight years, three NOAA scenarios); deployables can deploy at end of mission; scenario sources in the CSV. Into bac-utils on 2026-10-02 as a byte-identical copy with its scripts and tests. |
| 0.1.0 | 2026-09-17 | First version: NRLMSIS 2.1 table, NOAA prediction with band, six analog cycles, constant case, deployables, attitude switch, local time drift, sensitivity sweeps, profile contract with `[results.orbital_lifetime]`. |
