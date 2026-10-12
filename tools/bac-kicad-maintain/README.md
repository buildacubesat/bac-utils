# bac-kicad-maintain v1.2.0

Build a CubeSat – the sizes a project's KiCad files are supposed to use, applied in one pass. On boards, `check` and `apply` set every text item to 0.8 × 0.8 mm with a 0.1 mm stroke, centred and kept upright, and every courtyard line to 0.05 mm; with `--vias` they resize through-hole vias to 0.5 / 0.2 mm while GND keeps its size. On schematics, `--labels` sets local, global and hierarchical labels to 50 mil. `stats` lists the sizes a file uses, and `rename-library` moves a schematic's symbols from one library nickname to another, the cached copies in `lib_symbols` included. KiCad's own edit-text-and-graphics dialog does the first job interactively; here the result is reviewable, repeatable and the same across a project.

Files are edited by splicing byte ranges into the original text, never by re-serialising the parsed tree: untouched bytes stay identical, a git diff shows only the intended tokens, line endings and KiCad's one-child-per-line layout survive, and a second run is a no-op. Nothing is written without a confirmation (`--yes` for scripts), the previous content is kept as `<file>.bak` unless `--no-backup`, and `--dry-run` only reports. Every file of a run is parsed and planned before the first one is written, so a malformed file stops the batch with nothing changed.

The tool works on project files: `.kicad_pcb` and `.kicad_sch`. Footprint and symbol libraries are [`bac-kicad-symfields`](../bac-kicad-symfields/)' job (its `fix` sets footprint text sizes) and [`bac-kicad-libcheck`](../bac-kicad-libcheck/)'s; [`bac-kicad-schfields`](../bac-kicad-schfields/) edits symbol fields across a schematic hierarchy.

## 1. Install

```sh
uv tool install ./tools/bac-kicad-maintain     # from the bac-utils checkout
bac-kicad-maintain check boards/
```

The tool works without setup: the built-in defaults are the BAC board conventions. `bac-kicad-maintain init` writes them to `~/.config/bac/bac-kicad-maintain.toml` for editing (§4).

## 2. Usage

```
bac-kicad-maintain [--config PATH] check          PATH... [--text] [--courtyards] [--vias] [--labels] [--diff] [--json] [--exclude GLOB]
                                                          [--via-diameter MM] [--via-drill MM] [--preserve-net GLOB] [--via-types TYPE]
bac-kicad-maintain [--config PATH] apply          PATH... [the same] [--dry-run] [--yes] [--no-backup]
bac-kicad-maintain [--config PATH] stats          PATH... [--labels] [--json] [--exclude GLOB]
bac-kicad-maintain [--config PATH] rename-library PATH... --from NAME --to NAME [--diff] [--json] [--dry-run] [--yes] [--no-backup]
bac-kicad-maintain [--config PATH] init
```

`--config` sits before the subcommand, as in the sibling tools.

`PATH` is a board or schematic file or a directory; directories are searched recursively, `.git` and KiCad's `-backups` folders are skipped, symlinks are not followed, and `--exclude GLOB` (repeatable, also `[files] exclude` in the config) drops paths that match relative to the directory given or by file name. Which files a run looks at follows from the operations: the board operations collect `.kicad_pcb`, `--labels` and `rename-library` collect `.kicad_sch`. A file named on the command line that the run has no operation for is an error (`check sheet.kicad_sch` without `--labels` is told that `.kicad_pcb` was expected), and so is a run that finds no file at all – a `check` that scans the wrong folder must not pass.

### 2.1 check and apply

Without an operation flag the operations the config enables run – text and courtyards by default. With one or more flags only the flagged operations run, whatever the config says; `--vias` and `--labels` are therefore opt-in unless the config enables them. `check` reports and exits 1 when a file would change, 0 when everything is on the conventions; `apply` asks once, then writes every changed file with a `.bak` beside it. `--diff` prints a unified diff per changed file, `--json` a report instead of the panels; the two do not combine, and with `apply`, `--json` needs `--yes`, since a report has no prompt.

```
  pcb  bac-deployment-switch-v1.kicad_pcb
      ~ text items: 11
      ~ courtyard lines: 12
  bac-synth-v2.kicad_pcb: nothing to change
  Write 1 file(s)? [y/N] y
  ✓ Wrote boards/bac-deployment-switch-v1.kicad_pcb (backup bac-deployment-switch-v1.kicad_pcb.bak)
```

**Text** covers board text and text boxes, the reference, value and other property fields of footprints, and footprint text and text boxes, grouped items included. Dimensions and their text are left alone, and so is any text item without an `effects` list (a footprint's non-graphical properties, say). Size and stroke are set, `left`/`right`/`top`/`bottom` justification is removed (`mirror` stays; a `justify` list left empty goes entirely), and for footprint fields and text the `unlocked` flag is removed so KiCad keeps them upright – the rotation itself is not touched, since keep-upright does not mean rotate to zero. A changed item loses its `render_cache` so that KiCad rebuilds the outline with the new size. Text content, position, rotation, mirroring, visibility, font face, bold, italic and locking are preserved; centring can move a text relative to its unchanged anchor. `[text] layers` restricts the operation to the named layers.

**Courtyards** sets the stroke width of every graphic line, rectangle, circle, arc, polygon and curve on `F.CrtYd` and `B.CrtYd`, in the modern `(stroke (width …))` and the legacy `(width …)` form alike.

**Vias** resizes through-hole vias (`[vias] types` or `--via-types`, repeatable or comma-separated, adds `blind` and `micro`) to the configured diameter and drill, from `--via-diameter` and `--via-drill` for one run (positive, at most six decimals). A via whose net matches a preserve pattern (`GND` by default; `--preserve-net GLOB`, repeatable, replaces the list – patterns are case-sensitive and match the whole net name, so add `*/GND` for hierarchical grounds) keeps its size. Unconnected vias, vias whose numbered net the board does not declare, and vias with a `padstack` are skipped and counted. The via options need `--vias` or `vias.enabled = true`.

**Labels** sets the font size of local, global and hierarchical labels to `[labels] size_mil` (50 mil = 1.27 mm), both dimensions. Notes, text boxes, symbol fields, pin names, sheet pins, directive labels, the intersheet-reference fields of global labels and the cached symbols are left alone, and so are a label's position, rotation, justification, thickness, font face, bold, italic and visibility. No net is renamed. A hierarchical project is given as its directory so every sheet file is found; a single file changes that file only.

### 2.2 stats

`stats` reads boards and lists the text sizes by layer and the via sizes by type and net; with `--labels` it reads schematics and lists the label sizes. `--json` prints the same as a report.

### 2.3 rename-library

```sh
bac-kicad-maintain rename-library . --from 'bac Library v1' --to 'bac Library Symbols v1' --dry-run --diff
bac-kicad-maintain rename-library . --from 'bac Library v1' --to 'bac Library Symbols v1' --yes
```

Changes the library part of every placed symbol's `lib_id` and of the matching cached symbol IDs inside `lib_symbols` – nothing else: no text that happens to contain the name, no symbol or file names, no `sym-lib-table`, no installed library. The new nickname has to exist in KiCad's library tables for future library updates to resolve. When the old and the new name would give two cached symbols the same ID, the run stops before writing and names the ID; the cached definitions have to be resolved by hand first (a BAC power schematic had this exact situation).

## 3. Output and exit codes

Every run opens with the tool's panel, prints one block per file that would change (`pcb` or `sch`, then `~ <what>: <count>` lines, then the diff when asked) or a dim `nothing to change`, then the summary with the totals. `--json` replaces all of that with one JSON document: `tool`, `version`, `command`, `dry_run`, `files` (path, `changed`, `written`, `counts` with the same prose keys as the panels), `changed_files`, `written_files`. The 1.1.0 report had other keys (`text`, `vias_skipped_unknown_net`, a per-file `backup`); a consumer of that report needs updating.

Exit codes: 0 done (`check`: nothing to change); 1 `check` found changes, a file could not be read or parsed, or a write failed; 2 bad arguments. A file that changed on disk between planning and writing is not written and reported.

A backup is restored by copying it over the original: `cp board.kicad_pcb.bak board.kicad_pcb`. The `.bak` is the state before the most recent write – a second `apply` that changes the file replaces it – and the file itself is rewritten in place, as the sibling tools do; copy a board away first when the original has to survive more than one run. Close the board or schematic in KiCad before `apply` and reopen it afterwards; KiCad does not reload a file edited underneath it.

## 4. Adapting for your own project

`bac-kicad-maintain init` writes the config with every default; `--config PATH` points one run at another file. The sizes are plain numbers in millimetres (labels in mil), `enabled` per section decides what runs without flags, `[vias] preserve_nets` and `types` are lists, `[text] layers` restricts the text operation, `[files] exclude` is a list of globs. `examples/bac-kicad-maintain.toml` is the file `init` writes. A project on KiCad 9 or 10 needs nothing else; the tool reads both the single-line layout of older files and the one-child-per-line layout KiCad has written since version 8, and the test texts cover both.

## 5. Tests

```sh
uv run --no-sync pytest tools/bac-kicad-maintain
```

44 tests: the operations on texts (scope, preservation, idempotence, CRLF and BOM, the one-child-per-line layout with a `render_cache` and a missing `font`), the config file and its errors, and the command line (discovery, selectors, the via options in both forms, confirmation, backups, a failed write, the concurrent-change refusal, the reports, exit codes, every `--help` within 24 lines of 80 columns). The step-6 fixtures of `bac-kicad-generate-artifacts` (a KiCad 10 board with tabs, a synthetic two-sheet project) were run through `check --diff`, `apply` and a second `check` by hand. KiCad itself was not involved: the tests prove the file edits and their structure, not that KiCad renders the result – open one edited board in KiCad once.

## 6. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 1.2.0 | 2026-10-12 | Folded into bac-utils on `bac-common` and `bac-kicad-common`: the parser is `bac_common.sexp`, the backups are `<file>.bak` through `bac_kicad_common.files.write_back` (were `.bac-backup-<timestamp>.bak`), `apply` and `rename-library` ask before writing (`--yes`), Rich panels and summary, the config at `~/.config/bac/bac-kicad-maintain.toml` written by `init` (was an explicit `--config` only), `--exclude` and `--diff` as before, `--json` kept with new keys (§3), `--via-types` repeatable or comma-separated (was space-separated), the via options checked for six decimals on the command line as in the config, `--json` and `--diff` refused together as before, no matching file an error as before. The `.bak` is replaced by the next write and the file is rewritten in place (1.1.0 kept every timestamped backup and wrote through a temporary file). Scope is boards and schematics: the footprint-library text operation went to `bac-kicad-symfields fix`. Edits follow KiCad's layout – a removed list takes its line, an added one gets its own, a removed justification keyword takes its space (1.1.0 left blank lines and double spaces). Exit codes follow the house convention (a bad file is 1, bad arguments 2). 44 pytest tests replace the 15 unittest ones. |
| 1.1.0 | 2026-10-02 | As received (the date it was filed for the fold-in): one standard-library script with its own span-patching parser; text, courtyards, vias and labels; `stats`; `rename-library` with collision detection; timestamped backups and atomic writes; 15 unittest tests. Built without KiCad at hand. |
