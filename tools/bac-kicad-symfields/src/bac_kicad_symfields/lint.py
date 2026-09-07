# SPDX-License-Identifier: MIT
"""Lint findings and size fixes for symbol and footprint files.

Symbols: every property font must use one of the accepted sizes (1.27 mm
or 0.762 mm in the BAC library), pin names, pin numbers and text items must
use the pin size, and the ``Footprint`` property must start with the
library's footprint nickname. Footprints: property and text fonts must be
the footprint font (0.8 mm, thickness 0.1 mm), and no UUID may appear
twice. ``fix`` corrects the sizes by replacing the numbers in place; the
prefix and the UUIDs are reported only.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from bac_common.sexp import Atom, Edit, Node, apply_edits, fmt_number, line_indent
from bac_kicad_common.library import containers

from .config import Settings

__all__ = ["Finding", "lint_file", "fix_file", "duplicate_uuids"]


@dataclass(slots=True)
class Finding:
    item: str  # symbol or footprint name
    where: str  # "property Value", "pin 3 name", "text", "fp_text user", "uuid"
    kind: str  # size | thickness | prefix | uuid | field
    found: str
    expected: str
    fixable: bool = False


def _sizes(node: Node) -> list[tuple[Node, float, float]]:
    """Every ``(size x y)`` under ``node``'s effects/font with both numbers."""
    out = []
    for effects in node.children("effects"):
        for font in effects.children("font"):
            for size in font.children("size"):
                atoms = size.atoms()
                if len(atoms) >= 3:
                    x, y = atoms[1].number(), atoms[2].number()
                    if x is not None and y is not None:
                        out.append((size, x, y))
    return out


def _thicknesses(node: Node) -> list[tuple[Node, Node | None, float | None]]:
    """``(font, thickness_node, value)`` per font under ``node``; ``thickness_node`` is ``None`` when absent."""
    out = []
    for effects in node.children("effects"):
        for font in effects.children("font"):
            thickness = font.child("thickness")
            value = thickness.atoms()[1].number() if thickness and len(thickness.atoms()) > 1 else None
            out.append((font, thickness, value))
    return out


def _pretty(x: float, y: float) -> str:
    return fmt_number(x) if abs(x - y) < 1e-9 else f"{fmt_number(x)}×{fmt_number(y)}"


def _symbol_texts(sym: Node):
    """``(where, node)`` for every font-bearing element of a top-level symbol and its units."""
    for prop in sym.children("property"):
        yield f"property {prop.value(1)}", prop
    for node in sym.walk():
        if node is sym:
            continue
        if node.head == "pin":
            number = node.child("number")
            label = number.value(1) if number else "?"
            for part in ("name", "number"):
                child = node.child(part)
                if child is not None:
                    yield f"pin {label} {part}", child
        elif node.head in ("text", "text_box"):
            yield node.head, node


def _footprint_texts(root: Node):
    for prop in root.children("property"):
        yield f"property {prop.value(1)}", prop
    for node in root.children("fp_text"):
        yield f"fp_text {node.value(1)}", node
    for node in root.children("fp_text_box"):
        yield "fp_text_box", node


def duplicate_uuids(root: Node) -> list[tuple[str, int]]:
    """UUID values that appear more than once anywhere in the tree, with their counts."""
    counts = Counter(node.value(1) for node in root.find_all("uuid") if node.value(1))
    return [(value, n) for value, n in counts.items() if n > 1]


def lint_file(path: Path, root: Node, settings: Settings) -> list[Finding]:
    target, items = containers(path, root)
    findings: list[Finding] = []
    for container, name in items:
        if target == "symbol":
            findings.extend(_lint_symbol(container, name, settings))
        else:
            findings.extend(_lint_footprint(container, name, settings))
    return findings


def _lint_symbol(sym: Node, name: str, s: Settings) -> list[Finding]:
    out: list[Finding] = []
    allowed = " or ".join(fmt_number(v) for v in s.property_sizes)
    for where, node in _symbol_texts(sym):
        for _, x, y in _sizes(node):
            if where.startswith("property"):
                if not (s.property_size_ok(x) and s.property_size_ok(y)):
                    out.append(Finding(name, where, "size", _pretty(x, y), allowed, fixable=True))
            elif not (s.close(x, s.pin_size) and s.close(y, s.pin_size)):
                out.append(Finding(name, where, "size", _pretty(x, y), fmt_number(s.pin_size), fixable=True))
    for prop in sym.children("property"):
        if prop.value(1) == "Footprint":
            value = prop.value(2)
            if value and not value.startswith(s.footprint_prefix):
                out.append(Finding(name, "property Footprint", "prefix", value, f"{s.footprint_prefix}…"))
    return out


def _lint_footprint(root: Node, name: str, s: Settings) -> list[Finding]:
    out: list[Finding] = []
    for where, node in _footprint_texts(root):
        for _, x, y in _sizes(node):
            if not (s.close(x, s.fp_font_size) and s.close(y, s.fp_font_size)):
                out.append(Finding(name, where, "size", _pretty(x, y), fmt_number(s.fp_font_size), fixable=True))
        for _, _thickness, value in _thicknesses(node):
            if value is None:
                out.append(Finding(name, where, "thickness", "none", fmt_number(s.fp_font_thickness), fixable=True))
            elif not s.close(value, s.fp_font_thickness):
                out.append(
                    Finding(name, where, "thickness", fmt_number(value), fmt_number(s.fp_font_thickness), fixable=True)
                )
    for value, count in duplicate_uuids(root):
        out.append(Finding(name, "uuid", "uuid", f"{value} ×{count}", "unique"))
    return out


def fix_file(path: Path, text: str, root: Node, settings: Settings) -> tuple[str, list[Finding]]:
    """Correct every fixable size and thickness finding in place. Returns the new text and what changed."""
    target, items = containers(path, root)
    edits: list[Edit] = []
    fixed: list[Finding] = []
    for container, name in items:
        if target == "symbol":
            for where, node in _symbol_texts(container):
                wanted = None
                for size, x, y in _sizes(node):
                    if where.startswith("property"):
                        ok = settings.property_size_ok(x) and settings.property_size_ok(y)
                        wanted = settings.property_fix_size
                    else:
                        ok = settings.close(x, settings.pin_size) and settings.close(y, settings.pin_size)
                        wanted = settings.pin_size
                    if not ok:
                        edits.append(_size_edit(size, wanted))
                        fixed.append(Finding(name, where, "size", _pretty(x, y), fmt_number(wanted), fixable=True))
        else:
            for where, node in _footprint_texts(container):
                for size, x, y in _sizes(node):
                    if not (settings.close(x, settings.fp_font_size) and settings.close(y, settings.fp_font_size)):
                        edits.append(_size_edit(size, settings.fp_font_size))
                        fixed.append(
                            Finding(name, where, "size", _pretty(x, y), fmt_number(settings.fp_font_size), fixable=True)
                        )
                for font, thickness, value in _thicknesses(node):
                    want = fmt_number(settings.fp_font_thickness)
                    if value is None:
                        anchor = font.child("size") or font
                        indent = line_indent(text, anchor.start)
                        if anchor is font:  # a font with no size: put the thickness on its own line inside it
                            indent = indent + ("\t" if "\t" in indent else "  ")
                            edits.append(
                                (font.start + len("(font"), font.start + len("(font"), f"\n{indent}(thickness {want})")
                            )
                        else:
                            edits.append((anchor.end, anchor.end, f"\n{indent}(thickness {want})"))
                        fixed.append(Finding(name, where, "thickness", "none", want, fixable=True))
                    elif not settings.close(value, settings.fp_font_thickness):
                        atom = thickness.atoms()[1]
                        edits.append((atom.start, atom.end, want))
                        fixed.append(Finding(name, where, "thickness", fmt_number(value), want, fixable=True))
    return apply_edits(text, edits), fixed


def _size_edit(size: Node, wanted: float) -> Edit:
    """Replace the two numbers of a ``(size x y)`` node, keeping everything around them."""
    atoms: list[Atom] = size.atoms()
    first, last = atoms[1], atoms[2]
    value = fmt_number(wanted)
    return (first.start, last.end, f"{value} {value}")
