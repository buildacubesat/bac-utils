# Engineering notebooks

Build a CubeSat – the marimo notebooks that estimate a mission's numbers: link budget, optical payload, power budget, orbital lifetime, and the antenna visualizer. Each one is a single Python file with PEP 723 metadata, runs on its own with `uvx marimo edit --sandbox <file>`, and – except the visualizer – in the browser, which is where the bac.page links go: `bac.page/molab-<tool>-app` opens a notebook in app mode on marimo.app, ready to use, and `bac.page/molab-<tool>` opens it as a notebook in [molab](https://molab.marimo.io)'s editor. Both read the file from this repository's `main` branch, so a merged change is live at once and there is no copy to keep in step.

## 1. Notebooks

| Notebook | File | App | Notebook on molab | Version |
| :-- | :-- | :-- | :-- | :-- |
| Link Budget | `bac-link-budget/bac_link_budget.py` | [bac.page/molab-link-budget-app](https://bac.page/molab-link-budget-app) | [bac.page/molab-link-budget](https://bac.page/molab-link-budget) | 0.7.6 |
| Optical Payload | `bac-optical-payload/bac_optical_payload.py` | [bac.page/molab-optical-pld-app](https://bac.page/molab-optical-pld-app) | [bac.page/molab-optical-pld](https://bac.page/molab-optical-pld) | 0.7.6 |
| Power Budget | `bac-power-budget/bac_power_budget.py` | [bac.page/molab-power-budget-app](https://bac.page/molab-power-budget-app) | [bac.page/molab-power-budget](https://bac.page/molab-power-budget) | 0.5.6 |
| Orbital Lifetime | `bac-orbital-lifetime/bac_orbital_lifetime.py` | [bac.page/molab-orbital-lifetime-app](https://bac.page/molab-orbital-lifetime-app) | [bac.page/molab-orbital-lifetime](https://bac.page/molab-orbital-lifetime) | 0.2.7 |
| Antenna Visualizer | `bac-antenna-visualizer/bac_antenna_visualizer.py` | runs locally only (needs `bac-antenna-optimizer`) | – | 0.3.7 |
| Antenna Visualizer demo | `bac-antenna-visualizer/demo/bac_antenna_visualizer_demo.py` | [bac.page/molab-antenna-viz-app](https://bac.page/molab-antenna-viz-app) | [bac.page/molab-antenna-viz](https://bac.page/molab-antenna-viz); fetches its packs from `demo/packs/`; frozen snapshot, not a version of its own | of 0.3.7 |

Every notebook directory has the same shape: the notebook, a `README.md` with a version history, `tests/` with the headless checks, for the four published notebooks `examples/` with the profiles they ship as TOML files, and a small `pyproject.toml` that makes the directory a workspace member so `uv sync --all-packages` installs what the tests need; its version follows the notebook's `TOOL_VERSION`. The orbital lifetime also carries `scripts/`, the offline builders of its embedded data tables.

## 2. Rules of the class

- **The file is the tool.** A notebook stays one file with PEP 723 metadata in minimum bounds (`numpy>=2.0`, never `==`), so molab and `uvx marimo edit --sandbox` resolve it alike. It cannot depend on `bac-common` or on anything outside Pyodide's package list; `rich`, `python-dotenv`, `sgp4` and `pymsis` are out. The visualizer is the exception: it runs locally and imports the optimizer; its demo under `demo/` is a frozen copy of it without that import, which is how it runs on molab (`bac-antenna-visualizer/README.md` §6).
- **The repository is the source; the links read it.** Since 0.8.2 the four published notebooks are edited here, formatted and linted by the repository's ruff like every other file (the notebook-specific exemptions are E501, B018 and F841 – see the root `pyproject.toml`), and `marimo check` is their second lint. An edit that changes numbers is a new version with a revision-history row and re-recorded regression figures in the tool's README and handoff. Since 0.14.1 the bac.page links open the files from `main` on molab and marimo.app, so a merge publishes; nothing is copied anywhere.
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
| 0.16.2 | 2026-10-24 | Chart colors under marimo's "system" theme: `mo.app_meta().theme` reports the setting, "light" under "system", so the conventions cell cannot know the surface – and marimo's frontend can: on a dark surface it hands vega-embed the dark theme, which sets text, axis lines and ticks unless the spec names them. The six notebooks and the pricing notebook stop naming them (Vega's defaults on light, the dark theme on dark), use one series palette, the lighter nebula tints that read on a dark surface too, and drop the style cell's `.vega-embed text` rule, which never reached a chart (canvas inside a shadow root); `IS_DARK` keeps steering the muted rules, the band strip and the map tiles, which follow the explicit setting only. `notebooks/tests/test_theme.py` keeps the class on that shape. Link budget 0.7.6, optical payload 0.7.6 (its frame-view face labels in the muted gray), power budget 0.5.6, orbital lifetime 0.2.7, visualizer 0.3.7 (its band strip the yellow at low opacity on either surface; demo re-snapshotted), `bac-pricing` 1.4.2. No number changes. |
| 0.14.1 | 2026-10-12 | Two bac.page links per notebook: `bac.page/molab-<tool>-app` opens it in app mode on marimo.app, ready to use, `bac.page/molab-<tool>` as a notebook in molab's editor; both read the file from this repository's `main`, so the molab copies are gone and a merge publishes. Every intro links both for the tool itself and the app link for its siblings, the closing section both for each sibling. The optical payload's short link is `molab-optical-pld`, the visualizer demo's `molab-antenna-viz`. Link budget 0.7.5, optical payload 0.7.5, power budget 0.5.5, orbital lifetime 0.2.6, visualizer 0.3.6 (demo re-snapshotted). No number changes. |
| 0.14.0 | 2026-10-09 | Glossary links checked against the CubeSat Resources glossary: two anchors that did not exist fixed (`#ltdn`, `#beamwidth`), the power rails moved off the deployer-rail entry, first-use links added across the five notebooks; every linked entry is in the glossary. The muted gray of chart subtitles, rules, axis lines and ticks takes the AA values of the shared tokens (#6C6B67 light, #A3A29C dark) instead of #888884, and so does the pricing notebook (`bac-pricing` 1.4.1). Link budget 0.7.4, optical payload 0.7.4, power budget 0.5.4, orbital lifetime 0.2.5, visualizer 0.3.5 (demo re-snapshotted). The optical payload's assumptions name both readings of Q, resolution and Nyquist sampling, as the glossary does. No number changes. The row below carried 0.8.6 by mistake; this page follows the repository version. |
| 0.13.0 | 2026-10-08 | Each folder's `pyproject.toml` version follows the notebook's `TOOL_VERSION` again – four had kept the version they joined with (link budget and optical payload 0.7.0, power budget 0.5.0, orbital lifetime 0.2.0); `tests/test_versions.py` keeps them equal. No notebook changed. |
| 0.8.5 | 2026-10-06 | The bac.page links are the molab short links (`bac.page/molab-<tool>`, plus `molab-antenna-viz-demo`); link budget 0.7.3, optical payload 0.7.3, power budget 0.5.3, orbital lifetime 0.2.4, visualizer 0.3.4. |
| 0.8.4 | 2026-10-06 | The orbital lifetime's "Solar Activity Assumed" chart drew nothing in the browser (a dotted field name) – 0.2.3; the visualizer demo fetches its packs from `demo/packs/` in the repository when none are beside it, so the molab mirror works without uploads. |
| 0.8.3 | 2026-10-06 | Chart titles that Altair clipped at the chart width are split into a short title and a subtitle in all five notebooks – `chart_title(text, *notes)` joins the chart-conventions cell; link budget 0.7.2, optical payload 0.7.2, power budget 0.5.2, orbital lifetime 0.2.2, visualizer 0.3.3. |
| 0.8.2 | 2026-10-06 | The BAC planning orbit moves to 500 km in the four published notebooks (link budget 0.7.1, optical payload 0.7.1, power budget 0.5.1, orbital lifetime 0.2.1), their profiles, defaults, tests and READMEs; the lifetime takes the siblings' chart-conventions and style cells; the four files formatted and linted by ruff from now on, the exemptions dropped. |
| 0.8.1 | 2026-10-06 | The antenna visualizer's demo snapshot for molab under `bac-antenna-visualizer/demo/`, with tests; `marimo check` covers `notebooks/*/demo/*.py` too. |
| 0.8.0 | 2026-10-02 | The group created: the four published notebooks (link budget 0.7.0, optical payload 0.7.0, power budget 0.5.0, orbital lifetime 0.2.0) as byte-identical copies with example profiles and regression tests from their handoffs; the antenna visualizer moved in from `tools/` as 0.3.2; the shared harness; `marimo check` and the tests in CI. |
