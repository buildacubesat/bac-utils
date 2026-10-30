# bac-design-export v0.1.0

Build a CubeSat – exports the BAC guides in [bac-design](https://github.com/buildacubesat/bac-design) from Markdown to PDF as BAC documents, per Identity Guide §7.3. The Markdown stays authoritative; the PDFs in bac-design `exports/` are for handing to people outside git.

## 1. Install

```sh
uv run --no-sync bac-design-export              # from the bac-utils checkout: every guide into <design>/exports
uv run --no-sync bac-design-export --check      # write nothing, exit 1 if an export is stale
uv tool install ./tools/bac-design-export       # or as a standalone tool
```

The tool finds the bac-design checkout above the current folder or beside one (`~/bac/bac-design` next to `~/bac/bac-utils`), or takes `--design PATH`. No `--init` and no config.

WeasyPrint draws the pages and needs Pango 1.44 or newer from the system (`apt install libpango-1.0-0 libpangoft2-1.0-0`; Ubuntu and Fedora desktops have it). Without it, everything but the PDF step works: `--list`, `--check` and `--format html`.

## 2. Usage

```
bac-design-export [DOC ...] [--check] [--paper a4|letter] [--format pdf|html] [--design PATH] [-o DIR] [--dry-run] [-l]
```

| Flag | Meaning |
| :-- | :-- |
| `DOC` | Guide names (`bac-identity-guide`) or Markdown files; default every `guides/*.md` |
| `--check` | Write nothing; exit 1 if any PDF is missing or older than its sources |
| `--paper` | `a4` (default) or `letter`; a Letter export is written as `<name>-letter.pdf` |
| `--format` | `pdf` (default) or `html`, the page WeasyPrint would draw, for a quick look in a browser |
| `-o`, `--out-dir` | Where to write; default `<design>/exports` |
| `-l`, `--list` | Print the guides found and exit |

Exit codes: `0` every export current or written, `1` an export is stale under `--check`, a document failed or no checkout was found, `2` bad arguments.

A run over all seven guides takes about 45 seconds. The first run also cuts the static Nunito Sans weights (below) into `~/.cache/bac-design-export/fonts/`.

## 3. How a Guide Becomes a Document

1. **Front matter.** The first `# Title` is the document title. The bold line after it – `**Build a CubeSat – Brand, visual & communication standard** Version 1.3, 2026-10-29 · Authors: …` – gives the lead (the text after "Build a CubeSat –"), the version and date (the eyebrow and the running header) and, after a `·`, the meta line. A document without that line exports with its title only.
2. **Body.** markdown-it renders CommonMark with tables. Numbered headings (`## 3. Typography`, `### 4.1 …`) get their number in its own span, set in IBM Plex Mono. Relative links to other files in the repository become their GitHub addresses.
3. **Stylesheet**, assembled per run in this order:
   - `@font-face` rules for the self-hosted fonts in bac-design `fonts/`. Nunito Sans is a variable font; PDF renderers pick its instances unreliably, so the tool cuts static instances at 400, 500, 600 and 700 (opsz 10) with fontTools. IBM Plex Mono is used as shipped, and *BAC Symbols*, an alias for the same Plex Mono files, covers the arrows and box-drawing characters that Nunito Sans lacks. ✓ and ✗ come from the system font: no BAC font has ✗, and the pair should match – to be decided, Identity Guide §8.
   - `tokens.css` exactly as `bac-design-tokens` renders it, minus its Google Fonts imports, so the export works offline. No token value is copied into this tool.
   - `src/bac_design_export/print.css`: the page, the print type sizes and the running header and footer. It names no color, family or radius of its own – every one is a `var(--…)`.
   - The running header and footer of the document: its title, version and date, and the repository and license line.
4. **PDF.** WeasyPrint embeds the subset fonts and writes PDF bookmarks from the headings. The page reads: the logo, the kicker and eyebrow, the title, the lead and the contents with page numbers on page one; the body from page two; a colophon at the end.

## 4. `--check`

PDFs are not byte-identical between machines (font subsetting, library versions), so the check does not compare bytes. Each PDF carries `bac-design-export <version> · source <hash>` in its Creator field, a hash over the Markdown, the rendered stylesheet, the font file names, the logo, the paper size and the tool version. `--check` recomputes the hash and compares. A guide edit, a token change, a new mark revision or a new tool version each make the export stale.

## 5. Typst

Typst is a candidate backend for later. The tool keeps the HTML stage separate from the PDF step (`--format html`), so a Typst writer could sit beside WeasyPrint and take the same tokens.

## 6. License

MIT. The PDFs it writes carry the license of the guides they contain (CC BY-SA 4.0) and the BAC Marks, which the BAC Trademark Policy governs.

## 7. Version History

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.1.0 | 2026-10-29 | First release: Markdown → HTML → PDF with markdown-it and WeasyPrint, the tokens from `bac-design-tokens`, the self-hosted fonts with static Nunito Sans instances and Plex Mono for arrows and box drawing, ✓ and ✗ from the system font, A4 and Letter, the front matter parsed from each guide's bold line, contents with page numbers, running header and footer, `--check` by source hash, `--format html`. Replaces the pandoc → docx → LibreOffice route. |
