# BAC Antenna Visualizer

A marimo notebook that shows how an antenna's characteristics move when its geometry moves. It reads a *sensitivity pack* – the set of simulations `bac-antenna pack` writes for one antenna, one parameter varied at a time around the nominal design – and puts a slider on every axis. The 3D geometry is rebuilt from the optimizer's model at every slider position; the numbers, S-parameters, gain and axial ratio, pattern cuts, the 3D pattern and the field planes follow by interpolating between the neighboring simulated cases along the axis you moved. A sensitivity table gives the slope of each quantity per unit of each parameter and how straight that line is.

Views: reflection and coupling, a Smith chart of one probe with the impedance at the band edges and centre, gain and axial ratio versus frequency, pattern cuts, the 3D pattern, the electric field on the dumped planes in 3D, and the geometry in 3D.

Part of Build a CubeSat's [bac-utils](https://github.com/buildacubesat/bac-utils) (`notebooks/bac-antenna-visualizer/`), next to its four sibling notebooks and to [bac-antenna-optimizer](../../tools/bac-antenna-optimizer/), which makes the packs. The notebook itself runs locally and has no hosted copy; a frozen demo snapshot of it is uploaded to molab by hand (§6).

## 1. Run

```bash
cd ~/bac/bac-utils && uv sync --inexact --all-packages       # once; the optimizer is a workspace member
cd notebooks/bac-antenna-visualizer
uv run marimo edit --no-sandbox bac_antenna_visualizer.py   # or `uv run marimo run …` for the app view
uv run python -m unittest discover -s tests                 # headless checks; no FDTD data needed
```

`--no-sandbox` keeps marimo in the workspace environment. Without it marimo offers to build a sandbox from the notebook's inline metadata; that works too (the metadata names the optimizer as a path source), but it builds a second environment for nothing.

## 2. Where it finds packs

At start the notebook looks, in this order, for pack folders and pack zips:

1. the folders named in `BAC_ANTENNA_PACKS` (colon-separated; each may be a pack, a folder of packs or an antenna folder);
2. its own `packs/` folder (gitignored – drop release zips there);
3. the antenna folders of a bac-hardware checkout next to bac-utils (`../../../bac-hardware/rf/antenna/*/generated/sensitivity*` and `*-pack.zip`, relative to the notebook).

Every pack found appears in the dropdown under Other Packs, in that order. A path or URL of a pack folder or pack zip, or an uploaded zip, loads too – a release asset URL works directly. The status line under Control Panel says which pack is loaded and from where.

With bac-hardware checked out next to bac-utils, the S-band packs are found without any setup as soon as they have been generated there.

## 3. Packs

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

## 4. Glossary

Technical terms in the notebook link to the CubeSat Resources glossary (`cubesat-resources.space/references/glossary/#<slug>`). Slugs used that the glossary does not carry yet, to be added: `resonance`, `realized-gain`, `impedance-matching`, `hybrid-coupler`, `smith-chart`, `boresight`, `radiation-pattern`, `beamwidth`, `fdtd`. `axial-ratio` exists.

## 5. What it is not

Every number between simulated levels is a linear interpolation along one axis. With several sliders off nominal the headline numbers add the single-axis changes and say so; interactions are not modeled, and the charts follow the axis moved furthest. For the combined case, simulate it – the optimizer takes the same config and design.

## 6. Demo for molab

`demo/bac_antenna_visualizer_demo.py` is a frozen snapshot of the notebook that runs on [molab](https://molab.marimo.io) without the optimizer. Upload the file and a pack zip into the same molab folder; the demo finds packs beside itself (also in a `packs/` subfolder, the working directory and the file's own folder), and a path or an upload under Other Packs works too. Three things differ from the tracked notebook:

- **Geometry from the pack.** Instead of rebuilding the model live from the optimizer, the demo takes the stored models in `models.json`: at a simulated level the case's own model, between two levels a straight-line blend of the two neighboring models along the axis moved furthest – the same rule the charts use. For dimensions that move the primitives linearly – all five swept in the S-band packs do – the blend equals the live model to floating-point precision (`tests/test_demo.py` checks the synthetic pack against the optimizer's live model, and for both S-band packs that the blend of the two outermost cases reproduces every inner case's stored model). It falls back to the nearer case when the two models differ in structure, and to the nearest case with a stored model when one is missing. With several sliders off nominal the geometry follows the axis moved furthest, where the tracked notebook shows the combined position.
- **Packs beside the file** instead of a bac-hardware checkout or `BAC_ANTENNA_PACKS`.
- **No URL loading** – WebAssembly has no sockets.

A Snapshot callout at the top names the visualizer version and the packs it was frozen with (`TOOL_VERSION`, `SNAPSHOT_DATE`, `DEMO_PACKS` in the constants cell); the file has no version of its own and is not updated when the notebook changes – a new snapshot replaces it. The pack zips beside it are not tracked (`.gitignore`); the uploaded copy on molab is by hand, like the four published notebooks. `tests/test_demo.py` runs the demo headless on a synthetic pack, compares the blended geometry with the optimizer's live model, and – when pack zips sit in `demo/` – on those too.

## 7. Files

```
bac_antenna_visualizer.py     the notebook
packs/                        local pack folders or zips (gitignored)
demo/bac_antenna_visualizer_demo.py   the frozen demo snapshot for molab (§6); pack zips beside it are gitignored
tests/test_notebook.py        headless run on a pack the tool builds during the test, and on any pack found on the machine
tests/test_demo.py            the demo on the same synthetic pack, its geometry against the live model, and the pack zips in demo/
tests/visualizer_testkit.py   builds the synthetic pack for both test modules
pyproject.toml                dependencies; the optimizer as a workspace dependency
tests/conftest.py             puts the notebook and the test helper on the path for the workspace pytest
```

## 8. Version history

The notebook's own revision history (its last cell) has the detail per version.

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.3.2 | 2026-10-06 | Demo snapshot for molab added under `demo/` with tests (§6); README headings numbered. No change to the notebook. |
| 0.3.2 | 2026-10-02 | Moved from `tools/` to the `notebooks/` group with its four siblings; the paths it names follow. No change to what it shows. |
| 0.3.1 | 2026-10-02 | Brought onto the bac-utils conventions: SPDX header, ruff, tests collectable by the workspace pytest, a minimum version on the optimizer dependency. No change to what it shows. |
| 0.3.0 | 2026-09-28 | Runs locally only; molab code paths, the GitHub fallback and the wheel workflow removed; packs discovered from `BAC_ANTENNA_PACKS`, `packs/` and a bac-hardware checkout. |
| 0.2.0 | 2026-09-24 | Family conventions: the siblings' style and chart cells, two-column panel, headline cards, Smith chart, 3D pattern and field views in 0.2.x. |
| 0.1.0 | 2026-09-24 | First version: pack loader, one-axis interpolation, S-parameters, gain and axial ratio, pattern cuts. |
