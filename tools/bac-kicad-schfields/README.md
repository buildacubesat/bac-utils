# bac-kicad-schfields v0.2.0

Build a CubeSat – bulk-edits symbol fields and flags across a KiCad schematic hierarchy from TOML rules. Roughly what KiCad's symbol fields table does interactively, but deterministic, reviewable and repeatable: the rule file is the record of what was changed and why. The root sheet is given, the hierarchy is walked from there, and every sheet is edited by splicing byte ranges into its original text, so a diff shows only the intended change and a second run is a no-op.

## 1. Install

```sh
uv tool install ./tools/bac-kicad-schfields     # from the bac-utils checkout
bac-kicad-schfields Board.kicad_sch --rules rules/ --dry-run
```

No config file: the rules live with the project, so `--rules DIR` is always given.

## 2. Usage

```
bac-kicad-schfields SCHEMATIC --rules DIR [--dry-run] [--yes] [--no-backup]
                    [--allow-overwrite] [--allow-flags] [--include-cache] [--no-fill-empty]
```

`--dry-run` reports and writes nothing. Otherwise the run shows every change, asks once (`Write 2 sheet(s)? [y/N]`; `--yes` answers for scripts), keeps each sheet's previous content as `<sheet>.bak` unless `--no-backup`, and writes. Exit codes: `0` done, `1` a failed write, `2` bad arguments or rules.

```
  ! power.kicad_sch is instantiated 2×; one edit affects every instance
  file board.kicad_sch
  sym  R1  bac:R
      ~ Manufacturer PN = RC0603FR-0710KL   (60-project.toml)
  sym  R2  bac:R
      · Manufacturer PN skipped: would overwrite 'OLD-PN'; needs --allow-overwrite
  sym  TP1  bac:TP
      * dnp = unset → yes   (60-project.toml)
      * in_bom = yes → no   (60-project.toml)
```

Markers: `+` added, `~` filled an empty value, `!` overwrote a value, `*` changed a flag, `·` skipped with a reason.

## 3. Rule files

Only files with `target = "schematic"` are used; the same directory can hold the library rules of `bac-kicad-symfields`. `examples/rules/60-project.toml` is a commented example.

```toml
title = "Board-level fields and flags"
target = "schematic"

[match]
reference_regex = ["^(R|C|TP)"]

[[field]]
name = "Manufacturer PN"
value = "RC0603FR-0710KL"
when = { Value = "^10k$" }
when_reference = "^R"
overwrite = true

[[flag]]
name = "dnp"
value = true
when_reference = "^TP"
```

| `[match]` axis | Matches against |
| :-- | :-- |
| `reference_regex` | the reference designator, e.g. `^R([1-9]\|1[0-9])$` |
| `lib_id_regex` | the full `lib_id`, e.g. `^bac:` |
| `name_regex` | the name half of the `lib_id` |
| `sheet_regex` | the sheet file name |
| `properties` | regex per existing property value |

Axes combine with AND. Entry-level `when`, `when_name` and `when_reference` narrow one entry, so a file can hold a lookup table: several entries may share a field name, the first that matches a symbol wins. Library axes such as `reference_prefixes` are rejected on a schematic target rather than ignored. The `[[field]]` keys are those of `bac-kicad-symfields` (`value`, `requires`, `hide`, `size`, `overwrite`, `when`, `when_name`, plus `when_reference`).

Any property name works; there is no registry of known fields. `Reference` is refused: its value is stored both as a property and inside the `(instances …)` block, so rewriting the property alone would desynchronise the document – renaming references is an annotation operation, not a field edit.

### 3.1 Flags

The four booleans that are bare tokens in the file rather than properties: `dnp`, `in_bom`, `on_board`, `exclude_from_sim`. A `[[flag]]` entry needs `name` and `value = true|false`. Flag changes need `--allow-flags` on the run; a flag is rewritten in place when the symbol carries it and inserted after the last existing flag (or after `unit`) when it does not.

### 3.2 Overwriting

A field that already holds a value is replaced only when the rule says `overwrite = true` *and* the run passes `--allow-overwrite`. Without the flag the rule is reported as skipped with the value it would have replaced. Two gates, because a wrong regex here rewrites data across the whole board.

## 4. Hierarchy handling

Two things are reported rather than hidden. A sheet file instantiated by several hierarchical sheets is edited once but affects every instantiation; such files are listed with their count before anything happens. Multi-unit symbols appear once per unit in the file; all units of a reference are edited together and reported as one component with a unit count.

A schematic also holds a cached copy of every library symbol under `lib_symbols`. By default only the placed instances are edited, which is what the interactive fields table does. `--include-cache` also rewrites the cached definitions; be deliberate about it, because the cache is a snapshot of the library and editing it makes the schematic disagree with the library file, which `bac-kicad-libcheck` then correctly reports as stale.

New properties are placed at the symbol's origin, hidden, at 1.27 mm. The tool was tested on hand-written KiCad 9 schematics; open an edited schematic in the schematic editor before trusting it on anything that matters.

## 5. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.2.0 | 2026-09-07 | Moved into bac-utils from bac-kicad-tools (`bac-schfields`), renamed `bac-kicad-schfields`, rebuilt on `bac-common` and `bac-kicad-common`: the shared parser and field engine, standard flags, Rich output, `--dry-run` instead of dry-run-by-default with `--apply`, confirmation and `.bak` backups, `--help` from 30 lines to 23. Flag rules never touch the `lib_symbols` cache; a sheet that does not parse is reported and skipped; a failed write exits 1. 9 tests on a two-sheet fixture project (reused sheet, fill, overwrite gate, flag insert and rewrite, idempotency, symbols without properties). |
| 0.1.0 | 2026-09-04 | `bac-schfields` in bac-kicad-tools. |
