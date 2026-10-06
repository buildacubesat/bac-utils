# SPDX-License-Identifier: MIT
"""Replace marker text boxes on a board with a QR code made of filled rectangles.

The board carries one or more ``gr_text_box`` items whose text is the marker
(``QR_MARKER`` by default). Each is replaced by the modules of a QR code –
one filled ``gr_rect`` per dark module – centred in the box's bounding
square, on the box's own layer, mirrored left–right on back layers so the
code reads correctly when the board is turned over. The text is a literal
(``--qr`` or the config); ``${TITLE}``, ``${REVISION}`` and the other title
block variables are substituted first.

A reimplementation of Emil Fresk's kicad-qr-inserter
(https://github.com/korken89/kicad-qr-inserter, MIT) on the shared
s-expression reader: no pcbnew, so it runs from any Python, and the board is
edited by span so everything else in the file stays byte for byte as KiCad
wrote it. It works on a copy of the project in the output folder, never on
the project itself.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import qrcode
import qrcode.constants

from bac_common import sexp
from bac_common.errors import BacError

__all__ = ["QrError", "Placement", "find_markers", "qr_matrix", "insert_qr", "substitute_variables"]

_VARIABLE = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


class QrError(BacError):
    """No marker on the board, or a marker the stage cannot use."""


@dataclass(frozen=True)
class Placement:
    """One marker: its span in the file and the square it fills."""

    start: int
    end: int
    x0: float  # left edge of the square, mm
    y0: float  # top edge, mm
    side: float  # mm
    layer: str
    indent: str

    @property
    def back(self) -> bool:
        return self.layer.startswith("B.")


def substitute_variables(text: str, variables: dict[str, str]) -> str:
    """``${TITLE}`` and friends; an unknown variable is left as written."""
    return _VARIABLE.sub(lambda m: variables.get(m.group(1), m.group(0)), text)


def _box_text(node: sexp.Node) -> str:
    quoted = [a for a in node.atoms() if a.quoted]
    return quoted[0].value if quoted else ""


def _corners(node: sexp.Node) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for head in ("start", "end"):
        child = node.child(head)
        if child:
            atoms = child.atoms()
            if len(atoms) >= 3 and atoms[1].number() is not None and atoms[2].number() is not None:
                pts.append((float(atoms[1].value), float(atoms[2].value)))
    if pts:
        return pts
    poly = node.child("pts")
    if poly:
        for xy in poly.children("xy"):
            atoms = xy.atoms()
            if len(atoms) >= 3:
                pts.append((float(atoms[1].value), float(atoms[2].value)))
    return pts


def find_markers(text: str, root: sexp.Node, marker: str) -> list[Placement]:
    """Every top-level ``gr_text_box`` whose text is ``marker``. The square is the box's shorter side, centred."""
    out: list[Placement] = []
    for node in root.children("gr_text_box"):
        if _box_text(node) != marker:
            continue
        pts = _corners(node)
        layer = node.child("layer")
        if len(pts) < 2 or layer is None:
            raise QrError(f"A {marker} text box has no usable corners or layer.", f"offset {node.start} in the board")
        angle = node.child("angle")
        if angle is not None and (float(angle.value(1) or 0) % 180) != 0:
            raise QrError(f"A {marker} text box is rotated by {angle.value(1)}°.", "Rotate it back to 0° or 180°.")
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        side = min(w, h)
        if side <= 0:
            raise QrError(f"A {marker} text box has no area.", f"offset {node.start} in the board")
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        out.append(
            Placement(
                node.start,
                node.end,
                cx - side / 2,
                cy - side / 2,
                side,
                layer.value(1),
                sexp.line_indent(text, node.start),
            )
        )
    return out


def qr_matrix(data: str) -> list[list[bool]]:
    """The QR modules for ``data``: smallest version that fits, error correction L, no quiet zone."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=1, border=0)
    qr.add_data(data)
    qr.make(fit=True)
    return [[bool(cell) for cell in row] for row in qr.get_matrix()]


def _fill_token(version: int) -> str:
    """KiCad 9 and later write ``(fill yes)``; KiCad 8 wrote ``(fill solid)``."""
    return "yes" if version >= 20241229 else "solid"


def _rect(x0: float, y0: float, x1: float, y1: float, layer: str, fill: str, indent: str, nl: str) -> str:
    unit = sexp.indent_unit(indent)
    i1, i2 = indent + unit, indent + unit + unit
    n = sexp.fmt_number
    return (
        f"(gr_rect{nl}{i1}(start {n(x0)} {n(y0)}){nl}{i1}(end {n(x1)} {n(y1)}){nl}"
        f"{i1}(stroke{nl}{i2}(width 0){nl}{i2}(type default){nl}{i1}){nl}"
        f"{i1}(fill {fill}){nl}{i1}(layer {sexp.quoted(layer)}){nl}"
        f"{i1}(uuid {sexp.quoted(str(uuid.uuid4()))}){nl}{indent})"
    )


def insert_qr(text: str, root: sexp.Node, marker: str, data: str) -> tuple[str, int, float]:
    """Replace every marker box in ``text`` with the QR code for ``data``.

    Returns the new text, the number of boxes replaced and the smallest module size in mm.
    """
    placements = find_markers(text, root, marker)
    if not placements:
        raise QrError(
            f"No {marker} text box on the board.", "Add a square gr_text_box with that text where the QR code goes."
        )
    matrix = qr_matrix(data)
    size = len(matrix)
    fill = _fill_token(sexp.format_version(root))
    nl = "\r\n" if "\r\n" in text else "\n"
    edits: list[sexp.Edit] = []
    smallest = min(p.side for p in placements) / size
    for p in placements:
        module = p.side / size
        rects: list[str] = []
        for row, cells in enumerate(matrix):
            for col, dark in enumerate(cells):
                if not dark:
                    continue
                c = size - 1 - col if p.back else col
                x0, y0 = p.x0 + c * module, p.y0 + row * module
                rects.append(_rect(x0, y0, x0 + module, y0 + module, p.layer, fill, p.indent, nl))
        edits.append((p.start, p.end, (nl + p.indent).join(rects)))
    return sexp.apply_edits(text, edits), len(placements), smallest


def insert_qr_file(path: Path, marker: str, data: str) -> tuple[int, float]:
    """:func:`insert_qr` on a board file in place (the copy in the work folder); returns box count and module size."""
    text, root = sexp.parse_file(path)
    new_text, count, smallest = insert_qr(text, root, marker, data)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    return count, smallest
