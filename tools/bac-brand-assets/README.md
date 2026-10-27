# bac-brand-assets v0.1.0

Build a CubeSat – the construction of the BAC marks and the generator that writes them. The symbol, the wordmark and the logo described in the BAC Identity Guide §8 are defined here as geometry and type settings, and written as SVG into the `assets/` folder of the bac-design checkout, so every file is reproducible from a handful of numbers and nobody edits a mark by hand.

## 1. Install

```sh
uv run --no-sync bac-brand-assets            # from the bac-utils checkout: write every asset
uv run --no-sync bac-brand-assets --check    # write nothing, exit 1 if an asset is stale
uv run --no-sync bac-brand-assets -l         # the file names
```

No `--init` and no config: the tool finds the bac-design checkout as a sibling of bac-utils (or takes `--design PATH`) and writes into its `assets/` folder (or `-o DIR`). `--dry-run` lists what would change. It needs `fonts/Nunito[wght].ttf` in that checkout – the self-hosted copy the Identity Guide §3 prescribes – and nothing else from outside the repository, so a run is offline and deterministic.

## 2. What it writes

Nine files, three marks in three colourings, versioned like hardware (Project & Tooling Guide §2.2) with the version in the file name:

| File | What it is |
| :-- | :-- |
| `bac-symbol-{black,white,currentcolor}-v4r1.svg` | The cube mark on a 400 × 650 canvas |
| `bac-wordmark-{black,white,currentcolor}-v4r1.svg` | BUILD A / CUBESAT in Nunito, outlined |
| `bac-logo-{black,white,currentcolor}-v4r1.svg` | The horizontal lockup of the two |

The `currentcolor` files take the colour of the surrounding text when inlined in HTML, which is how the gallery and the docs site use the symbol; the black and white files are for everything that cannot inherit a colour. Every file carries a `<title>`, a `<desc>` with the construction and the trademark notice, and Dublin Core metadata naming nihil.space GmbH; none carries a `width` or `height`, only the `viewBox`.

## 3. The construction

All values live at the top of `src/bac_brand_assets/assets.py`; the Identity Guide §8 states the same numbers in prose. A change goes into both in the same change set, and the version in `VERSION` moves with it (a redrawn mark is a new `v`, an adjusted one a new `r`).

| Part | Construction |
| :-- | :-- |
| Symbol | A 1 × 1 × 2 box in true 30° isometric projection, cube edge 200: 346.41 wide, 600 tall, centred on the 400 × 650 canvas. One hexagonal outline with its six corners rounded 5 from the vertex, the inner edges (the top face's lower edges, the centre vertical, the lower cube's top face) as a second path ending on the rounded corners, and a dot at the centre of the top face – an ellipse 60 × 34.64, the 1:√3 ratio a circle takes in isometric projection. Stroke 15, round joins and caps, no fill. |
| Wordmark | Nunito at weight 350, uppercase, tracking −0.03 em; cap height 100, 150 from baseline to baseline, "BUILD A" justified to the width of "CUBESAT"; 25 of margin. Outlined with fontTools so the files have no font dependency. |
| Logo | The symbol on its own canvas; the wordmark to its right, 70 from the canvas edge, scaled so its two-line block is 70 % of the cube height and centred on the cube. At that size the letter stems are ~15, the same as the cube stroke. |

The coordinates are written with two decimals, which is below anything a renderer can show at any size and keeps the files small (1.5 KB for the symbol, 8 KB for the wordmark).

## 4. Templates

`templates/` holds the generators of the document templates in bac-design `templates/` (letterhead v1r1 in English and German, the 16:9 slides template v1r1). They are Node scripts on docx-js and pptxgenjs rather than part of the Python tool, with a Python step before and after:

```sh
cd templates && npm install                                   # docx, pptxgenjs
uv run --with cairosvg python marks.py ../../../../bac-design  # the marks as PNG
node letterhead.js                                            # bac-letterhead-{en,de}-v1r1.docx
node slides.js && python theme.py bac-slides-template-v1r1.pptx
```

The outputs are copied into bac-design `templates/` by hand; a change to a script moves the template's version (`v<version>r<revision>`, in the file name). Every number the scripts use – margins, sizes, colours, layout names – is listed in bac-design `templates/README.md`.

## 5. License

The code is MIT. The files it writes are BAC Marks of nihil.space GmbH: not covered by this repository's licences, their use governed by the [BAC Trademark Policy](https://github.com/buildacubesat/bac-design/blob/main/guides/bac-trademark-policy.md). Nunito is licensed under the SIL Open Font License 1.1, which permits outlining it into the marks.

## 6. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.1.0 | 2026-10-27 | First release with the marks at v4r1: the symbol reconstructed from exact isometric geometry (the v3r1 file was a bitmap trace), the wordmark reset in Nunito, replacing the legacy wordmark face, the horizontal logo as the one lockup; black, white and currentColor files with title, desc and Dublin Core metadata; `--check` for CI. |
