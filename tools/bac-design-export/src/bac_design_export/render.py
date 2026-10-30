# SPDX-License-Identifier: MIT
"""Turn a :class:`Document` into a standalone HTML page and a PDF.

The stylesheet is assembled per run, in this order: the ``@font-face`` rules for the
self-hosted fonts, ``tokens.css`` as bac-design-tokens renders it (without its Google Fonts
imports – the export works offline), ``print.css``, and the per-document running header and
footer. The PDF's Creator field carries a hash over everything that shapes the output, which
is how ``--check`` tells a stale export from a current one without comparing bytes.
"""

from __future__ import annotations

import hashlib
import html
from importlib.resources import files
from pathlib import Path

from bac_design_tokens.build import FONT_IMPORTS, by_name, css_value, render_css

from . import __version__
from .document import Document
from .fonts import SYMBOL_RANGE, SYMBOLS, Face, font_face_css

TOOL = "bac-design-export"
LICENCE = "github.com/buildacubesat/bac-design · CC BY-SA 4.0 · the BAC Marks: BAC Trademark Policy"
PAPERS = ("a4", "letter")


def print_css() -> str:
    return files("bac_design_export").joinpath("print.css").read_text(encoding="utf-8")


def tokens_css() -> str:
    css = render_css()
    for line in FONT_IMPORTS:
        css = css.replace(line, "")
    return css


def symbol_stacks() -> str:
    """--font-body and --font-display with the symbols face after their first family."""
    rules = []
    for name in ("font-body", "font-display"):
        tok = by_name()[name]
        first, _, rest = css_value(tok, tok.value).partition(",")
        rules.append(f"  --{name}: {first}, '{SYMBOLS}',{rest};")
    return ":root {\n" + "\n".join(rules) + "\n}\n"


def _css_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def running_css(doc: Document) -> str:
    version = " · ".join(p for p in (f"v{doc.version}" if doc.version else "", doc.date) if p)
    return (
        "@page {\n"
        f"  @top-left {{ content: {_css_string(doc.title)}; }}\n"
        f"  @top-right {{ content: {_css_string(version)}; }}\n"
        f"  @bottom-left {{ content: {_css_string(LICENCE)}; }}\n"
        "}\n"
    )


def stylesheet(doc: Document, faces: list[Face]) -> str:
    return "\n".join([font_face_css(faces), tokens_css(), symbol_stacks(), print_css(), running_css(doc)])


def source_hash(doc: Document, faces: list[Face], paper: str, logo: Path | None) -> str:
    """A hash over the Markdown, the stylesheet, the font files, the logo, the paper and the tool version."""
    h = hashlib.sha256()
    # the font-face rules name absolute paths, which differ between machines; the file names carry the versions
    for part in (
        __version__,
        paper,
        doc.path.read_text(encoding="utf-8"),
        tokens_css(),
        symbol_stacks(),
        print_css(),
        running_css(doc),
        SYMBOL_RANGE,
    ):
        h.update(part.encode("utf-8"))
    for face in faces:
        h.update(face.path.name.encode("utf-8"))
    if logo is not None and logo.is_file():
        h.update(logo.read_bytes())
    return h.hexdigest()[:16]


def creator(digest: str) -> str:
    return f"{TOOL} {__version__} · source {digest}"


def _toc(doc: Document) -> str:
    items = [h for h in doc.headings if h.level == 2]
    if len(items) < 3:
        return ""
    rows = "\n".join(
        f'<li><a href="#{h.anchor}"><span class="n">{html.escape(h.number)}</span>'
        f'<span class="t">{h.text}</span></a></li>'
        for h in items
    )
    return f'<nav class="toc"><p class="label">Contents</p><ol>\n{rows}\n</ol></nav>'


def page(doc: Document, faces: list[Face], paper: str, logo: Path | None, digest: str) -> str:
    """The standalone HTML page for ``doc``."""
    esc = html.escape
    logo_html = f'<img class="logo" src="{logo.as_uri()}" alt="Build a CubeSat">' if logo and logo.is_file() else ""
    front = [f'<header class="front">{logo_html}']
    if doc.eyebrow:
        front.append(f'<p class="eyebrow">{esc(doc.eyebrow)}</p>')
    front.append(f"<h1>{esc(doc.title)}</h1>")
    if doc.lead:
        front.append(f'<p class="lead">{esc(doc.lead)}</p>')
    if doc.meta:
        front.append(f'<p class="meta">{esc(doc.meta)}</p>')
    front.append("</header>")
    meta = [
        f'<meta name="generator" content="{esc(creator(digest))}">',
        '<meta name="author" content="nihil.space GmbH">',
        f'<meta name="description" content="{esc(doc.lead or doc.title)}">',
    ]
    if doc.date:
        meta += [
            f'<meta name="dcterms.created" content="{doc.date}">',
            f'<meta name="dcterms.modified" content="{doc.date}">',
        ]
    return f"""<!doctype html>
<html lang="en" class="{paper}">
<head>
<meta charset="utf-8">
<title>{esc(doc.title)}</title>
{chr(10).join(meta)}
<style>
{stylesheet(doc, faces)}
</style>
</head>
<body>
{"".join(front)}
{_toc(doc)}
<article>
{doc.body}
</article>
<p class="colophon">{esc(" · ".join(p for p in (doc.title, doc.version and "v" + doc.version, doc.date) if p))}<br>
Source: {esc(doc.path.parent.name)}/{esc(doc.path.name)} · exported by {TOOL} {__version__}<br>
{esc(LICENCE)}</p>
</body>
</html>
"""


def write_pdf(markup: str, out: Path) -> None:
    from weasyprint import HTML  # heavy import; only when a PDF is written

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part")
    HTML(string=markup, base_url=str(out.parent)).write_pdf(tmp, uncompressed_pdf=False)
    tmp.replace(out)


def pdf_creator(path: Path) -> str | None:
    """The Creator field of an existing export, or ``None`` when there is no readable file."""
    if not path.is_file():
        return None
    try:
        from pypdf import PdfReader

        info = PdfReader(path).metadata
    except Exception:  # noqa: BLE001 – an unreadable PDF is simply stale
        return None
    return str(info.creator) if info and info.creator else None
