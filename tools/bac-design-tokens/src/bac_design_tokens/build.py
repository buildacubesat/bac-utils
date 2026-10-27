# SPDX-License-Identifier: MIT
"""Turn ``tokens.json`` into every copy the repository keeps.

Each target is a file in the workspace and a function from its current text to the text it
should have. A target either owns the whole file (the two ``tokens.css`` copies) or a marked
region inside it (the Rich colours in ``bac_common.ui``, the style cell and chart lines of the
marimo notebooks), so hand-written code around the region stays untouched.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from pathlib import Path

from bac_common.errors import BacError

MODES = "space.buildacubesat.modes"
GENERIC_FAMILIES = {"system-ui", "sans-serif", "serif", "monospace", "ui-monospace", "ui-sans-serif", "cursive"}
ALIAS = re.compile(r"^\{([\w-]+)\}$")

FONT_IMPORTS = (
    "@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;500;600;700;800&display=swap');",
    "@import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:ital,opsz,wght@0,6..12,400;0,6..12,500;"
    "0,6..12,600;0,6..12,700;1,6..12,400&display=swap');",
    "@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600;0,700;"
    "1,400&display=swap');",
)


@dataclass(frozen=True, slots=True)
class Token:
    name: str
    type: str
    value: object
    dark: object | None
    description: str
    group: str
    group_description: str
    section: str


@cache
def load() -> dict:
    """The parsed ``tokens.json`` shipped inside the package."""
    return json.loads(files("bac_design_tokens").joinpath("tokens.json").read_text(encoding="utf-8"))


def tokens() -> list[Token]:
    """Every leaf token in file order, with its section, group and dark value."""
    out: list[Token] = []
    for section, groups in load().items():
        if section.startswith("$"):
            continue
        for group, body in groups.items():
            if group.startswith("$"):
                continue
            for name, tok in body.items():
                if name.startswith("$"):
                    continue
                dark = tok.get("$extensions", {}).get(MODES, {}).get("dark")
                out.append(
                    Token(
                        name,
                        tok["$type"],
                        tok["$value"],
                        dark,
                        tok.get("$description", ""),
                        group,
                        body.get("$description", ""),
                        section,
                    )
                )
    return out


def by_name() -> dict[str, Token]:
    return {t.name: t for t in tokens()}


def resolve(value: object, dark: bool = False) -> object:
    """Follow ``{alias}`` references to a literal value."""
    seen: set[str] = set()
    while isinstance(value, str) and (m := ALIAS.match(value)):
        name = m.group(1)
        if name in seen:
            raise BacError(f"alias loop at {name}")
        seen.add(name)
        tok = by_name()[name]
        value = tok.dark if dark and tok.dark is not None else tok.value
    return value


def hex_of(name: str, dark: bool = False) -> str:
    """A colour token's literal hex value in light or dark."""
    tok = by_name()[name]
    value = resolve(tok.dark if dark and tok.dark is not None else tok.value, dark)
    if not (isinstance(value, str) and re.fullmatch(r"#[0-9A-F]{6}", value)):
        raise BacError(f"{name} is not an uppercase #RRGGBB colour: {value}")
    return value


def css_value(tok: Token, value: object) -> str:
    if isinstance(value, str) and (m := ALIAS.match(value)):
        return f"var(--{m.group(1)})"
    if tok.type == "fontFamily":
        names = list(value)  # type: ignore[arg-type]
        return ", ".join(
            n if n in GENERIC_FAMILIES or (" " not in n and i > 0) else f"'{n}'" for i, n in enumerate(names)
        )
    if tok.type == "cubicBezier":
        return "cubic-bezier(" + ", ".join(f"{v:g}" for v in value) + ")"  # type: ignore[union-attr]
    return str(value)


def _declarations(toks: list[Token], indent: str, dark: bool) -> list[str]:
    lines: list[str] = []
    group = None
    for tok in toks:
        if tok.group != group:
            if group is not None:
                lines.append("")
            lines.append(f"{indent}/* {tok.group_description} */")
            group = tok.group
        value = tok.dark if dark and tok.dark is not None else tok.value
        note = f" /* {tok.description} */" if tok.description and not dark else ""
        lines.append(f"{indent}--{tok.name}: {css_value(tok, value)};{note}")
    return lines


def render_css() -> str:
    """The full ``tokens.css``."""
    canonical = [t for t in tokens() if t.section == "canonical"]
    semantic = [t for t in tokens() if t.section == "semantic"]
    dark = [t for t in semantic if t.dark is not None]
    head = """/* SPDX-License-Identifier: MIT OR CC-BY-SA-4.0 */
/* tokens.css – Build a CubeSat design tokens as CSS custom properties.

   Written by bac-design-tokens from tools/bac-design-tokens/src/bac_design_tokens/tokens.json,
   the canonical copy of the BAC Identity Guide 1.0 tokens (§3 typography, §4 colour, §5 form,
   §7 Mission surfaces) and the state, hero and chart tokens of the BAC Interface Design
   Guide 1.0. Change tokens.json and run `uv run --no-sync bac-design-tokens`; edits made here
   are overwritten. The bac-suite index page serves an identical copy, and the marimo style
   cells and the Rich colours in bac-common are written from the same file.

   Light and dark: the semantic tokens follow prefers-color-scheme, and a
   data-theme="light" or data-theme="dark" attribute on any element pins its
   subtree to one mode, text colour included (Interface Design Guide §3). */
"""
    out = [head, *FONT_IMPORTS, ""]
    out.append("/* 1. Canonical tokens – the same in light and dark */")
    out.append(":root {")
    out += _declarations(canonical, "  ", dark=False)
    out.append("}")
    out.append("")
    out.append('/* 2. Semantic tokens, light – the default, and anything under data-theme="light" */')
    out.append(":root,\n[data-theme='light'] {")
    out.append("  color-scheme: light;")
    out += _declarations(semantic, "  ", dark=False)
    out.append("}")
    out.append("")
    out.append("/* 3. Semantic tokens, dark – the same block twice: once for the system")
    out.append('   preference, once for data-theme="dark". */')
    out.append("@media (prefers-color-scheme: dark) {")
    out.append("  :root:not([data-theme='light']) {")
    out.append("    color-scheme: dark;")
    out += _declarations(dark, "    ", dark=True)
    out.append("  }")
    out.append("}")
    out.append("")
    out.append("[data-theme='dark'] {")
    out.append("  color-scheme: dark;")
    out += _declarations(dark, "  ", dark=True)
    out.append("}")
    out.append("")
    out.append("/* 4. A pinned subtree sets its own text colour: color is inherited as a")
    out.append('   computed value, so without this a data-theme="light" area inside a dark')
    out.append("   page would keep the page's light text. */")
    out.append("[data-theme] { color: var(--text); }")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Marked regions
# ---------------------------------------------------------------------------

RICH_BEGIN = "# bac-design-tokens: begin – written from tokens.json; change the tokens, not these lines"
RICH_END = "# bac-design-tokens: end"


def rich_block() -> str:
    return "\n".join(
        [
            RICH_BEGIN,
            f'GREEN = "{hex_of("bac-green")}"  # --bac-green: success, pass',
            f'RED = "{hex_of("bac-red")}"  # --bac-red: error, fail',
            f'YELLOW = "{hex_of("bac-yellow")}"  # --bac-yellow: warning, progress fill, inline bars',
            RICH_END,
        ]
    )


def update_rich(text: str) -> str:
    pattern = re.compile(re.escape(RICH_BEGIN.split(" –")[0]) + r".*?" + re.escape(RICH_END), re.S)
    if not pattern.search(text):
        raise BacError("bac_common/ui.py has no bac-design-tokens region")
    return pattern.sub(lambda _: rich_block(), text, count=1)


def marimo_style() -> str:
    """The canonical CSS of a notebook's style cell, unindented, without the <style> tags."""
    t, bg, mu = (hex_of(n) for n in ("text", "bg", "text-muted"))
    td, bgd, mud = (hex_of(n, dark=True) for n in ("text", "bg", "text-muted"))
    return f"""@import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,400;6..12,500;6..12,600;6..12,700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');

/* Written by bac-design-tokens from tokens.json – change the tokens, not this cell. */
:root {{
  --text:       {t};
  --bg:         {bg};
  --text-muted: {mu};
}}

/* Track marimo's own light/dark setting rather than the operating system.
   marimo sets color-scheme from that setting and light-dark() follows it. */
:root {{
  --text: light-dark({t}, {td});
  --bg:   light-dark({bg}, {bgd});
  --text-muted: light-dark({mu}, {mud});
}}

h1, h2, h3, h4 {{
  font-family: 'Nunito Sans', system-ui, sans-serif;
  font-weight: 500;
  color: var(--text);
}}

body, p, li, .prose {{
  font-family: 'Nunito Sans', system-ui, sans-serif;
  color: var(--text);
}}

code, pre, kbd {{
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}}

.marimo-callout {{ border-radius: 10px; }}

/* marimo styles markdown headings through --heading-font with a selector
   more specific than the rule above, which would leave them in its serif. */
:root {{ --heading-font: 'Nunito Sans', system-ui, sans-serif; }}"""


def _list(names: list[str]) -> str:
    return "[" + ", ".join(f'"{hex_of(n)}"' for n in names) + "]"


def update_notebook(text: str) -> str:
    """Rewrite the style cell up to its --heading-font line, and the chart constants."""
    style = re.compile(r"^( *)<style>\n.*?^ *:root \{ --heading-font: [^\n]*\}\n", re.S | re.M)
    m = style.search(text)
    if not m:
        raise BacError("no style cell ending in the --heading-font rule")
    indent = m.group(1)
    body = "\n".join((indent + line) if line else "" for line in ("<style>\n" + marimo_style()).split("\n"))
    text = text[: m.start()] + body + "\n" + text[m.end() :]

    palette = _list([f"chart-shared-{i}" for i in range(1, 6)])
    text, n = re.subn(r"^( *)PALETTE = \[[^\]]*\]", lambda m: f"{m.group(1)}PALETTE = {palette}", text, flags=re.M)
    if n != 1:
        raise BacError(f"expected one PALETTE line, found {n}")
    muted = f'MUTED = "{hex_of("text-muted", dark=True)}" if IS_DARK else "{hex_of("text-muted")}"'
    text, n = re.subn(
        r'^( *)MUTED = "#[0-9A-Fa-f]{6}" if IS_DARK else "#[0-9A-Fa-f]{6}"',
        lambda m: m.group(1) + muted,
        text,
        flags=re.M,
    )
    if n != 1:
        raise BacError(f"expected one MUTED line, found {n}")
    text_line = f'TEXT = "{hex_of("text", dark=True)}" if IS_DARK else "{hex_of("text")}"'
    text = re.sub(
        r'^( *)TEXT = "#[0-9A-Fa-f]{6}" if IS_DARK else "#[0-9A-Fa-f]{6}"',
        lambda m: m.group(1) + text_line,
        text,
        flags=re.M,
    )
    seq = _list(["chart-seq-1", "chart-seq-2", "chart-seq-3"])
    text = re.sub(r"^( *)SEQUENTIAL = \[[^\]]*\]", lambda m: f"{m.group(1)}SEQUENTIAL = {seq}", text, flags=re.M)
    dark_bg = tuple(int(hex_of("bg", dark=True)[i : i + 2], 16) for i in (1, 3, 5))
    text = re.sub(
        r"^( *)mix = \(\d+, \d+, \d+\) if IS_DARK else \(255, 255, 255\)",
        lambda m: f"{m.group(1)}mix = {dark_bg} if IS_DARK else (255, 255, 255)",
        text,
        flags=re.M,
    )
    return text


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Target:
    path: Path
    update: Callable[[str], str]

    def wanted(self) -> str:
        return self.update(self.path.read_text(encoding="utf-8") if self.path.exists() else "")


def notebooks(root: Path) -> list[Path]:
    found = sorted(root.glob("notebooks/bac-*/bac_*.py")) + sorted(root.glob("notebooks/bac-*/demo/bac_*.py"))
    found += sorted(root.glob("ops/*/src/*/notebook.py"))
    return found


def targets(root: Path) -> Iterator[Target]:
    css = render_css()
    yield Target(root / "tools/bac-reference-gallery/css/tokens.css", lambda _: css)
    yield Target(root / "ops/bac-suite/src/bac_suite/static/tokens.css", lambda _: css)
    yield Target(root / "lib/bac-common/src/bac_common/ui.py", update_rich)
    for path in notebooks(root):
        yield Target(path, update_notebook)


def find_root(start: Path) -> Path:
    """The workspace root: the nearest folder whose pyproject.toml declares the uv workspace."""
    for folder in (start, *start.parents):
        project = folder / "pyproject.toml"
        if project.is_file() and "[tool.uv.workspace]" in project.read_text(encoding="utf-8"):
            return folder
    raise BacError(f"no bac-utils workspace above {start}", "Run it inside the checkout or pass --root.")
