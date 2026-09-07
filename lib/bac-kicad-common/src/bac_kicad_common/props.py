# SPDX-License-Identifier: MIT
"""Properties: reading them with their spans, expanding ``${Field}`` references, rendering new ones.

Symbols, footprints and schematic instances all store fields as
``(property "Key" "Value" …)`` blocks, so inspection is shared. Rendering
differs per format – the footprint block carries a layer and a UUID, KiCad
10 symbols put ``(hide yes)`` outside ``(effects …)`` – and lives here too so
every tool writes the same shape.
"""

from __future__ import annotations

import re
import uuid as uuidlib
from dataclasses import dataclass

from bac_common.sexp import Node, fmt_number, quoted

from .rules import FieldRule

__all__ = [
    "SUBST_RE",
    "HIDE_OUTSIDE_EFFECTS_FROM",
    "Property",
    "Change",
    "VERBS",
    "properties",
    "property_value",
    "substitute",
    "render_symbol_property",
    "render_footprint_property",
    "render_schematic_property",
]

SUBST_RE = re.compile(r"\$\{([^}]+)\}")

# KiCad 10 (observed format version 20251024) moved (hide yes) out of
# (effects …) and made it a direct child of (property …), matching the
# footprint format. KiCad 9 and earlier keep it inside (effects …). The
# threshold is for symbol-library versions only: a KiCad 9 schematic already
# carries version 20250114, so render_schematic_property ignores it.
HIDE_OUTSIDE_EFFECTS_FROM = 20250000


@dataclass(slots=True)
class Property:
    """One ``(property "Key" "Value" …)`` block with the spans an edit needs."""

    key: str
    value: str
    value_start: int
    value_end: int
    node_start: int
    node_end: int
    node: Node


@dataclass(slots=True)
class Change:
    """One applied or planned edit: ``add``, ``fill``, ``set`` or ``flag``."""

    kind: str
    key: str
    value: str
    source: str
    previous: str = ""


# Markers in the step log: + added, ~ filled an empty value, ! overwrote, * changed a flag.
VERBS = {"add": "+", "fill": "~", "set": "!", "flag": "*"}


def properties(container: Node) -> list[Property]:
    """Direct ``property`` children of a container, with the spans of their value atoms."""
    out: list[Property] = []
    for node in container.children("property"):
        atoms = node.atoms()
        if len(atoms) < 3:
            continue
        key, value = atoms[1], atoms[2]
        out.append(Property(key.value, value.value, value.start, value.end, node.start, node.end, node))
    return out


def property_value(container: Node, key: str) -> str:
    """The value of the property named ``key`` on ``container``, or ``""``."""
    for node in container.children("property"):
        atoms = node.atoms()
        if len(atoms) >= 3 and atoms[1].value == key:
            return atoms[2].value
    return ""


def substitute(template: str, values: dict[str, str]) -> str | None:
    """Expand ``${Field}`` references. ``None`` when any referenced value is empty or absent."""
    missing: list[str] = []

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        val = values.get(key, "")
        if not val:
            missing.append(key)
        return val

    result = SUBST_RE.sub(repl, template)
    return None if missing else result


def render_symbol_property(rule: FieldRule, value: str, indent: str, unit: str, version: int) -> str:
    """A new property block for a library symbol, in the file's format version."""
    inner = indent + unit
    size = fmt_number(rule.size or 1.27)
    hide_outside = version >= HIDE_OUTSIDE_EFFECTS_FROM
    lines = [f"{indent}(property {quoted(rule.name)} {quoted(value)}", f"{inner}(at 0 0 0)"]
    if hide_outside:
        lines.extend([f"{inner}(show_name no)", f"{inner}(do_not_autoplace no)"])
        if rule.hide:
            lines.append(f"{inner}(hide yes)")
    lines.extend(
        [f"{inner}(effects", f"{inner}{unit}(font", f"{inner}{unit}{unit}(size {size} {size})", f"{inner}{unit})"]
    )
    if rule.hide and not hide_outside:
        lines.append(f"{inner}{unit}(hide yes)")
    lines.extend([f"{inner})", f"{indent})"])
    return "\n".join(lines)


def render_footprint_property(rule: FieldRule, value: str, indent: str, unit: str, version: int) -> str:
    """A new property block for a footprint: layer, UUID, font size and thickness."""
    inner = indent + unit
    size = fmt_number(rule.size or 1.0)
    thickness = fmt_number(rule.thickness or 0.15)
    lines = [
        f"{indent}(property {quoted(rule.name)} {quoted(value)}",
        f"{inner}(at 0 0 0)",
        f"{inner}(unlocked yes)",
        f"{inner}(layer {quoted(rule.layer)})",
    ]
    if rule.hide:
        lines.append(f"{inner}(hide yes)")
    lines.extend(
        [
            f"{inner}(uuid {quoted(str(uuidlib.uuid4()))})",
            f"{inner}(effects",
            f"{inner}{unit}(font",
            f"{inner}{unit}{unit}(size {size} {size})",
            f"{inner}{unit}{unit}(thickness {thickness})",
            f"{inner}{unit})",
            f"{inner})",
            f"{indent})",
        ]
    )
    return "\n".join(lines)


def render_schematic_property(rule: FieldRule, value: str, indent: str, unit: str, at: tuple[str, str]) -> str:
    """A new property block for a placed symbol instance, positioned at the symbol's origin."""
    inner = indent + unit
    size = fmt_number(rule.size or 1.27)
    lines = [
        f"{indent}(property {quoted(rule.name)} {quoted(value)}",
        f"{inner}(at {at[0]} {at[1]} 0)",
        f"{inner}(effects",
        f"{inner}{unit}(font",
        f"{inner}{unit}{unit}(size {size} {size})",
        f"{inner}{unit})",
    ]
    if rule.hide:
        lines.append(f"{inner}{unit}(hide yes)")
    lines.extend([f"{inner})", f"{indent})"])
    return "\n".join(lines)
