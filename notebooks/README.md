# Engineering notebooks

Build a CubeSat – the marimo notebooks that estimate a mission's numbers: link budget, optical payload, power budget, orbital lifetime, and the antenna visualizer. Each one is a single Python file with PEP 723 metadata, runs on its own with `uvx marimo edit --sandbox <file>`, and – except the visualizer – on [molab](https://molab.marimo.io) in the browser, which is where the bac.page links point. This folder is the home of the files; the molab copies are taken from here.

## 1. Notebooks

| Notebook | File | Published | Version |
| :-- | :-- | :-- | :-- |
| Link Budget | `bac-link-budget/bac_link_budget.py` | [bac.page/link-budget-tool](https://bac.page/link-budget-tool) | 0.7.2 |
| Optical Payload | `bac-optical-payload/bac_optical_payload.py` | [bac.page/optical-payload-tool](https://bac.page/optical-payload-tool) | 0.7.2 |
| Power Budget | `bac-power-budget/bac_power_budget.py` | [bac.page/power-budget-tool](https://bac.page/power-budget-tool) | 0.5.2 |
| Orbital Lifetime | `bac-orbital-lifetime/bac_orbital_lifetime.py` | bac.page/orbital-lifetime-tool (link pending) | 0.2.3 |
| Antenna Visualizer | `bac-antenna-visualizer/bac_antenna_visualizer.py` | runs locally only (needs `bac-antenna-optimizer`) | 0.3.3 |
| Antenna Visualizer demo | `bac-antenna-visualizer/demo/bac_antenna_visualizer_demo.py` | mirrored to molab from GitHub; fetches its packs from `demo/packs/`; frozen snapshot, not a version of its own | of 0.3.3 |

Every notebook directory has the same shape: the notebook, a `README.md` with a version history, `tests/` with the headless checks, for the four published notebooks `examples/` with the profiles they ship as TOML files, and a small `pyproject.toml` that makes the directory a workspace member so `uv sync --all-packages` installs what the tests need. The orbital lifetime also carries `scripts/`, the offline builders of its embedded data tables.

## 2. Rules of the class

- **The file is the tool.** A notebook stays one file with PEP 723 metadata in minimum bounds (`numpy>=2.0`, never `==`), so molab and `uvx marimo edit --sandbox` resolve it alike. It cannot depend on `bac-common` or on anything outside Pyodide's package list; `rich`, `python-dotenv`, `sgp4` and `pymsis` are out. The visualizer is the exception: it runs locally and imports the optimizer; its demo under `demo/` is a frozen copy of it without that import, which is how it runs on molab (`bac-antenna-visualizer/README.md` §6).
- **The repository is the source, molab the copy.** Since 0.8.2 the four published notebooks are edited here, formatted and linted by the repository's ruff like every other file (the notebook-specific exemptions are E501, B018 and F841 – see the root `pyproject.toml`), and `marimo check` is their second lint. An edit that changes numbers is a new version with a revision-history row and re-recorded regression figures in the tool's README and handoff; after such an edit the repository file goes to molab, never the other way round. The molab copies of 2026-10-02 (0.7.0 / 0.7.0 / 0.5.0 / 0.2.0) are the last ones that were byte-identical with the files here.
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
| 0.8.4 | 2026-10-06 | The orbital lifetime's "Solar Activity Assumed" chart drew nothing in the browser (a dotted field name) – 0.2.3; the visualizer demo fetches its packs from `demo/packs/` in the repository when none are beside it, so the molab mirror works without uploads. |
| 0.8.3 | 2026-10-06 | Chart titles that Altair clipped at the chart width are split into a short title and a subtitle in all five notebooks – `chart_title(text, *notes)` joins the chart-conventions cell; link budget 0.7.2, optical payload 0.7.2, power budget 0.5.2, orbital lifetime 0.2.2, visualizer 0.3.3. |
| 0.8.2 | 2026-10-06 | The BAC planning orbit moves to 500 km in the four published notebooks (link budget 0.7.1, optical payload 0.7.1, power budget 0.5.1, orbital lifetime 0.2.1), their profiles, defaults, tests and READMEs; the lifetime takes the siblings' chart-conventions and style cells; the four files formatted and linted by ruff from now on, the exemptions dropped. |
| 0.8.1 | 2026-10-06 | The antenna visualizer's demo snapshot for molab under `bac-antenna-visualizer/demo/`, with tests; `marimo check` covers `notebooks/*/demo/*.py` too. |
| 0.8.0 | 2026-10-02 | The group created: the four published notebooks (link budget 0.7.0, optical payload 0.7.0, power budget 0.5.0, orbital lifetime 0.2.0) as byte-identical copies with example profiles and regression tests from their handoffs; the antenna visualizer moved in from `tools/` as 0.3.2; the shared harness; `marimo check` and the tests in CI. |
