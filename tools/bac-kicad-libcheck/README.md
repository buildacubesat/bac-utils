# bac-kicad-libcheck v0.2.0

Build a CubeSat – verifies a KiCad library project. A library project is a schematic and board whose only purpose is to place every symbol and footprint of a library exactly once, so that the placement itself is the review: if a part is missing, duplicated, stale against its library copy, or its footprint's 3D model does not resolve, the run fails. Nothing is written; the tool only reads.

## 1. Install

```sh
uv tool install ./tools/bac-kicad-libcheck     # from the bac-utils checkout
cd path/to/library-project
bac-kicad-libcheck --init                      # writes ./bac-kicad-libcheck.toml to edit
bac-kicad-libcheck
```

The config describes the project, not the user, so it lives next to the project as `bac-kicad-libcheck.toml` rather than under `~/.config/bac/`. `examples/bac-kicad-libcheck.toml` is a commented copy of what `--init` writes. The library-sync check needs `kicad-cli` on `PATH` (it ships with KiCad 8 and later); without it the check is reported as a warning and the rest still runs.

## 2. Usage

```
bac-kicad-libcheck [--config PATH] [--skip-sync] [--strict] [--init]
```

`--config` names the project config (default `./bac-kicad-libcheck.toml`), `--skip-sync` leaves `kicad-cli` out, `--strict` turns warnings into failures. Exit codes: `0` all checks passed, `1` a failure (or a warning with `--strict`, or an unusable config), `2` bad arguments – suitable for CI.

```
─────────────────────────── Symbol placement ───────────────────────────
  ✗ bac:L 0402 10u – in library, never placed
  ✗ bac:C 0402 100n – placed 2× (C1, C2)
    1/3 placed exactly once
────────────────────────────── 3D models ───────────────────────────────
  ✗ bac:C-0402-100n – ${BAC_LIB_DIR}/3d/C-0402-100n.wrl
    but C-0402-100n.step exists
  ! bac:TP-1.0mm – no 3D model attached
```

## 3. Configuration

```toml
[project]
schematic = "LibraryProject.kicad_sch"
board = "LibraryProject.kicad_pcb"

[[symbol_library]]
nickname = "bac"
path = "libs/bac.kicad_symdir"

[[footprint_library]]
nickname = "bac"
path = "libs/bac.pretty"

[model_paths]
BAC_LIB_DIR = "."

[kicad]
cli = "kicad-cli"
erc_types = ["lib_symbol_mismatch", "lib_symbol_issues"]
drc_types = ["lib_footprint_mismatch", "lib_footprint_issues"]

[models]
extensions = [".step", ".stp", ".wrl"]
```

Libraries are declared explicitly rather than read from `sym-lib-table` and `fp-lib-table`, so the scope of the check is fixed and reviewable and does not change when someone adds an unrelated library to their table. The `nickname` must match the one in the project's library tables, because that is what appears in every `lib_id`. Relative paths resolve against the config file's directory. A symbol library may be a `.kicad_symdir` directory (KiCad 10) or a single packed `.kicad_sym`.

## 4. Checks

### 4.1 Placement

Every symbol in the declared libraries must appear exactly once across the schematic sheet hierarchy, and every footprint exactly once on the board. Three failure modes are reported: in the library but never placed; placed more than once (every offending reference is listed); placed but not in any declared library. Nothing is exempt – power symbols, fiducials and graphical footprints are held to the same rule, so if a part exists in the library it has to be on the sheet. Multi-unit symbols appear once per unit in the file and are de-duplicated on `(lib_id, reference)` before counting.

### 4.2 3D models

Every `(model …)` reference in every library footprint is resolved and checked. `${KIPRJMOD}` expands to the config file's directory; other variables resolve against `[model_paths]` first, then the environment. A footprint with no model at all is a warning, not a failure, since that is sometimes correct. When the referenced file is missing but a sibling with another known extension exists, the report says so – KiCad tolerates a `.step` reference backed by a `.wrl` file, which makes this a common and easily missed slip.

### 4.3 Library sync

Whether a placed item still matches its library copy is delegated to KiCad itself: `kicad-cli sch erc … --format json` and `kicad-cli pcb drc … --format json` are run and their reports filtered down to the library-mismatch violation types; everything else KiCad reports is ignored, since this is not a general ERC/DRC runner. The type names are configurable because they are the one part of this that can change between KiCad versions, and the defaults have not been verified against a KiCad 10 report yet. If a configured type never appears anywhere in the report, the run says so rather than quietly reporting a clean result – a filter that matches nothing looks identical to a project with no problems, and that distinction matters. Check that note the first time you run this against your KiCad version.

## 5. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.2.0 | 2026-09-07 | Moved into bac-utils from bac-kicad-tools (`bac-libcheck`), renamed `bac-kicad-libcheck`, rebuilt on `bac-common` and `bac-kicad-common`: the shared parser, standard flags, `--init` for the project config (`bac-kicad-libcheck.toml` instead of `libcheck.toml`), Rich sections and summary, a spinner around `kicad-cli`, config errors as `ERROR` lines. Reads `.kicad_symdir` directories as well as packed `.kicad_sym` files. 17 tests on a fixture library project with `kicad-cli` mocked. |
| 0.1.0 | 2026-09-04 | `bac-libcheck` in bac-kicad-tools. |
