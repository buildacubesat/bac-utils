# bac-kicad-generate-artifacts v0.6.1

Build a CubeSat – the release bundle of a KiCad project from one command. For every project folder given, the tool drives `kicad-cli` through the stages of a hardware release and puts the results into one folder: a 720 × 720 px 3D render, a 1920 × 1080 px pinout plot, the schematic PDF, the CSV BOM, an optional interactive HTML BOM, Gerbers and Excellon drills, the pick-and-place centroid file, the STEP model with author and organisation in its header, an optional QR code on the board, and a timestamped manufacturing ZIP. Every file is named after the BAC artifact scheme `<prefix>-<subsystem>-<name>-<vXrY>-<kind>.<ext>`, with the version and revision read from the board's title block.

Everything specific to a project – output root, naming prefix, author, BOM fields, plugin paths – lives in `~/.config/bac/bac-kicad-generate-artifacts.toml`, written by `--init`. The defaults are BAC's; §9 says what to change for another project.

## 1. Install

```sh
uv tool install ./tools/bac-kicad-generate-artifacts   # from the bac-utils checkout
bac-kicad-generate-artifacts --init
```

Programs on `PATH` at run time: `kicad-cli` from KiCad 10 (the stages are written against the 10.x command set and tested with 10.0.3; the tool does not probe the help text for older builds) and `inkscape` or `rsvg-convert` (librsvg) to rasterise the pinout plot. The WebP images are encoded by Pillow, so `cwebp` is no longer needed. Optional: a system `python3` that imports `pcbnew`, with the InteractiveHtmlBom plugin, for `--ibom`; `xdg-open`/`open` and `gerbview` for `--open`. The tool depends on `bac-common` from this repository, so it installs from the checkout, not from PyPI.

## 2. Usage

```
bac-kicad-generate-artifacts [options] KICAD_DIR [KICAD_DIR ...]
```

```sh
bac-kicad-generate-artifacts ~/bac/bac-hardware/inhibit/deployment-switch/kicad10
bac-kicad-generate-artifacts --ibom --qr https://bac.page/dsw-v1 --open deployment-switch/kicad10
bac-kicad-generate-artifacts --dry-run --skip step panel-a/kicad10 panel-b/kicad10
```

`KICAD_DIR` is the folder that holds the `.kicad_pro`, `.kicad_pcb` and `.kicad_sch` files. Several folders are processed in turn; one failing folder does not stop the others, and the summary (projects, done, failed) is printed on every path. Exit codes: `0` every project done, `1` at least one stage or project failed, or the config file is invalid, `2` bad arguments.

| Option | Effect |
| :-- | :-- |
| `--desktop DIR` | Output root. Default: `root` in the config, else `$XDG_DESKTOP_DIR` or `~/Desktop`. |
| `--only STAGES`, `--skip STAGES` | Run only, or run without, the named stages (comma-separated; §3 has the names). An unknown name exits 2 and lists them. |
| `--ibom` | Also build the interactive HTML BOM (opt-in: it needs KiCad's own Python). |
| `--qr TEXT` | Replace the `QR_MARKER` text boxes on the board with a QR code of `TEXT` (§5). |
| `--patch N` | Patch revision on the version tags: `v1r2` becomes `v1r2.N` for the board and the schematic. |
| `--open` | Open the output folder in the file manager and the ZIP in GerbView when the project is done. |
| `--dry-run` | Print the plan and record the commands (`--debug` shows them); nothing is written, not even the output folder. The QR stage only names its text, so the recorded board paths are the project's own. |
| `--config PATH`, `--init` | Another config file; first-time setup (§4). |

The run prints an opening panel, a rule per project with the board, title, revision, schematic and output folder, one `✓` line per stage with the file it wrote, its size and the time it took (`✗` with the reason when a stage fails, `·` for a skipped stage), and the summary. `--debug` adds every command that was run and keeps the `.work/` folder.

## 3. Stages

Stages run in this order; `--only` and `--skip` pick from them.

| Stage | Writes | Notes |
| :-- | :-- | :-- |
| `qr` | `.work/project/<board>.kicad_pcb` | Opt-in (`--qr TEXT` or `text` in `[qr]`). Copies the project folder into the work folder and replaces the marker boxes on the copy; the later board stages export from that copy. The project itself is never written. |
| `render` | `<base>-render.webp` | `kicad-cli pcb render` at 2160 × 2160 px, rotated 22.5°/−22.5°, zoom 0.8, side lights at 90°, transparent; cropped to the board, padded 10 %, squared and resized to 720 px, lossless WebP. `bac-cad-preview` frames its previews the same way. |
| `schematic` | `<sch-base>-schematic.pdf` | Black and white, all sheets. |
| `pinout` | `<base>-pinout.webp` | `Edge.Cuts`, `F.Fab` and `F.Silkscreen` as a single black-and-white SVG, rasterised at 4× and scaled to 80 % of a 1920 × 1080 px transparent canvas. |
| `bom` | `<sch-base>-bom.csv` | `kicad-cli sch export bom` with the field list, labels and grouping from `[bom]`. |
| `ibom` | `<base>-ibom.html` | Opt-in (`--ibom`). Exports a `kicadxml` netlist and runs the InteractiveHtmlBom plugin (`script` in `[ibom]`) with the first Python that imports `pcbnew`: `python` in `[ibom]`, then `/usr/bin/python3`, then `python3`. Dark mode, pin 1 highlighted, `BOM` as the DNP field; the plugin's browser tab opens only with `--open`. The plugin takes a relative `--dest-dir` as relative to the board's folder, so it gets absolute paths. |
| `gerbers` | `gerber/` | Into an emptied `gerber/`: the board's copper layers (read from its `(layers …)` block, in stack order) plus `F.Paste`, `B.Paste`, `F.Silkscreen`, `B.Silkscreen`, `F.Mask`, `B.Mask`, `Edge.Cuts`; on a panel also `User.Comments` (V-cut lines). RS-274X without X2 attributes, 6 digits, KiCad extensions. Zone fills are exported as saved: `--check-zones` is never passed, so a panel's fills stay as the panelizer left them and a board's fills are the ones its designer last filled. |
| `drills` | `drill/` | Into an emptied `drill/`: Excellon, absolute origin, millimetres, decimal format. |
| `centroid` | `centroid/<base>-centroid.pos` | ASCII, millimetres, both sides in one file, SMD only, DNP excluded, drill/place file origin. |
| `step` | `<base>-model.step` | `--subst-models --force`; then the STEP header's `FILE_NAME` entity gets the file's name, and `author` and `organization` from `[metadata]` replace the placeholders KiCad writes there (`Pcbnew`, `Kicad`) when they are set (`bac_common.cad`). |
| `zip` | `<base>-<YYYY-MM-DD-HH-MM>.zip` | Renames the Gerber and drill files from kicad-cli's `<board stem>-<layer>` to `<base>-<layer>`, rewrites the paths inside the `.gbrjob` job file to match, and zips `gerber/`, `drill/` and `centroid/`. The timestamp is UTC. Refuses when `gerbers`, `drills` or `centroid` failed in this run. |

`<base>` is `<prefix>-<subsystem>-<name>-<vXrY>` from the board's title block; `<sch-base>` carries the schematic's own tag, which differs only when the two title blocks disagree. Layer names in Gerber file names are KiCad's default names (`F_Cu`, `In1_Cu`, `F_Silkscreen`, `Edge_Cuts`): a layer the designer renamed in the board setup (`B.Cu MIX`) is mapped back to its default name, so a user layer name never puts a space into a Gerber file name. Two files that would get the same name are numbered `-2`, `-3`. A run into an output folder that exists replaces the render, plots and exports of the earlier run and adds its own ZIP; the earlier ZIPs stay.

A folder without a `.kicad_sch` file is a **panel**: the tool says so with a `!` line and proceeds; `schematic`, `pinout`, `bom` and `ibom` are skipped, `User.Comments` joins the Gerber layers, and the fills are exported as saved.

## 4. Names and the config file

The output folder is `<root>/<base>/`, so two projects of the same name in different subsystems never share a folder. The pieces of the scheme:

- **prefix** – `bac` (`prefix` in `[naming]`).
- **subsystem** – the folder below the hardware repository on the project's path: `.../bac-hardware/inhibit/deployment-switch/kicad10` gives `inhibit` (`hardware_root` in `[naming]` names the repository folder). A project outside that repository gets no subsystem and the prefix stands alone; so does a project folder that is the subsystem itself.
- **name** – the project's own kebab name: the `.kicad_pro` stem (or the board's) without the prefix and the trailing `-v<N>` token, so `bac-deployment-switch-v1` gives `deployment-switch` and the artifacts are `bac-inhibit-deployment-switch-v1r1-…`, never `bac-inhibit-bac-inhibit-…`. Without a usable stem the title block's title is slugified; the parent folder's name is the last resort.
- **vXrY** – the `v` token of the title block's title (`… v1`, `v1.2`) and the `rev` field normalised to `r<N>` (`1`, `r1`, `R 1` all give `r1`; other text becomes `r-<text>`); `--patch N` appends `.N`.

`--init` writes `~/.config/bac/bac-kicad-generate-artifacts.toml` with every key and its default, and finds the InteractiveHtmlBom plugin where KiCad's plugin manager installs it (Linux, Windows, macOS). It never overwrites an existing file. Every key is optional; the tool runs without the file.

```toml
[output]
root = ""              # empty: $XDG_DESKTOP_DIR or ~/Desktop; --desktop overrides
timeout_s = 600        # per command

[naming]
prefix = "bac"
hardware_root = "bac-hardware"

[metadata]
author = ""            # into the STEP header in place of KiCad's placeholders
organization = ""

[bom]
fields = "${ITEM_NUMBER},Reference,${QUANTITY},Manufacturer,Manufacturer PN,Value,Package,Tolerance,R Rated Power,C Class,C D Rated Voltage,Notes,${DNP},Alternative parts,Digikey URL"
labels = "#,Designator,Qty,Manufacturer,Manufacturer PN,Value,Package,Tolerance,R Rated Power,C Class,C D Rated Voltage,Notes,DNP,Alternative parts,Digikey URL"
group_by = "Value,Package,Manufacturer,Manufacturer PN,Tolerance,R Rated Power,C Class,C D Rated Voltage,Notes,${DNP},Alternative parts,Digikey URL"

[ibom]
script = ""            # generate_interactive_bom.py; --init fills it in when the plugin is installed
python = ""            # empty: /usr/bin/python3, then python3

[qr]
marker = "QR_MARKER"
text = ""              # default for --qr; the stage runs whenever a text is known
```

## 5. QR code

Place a square text box (`gr_text_box`) with the text `QR_MARKER` on the board where the code should go, on any layer. With `--qr TEXT` (or `text` in `[qr]`) the `qr` stage replaces every such box with the QR code for the text: one filled zero-width `gr_rect` per dark module, the module size the box's side divided by the code's size, error correction level L, the smallest version that holds the text, no quiet zone (leave room around the box). On a back layer the code is mirrored left to right so it reads correctly when the board is turned over. A box that is not square gets the code centred in the square of its shorter side. `${TITLE}`, `${REVISION}`, `${COMPANY}`, `${ISSUE_DATE}` and `${COMMENT1}` … `${COMMENT9}` in the text are replaced from the board's title block, so `--qr '${COMMENT4}'` encodes the bac.page link the deployment switch carries in its fourth comment.

The stage works on a copy of the project folder in `.work/project/` (backups, lock files and caches left out) and the later board stages of the same run export from that copy, so the render, Gerbers and STEP carry the code while the project itself is untouched; the copy is removed with `.work/` at the end of the project (kept with `--debug`, ignored by the next run). A box must sit at 0° or 180°; a rotated one is an error. When the modules come out smaller than 0.2 mm the ✓ line says so, since most fabs cannot print finer silkscreen. 3D model paths relative to `${KIPRJMOD}` resolve inside the copy, so models stored next to the project are found; models referenced relative to a folder outside the project are not. No board of the Build a CubeSat project carries a marker yet; the deployment switch fixture under `tests/fixtures/` does.

The stage is a reimplementation of Emil Fresk's [kicad-qr-inserter](https://github.com/korken89/kicad-qr-inserter) (MIT), which does the same with the `pcbnew` Python module. This version reads and edits the board through `bac_common.sexp`, so it needs no KiCad Python and changes nothing in the file but the marker boxes.

## 6. Fixtures and tests

`tests/fixtures/deployment-switch/kicad10/` is the BAC deployment switch (KiCad 10 format, one sheet, two footprints, 4.8 × 8.7 mm) with a `QR_MARKER` text box added on `B.SilkS`; it is the live fixture for a run with the installed KiCad. `tests/fixtures/eps/` holds a hand-written four-layer project with renamed inner layers, a hierarchical sheet and two marker boxes, and a schematic-less copy of it as a panel with a V-cut line on `User.Comments`. `kicad-cli` is not needed to run the tests: a stand-in runner writes the files each subcommand would produce. The 110 tests cover the title block and version tags, the naming, the layer map and the rename pass including the job file, the QR geometry front and back, every stage, the command line and the config.

A run on the deployment switch with kicad-cli present looks like this:

```sh
bac-kicad-generate-artifacts --desktop ~/Desktop/releases --qr '${COMMENT4}' tests/fixtures/deployment-switch/kicad10
```

## 7. Changes against 0.4.2 and 0.5.0

0.6.0 merges the two earlier lines: the stage architecture, `--only`/`--skip` and the parsing tests of the 0.5.0 candidate of 2026-05, and the behaviour of the installed 0.4.2 (panel mode, the rename pass, UTC timestamps, dry run, summary). On top of that: the package moves onto `bac-common` (Rich output, standard flags, config and `--init`, error boundary); the output folder and the artifacts are named after the project's own name instead of the parent folder (`adcs/magnetorquer-placeholder-XY/1U/kicad9` was `bac-adcs-1U-…`) and the prefix no longer doubles; renamed layers no longer leave spaces in Gerber names; the `.gbrjob` file is rewritten with the renamed paths; the stem is removed from the front of a file name only; collisions count up instead of clobbering `-dup`; a dry run creates nothing; kicad-cli's help text is no longer probed (10.x is the target); the STEP header carries name, author and organisation; `--open` replaces the unconditional launch of the file manager and GerbView; `--patch` replaces `--pcb-patch-rev` and `--schematic-patch-rev`; panel mode proceeds after its warning instead of prompting (`-y` is gone); `--keep-work` is gone, `--debug` keeps the work folder; the iBOM plugin path and interpreter come from the config instead of `--ibom-script` and `--ibom-python`, and the plugin runs with `--no-browser` unless `--open`; a project outside the hardware repository gets no subsystem instead of `unknown`; the WebP encoder is Pillow instead of `cwebp`; a failing stage prints a ✗ line on stdout and marks the project but the remaining stages still run (the top-level `ERROR` line is still stderr); the `kicad` launcher is no longer tried when `gerbview` is missing; `gerber/`, `drill/` and `centroid/` are emptied before an export and the STEP export passes `--force`, so a re-run replaces instead of accumulating. The QR stage is new.

## 8. Development

```sh
uv run pytest tools/bac-kicad-generate-artifacts
uv run ruff check tools/bac-kicad-generate-artifacts
```

Modules: `cli` (parser, the per-project loop, output), `project` (discovery, title block, tags, names, layers, the rename pass), `stages` (the eleven stages and their selection), `qr` (marker search and rectangle generation on `bac_common.sexp`), `runner` (program discovery, the subprocess wrapper with dry run and timeout), `config` (settings and the `--init` template).

## 9. Adapting for your own project

Set `prefix` and `hardware_root` in `[naming]` to your organisation's prefix and the name of the folder your hardware projects live under, or leave `hardware_root` pointing at a folder that does not exist to get `<prefix>-<name>-<vXrY>` without a subsystem. Put your name and organisation into `[metadata]`. Replace the `[bom]` field list with the symbol fields your library uses (`${ITEM_NUMBER}`, `${QUANTITY}` and `${DNP}` are KiCad's built-in columns). Boards whose title reads `<something> v<N>` with a numeric `rev` get clean `vXrY` tags; anything else still works but produces `r-<text>` or `v-unknownr-unknown`. The render camera and the pinout layers are constants at the top of `stages.py`.

## 10. License

MIT, like the rest of bac-utils. The QR stage follows Emil Fresk's kicad-qr-inserter (MIT, © 2024 Emil Fresk) in its approach; no code of it is included.

## 11. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.6.1 | 2026-10-07 | The output folder is named like the artifacts (`bac-inhibit-deployment-switch-v1r1/`, was `deployment-switch-v1r1/`), so two projects of one name in different subsystems no longer share a folder. From the first live run: the iBOM plugin gets absolute paths (it resolves `--dest-dir` against the board's folder), the program lookup happens at call time, `--init` keeps its `[table]` names. |
| 0.6.0 | 2026-10-06 | Rebuilt on `bac-common` as `tools/bac-kicad-generate-artifacts` in bac-utils, merging the 0.5.0 architecture with the 0.4.2 behaviour (§7). New: the `qr` stage, STEP header metadata, `--open`, `--patch`, `--init`/`--config`, the name from the project stem, Gerber names without spaces, `.gbrjob` rewrite, kicad-cli 10 targeted directly, Pillow instead of `cwebp`. Fixtures: the deployment switch and a synthetic project with a panel; 110 tests. |
| 0.5.0 | 2026-05 | Candidate (never installed): `Config`, `Runner`, `Plan` and `Stage` architecture, `--only`/`--skip`/`--verbose`, 48 tests of the pure functions. |
| 0.4.2 | 2026-08-06 | Panelized boards: also skip the pinout WebP export. |
| 0.4.1 | 2026-08-06 | Panelized boards: include the `User.Comments` layer in the Gerber export (V-cut lines). |
| 0.4.0 | 2026-08-06 | Guideline alignment: `-v`/`--version`, `--dry-run`, hidden `--debug`, semantic glyphs instead of emojis, errors to stderr, run summary, UTC hyphenated ZIP timestamp, branded header, `pyproject.toml` packaging. Panelized-board detection with confirmation prompt (`--yes` bypass) and explicit no-re-pour guard on Gerber export. Gerber/drill files renamed to the BAC artifact scheme. |
| 0.3.x | – | Prior iterations: multi-directory processing, iBOM export, patch-revision flags, centroid and STEP export. |
