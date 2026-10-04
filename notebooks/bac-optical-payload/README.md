# bac-optical-payload v0.7.0

Build a CubeSat – a first-order model of what a camera on a small satellite produces, as a marimo notebook with two modes. **Earth observation**: sensor, lens and orbit in; ground sample distance, swath and field of view, Rayleigh spot and sampling factor Q, motion and attitude smear, rolling-shutter skew, the footprint envelope and geolocation uncertainty, frame sizes raw, compressed and as a thumbnail, days to downlink, and access and illumination over a target with the access edges solved between samples. **Boom**: the same camera on a deployable boom looking back at the spacecraft – fill fraction, corners in frame, side view, a sweep of fill against boom length, and a depth-of-field check. A camera dropdown sets sensor and lens from a product (Raspberry Pi cameras, CHC5 modules, action cameras, DJI O4 air units, a phone).

Published at [bac.page/optical-payload-tool](https://bac.page/optical-payload-tool). Its siblings are the [Link Budget](../bac-link-budget/) and [Power Budget](../bac-power-budget/) notebooks, with which it exchanges mission profiles.

## 1. Run

```sh
uvx marimo edit --sandbox notebooks/bac-optical-payload/bac_optical_payload.py
uv run --no-sync marimo edit notebooks/bac-optical-payload/bac_optical_payload.py
```

The file runs on [molab](https://molab.marimo.io) unchanged; the bac.page link points at that copy, which is this file to the byte apart from the SPDX line at the top. The map's tiles and coastline need the browser online.

## 2. Profiles

The panel starts from the BAC primary imager (IMX477, C-mount 16 mm f/1.4, 450 km, Bern). `examples/` holds the three shipped profiles: `bac-optical-payload-profile-bac-demo-primary-imager.toml`, `bac-optical-payload-profile-bac-demo-boom-camera.toml` and `bac-optical-payload-profile-generic-1u-camera-module-3.toml`. The export carries `[map]` and `[results.optical_payload]` (frames, sizes, reach) for the siblings. A link budget profile loads with its station as the target and its usable kB/day as the downlink volume; a power budget profile with its activation location, planned activations and Sun-elevation gate.

## 3. Numbers at the defaults

43.6 m GSD at nadir, 176.8 × 132.5 km swath, 22.23° × 16.75° field, 26.4 m Rayleigh spot, Q 0.50, 0.08 px motion smear, 3.3 px skew, 18'495 kB raw and 1'850 kB compressed per frame, 93.44 min period, 88.4 km reach at nadir and 49.0 km net of the pointing error, two accesses over Bern in 30 days of 12.8 s and 8.1 s. Boom profile: 38.4 % fill, 8 of 8 corners, 598 mm to the center, hyperfocal 11'437 mm, depth of field 569–631 mm. Generic 1U: 147.7 m GSD, 0.53 accesses per day. These are the regression figures `tests/test_optical_payload.py` holds, from the 0.7.0 handoff.

## 4. Tests

```sh
uv run --no-sync pytest notebooks/bac-optical-payload
```

Through `notebooks/notebook_harness.py` as the siblings: the Earth geometry, data volume, reach and solved accesses, the spherical ground-offset helper, the boom and generic profiles, the focus refusal, the export contract and that `examples/` matches the shipped profile strings. `notebooks/tests/test_cross.py` checks the exchange with the siblings, including the 5.74 days to downlink a raw frame on the link budget's 3'221 kB/day.

## 5. Version history

The notebook's revision-history cell has the full text of every row.

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.7.0 | 2026-09-14 | Review fixes (accesses solved between samples, saved sensor and lens win over the preset, capacity import says when it has nothing, impossible focus refused, one spherical ground geometry, IMX296 color with a mono row); DJI O4 presets; power budget profiles load; `[map]` shared with the link budget; `reach_km` in the results; homogenized intro, warning, headings and assumptions. Into bac-utils on 2026-10-02 as a byte-identical copy. |
| 0.6.0 | 2026-09-13 | Camera dropdown with product presets; TT240-40 lens; `tool` and `[results.optical_payload]` in the profile; link budget profiles load. |
| 0.5.3 | 2026-09-13 | RunCam 5 and iPhone 18 Pro as scale references; lens circle fixes; 6 mm CS-mount lens. |
| 0.5.2 | 2026-09-11 | Depth of field in the boom views behind a switch. |
| 0.5.1 | 2026-09-11 | Downlink defaults revisited; BAC profiles carry the link budget's volumes. |
| 0.5.0 | 2026-09-11 | Earth observation mode named; thirteen target presets with a custom option; map at full width. |
| 0.4.0 | 2026-09-11 | Grayscale CARTO tiles following the theme; every map layer clipped. |
| 0.3.0 | 2026-09-11 | Map at the top of the results with tiles under the coastline. |
| 0.2.0 | 2026-09-11 | Common and mode columns in the panel; boom sweep, face labels, side view. |
| 0.1.0 | 2026-09-10 | Initial version: Earth observation geometry, smear, skew, pointing, access, data volume; boom mode. |
