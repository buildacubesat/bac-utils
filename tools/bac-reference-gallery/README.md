# bac-reference-gallery v0.3.0

Build a CubeSat – the reference gallery: seven HTML/CSS/SVG boards that show the three BAC guides applied to documents, interfaces, charts, hardware and a product sheet, the shared stylesheet `css/tokens.css` they are built on, and `bac-reference-gallery`, which renders the boards to PNG and PDF through a headless Chromium.

> These examples demonstrate the BAC design language. They are references, not prescribed layouts. Apply the underlying principles rather than copying the compositions verbatim. If a board disagrees with a guide, the guide wins.

The BAC Identity Guide, the BAC Interface Design Guide and the BAC Project & Tooling Guide are the normative text; the gallery is the visual bridge between their rules and actual surfaces. The HTML/CSS/SVG source is canonical for the gallery; PNG and PDF files are generated from it.

## 1. Install

```sh
uv tool install ./tools/bac-reference-gallery   # from the bac-utils checkout
bac-reference-gallery --init                    # checks the pages, offers to download Chromium
bac-reference-gallery
```

The pages ship inside the installed package, so the renderer works from any folder. It depends on `bac-common` from this repository and installs from the checkout, not from PyPI.

Rendering needs a Chromium. `--init` looks for one and, when there is none, offers to download Playwright's build (about 150 MB, into Playwright's cache in your home folder). `BAC_CHROMIUM_PATH` in the environment or a `.env` file (see `.env.example`, `--env-file PATH`) names any other Chromium or Chrome binary; the renderer starts that file, so point it only at a browser you trust. Without the variable the order is Playwright's Chromium, then `chromium`, `chromium-browser`, `google-chrome` or `google-chrome-stable` on `PATH`. A snap-packaged Chromium (Ubuntu's default) cannot read hidden folders such as `~/.local`, where an installed tool keeps its pages, so prefer Playwright's build there. No `--config`: the tool has no persistent settings besides that variable.

## 2. The boards

Open `index.html` in a browser for the overview; every board is a page under `examples/`.

1. `identity-overview` – palette, typography, form, voice and the Ops/Mission modes at a glance.
2. `ops-vs-mission` – the same technical content in Ops and in Mission.
3. `document-family` – engineering report, README, product sheet, presentation and datasheet voices.
4. `interface-patterns` – controls, form fields, semantic state, callouts, stat cards, tables, a dark-mode panel and terminal output.
5. `data-visualisation` – the chart series order, stroke encoding, direct labels and dark-surface shades.
6. `physical-interface` – LED semantics, silkscreen labels, the shared R/Y/G indicator and traceability labels.
7. `product-sheet` – a full portrait Mission product sheet (1055 × 1491 px), print-first.

The landscape boards are 1600 × 1000 px. Engineering values on the boards are labelled as examples and are not project status records; the product sheet carries no price, discount or contact address for that reason and points at the store instead.

The pages follow the system's light or dark setting (`prefers-color-scheme`). Ops surfaces switch with it. Mission surfaces do not: the dark viewport is dark in both modes, and the paper areas and the whole product sheet carry `data-theme="light"`, because Mission collateral is designed for paper. The dark-mode panel on board 4 carries `data-theme="dark"` and shows the override attribute at work. The fonts – Nunito for the wordmark, Nunito Sans for headings, IBM Plex Mono for body text – load from Google Fonts, as the Identity Guide prescribes; offline, or where Google Fonts is blocked, the pages fall back to system fonts, and the renderer says so. The renderer gives the font hosts 8 seconds per request; after the first one that does not answer it stops asking for the rest of the run, so a firewall that drops the requests costs one wait, not one per board.

## 3. tokens.css – the shared stylesheet

`css/tokens.css` is the executable copy of the guides' tokens and the stylesheet other BAC surfaces take their values from: the marimo style cell, the Rich colours in `bac-common`, the bac-suite index page. Those copies repeat literal values because their platforms require it; when they disagree with `tokens.css` and the guides, they are the ones to change. The file has three parts:

- Canonical tokens, the same in both modes: typography, the brand and nebula palettes, the warm neutral ramp, the Mission surfaces, spacing, radii, shadows, borders (Identity Guide §3–§7) and the motion tokens (Interface Design Guide §4.1).
- Semantic tokens for light (`:root` and any `data-theme="light"` subtree) and for dark (`prefers-color-scheme: dark` and any `data-theme="dark"` subtree): surfaces, text, borders, link and focus ring, the status tints, the chart series.
- Derived values the guides describe but do not list, each a `color-mix()` of canonical tokens: inks for text on the status tints (`--bac-green-ink` …), inks for nebula text on Mission paper (`--mission-cyan-ink`, `--mission-copper-ink`), and lighter chart shades for dark surfaces.

Two semantic tokens differ from Identity Guide §4.4 so that small text meets WCAG AA (decided 2026-10-08; the guide change is drafted): `--text-muted` is `#6C6B67` in light and `#A3A29C` in dark (the guide's `#888884` measures 3.09:1 on `--bg` and 4.34:1 on a dark card), and `--link` is `#2F5FD6` in light and `#4277FD` mixed 70 % with white in dark (`#4277FD` measures 3.45:1 on the light `--bg` and 4.18:1 on the dark one). `--focus-ring` stays `#4277FD` in both modes: a focus ring needs 3:1, which it has. Muted text on `--surface-sunken` is 4.23:1 in light, so the boards' Ops wells take `--bg` instead.

Use it from another page with `<link rel="stylesheet" href="tokens.css">` (or `@import`) and build on the semantic tokens – `--bg`, `--surface-card`, `--text`, `--text-muted`, `--border`, `--link`, `--focus-ring` – rather than on the ramp, so the page follows both modes.

## 4. Rendering

```
bac-reference-gallery [options]
```

```sh
bac-reference-gallery                                  # all boards, PNG and PDF, light
bac-reference-gallery --only ops-vs-mission --format png
bac-reference-gallery --theme dark --out-dir ~/Desktop/gallery
```

Each board becomes `png/<name>.png` and `pdf/<name>.pdf` under the output folder (`./exports` unless `--out-dir DIR`), at the board's own size and one CSS pixel per image pixel; a `--theme dark` render adds `-dark` to the names. A run of the whole gallery as PDF also writes `pdf/bac-reference-exemplars.pdf` (or `-dark`), every board as one page in gallery order – but only when every board succeeded; a run with `--only` or with a failed board leaves the combined file as it was, so it is never replaced by a partial one. Renders are meant to be regenerated, so existing files are overwritten and the ✓ line says `(overwritten)`.

`-l` lists the boards; `--only NAME` (repeatable) picks some of them, in gallery order; an unknown name is an error before anything starts. `--source DIR` renders another copy of the gallery, such as one adapted for your project. `--dry-run` lists each board with the formats it would write, and the combined PDF when there is one; it needs no browser and reports a browser problem instead of stopping at it. A board that fails to render prints its ✗ line and the run goes on; the opening panel and the summary are printed on every path once the arguments are valid, and Ctrl-C ends the run with `Interrupted.` without waiting on the browser.

Exit codes: `0` every board rendered, `1` at least one board failed or no browser was found, `2` bad arguments.

## 5. Adapting for your own project

Copy the folder (`index.html`, `css/`, `assets/`, `examples/`), change the canonical tokens in `css/tokens.css` to your own identity, and adjust the boards. Render your copy with `bac-reference-gallery --source path/to/your-gallery`. The board order comes from the links in `index.html`; a page under `examples/` that the index does not link is rendered after the linked ones. The renderer sizes each image from the page's `.board` element, so a board of another size needs no change in the tool.

## 6. Accessibility

Every text element on every page meets WCAG AA (4.5:1, or 3:1 for large text) in both light and dark mode, measured against the background each element sits on; `tests/test_pages.py` checks it in a headless Chromium where one is installed, together with a layout check, since text that spills onto another surface escapes that measurement. Chart lines keep 3:1 graphical contrast against their surface, using the derived dark shades on dark surfaces (Interface Design Guide §8.1). Colour is never the only carrier of state: pills, callouts and status cells pair it with ✓, ✗ or ! and a word. Every page declares `lang="en"`, table headers carry `scope`, images carry `alt` text (empty where decorative), icons and decorative marks are hidden from assistive technology, the form demo uses labelled `<input>` and `<select>` elements, and the index page's cards are single links with a 3 px blue focus ring. Motion is limited to the index cards' 2 px lift and the buttons' press, both with the guide's motion tokens and both off under `prefers-reduced-motion: reduce`. A light/dark switch on the page is not provided; the system setting and the `data-theme` attribute cover it.

## 7. Maintenance

When the guides change:

1. Update the canonical rule in the relevant guide.
2. Update `css/tokens.css` only when a canonical token changes.
3. Update the smallest relevant board.
4. Re-render the exports.
5. Do not add volatile project status, dates, prices or milestone promises to the boards unless the point of the example requires them.

`REFERENCE-MAP.md` maps each board to the guide it mainly demonstrates.

## 8. Development

From the bac-utils root:

```sh
uv run pytest tools/bac-reference-gallery
uv run ruff check tools/bac-reference-gallery && uv run ruff format --check tools/bac-reference-gallery
```

`test_cli.py` drives the command with a fake renderer, `test_render.py` the renderer's shutdown and font gate with fake Playwright objects, `test_site.py` and `test_browser.py` the page and browser lookup. `test_pages.py` reads the HTML and CSS directly (language, table scopes, image text, no em dash, no volatile data on the product sheet, no inline hex in the dark-mode demo, the two dark blocks of `tokens.css` identical) and, in a headless Chromium, checks text contrast and layout (nothing spills out of a board or a card) on every page in both modes, the text colour of a pinned subtree, and a full render. The browser tests use the Chromium `BAC_CHROMIUM_PATH` names, else Playwright's, and are skipped when there is neither.

## 9. License

The renderer (`src/`, `pyproject.toml`, `tests/`) is MIT. The pages, stylesheets, SVG illustrations, this README and the rendered exports are documentation and are licensed CC BY-SA 4.0; see `LICENSE.md`.

## 10. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.3.0 | 2026-10-08 | Joins bac-utils on `bac-common`. The command is `bac-reference-gallery` (was `bac-reference-render`): `make_parser` flags, the opening panel and the summary on every path (the 0.2.0 error path crashed on `Console.print(file=)`), a ✓ or ✗ line per board with one failure no longer ending the run, Ctrl-C without a hang, `--out-dir` (exports no longer land inside the installed package), `--source`, repeatable `--only`, `--theme light|dark`, the combined PDF only after a complete run of the whole gallery, a warning when the canonical fonts are missing and a bounded wait for the font hosts; `--init` checks the pages and the browser and offers Playwright's Chromium. Boards open from their file URL, sized from the page; the pages ship inside the package. Pages: light and dark through `prefers-color-scheme` and `data-theme`, every colour through `tokens.css`, which now mirrors the Identity Guide in full (type scale, weights, motion, Mission tokens, dark tints), loads the fonts and pins a subtree's text colour with its tokens; `--text-muted` and `--link` meet AA; every text passes AA in both modes (the kicker's yellow text, the muted text, copper and cyan on paper failed before); focus ring, reduced motion, `lang`, `scope`, labelled form controls, single-link index cards, SVG icons instead of typographic stand-ins on the product sheet; the product sheet without price, discount, contact address and `✦`, its SKU on the guide scheme; Rail B's value no longer red for a warning; two boards no longer overflow into the footer and the LED board's caption is no longer cut off. |
| 0.2.0 | 2026-09-02 | State as received in batch 1: seven boards, `tokens.css`, the Playwright renderer `bac-reference-render` with `-l`, `--only`, `--format`, `--dry-run`, `--init`, `--env-file`; runs from a checkout only. |
