# SPDX-License-Identifier: MIT
"""Hierarchical-label s-expressions in the shape KiCad 9 and 10 write them.

A label is one ``(hierarchical_label …)`` node with shape, position,
font effects, justification and a UUID. The tool emits them exactly as the
schematic file format does – tab-indented, one child per line, UUID quoted
– so the output can be pasted into a ``.kicad_sch`` between two existing
items, or into a text editor for further templating.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

__all__ = ["SHAPES", "JUSTIFY", "ROTATIONS", "LabelStyle", "fmt", "escape", "parse_names", "make_label", "render"]

SHAPES = ("input", "output", "bidirectional", "tri_state", "passive")
JUSTIFY = ("left", "right")
ROTATIONS = (0, 90, 180, 270)


@dataclass(frozen=True, slots=True)
class LabelStyle:
    """Everything about a label that is not its name or position."""

    shape: str = "passive"
    justify: str = "right"
    rotation: int = 0
    font_size: float = 1.27


def fmt(value: float) -> str:
    """A number the way KiCad writes it: up to four decimals, no trailing zeros, ``0`` not ``0.0``."""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def escape(name: str) -> str:
    """Backslashes and double quotes escaped for a quoted s-expression string."""
    return name.replace("\\", "\\\\").replace('"', '\\"')


def parse_names(text: str, *, gap_on_blank: bool = False) -> list[str | None]:
    """Net names, one per line, whitespace trimmed.

    Blank lines are dropped, unless ``gap_on_blank`` is set: then each one
    becomes ``None``, an empty slot that advances the position without
    emitting a label, so groups in the input stay groups in the schematic.
    """
    out: list[str | None] = []
    for line in text.splitlines():
        name = line.strip()
        if name:
            out.append(name)
        elif gap_on_blank:
            out.append(None)
    while out and out[-1] is None:
        out.pop()
    return out


def make_label(name: str, x: float, y: float, style: LabelStyle, uid: str | None = None) -> str:
    """One ``(hierarchical_label …)`` block."""
    uid = uid or str(uuid.uuid4())
    size = fmt(style.font_size)
    return (
        f'(hierarchical_label "{escape(name)}"\n'
        f"\t(shape {style.shape})\n"
        f"\t(at {fmt(x)} {fmt(y)} {style.rotation})\n"
        "\t(effects\n"
        "\t\t(font\n"
        f"\t\t\t(size {size} {size})\n"
        "\t\t)\n"
        f"\t\t(justify {style.justify})\n"
        "\t)\n"
        f'\t(uuid "{uid}")\n'
        ")"
    )


def render(
    names: Sequence[str | None],
    *,
    x: float = 0.0,
    y_start: float = 0.0,
    step: float = 2.54,
    style: LabelStyle = LabelStyle(),
    uuid_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> str:
    """All blocks, blank-line separated, ending with a newline. ``None`` entries advance ``y`` only."""
    blocks = []
    for index, name in enumerate(names):
        if name is None:
            continue
        # Multiply rather than accumulate so float error cannot creep into the 40th label.
        blocks.append(make_label(name, x, y_start + index * step, style, uuid_factory()))
    return "\n\n".join(blocks) + "\n" if blocks else ""
