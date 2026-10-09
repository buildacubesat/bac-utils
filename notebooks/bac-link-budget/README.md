# bac-link-budget v0.7.4

Build a CubeSat – a first-order link budget between a satellite in low Earth orbit and one ground station, as a marimo notebook. For every mode in an editable table it gives the margin against elevation in both directions, the usable data per pass and per day at the target margin, and the line-item budget of the featured mode in the AMSAT/IARU layout; pass statistics come from a two-body propagation over a rotating spherical Earth, averaged over eight orbit phases. General purpose with the BAC demo mission as the shipped default; LoRa rows use the SX1276 packet airtime, duplex is a hardware setting, and a station map shows the visibility circle and one day of ground track.

Published at [bac.page/molab-link-budget](https://bac.page/molab-link-budget). Its siblings are the [Optical Payload](../bac-optical-payload/) and [Power Budget](../bac-power-budget/) notebooks, with which it exchanges mission profiles; the [Orbital Lifetime](../bac-orbital-lifetime/) notebook reads its orbit.

## 1. Run

```sh
uvx marimo edit --sandbox notebooks/bac-link-budget/bac_link_budget.py     # its own environment from the PEP 723 header
uv run --no-sync marimo edit notebooks/bac-link-budget/bac_link_budget.py   # the bac-utils workspace environment
```

The file runs on [molab](https://molab.marimo.io) unchanged; the bac.page link points at that copy, which is this file to the byte apart from the SPDX line at the top.

## 2. Profiles

The panel starts from the BAC demo mission on UHF. `examples/` holds the three profiles the notebook ships, as the "Download profile" button writes them: `bac-link-budget-profile-bac-demo-uhf.toml`, `bac-link-budget-profile-bac-demo-s-band.toml` (full duplex, 100k) and `bac-link-budget-profile-generic-amateur-1u.toml`. Load one with the button at the top of the notebook; a key you leave out keeps the default. The export carries `[results.link_budget]` – usable kB/day, pass statistics, one `[[results.link_budget.modes]]` table per mode – for the siblings, and ignores it when loaded back. An optical payload profile loads with its target as the station, a power budget profile with its orbit, station and downlink share.

## 3. Numbers at the defaults

Bern, 500 km SSO, 10° minimum elevation, 3 dB target, seven days × eight phases, half duplex, 80 % downlink share: 3.68 passes per day, 5.67 min mean pass, 20.9 min contact per day, 94.47 min period, 1'563 km visibility radius; 50k GFSK 3'171 kB/day at the target margin (2'720 kB on the 10th-percentile day, 5'005 kB at 0 dB), margin 1.0 dB at 10° and 12.7 dB at zenith, uplink 12.6 dB; LoRa SF7 3'559 bps information rate over a 71.9 ms packet, SF12 141 bps over 1'810 ms; the S-band profile 2'395 kB/day (400 kB on the 10th-percentile day). These are the regression figures `tests/test_link_budget.py` holds, from the 0.7.1 handoff. Against 450 km (0.7.0): 0.25 more passes and 2.8 more contact minutes per day, 0.7 dB less margin at 10° on every link, 50 kB/day less on UHF because fewer minutes of each longer pass clear the target.

## 4. Tests

```sh
uv run --no-sync pytest notebooks/bac-link-budget
```

The notebook runs once per test module through `notebooks/notebook_harness.py` (`app.run()`, then `defs`); profile tests run a patched copy with the profile swapped in for the upload element. The tests check the pass statistics, every row of the mode table, the LoRa airtime formula against the datasheet case, the export contract and its round trip, the S-band and generic profiles, duplicate mode names, and that `examples/` matches the shipped profile strings. `notebooks/tests/test_cross.py` checks the exchange with the siblings.

## 5. Version history

The notebook's revision-history cell has the full text of every row.

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.7.4 | 2026-10-09 | Glossary links added on first use (J2, beamwidth, rotator, tumbling, noise figure, frame error rate, code rate, framing overhead, SNR, coherent detection, modulation index, duplex, time on air, radiation pattern); the muted gray on the AA values of the shared tokens (#6C6B67 light, #A3A29C dark); numbers unchanged. |
| 0.7.3 | 2026-10-06 | bac.page links point at the molab short links. |
| 0.7.2 | 2026-10-06 | Chart titles that Altair clipped split into a short title and a subtitle (`chart_title`); numbers unchanged. |
| 0.7.1 | 2026-10-06 | The BAC planning orbit moves to 500 km (was 450 km) in both BAC profiles and the panel default; the regression figures re-recorded. First edit made in the repository. |
| 0.7.0 | 2026-09-14 | Review fixes (explicit duplex, 10th percentile over every station-day, unique mode names, LoRa packet airtime, every enabled direction checked, validated numbers, escaped export); interoperability contract with `[results.link_budget]` and per-mode tables; role dropdown; sibling profiles load; two-column panel; station map; homogenized intro, warning and export. Into bac-utils on 2026-10-02 as a byte-identical copy. |
| 0.6.0 | 2026-09-10 | 3 dB target policy; noise referenced to the LNA input; P.676 gaseous absorption beside King's table; polarization loss from two axial ratios; frame length and FER inputs; provisional FEC entries. |
| 0.5.2 | 2026-09-10 | Decimal profile values no longer truncated on load. |
| 0.5.1 | 2026-09-10 | Mission profiles in TOML: load, save, two shipped profiles (the third came with 0.5.2). |
| 0.5.0 | 2026-09-09 | Bandwidth as a mode-table column; LoRa rows at different bandwidths in one table. |
| 0.4.3 | 2026-09-09 | Optional sidebar for the controls; headline cards name the minimum elevation. |
| 0.4.2 | 2026-09-09 | Headline cards name their mode once, above the row. |
| 0.4.1 | 2026-09-09 | The first featured row drives the uplink card, the reference line and the export. |
| 0.4.0 | 2026-09-08 | Settings and findings download as one markdown file; glossary spelling. |
| 0.3.0 | 2026-09-08 | General-purpose release: editable mode table with a modulation library. |
| 0.2.0 | 2026-09-08 | Separate LoRa transmit power; eight-phase pass averages; AMSAT/IARU line-item layout. |
| 0.1.0 | 2026-09-08 | Initial version: margins versus elevation, pass simulation, usable data, line-item budget. |
