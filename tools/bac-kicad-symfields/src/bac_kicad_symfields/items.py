# SPDX-License-Identifier: MIT
"""Apply field rules to the symbols and footprints of one library file.

Detection, precedence and the add/fill/overwrite decision live in
``bac_kicad_common``; this module knows where the containers are in each
format, renders the new blocks in the file's format version, and splices
everything into the original text.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bac_common.sexp import Edit, Node, apply_edits, format_version, indent_unit, line_indent
from bac_kicad_common.fields import plan_fields
from bac_kicad_common.library import containers, library_name, reference_prefix
from bac_kicad_common.props import (
    Change,
    properties,
    property_value,
    render_footprint_property,
    render_symbol_property,
)
from bac_kicad_common.rules import MatchContext, RuleSet, rules_for

__all__ = ["ItemResult", "process_file"]


@dataclass(slots=True)
class ItemResult:
    target: str
    name: str
    library: str
    prefix: str
    changes: list[Change]
    skipped: list[tuple[str, str]]


def process_file(
    path: Path,
    text: str,
    root: Node,
    rulesets: list[RuleSet],
    *,
    fill_empty: bool = True,
    allow_overwrite: bool = False,
) -> tuple[str, list[ItemResult]]:
    """``(new_text, results)``; ``new_text`` is ``text`` itself when nothing changed."""
    target, items = containers(path, root)
    library = library_name(path)
    version = format_version(root)
    render = render_symbol_property if target == "symbol" else render_footprint_property

    edits: list[Edit] = []
    results: list[ItemResult] = []
    for container, name in items:
        props = properties(container)
        prefix = reference_prefix(property_value(container, "Reference")) if target == "symbol" else ""
        ctx = MatchContext(
            target=target, name=name, library=library, prefix=prefix, properties={p.key: p.value for p in props}
        )
        rules = rules_for(rulesets, ctx)
        if not rules:
            continue
        plan = plan_fields(rules, props, fill_empty=fill_empty, allow_overwrite=allow_overwrite)
        edits.extend(plan.edits)
        if plan.adds:
            edits.append(_insertion(text, container, props, plan.adds, render, version))
        if plan.changes or plan.skipped:
            results.append(ItemResult(target, name, library, prefix, plan.changes, plan.skipped))
    return apply_edits(text, edits), results


def _insertion(text: str, container: Node, props, adds, render, version: int) -> Edit:
    """New property blocks go after the item's last property, or first inside an item that has none."""
    if props:
        anchor = props[-1]
        insert_at = anchor.node_end
        indent = line_indent(text, anchor.node_start)
    else:
        # Right after the item's name: the first line break inside the item,
        # or – for an item written on one line – directly behind the name atom.
        insert_at = text.find("\n", container.start, container.end)
        if insert_at == -1:
            atoms = container.atoms()
            insert_at = atoms[1].end if len(atoms) > 1 else atoms[0].end
        outer = line_indent(text, container.start)
        indent = outer + indent_unit(outer or "\t")
    unit = indent_unit(indent)
    blocks = [render(rule, value, indent, unit, version) for rule, value in adds]
    return (insert_at, insert_at, "\n" + "\n".join(blocks))
