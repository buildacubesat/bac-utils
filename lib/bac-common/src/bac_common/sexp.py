# SPDX-License-Identifier: MIT
"""A span-recording reader for KiCad s-expression files.

KiCad writes symbol libraries, footprints, schematics and boards as
s-expressions. Tools that edit them must not re-serialise the tree: KiCad's
own formatting (tabs, one child per line, number precision) would be lost
and every save would be a whole-file diff. So :func:`parse` returns
:class:`Node` and :class:`Atom` objects that remember the ``(start, end)``
character span they came from, and edits are applied to the original text
with :func:`apply_edits`. A file nothing was changed in comes back byte for
byte identical.

Strings are unescaped in :attr:`Atom.value` (``\\n`` becomes a newline) and
re-escaped by :func:`quoted` when a value is written back, so a value
round-trips even when it contains quotes or line breaks. The raw source of
any atom is ``text[atom.start:atom.end]``.

Lifted from the ``bac_kicad_core.sexpr`` module of bac-kicad-tools and
extended with tree helpers, the version token, and edit application.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .errors import BacError

__all__ = [
    "Atom",
    "Node",
    "Edit",
    "SexpError",
    "parse",
    "parse_file",
    "escape",
    "unescape",
    "quoted",
    "fmt_number",
    "apply_edits",
    "line_indent",
    "indent_unit",
    "format_version",
]

Edit = tuple[int, int, str]

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}


class SexpError(BacError):
    """The text is not a well-formed s-expression."""


@dataclass(slots=True)
class Atom:
    """A bare token or a quoted string. ``value`` is unescaped; the span covers the quotes."""

    value: str
    quoted: bool
    start: int
    end: int

    def raw(self, text: str) -> str:
        """The atom exactly as written in ``text``."""
        return text[self.start : self.end]

    def number(self) -> float | None:
        """The atom as a float, or ``None`` when it is not numeric."""
        try:
            return float(self.value)
        except ValueError:
            return None


@dataclass(slots=True)
class Node:
    """A parenthesised list. ``head`` is the first atom's value, if any."""

    start: int
    end: int = -1
    items: list[Atom | Node] = field(default_factory=list)

    @property
    def head(self) -> str | None:
        first = self.items[0] if self.items else None
        return first.value if isinstance(first, Atom) else None

    def atoms(self) -> list[Atom]:
        return [i for i in self.items if isinstance(i, Atom)]

    def children(self, head: str | None = None) -> list[Node]:
        """Direct child lists, optionally only those with ``head``."""
        out = [i for i in self.items if isinstance(i, Node)]
        if head is not None:
            out = [n for n in out if n.head == head]
        return out

    def child(self, head: str) -> Node | None:
        """The first direct child list with ``head``, or ``None``."""
        for item in self.items:
            if isinstance(item, Node) and item.head == head:
                return item
        return None

    def value(self, index: int = 1) -> str:
        """The value of the atom at ``index`` among this node's atoms, or ``""``."""
        atoms = self.atoms()
        return atoms[index].value if len(atoms) > index else ""

    def walk(self) -> Iterator[Node]:
        """This node and every list below it, depth first, in document order."""
        yield self
        for item in self.items:
            if isinstance(item, Node):
                yield from item.walk()

    def find_all(self, head: str) -> list[Node]:
        """Every list with ``head`` at any depth below this node."""
        return [n for n in self.walk() if n is not self and n.head == head]


def unescape(raw: str) -> str:
    """The value of a quoted string's body: ``\\"`` → ``"``, ``\\n`` → newline, ``\\\\`` → ``\\``."""
    out: list[str] = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def escape(value: str) -> str:
    """The inverse of :func:`unescape`, for writing a value into a quoted string."""
    return (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    )


def quoted(value: str) -> str:
    """``value`` as KiCad writes a string token."""
    return f'"{escape(value)}"'


def fmt_number(value: float, places: int = 6) -> str:
    """A number the way KiCad writes it: no exponent, trailing zeros trimmed, ``0`` not ``0.0``."""
    text = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def parse(text: str, *, where: str = "") -> Node:
    """Parse the first complete top-level list in ``text``. Text after it is ignored."""
    stack: list[Node] = []
    i, n = 0, len(text)
    prefix = f"{where}: " if where else ""

    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "(":
            node = Node(start=i)
            if stack:
                stack[-1].items.append(node)
            stack.append(node)
            i += 1
        elif c == ")":
            if not stack:
                raise SexpError(f"{prefix}unbalanced ')' at offset {i}")
            node = stack.pop()
            node.end = i + 1
            if not stack:
                return node
            i += 1
        elif c == '"':
            start = i
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            if i >= n:
                raise SexpError(f"{prefix}unterminated string starting at offset {start}")
            i += 1
            atom = Atom(unescape(text[start + 1 : i - 1]), True, start, i)
            if stack:
                stack[-1].items.append(atom)
        else:
            start = i
            while i < n and not text[i].isspace() and text[i] not in '()"':
                i += 1
            if stack:
                stack[-1].items.append(Atom(text[start:i], False, start, i))

    raise SexpError(f"{prefix}no complete top-level expression found")


def parse_file(path: Path) -> tuple[str, Node]:
    """Read ``path`` and parse it. Returns the text (for span lookups and edits) and the root.

    Line endings are kept as they are in the file, so edits spliced into
    ``text`` and written back with ``newline=""`` change nothing else.
    """
    try:
        with path.open(encoding="utf-8", newline="") as f:
            text = f.read()
    except UnicodeDecodeError as exc:
        raise SexpError(f"{path}: not UTF-8 text", str(exc)) from exc
    except OSError as exc:
        raise SexpError(f"Cannot read {path}", exc.strerror or str(exc)) from exc
    return text, parse(text, where=str(path))


def apply_edits(text: str, edits: Iterable[Edit]) -> str:
    """Apply ``(start, end, replacement)`` edits to ``text``.

    Edits are applied back to front so that earlier offsets stay valid. Two
    edits that overlap are a programming error and raise; two insertions at
    the same offset are applied in the order given.
    """
    ordered = sorted(enumerate(edits), key=lambda item: (item[1][0], item[1][1], item[0]))
    previous_start = None
    for _, (start, end, _) in reversed(ordered):
        if end < start or (previous_start is not None and end > previous_start):
            raise SexpError("Overlapping edits", f"an edit ending at {end} runs into one starting at {previous_start}")
        previous_start = start
    out = text
    for _, (start, end, replacement) in reversed(ordered):
        out = out[:start] + replacement + out[end:]
    return out


def line_indent(text: str, offset: int) -> str:
    """The whitespace at the start of the line containing ``offset``."""
    line_start = text.rfind("\n", 0, offset) + 1
    line = text[line_start:offset]
    return line[: len(line) - len(line.lstrip())]


def indent_unit(indent: str) -> str:
    """One indentation level in the style of ``indent``: a tab if it uses tabs, two spaces otherwise."""
    return "\t" if "\t" in indent else "  "


def format_version(root: Node) -> int:
    """The file's ``(version NNNNNNNN)`` token, or 0 when absent."""
    node = root.child("version")
    value = node.value(1) if node else ""
    return int(value) if value.isdigit() else 0
