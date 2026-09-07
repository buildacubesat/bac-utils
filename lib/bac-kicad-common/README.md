# bac-kicad-common v0.1.0

Build a CubeSat – the KiCad library logic shared by `bac-kicad-symfields`, `bac-kicad-schfields` and `bac-kicad-libcheck`: TOML field rules and how they match items, property inspection with the spans an edit needs, the field engine that decides what a rule does to an item, rendering of new property blocks per file format, and the write-back with backup and confirmation. The s-expression reader itself lives in `bac_common.sexp`.

Lifted from `bac_kicad_core` of the bac-kicad-tools repository, which is folded into bac-utils.

## 1. What it provides

| Module | Contents |
| :-- | :-- |
| `bac_kicad_common.rules` | `load_rules_dir(dir, target=)`, `load_ruleset(path)`, `RuleSet`, `FieldRule`, `FlagRule`, `MatchContext`, `rules_for()`, `flags_for()`; every structural problem is a `RuleError` (a `ConfigError`) naming the file |
| `bac_kicad_common.props` | `properties(node)` → `Property` records with value and node spans, `property_value()`, `substitute()` for `${Field}` references, `Change` and its markers, `render_symbol_property()` (KiCad 9 and 10 shapes), `render_footprint_property()`, `render_schematic_property()` |
| `bac_kicad_common.fields` | `plan_fields(rules, props, fill_empty=, allow_overwrite=)` → `FieldPlan` with edits for existing values, blocks to add, the change log and skips |
| `bac_kicad_common.library` | suffixes, `find_files()`, `library_name()`, `containers()`, `reference_prefix()` |
| `bac_kicad_common.files` | `write_back(path, text, backup=)` (backup first, then write), `confirm(question, yes=)` |
| `bac_kicad_common.report` | `print_item()`, `print_changes()` – the shared step-log lines with `+ ~ ! *` markers |

## 2. Rule files

Rules are TOML, one directory for all tools. Each file declares `target = "symbol" | "footprint" | "schematic"`, an optional `[match]` block that picks the population, and `[[field]]` entries (plus `[[flag]]` entries on schematics) that may narrow themselves with `when`, `when_name` and `when_reference`. Filename order is precedence order; first match wins per field name. Match axes that do not apply to a target are rejected at load time. `Reference` is refused on schematics because its value also lives in the `(instances …)` block. The tool READMEs document the keys.

## 3. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.1.0 | 2026-09-07 | Lifted from bac-kicad-tools `bac_kicad_core` (`rules.py`, `splice.py`) and the container logic of its `items.py`; the field engine factored out of `bac-symfields` and `bac-schfields` into `plan_fields()`; KiCad 10 symbol properties rendered with `(show_name no)` and `(do_not_autoplace no)` so KiCad's next save adds no diff; write-back with backup and confirmation; `RuleError` is a `ConfigError` that exits 2, like a usage error. Line endings are preserved on write-back. 23 tests on the four BAC library fixtures. |
