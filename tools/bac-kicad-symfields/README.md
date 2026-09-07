# bac-kicad-symfields v0.3.0

Build a CubeSat – one tool for keeping a KiCad symbol and footprint library uniform. `fields` adds, fills and (when allowed) overwrites property fields from TOML rule files; `lint` reports what drifts from the library conventions – font sizes, the footprint nickname prefix, duplicate UUIDs, and with `--rules` the fields that are missing; `fix` corrects the sizes. KiCad's own symbol fields table and library editor do the same interactively, but the change is not reviewable, not repeatable and leaves no record. Here the rule file is the record.

Files are edited by splicing byte ranges into the original text, never by re-serialising the parsed tree: untouched bytes stay identical, a git diff shows only the intended change, and a second run is a no-op. Nothing is written without a confirmation (`--yes` for scripts), the previous content is kept as `<file>.bak` unless `--no-backup`, and `--dry-run` only reports. KiCad 9 and 10 formats are both handled; the four BAC library files under `tests/fixtures/` round-trip byte for byte.

## 1. Install

```sh
uv tool install ./tools/bac-kicad-symfields     # from the bac-utils checkout
bac-kicad-symfields lint libs/
```

The tool works without setup: the built-in defaults are the BAC library conventions. `bac-kicad-symfields init` writes them to `~/.config/bac/bac-kicad-symfields.toml` for editing (§5).

## 2. Usage

```
bac-kicad-symfields fields PATH... --rules DIR [--dry-run] [--yes] [--no-backup] [--no-fill-empty] [--allow-overwrite]
bac-kicad-symfields lint   PATH... [--rules DIR]
bac-kicad-symfields fix    PATH... [--dry-run] [--yes] [--no-backup]
bac-kicad-symfields init
```

`PATH` is a `.kicad_sym` or `.kicad_mod` file, a `.kicad_symdir` or `.pretty` directory, or any parent directory – directories are searched recursively and both file types are handled in one pass. `--rules DIR` may be omitted when the config names a rules directory.

### 2.1 fields

Every rule file that matches an item is applied in filename order; per field name the first matching entry wins. A field that is absent is added after the item's last property, hidden by default, at the size the rule gives (1.27 mm for symbols and 1.0 mm for footprints when it gives none). A field that exists but is empty is filled, unless `--no-fill-empty`. A field that holds a value is left alone – unless the rule says `overwrite = true` *and* the run passes `--allow-overwrite`. Two gates, because a wrong regex here rewrites data across the whole library rather than merely adding a blank field. Without the flag the rule is reported as skipped, with what it would have replaced.

```
  sym  bac:TI TPSM5D1806RDBR [U]
      + Manufacturer = (empty placeholder)   (00-general.toml)
      + Manufacturer PN = (empty placeholder)   (00-general.toml)
  sym  bac:bac R [R]
      ~ Max Height = 0.55 mm   (10-passives.toml)
      · Datasheet URL skipped: requires Manufacturer PN
  fp   bac:R-0603-100k
      + Land Pattern = IPC-7351 nominal   (30-footprints.toml)
  Write 3 file(s)? [y/N]
```

Markers: `+` added, `~` filled an empty value, `!` overwrote a value, `·` skipped with a reason.

### 2.2 lint

Reports, per file, everything that deviates from the conventions in the config, as a table (file, item, where, found, expected), and exits 1 when there is anything to report – made for CI on a library repository.

| Check | Symbols | Footprints |
| :-- | :-- | :-- |
| Property font size | must be one of `property_sizes` (1.27 or 0.762) | must be `font_size` (0.8) |
| Pin names, pin numbers, text items | must be `pin_size` (1.27) | – |
| Font thickness | – | must be `font_thickness` (0.1); a missing thickness is a finding |
| `Footprint` property | must start with `footprint_prefix` | – |
| UUIDs | – | no value may appear twice in a file |
| Fields (with `--rules`) | anything `fields` would add, fill or overwrite | same |

### 2.3 fix

Sets every non-conforming size in place: a symbol property size outside `property_sizes` becomes `property_fix_size` (0.762), pin and text sizes become `pin_size`, footprint property and text fonts become `font_size` with `font_thickness` (a missing thickness is inserted). Only the numbers change. The footprint prefix and duplicate UUIDs are reported by `lint` and left to you: which of two identical lines to delete is a decision, not a fix.

Exit codes: `0` done (`lint`: clean), `1` findings or a failed write, `2` bad arguments or an unusable rules directory.

## 3. Rule files

TOML, one directory for all the KiCad tools. Each file declares a `target` (`symbol`, the default, or `footprint`; `schematic` files belong to `bac-kicad-schfields` and are skipped here), an optional `[match]` block that picks the population, and `[[field]]` entries. `examples/rules/` holds a commented set using the BAC field vocabulary.

```toml
title = "Passive components"
target = "symbol"

[match]
reference_prefixes = ["R", "C", "L"]

[[field]]
name = "Max Height"
value = "0.55 mm"
size = 0.762
when = { Package = "^0603$" }
```

| `[match]` axis | Applies to | Matches against |
| :-- | :-- | :-- |
| `reference_prefixes` | symbols | leading letters of the `Reference` property (`#` stripped) |
| `libraries` | both | the `.kicad_symdir` / `.pretty` directory name without its suffix |
| `name_regex` | both | symbol or footprint name, searched |
| `properties` | both | regex per existing property value, e.g. `Value = "^1k$"` |

Axes combine with AND, values within an axis with OR; an omitted axis is a wildcard. An axis that does not apply to the target (`reference_prefixes` on footprints, which all say `REF**`) is a load-time error.

| `[[field]]` key | Default | Meaning |
| :-- | :-- | :-- |
| `name` | required | property key as it appears in KiCad |
| `value` | `""` | the value; empty creates the field as a placeholder; `${Other Field}` expands to another property of the same item, in rule order |
| `requires` | `[]` | fields that must exist and be non-empty, else this entry is skipped |
| `hide` | `true` | whether a new property is hidden |
| `size` | format default | font size in mm |
| `thickness` | `0.15` | footprints only, stroke thickness in mm |
| `layer` | `F.Fab` | footprints only |
| `overwrite` | `false` | allow replacing an existing non-empty value (needs `--allow-overwrite` on the run) |
| `when` | `{}` | regex per property value, narrowing this one entry |
| `when_name` | – | regex on the item name, narrowing this one entry |

Several entries may share a name; `when` is evaluated before de-duplication, so a file can hold a lookup table – order the entries most specific first, and anchor the regexes (`^1k$`, not `1k`, which also matches `21k`).

## 4. Output shape

New symbol properties follow the file's format version: KiCad 10 files (`version 20251024` and later) get `(show_name no)`, `(do_not_autoplace no)` and `(hide yes)` as direct children of the property, KiCad 9 files keep `(hide yes)` inside `(effects …)`. New footprint properties get `(unlocked yes)`, a layer, a fresh UUID and the footprint font. Values with quotes or line breaks are escaped the way KiCad writes them.

## 5. Adapting for your own project

`bac-kicad-symfields init` writes the conventions to `~/.config/bac/bac-kicad-symfields.toml`:

```toml
rules = ""                      # default --rules directory
tolerance = 0.001

[symbol]
property_sizes = [1.27, 0.762]  # accepted property font sizes (mm)
property_fix_size = 0.762       # what fix sets a non-accepted size to
pin_size = 1.27                 # pin names, numbers and text items
footprint_prefix = "bac KiCad Library Footprints v1:"

[footprint]
font_size = 0.8
font_thickness = 0.1
```

Change the sizes and the prefix to your library's, point `rules` at your rule directory, and copy `examples/rules/` as a starting point – replace the illustrative heights and the field names with your own vocabulary before running `fields` without `--dry-run`.

## 6. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.3.0 | 2026-09-07 | Moved into bac-utils from bac-kicad-tools (`bac-symfields`), renamed `bac-kicad-symfields`, rebuilt on `bac-common` and `bac-kicad-common` with the shared span-recording parser. Subcommands: `fields` (the previous tool), `lint` and `fix` absorb the four `bac-kicad-misc` scripts (`kicad9_sym_lint.py`, `kicad9_sym_surgical_fix_sizes.py`, `kicad9_fp_text_fontfix.py`; `kicad9_sym_fix_text_sizes.py` dropped – it stripped quotes and wrote libraries on one line). Accepted property sizes 1.27 and 0.762 with 0.635 corrected to 0.762; pin, text and footprint fonts checked; duplicate UUIDs reported; lint exits 1 (was 2). Standard flags, Rich output, `--dry-run`, confirmation and `.bak` backups, config with `init`; KiCad 10 properties carry `show_name`/`do_not_autoplace`; example rules in the BAC field vocabulary. A failed write exits 1. 18 tests plus the shared library's 23. |
| 0.2.0 | 2026-09-04 | `bac-symfields` in bac-kicad-tools: symbol and footprint targets, per-field size, KiCad 10 `(hide yes)` placement. |
| 0.1.0 | 2026-09-04 | First version, symbols only. |
