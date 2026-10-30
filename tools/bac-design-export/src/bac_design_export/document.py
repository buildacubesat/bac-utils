# SPDX-License-Identifier: MIT
"""Read one guide: its front matter from the first lines, its body as HTML.

A guide opens with ``# Title`` and, on the next paragraph, a bold line that names the
standard, its version and date: ``**Build a CubeSat – Brand, visual & communication
standard** Version 1.3, 2026-10-29 · Authors: …``. The bold line becomes the lead, the
version and date the eyebrow, anything after a ``·`` the meta line. A document without
the bold line (the condensed checklist) exports with its title only.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

from markdown_it import MarkdownIt

REPO_URL = "https://github.com/buildacubesat/bac-design/blob/main"

FRONT = re.compile(
    r"^\*\*(?P<lead>.+?)\*\*\s*Version\s+(?P<version>[\w.]+),\s*(?P<date>\d{4}-\d{2}-\d{2})(?P<rest>.*)$"
)
HEADING = re.compile(r"<h([2-4])>(.*?)</h\1>", re.S)
NUMBER = re.compile(r"^(\d+(?:\.\d+)*\.?)\s+")
HREF = re.compile(r'href="(?!https?:|mailto:|#)([^"]+)"')


@dataclass
class Heading:
    level: int
    number: str
    text: str
    anchor: str


@dataclass
class Document:
    path: Path
    title: str
    lead: str = ""
    version: str = ""
    date: str = ""
    meta: str = ""
    body: str = ""
    headings: list[Heading] = field(default_factory=list)

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def eyebrow(self) -> str:
        parts = [f"Version {self.version}" if self.version else "", self.date]
        return " · ".join(p for p in parts if p)


def _markdown() -> MarkdownIt:
    return MarkdownIt("commonmark", {"html": False, "typographer": False}).enable(["table", "strikethrough"])


def _slug(text: str, seen: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", html.unescape(re.sub(r"<[^>]+>", "", text)).lower()).strip("-") or "section"
    slug, n = base, 2
    while slug in seen:
        slug, n = f"{base}-{n}", n + 1
    seen.add(slug)
    return slug


def _rewrite_href(match: re.Match[str], folder: str) -> str:
    """A relative link to another file in the repository becomes its GitHub address."""
    target = match.group(1)
    if target.startswith("../"):
        target = target[3:]
    elif folder:
        target = f"{folder}/{target}"
    return f'href="{REPO_URL}/{target}"'


def read(path: Path) -> Document:
    """Parse ``path`` into a :class:`Document`."""
    lines = path.read_text(encoding="utf-8").splitlines()
    title = path.stem
    start = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title, start = line[2:].strip(), i + 1
            break
    doc = Document(path=path, title=title)

    # the bold front-matter line is the first non-empty paragraph after the title
    j = start
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j < len(lines) and (m := FRONT.match(lines[j].strip())):
        lead = m["lead"].strip().rstrip(".")
        doc.lead = lead.split(" – ", 1)[1] if lead.startswith("Build a CubeSat – ") else lead
        doc.version, doc.date = m["version"], m["date"]
        doc.meta = m["rest"].strip().lstrip("·").strip()
        start = j + 1

    body = _markdown().render("\n".join(lines[start:]))
    folder = path.parent.name if path.parent.name in {"guides", "checklists", "templates"} else ""
    body = HREF.sub(lambda m: _rewrite_href(m, folder), body)

    seen: set[str] = set()

    def heading(m: re.Match[str]) -> str:
        level, inner = int(m.group(1)), m.group(2).strip()
        number = ""
        if n := NUMBER.match(inner):
            number, inner = n.group(1).rstrip("."), inner[n.end() :]
        anchor = _slug(f"{number} {inner}", seen)
        doc.headings.append(Heading(level, number, inner, anchor))
        num = f'<span class="num">{number}</span>' if number else ""
        return f'<h{level} id="{anchor}">{num}<span class="text">{inner}</span></h{level}>'

    doc.body = HEADING.sub(heading, body)
    return doc
