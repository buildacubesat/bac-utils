# bac-brand-assets v0.2.0

Build a CubeSat – the construction of the BAC marks and the generator that writes them. The symbol, the wordmark and the logo described in the BAC Identity Guide §8 are defined here as geometry and type settings, and written as SVG into the `assets/` folder of the bac-design checkout, so every file is reproducible from a handful of numbers and nobody edits a mark by hand.

## 1. Install

```sh
uv run --no-sync bac-brand-assets            # from the bac-utils checkout: write every asset
uv run --no-sync bac-brand-assets --check    # write nothing, exit 1 if an asset is stale
uv run --no-sync bac-brand-assets -l         # the file names
uv run --no-sync bac-brand-assets --no-raster  # SVG only
```

No `--init` and no config: the tool finds the bac-design checkout as a sibling of bac-utils (or takes `--design PATH`) and writes into its `assets/` folder (or `-o DIR`). `--dry-run` lists what would change. It needs `fonts/Nunito[wght].ttf` in that checkout – the self-hosted copy the Identity Guide §3 prescribes – and nothing else from outside the repository, so a run is offline and deterministic.

## 2. What it writes

28 SVG files, versioned like hardware (Project & Tooling Guide §2.2) with the version in the file name:

| File | What it is |
| :-- | :-- |
| `bac-symbol-{black,white,currentcolor}-v4r1.svg` | The cube mark on a 400 × 650 canvas |
| `bac-wordmark-{black,white,currentcolor}-v4r1.svg` | BUILD A / CUBESAT in Nunito, outlined |
| `bac-logo-{black,white,currentcolor}-v4r1.svg` | The horizontal lockup of the two |
| `bac-logo-tagline-{black,white,currentcolor}-v4r1.svg` | The logo with SPACE FOR EVERYONE under the wordmark, in mono between two rules |
| `bac-symbol-badge-{light,dark}-v4r1.svg`, `bac-logo-badge-{light,dark}-v4r1.svg` | The symbol on a filled, rounded hexagonal badge, and the logo on that badge merged with a rounded rectangle around the wordmark – for stickers, avatars and busy backgrounds; light is white with a `--border-strong` hairline, dark is `--bg` dark with its hairline |
| `rocinante-{symbol,wordmark,logo}-{black,white,currentcolor,colour}-v2r1.svg` | The Rocinante marks (the flight software stack): the horse in its ring, ROCINANTE over "CUBESAT SOFTWARE STACK", and the stacked lockup; `colour` is the two-tone in brand colours |

Every coloured SVG is also rendered to `png/` and `webp/` at 512 and 2048 px on the longest side (`bac-logo-black-v4r1-2048.png`), transparent, the WebP lossless – 84 files for the places that cannot take an SVG. A rendering counts as current when it exists, since encoders differ between machines; delete one to have it redone. The `currentcolor` files take the colour of the surrounding text when inlined in HTML, which is how the gallery and the docs site use the symbol; the black and white files are for everything that cannot inherit a colour. Every file carries a `<title>`, a `<desc>` with the construction and the trademark notice, and Dublin Core metadata naming nihil.space GmbH; none carries a `width` or `height`, only the `viewBox`.

## 3. The construction

All values live at the top of `src/bac_brand_assets/assets.py`; the Identity Guide §8 states the same numbers in prose. A change goes into both in the same change set, and the version in `VERSION` moves with it (a redrawn mark is a new `v`, an adjusted one a new `r`).

| Part | Construction |
| :-- | :-- |
| Symbol | A 1 × 1 × 2 box in true 30° isometric projection, cube edge 200: 346.41 wide, 600 tall, centred on the 400 × 650 canvas. One hexagonal outline with its six corners rounded 5 from the vertex, the inner edges (the top face's lower edges, the centre vertical, the lower cube's top face) as a second path ending on the rounded corners, and a dot at the centre of the top face – an ellipse 60 × 34.64, the 1:√3 ratio a circle takes in isometric projection. Stroke 15, round joins and caps, no fill. |
| Wordmark | Nunito at weight 350, uppercase, tracking −0.03 em; cap height 100, 150 from baseline to baseline, "BUILD A" justified to the width of "CUBESAT"; 25 of margin. Outlined with fontTools so the files have no font dependency. |
| Logo | The symbol on its own canvas; the wordmark to its right, 70 from the canvas edge, scaled so its two-line block is 70 % of the cube height and centred on the cube. At that size the letter stems are ~15, the same as the cube stroke. |
| Tagline | "SPACE FOR EVERYONE" in IBM Plex Mono with 0.286 em tracking (the Rocinante subtitle's), sized so the text takes 72 % of the wordmark's width, centred under it 2.34 tagline sizes below the baseline; a rule either side fills the rest of the width. The wordmark-and-tagline block is centred on the cube. |
| Badge | The cube's hexagon grown by 70, corners rounded 60 from the vertex, a 2-unit hairline. The logo badge merges that hexagon with a rectangle grown by the same 70 around the wordmark and reaching left to the cube's centre line, so the two meet on the hexagon's diagonals; the merged outline is rounded 60, the two concave corners where they meet 30. Light: white on `#D0D0D0`; dark: `#1F1E1D` on `#3F3E3D`. |
| Rocinante | The head, eye and ear are the vector paths of the original Krita artwork (`Rocinante_Logo.kra`), scaled 5× onto a 550 × 550 canvas with the ring's centre at the centre. The ring is a true circle, centre-line radius 241.35, stroke 11, with three gaps (at −80…−56°, 97…117°, 155…167°) where the ears and the neck cross it. ROCINANTE in Nunito 350 at 120 with 15 tracking; the subtitle in IBM Plex Mono 400 at 35 with 10 tracking and a 54-unit rule either side; the logo stacks the wordmark 160 under the ring. Two-tone in brand colours: `--text-strong` `#1F1F1F` for head and word, `--bac-blue` `#004C8B` for ring and subtitle. |

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
| 0.2.0 | 2026-10-27 | The logo with tagline; the symbol and logo badges (light, dark); the Rocinante marks at v2r1 from the Krita vector layers, monochrome and two-tone in brand colours; the subtitle-with-rules setting shared by the Rocinante wordmark and the BAC tagline; PNG and WebP renderings at 512 and 2048 px. 28 SVG and 84 raster files. |
| 0.1.0 | 2026-10-27 | First release with the marks at v4r1: the symbol reconstructed from exact isometric geometry (the v3r1 file was a bitmap trace), the wordmark reset in Nunito, replacing the legacy wordmark face, the horizontal logo as the one lockup; black, white and currentColor files with title, desc and Dublin Core metadata; `--check` for CI. |
