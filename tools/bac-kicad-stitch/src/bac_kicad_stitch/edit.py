# SPDX-License-Identifier: MIT
"""Splicing stitching vias into the board text, and taking them out again.

New vias go after the last top-level via or track (before the zones, where
KiCad keeps them) and are listed in one group named ``bac-stitch``, so
KiCad shows them as a unit and ``remove`` finds them again. Via UUIDs are
derived from the board UUID and the position, so the same placement writes
the same bytes.
"""

from __future__ import annotations

import uuid as uuidlib

from bac_common.sexp import Edit, Node, apply_edits, fmt_number, line_indent, quoted

from .board import Via
from .config import GROUP_NAME

__all__ = ["via_uuid", "insert_vias", "remove_vias"]

_NAMESPACE = uuidlib.UUID("5f3c1a4e-2b7d-4f0e-9c6a-1d2e3f4a5b6c")


def via_uuid(board_uuid: str, x: float, y: float) -> str:
    return str(uuidlib.uuid5(_NAMESPACE, f"{board_uuid}:{fmt_number(x)}:{fmt_number(y)}"))


def _board_uuid(root: Node) -> str:
    node = root.child("uuid")
    return node.value(1) if node else ""


def _via_block(via: Via, uuid: str, indent: str, unit: str, net_layers: tuple[str, str]) -> str:
    i2 = indent + unit
    return (
        f"{indent}(via\n"
        f"{i2}(at {fmt_number(via.x)} {fmt_number(via.y)})\n"
        f"{i2}(size {fmt_number(via.size)})\n"
        f"{i2}(drill {fmt_number(via.drill)})\n"
        f"{i2}(layers {quoted(net_layers[0])} {quoted(net_layers[1])})\n"
        f"{i2}(net {quoted(via.net)})\n"
        f"{i2}(uuid {quoted(uuid)})\n"
        f"{indent})\n"
    )


def _group_block(uuids: list[str], group_uuid: str, indent: str, unit: str) -> str:
    i2, i3 = indent + unit, indent + unit + unit
    lines = [f"{indent}(group {quoted(GROUP_NAME)}", f"{i2}(uuid {quoted(group_uuid)})"]
    members = [quoted(u) for u in uuids]
    if members:
        lines.append(f"{i2}(members " + " ".join(members[:2]))
        for k in range(2, len(members), 2):
            lines.append(f"{i3}" + " ".join(members[k : k + 2]))
        lines.append(f"{i2})")
    lines.append(f"{indent})")
    return "\n".join(lines) + "\n"


def _anchor_after(root: Node, heads: tuple[str, ...]) -> Node | None:
    last = None
    for child in root.children():
        if child.head in heads:
            last = child
    return last


def _newline(text: str) -> str:
    """The file's line ending, from its first line."""
    first = text.find("\n")
    return "\r\n" if first > 0 and text[first - 1] == "\r" else "\n"


def _newline_after(text: str, offset: int) -> int:
    nl = text.find("\n", offset)
    return len(text) if nl < 0 else nl + 1


def insert_vias(text: str, root: Node, vias: list[Via]) -> tuple[str, list[str]]:
    """The board text with ``vias`` added to the stitch group. Returns the text and the new UUIDs."""
    if not vias:
        return text, []
    board_uuid = _board_uuid(root)
    children = root.children()
    first = children[0] if children else None
    indent = line_indent(text, first.start) if first else "\t"
    unit = "\t" if "\t" in indent else "  "
    copper_outer = _outer_layers(root)

    anchor = _anchor_after(root, ("via", "segment", "arc"))
    if anchor is None:
        anchor = _anchor_after(root, ("footprint", "gr_line", "gr_arc", "gr_circle", "gr_rect", "gr_poly", "gr_text"))
    if anchor is None:
        insert_at = root.end - 1
        insert_at = text.rfind("\n", 0, insert_at) + 1
    else:
        insert_at = _newline_after(text, anchor.end)

    nl = _newline(text)
    new_uuids = [via_uuid(board_uuid, v.x, v.y) for v in vias]
    blocks = "".join(_via_block(v, u, indent, unit, copper_outer) for v, u in zip(vias, new_uuids, strict=True))
    edits: list[Edit] = [(insert_at, insert_at, blocks.replace("\n", nl))]

    group = next((g for g in root.children("group") if g.value(1) == GROUP_NAME), None)
    if group is not None:
        members = group.child("members")
        existing = [a.value for a in members.atoms()[1:]] if members else []
        group_uuid = group.child("uuid").value(1) if group.child("uuid") else via_uuid(board_uuid, 0, 0)
        g_indent = line_indent(text, group.start)
        edits.append(
            (
                group.start,
                _newline_after(text, group.end),
                _group_block(existing + new_uuids, group_uuid, g_indent, unit),
            )
        )
    else:
        last_group = _anchor_after(root, ("group",))
        if last_group is not None:
            at = _newline_after(text, last_group.end)
        else:
            at = text.rfind("\n", 0, root.end - 1) + 1
        group_uuid = via_uuid(board_uuid, -1, -1)
        edits.append((at, at, _group_block(new_uuids, group_uuid, indent, unit).replace("\n", nl)))
    return apply_edits(text, edits), new_uuids


def remove_vias(text: str, root: Node) -> tuple[str, int]:
    """The board text without the stitch group and its vias. Returns the text and how many vias went."""
    group = next((g for g in root.children("group") if g.value(1) == GROUP_NAME), None)
    if group is None:
        return text, 0
    members = group.child("members")
    uuids = {a.value for a in members.atoms()[1:]} if members else set()
    edits: list[Edit] = []
    removed = 0
    for via in root.children("via"):
        node = via.child("uuid")
        if node and node.value(1) in uuids:
            start = text.rfind("\n", 0, via.start) + 1
            edits.append((start, _newline_after(text, via.end), ""))
            removed += 1
    start = text.rfind("\n", 0, group.start) + 1
    edits.append((start, _newline_after(text, group.end), ""))
    return apply_edits(text, edits), removed


def _outer_layers(root: Node) -> tuple[str, str]:
    layers = root.child("layers")
    copper = []
    if layers:
        for entry in layers.children():
            atoms = entry.atoms()
            if len(atoms) >= 3 and atoms[1].value.endswith(".Cu"):
                copper.append(atoms[1].value)
    front = "F.Cu" if "F.Cu" in copper else (copper[0] if copper else "F.Cu")
    back = "B.Cu" if "B.Cu" in copper else (copper[-1] if copper else "B.Cu")
    return front, back
