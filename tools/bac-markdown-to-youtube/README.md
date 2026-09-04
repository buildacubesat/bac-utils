# bac-markdown-to-youtube v0.2.0

Build a CubeSat – converts Markdown into the formatting YouTube renders in video descriptions. Write the description once in Markdown next to the script, run it through the tool, paste the result into YouTube Studio.

YouTube understands three inline styles: `*bold*`, `_italic_` and `-strikethrough-`, and it nests them (`*_bold italic_*`). It renders a style only when whitespace or the line boundary surrounds the styled span; `*bold*,` shows the asterisks. The tool inserts that whitespace where the Markdown source has punctuation directly after (or before) a styled phrase, which is the one visible change from the source text. Everything Markdown has and YouTube lacks – headings, links, code, block quotes, HTML – is flattened to plain text.

## 1. Install

```sh
uv tool install ./tools/bac-markdown-to-youtube     # from the bac-utils checkout
bac-markdown-to-youtube -v
```

No `--init`: the tool has no settings.

## 2. Usage

```
bac-markdown-to-youtube [INPUT] [-o FILE]
```

`INPUT` is a Markdown file; without it (or with `-`) the tool reads stdin. Output goes to stdout unless `-o FILE` names a file, so both of these work:

```sh
bac-markdown-to-youtube description.md | pbcopy
bac-markdown-to-youtube description.md -o description.txt
```

Exit codes: `0` converted, `1` the input was not UTF-8 or the output could not be written, `2` bad arguments.

## 3. Conversion table

| Markdown | YouTube |
| :-- | :-- |
| `**bold**`, `__bold__` | `*bold*` |
| `*italic*`, `_italic_` | `_italic_` |
| `***both***`, `___both___` | `*_both_*` |
| `~~gone~~` | `-gone-` |
| `Buy **now**, not **later**.` | `Buy *now* , not *later* .` |
| `# Heading` (any level) | `*Heading*` |
| `[text](url)` | `text: url` (no colon when the text ends in punctuation) |
| `<https://…>`, bare URLs | the URL, untouched |
| `` `code` ``, fenced blocks | the code, without the backticks or fences |
| `* item`, `+ item` | `- item` |
| `> quote` | `quote` |
| `<br>`, other HTML tags, `<!-- comments -->` | a line break, nothing, nothing |
| `\*`, `\_` and other escapes | the literal character |

Underscores inside words (`snake_case_name`) and asterisks between digits (`2*3*4`) are left alone. Numbered lists, tables and horizontal rules pass through as text.

## 4. Version history

| Version | Date | Change |
| :-- | :-- | :-- |
| 0.2.0 | 2026-09-04 | Rewritten on `bac-common` as a filter with `-o FILE` and stdin/stdout mode. Conversion runs in passes with placeholders, which fixes `**bold**` becoming `_bold_` and `***x***` becoming `__x__`; all heading levels; whitespace inserted around styled spans next to punctuation (YouTube does not render them otherwise); links, autolinks and bare URLs preserved with their underscores; code spans and fences unwrapped instead of converted; `<` and `>` kept as text (only HTML tags and comments are dropped); `*` bullets become `-`; escapes honoured. Running the module directly no longer crashes. Conversion table with 29 cases, 35 tests. |
| 0.1.0 | – | Regex script writing `<stem>.txt` next to the input; only H1 handled. |
