# SPDX-License-Identifier: MIT
"""The field engine: decide what a set of rules does to one item's properties.

Shared by the library tool (symbols, footprints) and the schematic tool.
The decision per rule is the same everywhere: a field that is absent is
added, an empty one is filled, a non-empty one is left alone unless the rule
says ``overwrite = true`` *and* the run allows it. Rendering and inserting
the new blocks is the caller's job because the block shape differs per
format; this module returns what to add and the edits for existing values.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bac_common.sexp import Edit, quoted

from .props import Change, Property, substitute
from .rules import FieldRule

__all__ = ["FieldPlan", "plan_fields"]


@dataclass
class FieldPlan:
    """What the rules do to one item: edits for existing values, blocks to add, and the log."""

    edits: list[Edit] = field(default_factory=list)
    adds: list[tuple[FieldRule, str]] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    values: dict[str, str] = field(default_factory=dict)

    @property
    def touched(self) -> bool:
        return bool(self.edits or self.adds)


def plan_fields(
    rules: list[FieldRule],
    props: list[Property],
    *,
    fill_empty: bool = True,
    allow_overwrite: bool = False,
) -> FieldPlan:
    """Apply ``rules`` in order to the item that carries ``props``.

    ``${Field}`` references resolve against the item's current values, which
    include fields added earlier in the same run, so rules may build on each
    other in declaration order.
    """
    by_key = {p.key: p for p in props}
    plan = FieldPlan(values={p.key: p.value for p in props})

    for rule in rules:
        unmet = [r for r in rule.requires if not plan.values.get(r)]
        if unmet:
            plan.skipped.append((rule.name, "requires " + ", ".join(unmet)))
            continue

        value = substitute(rule.value, plan.values)
        if value is None:
            plan.skipped.append((rule.name, "unresolved ${…} reference"))
            continue

        existing = by_key.get(rule.name)
        if existing is None:
            plan.adds.append((rule, value))
            plan.values[rule.name] = value
            plan.changes.append(Change("add", rule.name, value, rule.source))
        elif not existing.value.strip() and fill_empty and value:
            plan.edits.append((existing.value_start, existing.value_end, quoted(value)))
            plan.values[rule.name] = value
            plan.changes.append(Change("fill", rule.name, value, rule.source))
        elif rule.overwrite and value and existing.value != value:
            if allow_overwrite:
                plan.edits.append((existing.value_start, existing.value_end, quoted(value)))
                plan.values[rule.name] = value
                plan.changes.append(Change("set", rule.name, value, rule.source, previous=existing.value))
            else:
                plan.skipped.append((rule.name, f"would overwrite {existing.value!r}; needs --allow-overwrite"))
    return plan
