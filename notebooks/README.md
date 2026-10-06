# Engineering notebooks

Build a CubeSat – the marimo notebooks that estimate a mission's numbers: link budget, optical payload, power budget, orbital lifetime, and the antenna visualizer. Each one is a single Python file with PEP 723 metadata, runs on its own with `uvx marimo edit --sandbox <file>`, and – except the visualizer – on [molab](https://molab.marimo.io) in the browser, which is where the bac.page links point. This folder is the home of the files; the molab copies are taken from here.

## 1. Notebooks

| Notebook | File | Published | Version |
| :-- | :-- | :-- | :-- |
| Link Budget | `bac-link-budget/bac_link_budget.py` | [bac.page/link-budget-tool](https://bac.page/link-budget-tool) | 0.7.0 |
| Optical Payload | `bac-optical-payload/bac_optical_payload.py` | [bac.page/optical-payload-tool](https://bac.page/optical-payload-tool) | 0.7.0 |
| Power Budget | `bac-power-budget/bac_power_budget.py` | [bac.page/power-budget-tool](https://bac.page/power-budget-tool) | 0.5.0 |
| Orbital Lifetime | `bac-orbital-lifetime/bac_orbital_lifetime.py` | bac.page/orbital-lifetime-tool (link pending) | 0.2.0 |
| Antenna Visualizer | `bac-antenna-visualizer/bac_antenna_visualizer.py` | runs locally only (needs `bac-antenna-optimizer`) | 0.3.2 |
| Antenna Visualizer demo | `bac-antenna-visualizer/demo/bac_antenna_visualizer_demo.py` | uploaded to molab by hand with its pack; frozen snapshot, not a version of its own | of 0.3.2 |

Every notebook directory has the same shape: the notebook, a `README.md` with a version history, `tests/` with the headless checks, for the four published notebooks `examples/` with the profiles they ship as TOML files, and a small `pyproject.toml` that makes the directory a workspace member so `uv sync --all-packages` installs what the tests need. The orbital lifetime also carries `scripts/`, the offline builders of its embedded data tables.

## 2. Rules of the class

- **The file is the tool.** A notebook stays one file with PEP 723 metadata in minimum bounds (`numpy>=2.0`, never `==`), so molab and `uvx marimo edit --sandbox` resolve it alike. It cannot depend on `bac-common` or on anything outside Pyodide's package list; `rich`, `python-dotenv`, `sgp4` and `pymsis` are out. The visualizer is the exception: it runs locally and imports the optimizer; its demo under `demo/` is a frozen copy of it without that import, which is how it runs on molab (`bac-antenna-visualizer/README.md` §6).
- **Byte-identical with molab.** The four published notebooks are the molab copies to the byte (plus the SPDX line at the top). They are exempt from `ruff format` and `ruff check` in the root `pyproject.toml`; `marimo check` is their lint. An edit that changes numbers is a new version with a revision-history row and re-recorded regression figures in the tool's handoff; after such an edit the repository file goes to molab, never the other way round.
- **No `-v`, no `--help`.** The class is exempt from the CLI flags of the BAC Project & Tooling Guide §3.3: the version is `TOOL_VERSION` in the constants cell and in every export's header.
- **One profile contract.** The notebooks exchange TOML mission profiles (`tool`, `tool_version`, `[orbit]`, `[ground_station]`, `[target]`, `[map]`, `[results.<tool>]`; Tooling Guide §2.7.1). A tool loads what it understands from a sibling's profile and says what it ignored. `tests/test_cross.py` checks the exchange.
- **US spelling and title-case headings** inside the notebooks, as the guide's §4 says for this class.

## 3. Running and testing

```sh
uvx marimo edit --sandbox notebooks/bac-link-budget/bac_link_budget.py   # interactive, in its own environment
uv run --no-sync marimo edit notebooks/bac-power-budget/bac_power_budget.py   # interactive, in the workspace environment
uv run --no-sync marimo check notebooks/*/bac_*.py notebooks/*/demo/*.py  # the class's lint
uv run --no-sync pytest notebooks                                         # every headless check, about a minute
```

`notebook_harness.py` is the shared headless helper: `run(path)` executes a notebook with `app.run()` and returns its `defs`; `run(path, profile_toml)` does the same on a temporary copy with the profile swapped in for the upload element, which is how the tests load profiles without a browser. `conftest.py` puts it on the path for every notebook's `tests/`; run pytest from the repository root (any path under `notebooks/` works as the argument) so that this conftest is picked up.

## 4. Version history

This page follows the repository version; each notebook keeps its own history in its README and its revision-history cell.

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.8.1 | 2026-10-06 | The antenna visualizer's demo snapshot for molab under `bac-antenna-visualizer/demo/`, with tests; `marimo check` covers `notebooks/*/demo/*.py` too. |
| 0.8.0 | 2026-10-02 | The group created: the four published notebooks (link budget 0.7.0, optical payload 0.7.0, power budget 0.5.0, orbital lifetime 0.2.0) as byte-identical copies with example profiles and regression tests from their handoffs; the antenna visualizer moved in from `tools/` as 0.3.2; the shared harness; `marimo check` and the tests in CI. |
