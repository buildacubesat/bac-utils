# bac-design-tokens v0.1.0

Build a CubeSat – the canonical design tokens of the BAC Identity Guide 1.0 and the BAC Interface Design Guide 1.0, and the generator that writes every copy the repository keeps. Colours, type, spacing, radii and motion are defined once, in `src/bac_design_tokens/tokens.json`; the stylesheets, the terminal colours and the notebook style cells are written from it, so no surface carries values of its own.

## 1. Install

```sh
uv run --no-sync bac-design-tokens            # from the bac-utils checkout: write every copy
uv run --no-sync bac-design-tokens --check    # write nothing, exit 1 if a copy is stale
```

No `--init` and no config: the tool finds the checkout from the current folder (or `--root PATH`) and writes only inside it.

## 2. What it writes

| Copy | What the generator owns |
| :-- | :-- |
| `tools/bac-reference-gallery/css/tokens.css` | the whole file |
| `ops/bac-suite/src/bac_suite/static/tokens.css` | the whole file, identical to the gallery's |
| `lib/bac-common/src/bac_common/ui.py` | the `GREEN`, `RED`, `YELLOW` lines between the `bac-design-tokens` markers |
| every marimo notebook (`notebooks/bac-*/bac_*.py`, `notebooks/bac-*/demo/bac_*.py`, `ops/*/src/*/notebook.py`) | the style cell from `<style>` to its `--heading-font` rule, and the chart lines `PALETTE`, `MUTED` and, where present, `TEXT`, `SEQUENTIAL` and the tint mix |

Code around a marked region stays as written; a notebook can add its own rules after the `--heading-font` line (bac-pricing does). The tool's tests run `--check`, so a token change that is not regenerated fails CI.

BAC Ground keeps its own repository and takes a copy of the generated `tokens.css`.

## 3. tokens.json

The file follows the W3C design-tokens format: groups carry a `$description`, tokens a `$type` and a `$value`, and `{name}` refers to another token. Two top-level sections map to the stylesheet's blocks:

- `canonical` – values that are the same in light and dark: type, brand and status fills, the nebula triad and its inks, the neutral ramp, Mission surfaces, the hero card, the shared chart palette, spacing, corners and motion.
- `semantic` – values that switch with the theme. The light value is `$value`; the dark value sits in `$extensions."space.buildacubesat.modes".dark`.

Every colour is a literal uppercase `#RRGGBB` (or an `rgba()` for the Mission glow and wells), so the Rich and marimo copies can use the values directly. The tests check the AA contrast pairs the guides promise in both modes.

To change a value: edit `tokens.json`, run `uv run --no-sync bac-design-tokens`, check the gallery in both modes (`uv run --no-sync bac-reference-gallery --serve`), and commit `tokens.json` together with every copy it rewrote. A change of meaning – a new token, a retired one – belongs in the guides first.

## 4. License

The code is MIT. `tokens.json` and the stylesheets written from it are MIT or CC BY-SA 4.0, at your option, like the gallery's stylesheets, so any software – BAC Ground included – can take the values.

## 5. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.1.0 | 2026-10-27 | First release with the 1.0 guides: `tokens.json` as the single source of the BAC tokens (the BAC Ground console language with Nunito / Nunito Sans / IBM Plex Mono, light #F9F9F9 and dark #1F1E1D, the console status fills and inks, the Orbital Teal / Ion Violet / Plasma Rose triad, Mission paper #F4F1EA, pill and 6/10 px corners, no shadows, the hero card and the neutral dark-mode accent), and the generator for the gallery and bac-suite stylesheets, the Rich colours and the notebook style cells, with `--check` for CI. |
