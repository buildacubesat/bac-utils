# SPDX-License-Identifier: MIT
"""Metadata in exported CAD files.

Exporters put placeholders into the ``FILE_NAME`` entity of a STEP file
(KiCad writes ``Pcbnew`` and ``Kicad`` as author and organisation, and the
board's stem as the name). A release artifact should say who made it and
what it is, so :func:`set_step_header` sets name, author, organisation and
authorisation in the ISO 10303-21 header and leaves the data section
untouched. The header is the first few hundred bytes of the file; the rest
is copied through unchanged. Non-ASCII characters are written in the
standard's ``\\X2\\…\\X0\\`` form, so every STEP reader can take the header.

STEP is the first format here because bac-kicad-generate-artifacts exports
it. The FreeCAD artifacts tool adds 3MF (``<metadata>`` elements) when it
exists; STL carries only the ``solid`` name line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from .errors import BacError

__all__ = ["StepHeader", "StepHeaderError", "read_step_header", "set_step_header", "step_product_names"]

_HEADER_END = b"ENDSEC;"


class StepHeaderError(BacError):
    """The file has no readable ISO 10303-21 header."""


@dataclass(slots=True)
class StepHeader:
    """The ``FILE_NAME`` entity: name, time stamp, authors, organisations, preprocessor, system, authorisation."""

    name: str
    time_stamp: str
    author: list[str]
    organization: list[str]
    preprocessor_version: str
    originating_system: str
    authorization: str

    def entity(self) -> str:
        """The entity as Part 21 writes it, on one line."""
        return (
            "FILE_NAME("
            + ",".join(
                [
                    _quote(self.name),
                    _quote(self.time_stamp),
                    _list(self.author),
                    _list(self.organization),
                    _quote(self.preprocessor_version),
                    _quote(self.originating_system),
                    _quote(self.authorization),
                ]
            )
            + ");"
        )


def _quote(value: str) -> str:
    """A Part 21 string: ``'`` doubled, characters outside printable ASCII as ``\\X2\\…\\X0\\`` (ISO 10303-21 §6.4)."""
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if run:
            wide = any(ord(r) > 0xFFFF for r in run)
            digits = "".join(f"{ord(r):08X}" if wide else f"{ord(r):04X}" for r in run)
            out.append(("\\X4\\" if wide else "\\X2\\") + digits + "\\X0\\")
            run.clear()

    for c in value:
        if " " <= c <= "~":
            flush()
            out.append("''" if c == "'" else c)
        else:
            run.append(c)
    flush()
    return "'" + "".join(out) + "'"


_CONTROL = re.compile(r"\\X2\\((?:[0-9A-F]{4})+)\\X0\\|\\X4\\((?:[0-9A-F]{8})+)\\X0\\")


def _decode(raw: str) -> str:
    """Undo the ``\\X2\\…\\X0\\`` (UCS-2) and ``\\X4\\…\\X0\\`` (UCS-4) encodings of a Part 21 string."""

    def one(m: re.Match[str]) -> str:
        if m.group(1):
            return "".join(chr(int(m.group(1)[i : i + 4], 16)) for i in range(0, len(m.group(1)), 4))
        return "".join(chr(int(m.group(2)[i : i + 8], 16)) for i in range(0, len(m.group(2)), 8))

    return _CONTROL.sub(one, raw)


def _list(values: list[str]) -> str:
    return "(" + ",".join(_quote(v) for v in values) + ")"


def _split_args(body: str) -> list[str | list[str]]:
    """Split ``'a','b',('c','d')`` into ``["a", "b", ["c", "d"]]``. Strings may contain ``''`` for a quote."""
    out: list[str | list[str]] = []
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c in " \t\r\n,":
            i += 1
        elif c == "'":
            value, i = _read_string(body, i)
            out.append(value)
        elif c == "(":
            depth, j = 1, i + 1
            while j < n and depth:
                if body[j] == "'":
                    _, j = _read_string(body, j)
                    continue
                depth += body[j] == "("
                depth -= body[j] == ")"
                j += 1
            inner = _split_args(body[i + 1 : j - 1])
            out.append([v for v in inner if isinstance(v, str)])
            i = j
        else:
            j = i
            while j < n and body[j] not in ",()":
                j += 1
            out.append(body[i:j].strip())
            i = j
    return out


def _read_string(body: str, start: int) -> tuple[str, int]:
    """Read a Part 21 string starting at the opening quote; returns the value and the index after it."""
    i = start + 1
    chars: list[str] = []
    n = len(body)
    while i < n:
        if body[i] == "'":
            if i + 1 < n and body[i + 1] == "'":
                chars.append("'")
                i += 2
                continue
            return _decode("".join(chars)), i + 1
        chars.append(body[i])
        i += 1
    raise StepHeaderError("Unterminated string in the STEP header")


def _header_span(data: bytes) -> tuple[int, int]:
    """Byte offsets of ``FILE_NAME(`` … ``);`` inside the HEADER section."""
    end = data.find(_HEADER_END)
    if end < 0 or not data.lstrip().startswith(b"ISO-10303-21;"):
        raise StepHeaderError("Not a STEP file: no ISO-10303-21 header")
    start = data.find(b"FILE_NAME(", 0, end)
    if start < 0:
        raise StepHeaderError("STEP header has no FILE_NAME entity")
    text = data[start:end].decode("utf-8", errors="replace")
    i, depth = len("FILE_NAME("), 1
    while i < len(text) and depth:
        c = text[i]
        if c == "'":
            _, i = _read_string(text, i)
            continue
        depth += (c == "(") - (c == ")")
        i += 1
    if depth or text[i : i + 1] != ";":
        raise StepHeaderError("STEP header's FILE_NAME entity is not terminated")
    return start, start + len(text[: i + 1].encode("utf-8"))


def _parse(entity: str) -> StepHeader:
    body = entity[len("FILE_NAME(") : -2]
    args = _split_args(body)
    if len(args) != 7:
        raise StepHeaderError(f"FILE_NAME has {len(args)} arguments, expected 7")

    def s(i: int) -> str:
        v = args[i]
        return v if isinstance(v, str) else ""

    def lst(i: int) -> list[str]:
        v = args[i]
        return list(v) if isinstance(v, list) else ([v] if v else [])

    return StepHeader(s(0), s(1), lst(2), lst(3), s(4), s(5), s(6))


def read_step_header(path: Path) -> StepHeader:
    """The ``FILE_NAME`` entity of a STEP file."""
    with path.open("rb") as f:
        head = f.read(65536)
    start, stop = _header_span(head)
    return _parse(head[start:stop].decode("utf-8", errors="replace"))


def set_step_header(
    path: Path,
    *,
    name: str | None = None,
    author: str | None = None,
    organization: str | None = None,
    authorization: str | None = None,
    overwrite: bool = False,
) -> StepHeader:
    """Fill ``FILE_NAME`` fields in place and return the header as written.

    ``name`` replaces the model name whenever given (exporters write a path
    there, which is wrong once the file has moved). ``author``,
    ``organization`` and ``authorization`` fill their field only when it is
    empty, unless ``overwrite`` is set. Fields passed as ``None`` are left
    alone. The data section is copied through byte for byte.
    """
    data = path.read_bytes()
    start, stop = _header_span(data)
    header = _parse(data[start:stop].decode("utf-8", errors="replace"))
    new = replace(header)
    if name is not None:
        new.name = name
    if author is not None and (overwrite or not any(new.author)):
        new.author = [author]
    if organization is not None and (overwrite or not any(new.organization)):
        new.organization = [organization]
    if authorization is not None and (overwrite or not new.authorization):
        new.authorization = authorization
    if new != header:
        path.write_bytes(data[:start] + new.entity().encode("utf-8") + data[stop:])
    return new


def step_product_names(path: Path) -> list[str]:
    """The ``PRODUCT`` entity names in document order (the top-level assembly is usually first)."""
    names: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            idx = line.find("PRODUCT(")
            if idx < 0 or line[idx - 1 : idx].isalpha():
                continue
            try:
                value, _ = _read_string(line, line.index("'", idx))
            except (ValueError, StepHeaderError):
                continue
            names.append(value)
    return names
