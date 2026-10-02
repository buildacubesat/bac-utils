# bac-antenna-optimizer

A workflow around [openEMS](https://openems.de) for designing antennas that have to be right before anyone builds them: parametric geometry, automatic meshing rules, band targets and scoring, a fast pre-tuner, circular-polarization post-processing, unattended tolerance sweeps, and a report pipeline that turns a run directory into charts, drawings, KiCad board files and a datasheet.

Part of Build a CubeSat's [bac-utils](https://github.com/buildacubesat/bac-utils) (`tools/bac-antenna-optimizer/`). The antennas designed with it live in [bac-hardware](https://codeberg.org/buildacubesat-project/bac-hardware) under `rf/antenna/`, each with an `antenna.toml` that pins the tool tag (`bac-antenna-optimizer-vX.Y.Z`). The first of them is the camera-through S-band cross patch; the engineering log of that design is `HANDOFF.md`.

## What the tool does, and what openEMS does

openEMS is the solver: an open-source FDTD field solver you drive from Python with CSXCAD for the geometry. It has no GUI, no automatic meshing and no optimizer, and most of the ways a simulation goes wrong are in the mesh. This tool is the layer above it:

- **An antenna is a few numbers.** A design is a JSON of parameters (`{"length_mm": 320}`), a config is a TOML with the target bands, the feed network, the mesh rules and a `[geometry]` section owned by the antenna type. The tool builds the openEMS model from that; changing a design never means editing solver code.
- **Meshing rules, applied every time.** Cells per wavelength, metal-edge refinement, a minimum number of cells across thin gaps and boards, fine cells around small features, an air margin sized to the boundary condition.
- **Targets and scoring.** Each band has limits for match, gain (in the wanted hand), axial ratio and efficiency; a run ends in a score, not a pile of curves.
- **Ports first, the network afterwards.** Every port is simulated alone; the feed network (a 90° hybrid, a turnstile harness, anything) is applied as complex weights in post-processing, with its real phase and amplitude errors if you give them. Reflected power that a hybrid would dump in its load is reported as such.
- **Fast estimates.** A cavity model tunes patch antennas in seconds; `--backend coarse` runs openEMS on a coarse mesh for everything else.
- **Sweeps.** Plan files list the cases; the runner works through them unattended, resumes after a stop, and can redo the post-processing from saved field data without rerunning the solver.
- **Checks.** Radiated power against accepted power, the polarization hand calibrated against a helix of known sense, a mesh-convergence case in every sweep.
- **Reports.** `bac-antenna report antenna.toml` writes charts (S-parameters, Smith chart, gain and AR versus frequency, pattern cuts, 3D pattern, field planes), drawings, KiCad board files and templated documents from the run results.

## Install

openEMS itself: the build script in the [openEMS-Project](https://github.com/thliebig/openEMS-Project) repository is the reliable route; distribution packages exist but are often old. Then, in this folder:

```bash
uv sync --extra simulation --extra report
export CSXCAD_INSTALL_PATH=<openEMS install> OPENEMS_INSTALL_PATH=<openEMS install>
uv pip install <openEMS-Project>/CSXCAD/python <openEMS-Project>/openEMS/python
uv run python -c "import openEMS, CSXCAD; print('ok')"
uv run python -m unittest discover -s tests     # no openEMS needed for the tests
```

From then on use `uv run` or `uv sync --inexact`; a plain `uv sync` removes the openEMS bindings.

## Quick start

```bash
# the smallest example: a half-wave dipole, coarse mesh, a few seconds
uv run bac-antenna simulate -c config/dipole_435.toml -p designs/dipole_435.json --backend coarse --output runs/dipole
# look at what you built (ParaView) before believing any number
paraview runs/dipole/geometry.vtp

# a patch antenna: cavity estimate in seconds, then the full run (~2 min)
uv run bac-antenna check -c config/cross_2200_dual_v2.toml
uv run bac-antenna optimize -c config/cross_2200_dual_v2.toml --backend cavity --runs 100 --output runs/opt
uv run bac-antenna simulate -c config/cross_2200_dual_v2.toml -p designs/cross_2200_dual_v2.json --output runs/frozen

# tolerances, unattended and resumable
uv run bac-antenna sweep -c config/cross_2200_dual_v2.toml -p designs/cross_2200_dual_v2.json --plan plans/freeze.toml --output runs/freeze
uv run bac-antenna sweep ... --reprocess     # redo post-processing from saved fields (new columns, new outputs)

# an antenna folder: drawings, charts, boards, README from templates (see bac-hardware/rf/antenna/*)
uv run --extra report bac-antenna report <folder>/antenna.toml
```

Commands: `check` (cavity estimate, patches only), `optimize`, `simulate`, `sweep`, `report`, `pack` (sensitivity pack for the [antenna visualizer](../bac-antenna-visualizer/): `bac-antenna pack design/sensitivity.toml`), `migrate` (0.5 → 0.6 file layout). Backends: `cavity` (patches, seconds), `coarse` (openEMS, coarse mesh), `openems`, `mock` (for testing the loop).

## Antenna types

Built in: `cross_patch` and `annular_ring` (patches over a ground plane with a camera bore, capacitive probe feeds, single or dual), `dipole` (the example), `turnstile` (four tape elements on the end face of a body, four ports). A config picks one:

```toml
[antenna]
type = "cross_patch"            # or "file:design/model.py" for your own, see below
```

Everything the type needs lives in `[geometry]` and is validated by the type. Everything else in the config is generic:

| section | what |
|---|---|
| `[[band]]` | name, `low_hz`, `high_hz`, `weight` (0 = reported only), `max_s11_db`, `min_gain_dbic`, `max_ar_db`, `cp_span_hz` |
| `[polarization]` | `hand` (rhcp/lhcp), `openems_rhcp_sense` (the calibrated sign, see HANDOFF §8) |
| `[feed_network]` | `mode` single / quadrature / turnstile / custom (default from the port count), `phase_error_deg`, `amplitude_error_db`, `weights` |
| `[search]`, `[fixed]` | parameter ranges the optimizer samples, and fixed values |
| `[optimizer]`, `[weights]` | the search schedule and the score weights |
| `[mesh]` | `cells_per_wavelength`, `air_margin_mm`, `boundary`, excitation band, `frequency_points`, `end_criteria`, `mesh_growth`, plus the patch-specific `gap_cells`, `substrate_cells`, `refine_cell_mm` |
| `[pattern]`, `[dump]` | far-field cut resolution and planes; E-field dumps on the type's field planes |

Configs in `config/` are examples and test fixtures; a real antenna's configs live in its folder in bac-hardware.

### Writing your own

An antenna type is a small Python class. The dipole is the whole of it:

```python
from bac_antenna.antennas import AntennaType
from bac_antenna.geometry import PRIORITY_METAL, FieldPlane, Model, Port, Primitive


class Dipole(AntennaType):
    name = "dipole"
    params = ("length_mm",)  # what the optimizer varies; ranges come from [search]

    def valid(self, p, config):  # constraints between parameters
        return p["length_mm"] > 2 * config.geometry["gap_mm"]

    def model(self, p, config):  # geometry, ports, mesh hints
        g = config.geometry
        w, gap, h = g["strip_width_mm"], g["gap_mm"], p["length_mm"] / 2
        arms = (
            Primitive("box", "arm", "metal", PRIORITY_METAL, start=(gap / 2, -w / 2, 0), stop=(h, w / 2, 0)),
            Primitive("box", "arm", "metal", PRIORITY_METAL, start=(-h, -w / 2, 0), stop=(-gap / 2, w / 2, 0)),
        )
        port = Port((-gap / 2, 0, 0), (gap / 2, 0, 0), "x", 73.0)
        return Model(
            arms,
            (port,),
            fixed_lines={"x": (-h, -gap / 2, gap / 2, h), "y": (-w / 2, w / 2), "z": (0.0,)},
            bounds=(-h, h, -w / 2, w / 2, 0, 0),
            edge_props=("arm",),
            field_planes=(FieldPlane("E_plane", (-1e9, -1e9, 0), (1e9, 1e9, 0)),),
        )


ANTENNA = Dipole()
```

Save it as `design/model.py` next to your config, set `type = "file:design/model.py"`, and every command works on it: `simulate --backend coarse` for a first look, `optimize`, `sweep`, `report`. Primitives are boxes, cylinders, polygons and extruded polygons with a material (`metal`, or `dielectric` with `epsilon_r` and `loss_tangent`); ports are lumped ports along x, y or z; `fixed_lines` are the mesh lines that must exist (every thin sheet and feed needs one), `bounds` is the structure's extent, `phase_centre` the far-field reference, `edge_props` the metals whose edges get refined, `field_planes` where E-field dumps are taken. Optional: `shape()` for the cavity estimator (patches), `report_values()` / `report_globals()` for template values, `exporters` for drawings and board files.

## Sensitivity packs

`bac-antenna pack design/sensitivity.toml` reads an axes file in the antenna folder (which parameter or config key each slider moves, its levels, where the runs are), matches existing cases to the levels by their effective parameters, writes a sweep plan for the levels without a run, and packs the matched cases' small result files into `generated/sensitivity/` (gzipped CSV + JSON, a few MB) for the [antenna visualizer](../bac-antenna-visualizer/) – including the complex probe reflection for the Smith chart and, when the `report` extra (h5py) is installed, the resampled E-field planes of cases run with dumps. `--zip` also writes `<name>-pack.zip` beside the folder, the form to attach to the antenna's release; `--public <dir>` copies the folder elsewhere. `source` and `release` in the axes file travel into `pack.json` as provenance, and so does the tool version.

## Images

Line charts and drawings are SVG. Raster output – the 3D pattern, the field planes and the drawing renders – is lossless WebP (Pillow, in the `report` extra), a third to a half the size of the PNGs it replaces; PNG leftovers from earlier versions are removed when the WebP is written. The templates reference `.webp`. Drawings are SVG only.

A regenerate of an unchanged folder is byte-identical apart from the date line in `STATUS.md`: board UUIDs are derived, not random, and the chart SVGs carry no timestamp. In a checkout without `sim/runs`, `report` stops before touching documents and boards (`--allow-missing` overrides).

## Outputs of a run

`result.json` (band metrics, score), `openems_diagnostics.json` (per-port S at band centre, power reflected into the feed network, probe resonance, pattern summary, power cross-check), `s11_sweep.csv` (network input), `sparams.csv` / `sparams_complex.csv` (per port), `farfield_samples.csv`, `farfield_cuts.csv`, `farfield_sphere.csv`, `geometry.vtp` / `geometry.xml`, and per port `simulation_port*/` with the field data (large; the antenna folders' `.gitignore` drops it). Sweeps add `sweep_summary.csv`, one row per case.

## Before trusting a number

Look at `geometry.vtp` in ParaView. Run the mesh-refinement case, and keep `end_criteria` at 1e-5: openEMS does not stop at the same timestep twice, and at 1e-4 that costs a point of efficiency and half a point of run-to-run spread. Check `p_rad_over_p_acc` in the diagnostics is below 1 and close to the expected efficiency. For circular polarization, make sure `polarization.openems_rhcp_sense` was calibrated (HANDOFF §8) – the hand of every CP statement rests on it. Then build the antenna and measure it; the simulation is only as good as its comparison with a VNA.

## Version history

The engineering log in `HANDOFF.md` dates every version from 0.1.0 (2026-09-20) on; this table carries the releases that matter to a user of the tool.

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.7.4 | 2026-10-02 | Brought onto the bac-utils conventions: SPDX headers, ruff, en dash in the generated tables, tests collectable by the workspace pytest, hatchling. One fix: `report/drawings.py` used an f-string form that only Python 3.12 parses, so the report pipeline failed to import on 3.11. No change to any model, mesh or result. |
| 0.7.3 | 2026-09-28 | Idempotent regenerate: deterministic KiCad UUIDs and SVG ids, no drawing rasters, the missing-runs guard (`--allow-missing`). The version pinned by the S-band cross patch in bac-hardware (tag `bac-antenna-optimizer-v0.7.3`). |
| 0.7.2 | 2026-09-28 | Lossless WebP for raster images, `pack --zip`, provenance fields in `pack.json`, pack discovery inside a bac-hardware checkout. |
| 0.7.0 | 2026-09-24 | Sensitivity packs (`bac-antenna pack`) for the visualizer. |
| 0.6.0 | 2026-09-24 | General-purpose core: antenna types as plugins, `[feed_network]`, the coarse estimator, `bac-antenna migrate`. |
| 0.5.0 | 2026-09-23 | Report pipeline: drawings, charts, KiCad board files and the antenna folder from templates. |
| 0.1.0 | 2026-09-20 | Optimisation scaffold with the cavity model and the openEMS backend. |
