# SPDX-License-Identifier: MIT
"""Parsing and rendering of ``CSR-RESOURCES`` blocks.

A block is the region between a matched pair of markers::

    <!-- CSR-RESOURCES:START block-id -->
    - **[Title](https://example.com/doc.pdf)** `PDF` – Short description
    <!-- CSR-RESOURCES:END block-id -->

Markdown is the source of truth for *which* resources are in a block, so the
parser is tolerant: bold is optional, the type badge is optional, the
description separator may be an en dash, em dash, hyphen or colon, and the
description may be absent or continue on the following non-bullet line(s).
URLs may contain one level of parentheses. Anything else inside a block is
reported as an unparsed line, never silently dropped.

The renderer always writes the canonical form shown above.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .utils import file_type_from_url, normalize_url

START_RE = re.compile(r"^\s*<!--\s*CSR-RESOURCES:START\s+(?P<id>\S+)\s*-->\s*$")
END_RE = re.compile(r"^\s*<!--\s*CSR-RESOURCES:END\s+(?P<id>\S+)\s*-->\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

# `- **[title](url)** `TYPE` – description`, with every decoration optional.
ENTRY_RE = re.compile(
    r"^[-*]\s+"
    r"(?P<b1>\*\*)?\[(?P<title>[^\]]+)\]\((?P<url>(?:[^()\s]|\([^()\s]*\))+)\)(?P<b2>\*\*)?"
    r"\s*(?:`(?P<type>[^`]+)`)?"
    r"\s*(?:[–—:\-]\s*(?P<desc>.*?))?"  # convention-check: allow A1
    r"\s*$"
)


@dataclass(slots=True)
class Entry:
    title: str
    url: str
    file_type: str
    description: str
    line_no: int
    raw: str

    @property
    def key(self) -> str:
        return normalize_url(self.url)


@dataclass(slots=True)
class UnparsedLine:
    line_no: int
    raw: str


@dataclass(slots=True)
class Block:
    block_id: str
    file: str  # repo-relative posix path
    start_line: int  # 1-based line of the START marker
    end_line: int  # 1-based line of the END marker
    heading_context: list[str]
    entries: list[Entry] = field(default_factory=list)
    unparsed: list[UnparsedLine] = field(default_factory=list)

    @property
    def urls(self) -> set[str]:
        return {e.key for e in self.entries}

    @property
    def description(self) -> str:
        return " / ".join(self.heading_context) or self.file


@dataclass(slots=True)
class MarkerProblem:
    file: str
    line_no: int
    message: str


@dataclass(slots=True)
class ScanResult:
    blocks: list[Block]
    problems: list[MarkerProblem]

    def by_id(self) -> dict[str, list[Block]]:
        grouped: dict[str, list[Block]] = {}
        for b in self.blocks:
            grouped.setdefault(b.block_id, []).append(b)
        return grouped

    def duplicate_ids(self) -> dict[str, list[Block]]:
        return {bid: bs for bid, bs in self.by_id().items() if len(bs) > 1}


def parse_entry(line: str, line_no: int = 0) -> Entry | None:
    m = ENTRY_RE.match(line.rstrip())
    if not m:
        return None
    url = m.group("url").strip()
    file_type = (m.group("type") or "").strip() or file_type_from_url(url)
    return Entry(
        title=m.group("title").strip(),
        url=url,
        file_type=file_type,
        description=(m.group("desc") or "").strip(),
        line_no=line_no,
        raw=line,
    )


def parse_file(text: str, rel_file: str) -> tuple[list[Block], list[MarkerProblem]]:
    """Parse all blocks in one markdown file.

    Marker pairs must be well-formed: a START without matching END, an END
    without START, or nested STARTs are reported as problems and the affected
    region is not returned as a block.
    """
    blocks: list[Block] = []
    problems: list[MarkerProblem] = []
    heading_stack: list[tuple[int, str]] = []
    current: Block | None = None

    for idx, line in enumerate(text.splitlines(), start=1):
        if current is None:
            h = HEADING_RE.match(line)
            if h:
                level = len(h.group(1))
                heading_stack = [(lvl, t) for lvl, t in heading_stack if lvl < level]
                heading_stack.append((level, h.group(2).strip()))
                continue
            s = START_RE.match(line)
            if s:
                current = Block(
                    block_id=s.group("id"),
                    file=rel_file,
                    start_line=idx,
                    end_line=0,
                    heading_context=[t for _, t in heading_stack],
                )
                continue
            e = END_RE.match(line)
            if e:
                problems.append(MarkerProblem(rel_file, idx, f"END marker for '{e.group('id')}' without START"))
            continue

        # Inside a block.
        e = END_RE.match(line)
        if e:
            if e.group("id") != current.block_id:
                problems.append(
                    MarkerProblem(
                        rel_file,
                        idx,
                        f"END marker id '{e.group('id')}' does not match START id '{current.block_id}'",
                    )
                )
                # Close the block anyway so parsing can continue.
            current.end_line = idx
            blocks.append(current)
            current = None
            continue
        if START_RE.match(line):
            problems.append(MarkerProblem(rel_file, idx, f"nested START marker inside '{current.block_id}'"))
            continue
        if not line.strip():
            continue
        entry = parse_entry(line, idx)
        if entry is not None:
            current.entries.append(entry)
        elif current.entries and not current.entries[-1].description and _is_continuation(line):
            # Description written on the line after the link. Only one such
            # line is absorbed; further prose is reported, not swallowed.
            last = current.entries[-1]
            last.description = line.strip()
            last.raw += "\n" + line
        else:
            current.unparsed.append(UnparsedLine(idx, line))

    if current is not None:
        problems.append(
            MarkerProblem(rel_file, current.start_line, f"START marker for '{current.block_id}' without END")
        )

    return blocks, problems


def _is_continuation(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith(("-", "*", "#", "<!--"))


def scan_docs(docs_path: Path, repo_root: Path) -> ScanResult:
    blocks: list[Block] = []
    problems: list[MarkerProblem] = []
    for md in sorted(docs_path.rglob("*.md")):
        rel = md.relative_to(repo_root).as_posix()
        b, p = parse_file(md.read_text(encoding="utf-8"), rel)
        blocks.extend(b)
        problems.extend(p)
    return ScanResult(blocks=blocks, problems=problems)


def render_entry(title: str, url: str, file_type: str, description: str) -> str:
    line = f"- **[{title}]({url})** `{file_type}`"
    if description:
        line += f" – {description}"
    return line


def render_block_body(lines: list[str]) -> str:
    """Body between the markers, including the surrounding newlines."""
    if not lines:
        return "\n"
    return "\n" + "\n".join(sorted(lines, key=str.lower)) + "\n"


def replace_block_body(text: str, block: Block, body: str) -> str:
    """Return ``text`` with the body of ``block`` replaced.

    ``block`` must have been parsed from ``text``; line numbers are used to
    locate the region, so the file must not have changed since the scan.
    """
    lines = text.splitlines(keepends=True)
    start = lines[block.start_line - 1]
    end = lines[block.end_line - 1]
    if not START_RE.match(start) or not END_RE.match(end):
        raise ValueError(f"{block.file}: block '{block.block_id}' markers moved since scan")
    start_marker = start.rstrip("\n")
    head = "".join(lines[: block.start_line - 1])
    tail = "".join(lines[block.end_line - 1 :])
    return head + start_marker + body + tail
