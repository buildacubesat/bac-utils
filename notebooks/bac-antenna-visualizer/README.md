# BAC Antenna Visualizer

A marimo notebook that shows how an antenna's characteristics move when its geometry moves. It reads a *sensitivity pack* – the set of simulations `bac-antenna pack` writes for one antenna, one parameter varied at a time around the nominal design – and puts a slider on every axis. The 3D geometry is rebuilt from the optimizer's model at every slider position; the numbers, S-parameters, gain and axial ratio, pattern cuts, the 3D pattern and the field planes follow by interpolating between the neighboring simulated cases along the axis you moved. A sensitivity table gives the slope of each quantity per unit of each parameter and how straight that line is.

Views: reflection and coupling, a Smith chart of one probe with the impedance at the band edges and centre, gain and axial ratio versus frequency, pattern cuts, the 3D pattern, the electric field on the dumped planes in 3D, and the geometry in 3D.

Part of Build a CubeSat's [bac-utils](https://github.com/buildacubesat/bac-utils) (`notebooks/bac-antenna-visualizer/`), next to its four sibling notebooks and to [bac-antenna-optimizer](../../tools/bac-antenna-optimizer/), which makes the packs. It runs locally; there is no hosted copy.

## Run

```bash
cd ~/bac/bac-utils && uv sync --inexact --all-packages       # once; the optimizer is a workspace member
cd notebooks/bac-antenna-visualizer
uv run marimo edit --no-sandbox bac_antenna_visualizer.py   # or `uv run marimo run …` for the app view
uv run python -m unittest discover -s tests                 # headless checks; no FDTD data needed
```

`--no-sandbox` keeps marimo in the workspace environment. Without it marimo offers to build a sandbox from the notebook's inline metadata; that works too (the metadata names the optimizer as a path source), but it builds a second environment for nothing.

## Where it finds packs

At start the notebook looks, in this order, for pack folders and pack zips:

1. the folders named in `BAC_ANTENNA_PACKS` (colon-separated; each may be a pack, a folder of packs or an antenna folder);
2. its own `packs/` folder (gitignored – drop release zips there);
3. the antenna folders of a bac-hardware checkout next to bac-utils (`../../../bac-hardware/rf/antenna/*/generated/sensitivity*` and `*-pack.zip`, relative to the notebook).

Every pack found appears in the dropdown under Other Packs, in that order. A path or URL of a pack folder or pack zip, or an uploaded zip, loads too – a release asset URL works directly. The status line under Control Panel says which pack is loaded and from where.

With bac-hardware checked out next to bac-utils, the S-band packs are found without any setup as soon as they have been generated there.

## Packs

A pack is what `bac-antenna pack design/sensitivity.toml` writes into an antenna folder's `generated/sensitivity*/`, and with `--zip` also as `<name>-pack.zip` beside it:

| file | content |
|---|---|
| `pack.json` | axes, levels and the case behind each, nominal case, bands and targets, provenance (source, release, tool version) |
| `cases.csv.gz` | one row per case: parameters, axis values, band metrics, resonance, load fraction, pattern summary |
| `sweeps.csv.gz`, `samples.csv.gz` | S-parameters (including the complex probe reflection) and broadside gain/AR versus frequency |
| `cuts.csv.gz`, `sphere.csv.gz` | pattern cuts and the full sphere at band centre |
| `efield.csv.gz` | \|E\| on each dumped plane, resampled, for the cases run with field dumps |
| `models.json` | geometry primitives per case |
| `config.toml`, `design.json` | the nominal antenna, from which the live geometry is rebuilt |

Packs are not tracked in git; the pack zip attached to the antenna's release is the archival copy, and a checkout regenerates them from the antenna folder's runs. To refresh the S-band packs:

```bash
cd <bac-hardware>/rf/antenna/s-band-cross-patch
uv run --project <bac-utils>/tools/bac-antenna-optimizer --extra report bac-antenna pack design/sensitivity.toml --zip
uv run --project <bac-utils>/tools/bac-antenna-optimizer --extra report bac-antenna pack design/sensitivity-2400.toml --zip
```

Axes are defined in the antenna's `design/sensitivity*.toml`: each axis names the design parameters (`params`) or the config key (`set`) it moves, its levels, and any extra overrides its runs need (`also`); `ignore` lists config keys a run may change without counting as a different antenna; `source` and `release` are shown in the status line. Levels without a run are written to a sweep plan.

## Glossary

Technical terms in the notebook link to the CubeSat Resources glossary (`cubesat-resources.space/references/glossary/#<slug>`). Slugs used that the glossary does not carry yet, to be added: `resonance`, `realized-gain`, `impedance-matching`, `hybrid-coupler`, `smith-chart`, `boresight`, `radiation-pattern`, `beamwidth`, `fdtd`. `axial-ratio` exists.

## What it is not

Every number between simulated levels is a linear interpolation along one axis. With several sliders off nominal the headline numbers add the single-axis changes and say so; interactions are not modeled, and the charts follow the axis moved furthest. For the combined case, simulate it – the optimizer takes the same config and design.

## Files

```
bac_antenna_visualizer.py     the notebook
packs/                        local pack folders or zips (gitignored)
tests/test_notebook.py        headless run on a pack the tool builds during the test, and on any pack found on the machine
pyproject.toml                dependencies; the optimizer as a workspace dependency
tests/conftest.py             puts the notebook on the path for the workspace pytest
```

## Version history

The notebook's own revision history (its last cell) has the detail per version.

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.3.2 | 2026-10-02 | Moved from `tools/` to the `notebooks/` group with its four siblings; the paths it names follow. No change to what it shows. |
| 0.3.1 | 2026-10-02 | Brought onto the bac-utils conventions: SPDX header, ruff, tests collectable by the workspace pytest, a minimum version on the optimizer dependency. No change to what it shows. |
| 0.3.0 | 2026-09-28 | Runs locally only; molab code paths, the GitHub fallback and the wheel workflow removed; packs discovered from `BAC_ANTENNA_PACKS`, `packs/` and a bac-hardware checkout. |
| 0.2.0 | 2026-09-24 | Family conventions: the siblings' style and chart cells, two-column panel, headline cards, Smith chart, 3D pattern and field views in 0.2.x. |
| 0.1.0 | 2026-09-24 | First version: pack loader, one-axis interpolation, S-parameters, gain and axial ratio, pattern cuts. |
