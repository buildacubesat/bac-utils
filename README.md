# bac-utils

Build a CubeSat – the utilities that keep the project running: KiCad release and library tooling, antenna simulation, Blender video editing helpers, media conversion, content and resource pipelines, repository checks, and the business operations suite. Every tool follows the [BAC Project & Tooling Guide](https://buildacubesat.space) and the BAC Interface Design Guide, so they look and behave alike: the same flags, the same terminal output, the same config locations.

The repository holds the generally usable state of each tool. Anything specific to one project – vendor prices, sheet IDs, repository paths, plugin locations – lives in your own config and data directories, created by each tool's `--init`. What ships here is the tool, sample data under `examples/`, and an `.env.example` where secrets are involved. See §6 to adapt a tool for your own project.

## 1. Tools

This table is the record of what exists, what is being worked on and what is planned; an available tool's name links to its directory: **available** has a tool directory, tests and a version; **in progress** has a directory on a branch or a concept note and work under way; **planned** has a decided home here and nothing built yet. Tools are listed by name within their group: libraries, command-line tools (with the one Tk window and the gallery), notebooks, the web app, the operations suite, the Blender extension.

| Tool | Type | Domain | What it does | Status | Version |
| :-- | :-- | :-- | :-- | :-- | :-- |
| [`bac-common`](lib/bac-common/) | library | CLI scaffold | Shared CLI scaffold: standard flags, TOML config, `.env` loading, `--init` helpers, the BAC terminal profile, error boundary, span-preserving s-expression parser, STEP header metadata, Google Sheets reader (`gsheets` extra), test harness | available | v0.4.1 |
| [`bac-kicad-common`](lib/bac-kicad-common/) | library | KiCad | Shared KiCad library tooling: TOML field rules, property rendering for KiCad 9 and 10, span edits, write-back with backup | available | v0.1.0 |
| [`bac-suite-db`](lib/bac-suite-db/) | library | ops | Shared PostgreSQL layer of the operations suite: `bac.items` and `bac.catalog`, bootstrap config and the DSN in `.env`, the SKU scheme as a parser, an engine registry, the `bac-db` command (migrate, import, export, status) | available | v0.1.0 |
| [`bac-antenna-optimizer`](tools/bac-antenna-optimizer/) | CLI | RF | Antenna design around openEMS: parametric geometry, meshing rules, band targets, cavity-model pre-tuner, tolerance sweeps, sensitivity packs, reports with drawings, charts and KiCad board files | available | v0.7.4 |
| [`bac-cad-preview`](tools/bac-cad-preview/) | CLI | CAD | Renders STEP, STL and 3MF files to 720 px WebP previews framed like the KiCad artifacts render, with an X/Y/Z scale gizmo; the preview stage of the planned `bac-freecad-generate-artifacts` | available | v0.5.0 |
| [`bac-can-up`](tools/bac-can-up/) | CLI | bench | Brings up the CANable SLCAN interface: fresh `slcand`, bitrate, `can0` up | available | v1.2.0 |
| `bac-catalog` | CLI | store | Builds the static part catalog the builder reads from the `part.toml` files next to the hardware designs | planned | – |
| [`bac-convention-check`](tools/bac-convention-check/) | CLI | repo | Lints a tree against the BAC guides (typography, naming, licensing, packaging, flags); runs in this repo's CI | available | v0.2.1 |
| [`bac-csr-ingest`](tools/bac-csr-ingest/) | CLI | resources | Ingests documents and links into the CubeSat Resources site: extraction, LLM classification, review, upload, index, commit | available | v0.4.0 |
| `bac-freecad-generate-artifacts` | CLI | CAD | FreeCAD counterpart of the KiCad artifacts tool: exports the file types and iterations of a part through the FreeCAD CLI, renders previews (absorbs `bac-cad-preview`), fills missing author, organisation and part metadata in STEP and 3MF output | planned | – |
| [`bac-issue-print`](tools/bac-issue-print/) | CLI | repo | Prints a Codeberg issue with all comments as Markdown | available | v0.1.0 |
| [`bac-kicad-generate-artifacts`](tools/bac-kicad-generate-artifacts/) | CLI | KiCad | Produces the release bundle for a KiCad project through kicad-cli: render, pinout, schematic PDF, BOM, iBOM, Gerbers, drills, centroid, STEP with header metadata, QR code on a copy of the board, manufacturing ZIP; panels without a schematic | available | v0.6.1 |
| [`bac-kicad-hlabels`](tools/bac-kicad-hlabels/) | CLI | KiCad | Emits hierarchical-label blocks for a list of net names, ready to paste into a schematic | available | v0.1.0 |
| [`bac-kicad-libcheck`](tools/bac-kicad-libcheck/) | CLI | KiCad | Verifies a library project: every symbol and footprint placed once, 3D models resolvable, in sync per KiCad's ERC/DRC | available | v0.2.0 |
| `bac-kicad-maintain` | CLI | KiCad | Maintenance of project files: text and courtyard normalisation on boards, via resizing, schematic label sizes, library namespace migration, size statistics | planned | – |
| [`bac-kicad-schfields`](tools/bac-kicad-schfields/) | CLI | KiCad | Bulk-edits symbol fields and flags across a schematic hierarchy from TOML rules | available | v0.2.0 |
| [`bac-kicad-symfields`](tools/bac-kicad-symfields/) | CLI | KiCad | Fills fields, lints and fixes text sizes and footprint references in symbol and footprint libraries, preserving file formatting | available | v0.3.0 |
| [`bac-markdown-to-youtube`](tools/bac-markdown-to-youtube/) | CLI | content | Converts Markdown to YouTube description markup | available | v0.2.0 |
| [`bac-media-convert`](tools/bac-media-convert/) | CLI | media | Batch conversions: square WebP for the store, constant-frame-rate MP4 from variable-rate WebM | available | v0.1.1 |
| [`bac-reference-gallery`](tools/bac-reference-gallery/) | CLI and pages | design | Seven design-reference boards for the three BAC guides (identity, Ops and Mission, documents, interface patterns, charts, hardware, a product sheet) in light and dark, `tokens.css` as the shared stylesheet the other BAC surfaces take their values from, and a renderer to PNG and PDF through a headless Chromium | available | v0.3.0 |
| [`bac-store-product-cropper`](tools/bac-store-product-cropper/) | Tk GUI | media | Framing product photos for the store by hand, one window per batch, each crop exported as WebP under a size target; may later fold into a store artifact-generation tool | available | v0.2.0 |
| [`bac-update-content-plan`](tools/bac-update-content-plan/) | CLI | content | Renders the content plan from a Google Sheet into the docs repository as one Markdown table; commits and pushes on request | available | v0.4.1 |
| [`bac-antenna-visualizer`](notebooks/bac-antenna-visualizer/) | marimo notebook | RF | A slider per geometry parameter over an optimizer sensitivity pack: S-parameters, Smith chart, gain and axial ratio, pattern cuts, 3D pattern and fields; runs locally, with a frozen demo snapshot for molab under `demo/` that fetches its packs from the repository | available | v0.3.4 |
| `bac-battery-pack` | marimo notebook | power | Battery pack configuration (cell, S × P, depth of discharge, temperature) and aging: cycle and calendar capacity fade over the mission, usable energy at end of life, the pack figures the power budget takes | planned | – |
| [`bac-link-budget`](notebooks/bac-link-budget/) | marimo notebook | RF | Link budget for a CubeSat radio link: passes, margins, data volume per day, validated against the AMSAT/IARU link model and SGP4 | available | v0.7.3 |
| [`bac-optical-payload`](notebooks/bac-optical-payload/) | marimo notebook | optics | Earth-observation and boom-camera optics: GSD, swath, smear, access and illumination over a target, days to downlink | available | v0.7.3 |
| `bac-orbit-viewer` | marimo notebook | orbit | 3D view of a mission's geometry around the globe from any sibling's profile | planned | – |
| [`bac-orbital-lifetime`](notebooks/bac-orbital-lifetime/) | marimo notebook | orbit | Decay under drag with NRLMSIS 2.1 and ten solar-activity scenarios; lifetime against launch date; disposal rules | available | v0.2.4 |
| [`bac-power-budget`](notebooks/bac-power-budget/) | marimo notebook | power | Generation, storage and loads over the orbit with a scheduler and safe mode | available | v0.5.3 |
| `bac-pv-aging` | marimo notebook | power | Single-diode model of a solar cell string fitted to datasheet points and aged over the mission by UV, atomic oxygen, displacement damage and thermal cycling: BOL and EOL IV curves, the EOL power factor the power budget takes | planned | – |
| `bac-thermal` | marimo notebook | thermal | Lumped-parameter thermal model of the spacecraft over the orbit, hot and cold cases, battery heater energy | planned | – |
| `bac-builder` | web app | store | Web app to configure a CubeSat build from BAC parts with a 3D view, tied to the store's prices and stock; cart, quote, CSV and PDF outputs; mass, power and data budgets per build | planned | – |
| [`bac-pricing`](ops/bac-pricing/) | marimo notebook | ops | Assembly pricing: multi-level BOM cost rollup and batch-waterfall price derivation as a pure engine, the notebook over it, the `pricing` schema of the operations suite; `bac-pricing` opens the notebook on the configured backend | available | v1.4.0 |
| [`bac-suite`](ops/bac-suite/) | CLI | ops | The operations suite's orchestrated shell: one web app with every installed engine's notebook behind a common index | available | v0.2.0 |
| [`bac-vse-tools`](blender/bac-vse-tools/) | Blender extension | video | One extension with three sub-panels in the VSE sidebar: bulk import of a folder of clips end to end, proxies built one strip at a time, meta strips separated with their trim kept | available | v1.0.0 |

Related, maintained elsewhere: [`bac-page`](https://github.com/buildacubesat/bac.page/tree/main/cli), the CLI for the bac.page URL shortener, lives with the GitHub Pages repository it writes to.

## 2. Install

Each tool is its own `uv` project and installs independently:

```sh
uv tool install ./tools/bac-issue-print
bac-issue-print --init
```

Tools that build on `bac-common` install from the checkout, not from PyPI; after pulling a new version, `uv tool install --force --reinstall ./tools/<name>` replaces the installed one. A tool with an optional extra takes it in the path: `uv tool install './tools/bac-cad-preview[step]'`. The suite's command-line tools install together – `uv tool install ./lib/bac-suite-db --with ./ops/bac-pricing` gives `bac-db` with the pricing engine – and `ops/README.md` describes the group. The reference gallery renders through a headless Chromium; `bac-reference-gallery --init` finds one or downloads Playwright's. The antenna optimizer runs inside the workspace environment because it needs the openEMS bindings (its README has the setup), and the notebooks run through marimo (§3).

The Blender extension is installed from a zip of `blender/bac-vse-tools/src/bac_vse_tools/` through Preferences → Get Extensions → Install from Disk; its README has the two ways to build the zip.

To work on the repository itself:

```sh
uv sync --all-packages
uv run pytest
uv run ruff check .
```

## 3. Notebooks

The engineering notebooks under `notebooks/` – link budget, optical payload, power budget, orbital lifetime, and the local-only antenna visualizer (with a frozen demo snapshot that runs on molab) – are single marimo files with PEP 723 metadata. Run one in its own environment with `uvx marimo edit --sandbox notebooks/bac-link-budget/bac_link_budget.py`, or in the workspace environment with `uv run marimo edit <file>`. The four published ones are the files behind the bac.page links – edited here and copied to molab, never the other way round; each of them carries the shipped profiles as TOML files under `examples/` and headless regression tests. The BAC profiles assume the 500 km planning orbit. `notebooks/README.md` has the rules of the class.

## 4. Layout

```
lib/       shared libraries (bac-common, bac-kicad-common, bac-suite-db)
notebooks/ engineering notebooks (marimo, single files, published for the community)
tools/     one directory per CLI tool, installable with uv tool install; the antenna optimizer's
           simulation output (runs/) stays out of git and the kept runs live in bac-hardware
ops/       business operations suite (Marimo notebooks + PostgreSQL)
blender/   Blender extensions
```

Every tool directory has the same shape: `pyproject.toml`, `src/bac_<name>/cli.py`, `README.md` with a version history, `tests/`, and where the tool consumes data, `examples/`. The reference gallery adds its pages beside them (`index.html`, `css/`, `assets/`, `examples/`), and the wheel carries them inside the package.

## 5. Conventions

Every CLI tool built on `bac-common` prints `<tool> vX.Y.Z` for `-v/--version`, accepts a hidden `--debug` that shows tracebacks, and keeps `--help` within 24 lines including two or three examples (at the end; the older Typer tools – `bac-csr-ingest`, `bac-kicad-symfields`, `bac-media-convert` – still print them above the options). The other standard flags appear where they apply: `--dry-run` where a run writes or changes something (on the subcommand that does, for the tools with subcommands), `--init` where the tool has a first-time setup – settings to write, or a browser to fetch for the reference gallery – and `--config PATH` where it keeps persistent settings, `--env-file PATH` where it reads secrets or machine-specific values, `-l/--list` where it works on a named set. Filters that write to stdout (`bac-markdown-to-youtube`, `bac-kicad-hlabels`) and read-only tools (`bac-convention-check`) have no `--dry-run`. Each tool's README lists its flags. The antenna optimizer predates the scaffold and is the one exception: its `-v` prints `bac-antenna 0.7.4` (the command name, no `v`), it has `-l` but no hidden `--debug`, and its `--help` is 25 lines without examples; moving it onto `bac-common` is an open follow-up. The notebooks are exempt from the flags and carry their version in `TOOL_VERSION` and in every export's header.

Config lives at `~/.config/bac/<tool>.toml`; secrets in a `.env` file loaded with python-dotenv. Exit codes are 0 for success, 1 for a runtime error, 2 for bad arguments. Errors go to stderr; tracebacks appear only with `--debug`. Terminal output uses the BAC Interface Design Guide's terminal profile through `bac_common.ui`; web pages and notebooks take their colours from the reference gallery's `tokens.css`.

Software in this repository is licensed MIT (see `LICENSE`); documentation CC BY-SA 4.0. Software versions follow SemVer and display with a `v` prefix.

## 6. Adapting for your own project

Run `<tool> --init`. It asks for the paths, identifiers and endpoints the tool needs, writes `~/.config/bac/<tool>.toml`, and where secrets are involved, a `.env` next to your working directory with empty values to fill in. Tools that consume data files take a data directory from that config; the copies under each tool's `examples/` show the expected shape and can be copied as a starting point. Nothing in the repository needs editing to point a tool at your own project.

## 7. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.13.0 | 2026-10-08 | `bac-reference-gallery` v0.3.0 joins on `bac-common`: the seven boards in light and dark with every colour through `tokens.css`, now the shared stylesheet and a full copy of the Identity Guide's tokens with AA-safe `--text-muted` and `--link`; every text on every board passes WCAG AA in both modes, with focus rings, reduced motion, `lang`, table scopes and labelled form controls; the product sheet without price and contact data; the renderer as `bac-reference-gallery` with `--out-dir`, `--theme`, `--source`, the pages inside the package and `--init` for the browser. `bac-common` v0.4.1 and `bac-update-content-plan` v0.4.1: the service-account key's path says where it came from. Final README pass: the tool table grouped and ordered as its intro says, §2 on installing every kind of tool, §5 states the standard flags that apply instead of claiming all of them everywhere; the notebooks' `pyproject.toml` versions follow their `TOOL_VERSION` (notebooks 0.8.6); the `bac-convention-check` row says v0.2.1 again (it read v0.2.2 since 0.8.3, a typo). The LICENSE names nihil.space GmbH and the Build a CubeSat contributors as copyright holders. |
| 0.12.0 | 2026-10-07 | `bac-vse-tools` v1.0.0: the three Blender add-ons as one extension under `blender/` with a manifest, three panels under VSE Tools and settings in a property group on the scene; Bulk Import no longer saves the open file and keeps its copies out of the media folder (autosave opt-in, confirmed) and keeps Blender's A/V sync through the Add Movie operator, the proxy build runs as a background job with a timeout over the whole wait and stale proxies ignored, Separate Meta asks before removing strips. Tested headless inside Blender 4.5 through the `bpy` wheel; `blender/` joins ruff and pytest. |
| 0.11.0 | 2026-10-07 | `bac-update-content-plan` v0.4.0 rewritten on `bac-common` (sheet, range, repository and branch in `~/.config/bac/`, the repository validated before the sheet is fetched, pipes escaped, the commit limited to the file, confirmation before `git push`, `--dry-run` reports what would change) and `bac-store-product-cropper` v0.2.0 repackaged under its new name (the double-Enter save, the stretched preview, the quality-order crash and the double listing fixed; `--out-dir`, collision check, skip of existing outputs). `bac-common` v0.4.0 adds `bac_common.gsheets` behind the `gsheets` extra. `bac-media-convert` v0.1.1: "the store" replaces "the shop" here and in its own text; the planned `bac-builder` and `bac-catalog` rows follow. |
| 0.10.0 | 2026-10-07 | The business operations suite joins under `ops/`: `bac-suite-db` v0.1.0 (the shared PostgreSQL layer lifted from bac-pricing's `bac_store.py`, `bac-db` on `bac-common`, the DSN in `.env` and redacted everywhere, the SKU scheme as a parser), `bac-pricing` v1.4.0 (engine, store and notebook as a package with the `bac-pricing` launcher, the data files as `examples/` with the three SKUs migrated to the guide scheme, the notebook on the shared style cell with one control panel, validation on import, the parity test as pytest with a guarded live variant) and `bac-suite` v0.2.0 (engines found through entry points). The SQL was run against PostgreSQL 16 before release and the live tests keep doing so with `BAC_TEST_DSN`; `ops/README.md` describes the group. |
| 0.9.1 | 2026-10-07 | `bac-kicad-generate-artifacts` v0.6.1: the output folder carries the full artifact name (`bac-inhibit-deployment-switch-v1r1/`), fixes from the first live run (absolute paths for the iBOM plugin, program lookup at call time, `--init` text). |
| 0.9.0 | 2026-10-06 | `bac-kicad-generate-artifacts` v0.6.0 joins on `bac-common`: the 0.5.0 stage architecture with the installed 0.4.2's behaviour, the live-run bugs of 2026-10-02 fixed (names from the project stem, no doubled prefix, no spaces in Gerber names, `.gbrjob` rewritten), a QR stage on `bac_common.sexp` after Emil Fresk's kicad-qr-inserter, STEP header metadata through the new `bac_common.cad` (`bac-common` v0.3.0), kicad-cli 10 targeted directly; the deployment switch and a synthetic project as fixtures. |
| 0.8.5 | 2026-10-06 | The notebooks' bac.page links are the molab short links (`bac.page/molab-<tool>`, the demo at `molab-antenna-viz-demo`); five patch bumps. |
| 0.8.4 | 2026-10-06 | `bac-orbital-lifetime` v0.2.3: the "Solar Activity Assumed" chart drew nothing in the browser since 0.1.0 (a dot in the data column name is nested access to Vega-Lite). The visualizer demo fetches its two S-band packs from `notebooks/bac-antenna-visualizer/demo/packs/` (now tracked) when none sit beside it, so a molab mirror of the file works as is. |
| 0.8.3 | 2026-10-06 | Chart titles that Altair clipped are split into title and subtitle in the five notebooks (`chart_title` in the shared chart-conventions cell): `bac-link-budget` v0.7.2, `bac-optical-payload` v0.7.2, `bac-power-budget` v0.5.2, `bac-orbital-lifetime` v0.2.2, `bac-antenna-visualizer` v0.3.3. The tool table gains a Type column and links every available tool to its directory. |
| 0.8.2 | 2026-10-06 | The BAC planning orbit moves to 500 km (was 450 km): `bac-link-budget` v0.7.1, `bac-optical-payload` v0.7.1, `bac-power-budget` v0.5.1 and `bac-orbital-lifetime` v0.2.1 with their profiles, panel defaults, regression figures and READMEs; the lifetime takes the siblings' chart-conventions and style cells; the four notebooks are formatted and linted by ruff from now on (exemptions dropped, F841 added for cell globals). |
| 0.8.1 | 2026-10-06 | `bac-antenna-visualizer`: a demo snapshot for molab under `notebooks/bac-antenna-visualizer/demo/` – the visualizer without the optimizer, geometry from the pack's stored models, packs found beside the file – with its own headless tests; the demo is covered by `marimo check` in CI. |
| 0.8.0 | 2026-10-02 | The `notebooks/` group: `bac-link-budget` v0.7.0, `bac-optical-payload` v0.7.0, `bac-power-budget` v0.5.0 and `bac-orbital-lifetime` v0.2.0 come in as byte-identical copies of the published files with example profiles and regression tests from their handoffs; `bac-antenna-visualizer` v0.3.2 moves there from `tools/`; a shared headless harness; `marimo check` and the notebook tests in CI. `bac-convention-check` v0.2.1 stops flagging a notebook's build-system-less pyproject. |
| 0.7.0 | 2026-10-02 | `bac-cad-preview` v0.5.0 joins on `bac-common`: STEP, STL and 3MF previews framed like the KiCad artifacts render, faces named with the project's axis letters, `--out-dir`, output collisions refused; the `step` extra carries OpenCascade. |
| 0.6.0 | 2026-10-02 | The two antenna tools from the S-band sessions brought in: `bac-antenna-optimizer` v0.7.4 (tag `bac-antenna-optimizer-v0.7.3` marks the version that generated the S-band cross patch in bac-hardware) and `bac-antenna-visualizer` v0.3.1, both on the conventions; the root `.gitignore` takes over their ignore rules. `bac-common` v0.2.1 and a root `conftest.py` pin the terminal widths under test, so the suite passes at any width (five tests failed at 80 columns before). The tool table becomes the tracking view of everything planned for the repository. |
| 0.5.0 | 2026-09-07 | The KiCad library tools and the CAN bench tool: `bac-kicad-symfields` v0.3.0, `bac-kicad-schfields` v0.2.0 and `bac-kicad-libcheck` v0.2.0 folded in from the separate bac-kicad-tools repository (the four `bac-kicad-misc` lint scripts absorbed as `symfields lint` and `fix`), `bac-can-up` v1.2.0 ported from `canup.sh`. New `bac-kicad-common` v0.1.0; `bac-common` v0.2.0 adds `bac_common.sexp`. All batch-1 tools have now arrived. |
| 0.4.0 | 2026-09-04 | Four small tools on the scaffold: `bac-markdown-to-youtube` v0.2.0 (rewritten conversion), `bac-issue-print` v0.1.0 (ported from shell, pagination, token), `bac-kicad-hlabels` v0.1.0 (flags, `--gap-on-blank`), `bac-media-convert` v0.1.0 (`webp-square`, `cfr`; the two shell loops retired). `bac-common` v0.1.1: `.env` is searched from the working directory, `run_typer` puts Typer tools inside the error boundary. |
| 0.3.0 | 2026-09-02 | `bac-convention-check` v0.2.0 ported to Python with TOML rule sets; runs on the repository in CI. |
| 0.2.0 | 2026-09-02 | `bac-csr-ingest` v0.4.0: first tool on `bac-common`; classifier trust boundary, upload guard, phase order. Root pytest runs in importlib mode so tools may share test module names. |
| 0.1.0 | 2026-09-02 | Repository skeleton: uv workspace, CI, `bac-common` v0.1.0 lifted from the CSR Ingest reference implementation. Tools follow in the homogenization plan's order. |
