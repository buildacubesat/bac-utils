# bac-kicad-stitch v0.1.0

Build a CubeSat – ground stitching vias where a board needs them. `stitch` reads a board's filled ground zones, works out every spot where a through via would be DRC-clean on all copper layers, and adds vias until no point of the ground copper is farther than the pitch from one. The ground vias already on the board count, so a region that is dense with them gets nothing, and a second run adds nothing. `report` only measures, `remove` takes the added vias out again. A preview SVG shows the ground copper, where a via may go, the vias before and after, and the gaps no via can close.

The pitch is either given in millimetres or derived from the highest frequency of interest as wavelength / 20 in the board's dielectric (εr from the stackup): 1 GHz gives about 7 mm, 700 MHz about 10 mm, the default. What matters is the edge-rate content of the fastest signals, not the clock – a board with a 160 MHz-class MCU and CAN FD is served by 10 mm, an RF board by its carrier frequency. On the MCU MicroMod carrier the default adds 17 vias; 5 mm would add 122. Instead of counting vias per square centimetre – which a cluster under a connector satisfies while the other end of the plane goes without – the measure is coverage: the share of the ground copper within the pitch of a ground via. Placement is farthest-point first and deterministic: the worst-covered point of the ground copper picks, among the clean spots within a pitch of it, the one farthest from every via, so vias spread instead of bunching at the gaps. Where a point of the ground copper has no clean spot within a pitch at all – under a fine-pitch part whose courtyard is avoided, in a sliver between pads – it is reported as a gap with its position.

A spot is clean when, on every copper layer, the via copper keeps the clearance from the fixed copper of other nets – tracks, pads, vias and graphics – and the drill keeps the hole-to-hole distance from every other hole; when it is inside the outline by the edge clearance, outside rule areas that forbid vias, and outside the courtyards the settings avoid; and when it sits in the ground fill of at least two layers (`--min-layers`), so no via is left stranded. Other nets' zone fills are not obstacles by default, because KiCad refills them around a new via with the zone clearance – a stitching via through a power plane costs a small hole in that plane, which is the usual trade; `--keep-zones` makes those fills obstacles too when a plane must stay whole. A margin of 0.05 mm is kept beyond every clearance so a via never sits exactly on a DRC limit.

Files are edited by splicing byte ranges into the original text, never by re-serialising: a diff shows the new vias and the `bac-stitch` group, nothing else, and line endings and KiCad's layout survive. The vias go where KiCad keeps them (after the last via or track, before the zones), each with a UUID derived from the board UUID and the position, so the same plan writes the same bytes. Nothing is written without a confirmation (`--yes` for scripts), the previous content is kept as `<file>.bak` unless `--no-backup`, and `--dry-run` only reports. After writing, `kicad-cli pcb drc` runs when it is on the PATH (`--no-drc` to skip) and its JSON report lands next to the board.

The tool needs the zones filled and saved – KiCad writes the fill polygons into the file, and they are what the tool reads. After stitching, refill the zones in KiCad (B); the new vias connect to the ground fill and the other nets' fills clear around them.

## 1. Install

```sh
uv tool install ./tools/bac-kicad-stitch     # from the bac-utils checkout
bac-kicad-stitch report board.kicad_pcb --preview plan.svg
```

The tool works without setup: the built-in defaults are the BAC board conventions (0.6 / 0.3 mm vias, 0.2 mm clearance, 0.25 mm hole to hole, 0.5 mm to the edge, 10 mm pitch). `bac-kicad-stitch init` writes them to `~/.config/bac/bac-kicad-stitch.toml` for editing (§4).

## 2. Usage

```
bac-kicad-stitch [--config PATH] report BOARD [placement options] [--preview SVG] [--json]
bac-kicad-stitch [--config PATH] stitch BOARD [placement options] [--preview SVG] [--json] [--dry-run] [--yes] [--no-backup] [--drc/--no-drc]
bac-kicad-stitch [--config PATH] remove BOARD [--json] [--dry-run] [--yes] [--no-backup]
bac-kicad-stitch [--config PATH] init
```

`--config` sits before the subcommand, as in the sibling tools. `BOARD` is one `.kicad_pcb`.

Placement options, each overriding its config value for one run:

| Option | Default | Meaning |
| :-- | :-- | :-- |
| `--net NAME` | `GND` | The ground net. |
| `--pitch MM` | 10 | Target pitch: no ground copper farther than this from a via. |
| `--max-frequency HZ` | – | Derive the pitch as wavelength / fraction at this frequency instead. |
| `--fraction N` | 20 | The wavelength fraction for `--max-frequency`. |
| `--epsilon-r ER` | stackup | Dielectric constant for the wavelength; the stackup average, or 4.4 without one. |
| `--via-size MM`, `--via-drill MM` | 0.6, 0.3 | The via. |
| `--clearance MM` | 0.2 | Copper clearance to other nets. |
| `--hole-to-hole MM` | 0.25 | Hole-to-hole clearance. |
| `--edge-clearance MM` | 0.5 | Copper to board edge. |
| `--margin MM` | 0.05 | Extra distance beyond every clearance. |
| `--min-layers N` | 2 | Ground fill layers a via must sit in. |
| `--keep-zones` / `--refill-zones` | refill | Whether other nets' zone fills are obstacles. |
| `--courtyards MODE` | `avoid-fine-pitch` | `allow`, `avoid` (every courtyard), or `avoid-fine-pitch`. |
| `--fine-pitch MM`, `--fine-pitch-pads N` | 0.65, 6 | A footprint is fine-pitch with at least N pads and a pad pitch below MM. |
| `--edge-fence` / `--no-edge-fence` | off | A row of vias along the board edge first. |
| `--edge-fence-pitch MM` | pitch / 2 | The fence pitch. |
| `--step MM` | 0.1 | Candidate grid step; finer finds more spots in tight copper and takes longer. |

### 2.1 report and stitch

Both read the board, plan, and print the plan: the copper layers and which carry ground fill, the pitch, the via, the ground area and the area where a via may go, the avoided courtyards, one `+ via at (x, y)` line per via to add, and the gaps (ten at most; `--preview` draws them all, `--json` lists them). `report` stops there. `stitch` asks once, writes the board with a `.bak` beside it, and runs DRC when `kicad-cli` is found. The summary has the existing ground vias, the vias added (fence vias separately), the coverage before and after, and the gaps.

```
  ✓ Wrote board.kicad_pcb (backup board.kicad_pcb.bak)
  ✓ DRC clean (board-drc.json)

    Existing ground vias  :     157
    Vias added            :      17
    Coverage before       :  83.7 %
    Coverage after        : 100.0 %
    Gaps                  :       0
```

A board that is already covered says `nothing to add` and is not written. Vias added earlier are ordinary ground vias to the next run, so a run with a larger pitch leaves them; `remove` first when the plan should start over. Vias moved or deleted by hand in KiCad stay as moved: the group is a list of UUIDs, and a UUID no longer on the board is simply not counted.

### 2.2 remove

Deletes the `bac-stitch` group and every via it lists, by span, so the file comes back byte for byte as it was before `stitch` when nothing else changed. Vias added by hand to the group in KiCad go too.

### 2.3 The preview

`--preview plan.svg` draws the outline, the ground copper (grey), the area where a via may go (green), the avoided courtyards (yellow), the existing ground vias (dark grey), the new vias (green, fence vias blue) and a dashed red circle of one pitch around each gap. It is the quickest way to see why a region gets no vias: a wide grey band is copper of another net on some layer – a power trace on an inner layer, say – buffered by the clearance and via radius.

## 3. Output and exit codes

`--json` replaces the panels with one document: `tool`, `version`, `command`, `dry_run`, `path`, `net`, `pitch_mm`, `fence_pitch_mm`, `existing_vias`, `placed` (`x`, `y`, `fence`), `coverage_before`, `coverage_after`, `ground_area_mm2`, `allowed_area_mm2`, `gaps` (`x`, `y`, `distance_mm` to the nearest via), `gap_area_mm2`, `avoided_footprints`, `written`, `drc` (`exit_code`, `violations`, `report`). With `stitch`, `--json` needs `--yes`. `remove --json` reports `vias_removed` and `written`.

Exit codes: 0 done – gaps are reported, not failed; 1 a file could not be read or parsed, a write failed, or DRC found violations; 2 bad arguments. A file that changed on disk between planning and writing is not written and reported.

A backup is restored by copying it over the original: `cp board.kicad_pcb.bak board.kicad_pcb`. Close the board in KiCad before `stitch` or `remove` and reopen it afterwards; KiCad does not reload a file edited underneath it.

## 4. Adapting for your own project

`bac-kicad-stitch init` writes the config with every default; `--config PATH` points one run at another file. `[via]` has the net, size and drill, `[rules]` the clearances the project's design rules use (the tool does not read the `.kicad_pro` or `.kicad_dru`; copy the numbers), `[placement]` the pitch or frequency, the layer count, zones, courtyards, fence and step. `examples/bac-kicad-stitch.toml` is the file `init` writes. Boards written by KiCad 9 and 10 are read; nets are matched by name, as KiCad 10 writes them.

What the tool models, and what it does not: pads of every shape (custom pads as their anchor and primitives), tracks and arcs, vias on their layers, copper graphics, zone fills, drill holes with offsets and oval drills, Edge.Cuts outlines from lines, arcs, rects, circles and polygons on the board and in footprints (cutouts included), courtyards as the convex hull of their drawing, rule areas with vias not allowed. Not modelled: net-class or custom DRC rules beyond the single clearance given, solder-mask and silkscreen, pad-to-zone thermal spokes (the via sits in the fill polygon as written), blind or buried vias (every new via is through), and the mechanical sense of a spot – a via in a connector's keep-out drawing on a user layer is not refused. DRC after writing catches what the model misses.

## 5. Tests

```sh
uv run --no-sync pytest tools/bac-kicad-stitch
```

17 tests on a synthetic two-layer board (outline, ground fill with an island, a track of another net, a rotated fine-pitch footprint, one ground via): the footprint transform and arcs, the board model, the masks (edge, track, island, courtyard), determinism and full coverage of the plan, the second run adding nothing, byte-stable insertion and a removal that restores the original, the edge fence, the frequency-derived pitch, the config checks, and the command line (confirmation, CRLF kept, backups, `--json`, `init`, bad arguments). The MCU MicroMod carrier board (6 layers, 169 footprints, 157 ground vias) was the development board: the model was checked against it by confirming that no pad of another net lands inside the ground fill and no other net's via is centred in it, and the plan was written, re-run and removed by hand. DRC in KiCad on the written board is the user's check.

## 6. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.1.0 | 2026-10-19 | First version: `report`, `stitch`, `remove`, `init`; coverage by pitch or frequency; farthest-point placement with gaps; the `bac-stitch` group; preview SVG; DRC through `kicad-cli` after writing. Tested by Mänu on the MCU MicroMod carrier board: the plan, the write, the group in KiCad. |
