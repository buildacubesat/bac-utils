# bac-power-budget v0.5.4

Build a CubeSat – a first-order energy balance on one timeline, as a marimo notebook. The optical payload's propagator (two-body plus J2, RAAN from the LTDN, Almanac Sun, 10 s steps) is extended with the link budget's station test and a per-face illumination model, so one run gives, per sample, sunlit or in shadow, over the station, over the target and whether the target is lit. Generation comes from the cells on each face under one of three attitude models, consumption from an editable table of average watts per mode, the beacon from cadence arithmetic, and the two integrate into a battery state of charge with a safe-mode fallback. Payload activations come from one of nine trigger modes with gates and caps. Six cards answer what duty cycle the radio and the camera can have before the battery goes negative.

Published at [bac.page/molab-power-budget](https://bac.page/molab-power-budget). Its siblings are the [Link Budget](../bac-link-budget/) and [Optical Payload](../bac-optical-payload/) notebooks, with which it exchanges mission profiles.

## 1. Run

```sh
uvx marimo edit --sandbox notebooks/bac-power-budget/bac_power_budget.py
uv run --no-sync marimo edit notebooks/bac-power-budget/bac_power_budget.py
```

The file runs on [molab](https://molab.marimo.io) unchanged; the bac.page link points at that copy, which is this file to the byte apart from the SPDX line at the top.

## 2. Profiles

The panel starts from the BAC demo mission (1.5U, LG MJ1 2S2P, Anysolar SM141K10TF modules on the four side faces, the placeholder loads). `examples/` holds the two shipped profiles: `bac-power-budget-profile-bac-demo-1u5.toml` and `bac-power-budget-profile-generic-1u.toml`. Loads travel in the profile as `[[loads]]` tables; the export adds `[results.power_budget]` for the siblings. A link budget profile loads with its station, downlink share and the LoRa SF12 packet airtime for the backstop beacon, and its pass statistics feed a cross-check callout; an optical payload profile with its target, half its swath as the reach, its frames per day and its Sun-elevation gate, its 30-day span clamped to the 7-day slider.

## 3. Numbers at the defaults

500 km SSO, LTDN 10:30, epoch 2027-06-21, two days, tumbling, 50 °C cells, 2S2P modules as shipped: 50.3 Wh/day generated at the battery against 89.5 Wh/day asked by the nominal schedule; requested margin −1.63 W, run margin −0.30 W after 23.2 h of safe mode; worst state of charge 39 %; eclipse fraction 37 %; CW beacon 5.76 Wh/day; pack 50.9 Wh with 15.3 Wh usable at 30 % depth of discharge; module MPP 10.0 V hot against the 11.7 V the LTM8062 needs, so the charger-headroom callout fires; 4.0 passes per day over Bern; sustainable pass minutes and frames 0 because the nominal watts alone exceed generation. These are the regression figures `tests/test_power_budget.py` holds, from the 0.5.1 handoff; every load in the BAC profile is a labelled placeholder.

## 4. Tests

```sh
uv run --no-sync pytest notebooks/bac-power-budget
```

Through `notebooks/notebook_harness.py` as the siblings: the energy balance, pack and charger figures, single-phase pass statistics, the order of the mode totals, the export contract and its round trip, the generic profile, invalid loads reported, and that `examples/` matches the shipped profile strings. `notebooks/tests/test_cross.py` checks the exchange with the siblings.

## 5. Version history

The notebook's revision-history cell has the full text of every row.

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.5.4 | 2026-10-09 | Power rails link to a power-rail glossary entry instead of the deployer-rail one; first-use links added (solar strings, tumbling, nadir, degraded mode, time on air, orbit-average power, load shedding, eFuses); the muted gray on the AA values of the shared tokens (#6C6B67 light, #A3A29C dark); numbers unchanged. |
| 0.5.3 | 2026-10-06 | bac.page links point at the molab short links. |
| 0.5.2 | 2026-10-06 | The shared `chart_title` helper added to the chart-conventions cell; numbers unchanged. |
| 0.5.1 | 2026-10-06 | The BAC planning orbit moves to 500 km (was 450 km) in the BAC profile and the panel default; the regression figures re-recorded. First edit made in the repository. |
| 0.5.0 | 2026-09-14 | Homogenization with the siblings: intro, warning, title-case headings, assumptions with glossary links, report header and export text; two cross-checks from the siblings' results tables; profile author detection by signature table; the LoRa backstop's airtime from a link budget 0.7.0 profile; the beacon ladder documented in the BAC profile. Into bac-utils on 2026-10-02 as a byte-identical copy. |
| 0.4.1 | 2026-09-14 | Tighter wording; Schedule at the top; charts fill the width; passes and activations as bands. |
| 0.4.0 | 2026-09-14 | Panel wording, S and P module controls, modules to 4U, three rows of two cards, radio row; GUI-review fixes to the activation mechanics and face packing. |
| 0.3.0 | 2026-09-14 | Nine payload trigger modes with gates and caps; configurable modules with a fit check; review fixes (rated irradiance per cell, radio controls set the radio row, mode columns are the draw in that mode, validated loads, requested against run margin). |
| 0.2.0 | 2026-09-13 | Imaging generalized to payload; more cells; volts beside the SoC sliders; beacon policy; scenarios explained. |
| 0.1.0 | 2026-09-13 | Initial version: one timeline, per-face generation, loads per mode, beacon, state of charge with safe mode. |
