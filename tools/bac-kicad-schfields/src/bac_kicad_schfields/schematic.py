# SPDX-License-Identifier: MIT
"""Walk a schematic hierarchy and edit the fields and flags of placed symbols.

A schematic stores placed instances as top-level ``(symbol …)`` nodes and a
cached copy of every library symbol under ``(lib_symbols …)``. Only the
instances are edited unless asked; the four booleans ``dnp``, ``in_bom``,
``on_board`` and ``exclude_from_sim`` are bare tokens rather than
properties and are handled as flags.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bac_common.sexp import Edit, Node, SexpError, apply_edits, indent_unit, line_indent, parse_file
from bac_kicad_common.fields import plan_fields
from bac_kicad_common.props import Change, properties, property_value, render_schematic_property
from bac_kicad_common.rules import FLAG_NAMES, MatchContext, RuleSet, flags_for, rules_for

__all__ = ["InstanceResult", "SheetInfo", "walk_hierarchy", "process_sheet"]


@dataclass(slots=True)
class InstanceResult:
    file: Path
    reference: str
    lib_id: str
    units: int
    changes: list[Change]
    skipped: list[tuple[str, str]]
    cached: bool = False


@dataclass(slots=True)
class SheetInfo:
    path: Path
    instantiations: int = 1
    readable: bool = True  # False when the file is missing or does not parse; see Hierarchy.warnings


@dataclass
class Hierarchy:
    sheets: list[SheetInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _instance_reference(sym: Node) -> str:
    """The reference from the instances block, authoritative since KiCad 6."""
    instances = sym.child("instances")
    if instances is None:
        return ""
    for project in instances.children("project"):
        for path in project.children("path"):
            ref = path.child("reference")
            if ref is not None and ref.value(1):
                return ref.value(1)
    return ""


def walk_hierarchy(root_sheet: Path) -> Hierarchy:
    """Every sheet file reachable from the root, with how often each is instantiated.

    A file reused by several hierarchical sheets is edited once but affects
    every instantiation, so the count is surfaced rather than hidden.
    """
    out = Hierarchy()
    counts: dict[Path, int] = {}
    order: list[Path] = []
    unreadable: set[Path] = set()

    def walk(path: Path) -> None:
        path = path.resolve()
        first_visit = path not in counts
        counts[path] = counts.get(path, 0) + 1
        if not first_visit:
            return
        order.append(path)
        if not path.exists():
            out.warnings.append(f"sheet not found: {path}")
            unreadable.add(path)
            return
        try:
            _, root = parse_file(path)
        except SexpError as exc:
            out.warnings.append(exc.message)
            unreadable.add(path)
            return
        for sheet in root.children("sheet"):
            sheetfile = property_value(sheet, "Sheetfile") or property_value(sheet, "Sheet file")
            if sheetfile:
                walk(path.parent / sheetfile)

    walk(root_sheet)
    out.sheets = [SheetInfo(p, counts[p], p not in unreadable) for p in order]
    return out


def _symbol_position(sym: Node) -> tuple[str, str]:
    at = sym.child("at")
    if at is not None and len(at.atoms()) >= 3:
        return at.value(1), at.value(2)
    return "0", "0"


def _flag_anchor(sym: Node) -> Node | None:
    """The node a missing flag is inserted after: the last existing flag, else unit/at/lib_id."""
    existing = [n for name in FLAG_NAMES for n in sym.children(name)]
    if existing:
        return max(existing, key=lambda n: n.start)
    for head in ("unit", "at", "lib_id"):
        node = sym.child(head)
        if node is not None:
            return node
    return None


def _process_symbol(
    text: str,
    sym: Node,
    ctx: MatchContext,
    rulesets: list[RuleSet],
    *,
    fill_empty: bool,
    allow_overwrite: bool,
    allow_flags: bool,
    flags: bool = True,
) -> tuple[list[Edit], list[Change], list[tuple[str, str]]]:
    props = properties(sym)
    plan = plan_fields(rules_for(rulesets, ctx), props, fill_empty=fill_empty, allow_overwrite=allow_overwrite)
    edits = list(plan.edits)
    changes = list(plan.changes)
    skipped = list(plan.skipped)

    if plan.adds:
        if props:
            anchor_end, anchor_start = props[-1].node_end, props[-1].node_start
        else:
            # After (at …) when present, else the first line break inside the
            # symbol, else – symbol written on one line – behind its head.
            at = sym.child("at")
            newline = text.find("\n", sym.start, sym.end)
            anchor_end = at.end if at else (newline if newline != -1 else sym.atoms()[0].end)
            anchor_start = at.start if at else sym.start
        indent = line_indent(text, anchor_start) or line_indent(text, sym.start) + "\t"
        unit = indent_unit(indent)
        blocks = [render_schematic_property(r, v, indent, unit, _symbol_position(sym)) for r, v in plan.adds]
        edits.append((anchor_end, anchor_end, "\n" + "\n".join(blocks)))

    for rule in flags_for(rulesets, ctx) if flags else []:
        wanted = "yes" if rule.value else "no"
        node = sym.child(rule.name)
        present = node.value(1) if node is not None else ""
        if present == wanted:
            continue
        if not allow_flags:
            skipped.append((rule.name, f"flag change needs --allow-flags ({present or 'unset'} → {wanted})"))
            continue
        if node is not None and len(node.atoms()) > 1:
            atom = node.atoms()[1]
            edits.append((atom.start, atom.end, wanted))
        else:
            anchor = _flag_anchor(sym)
            if anchor is None:
                skipped.append((rule.name, "no place found to insert the flag"))
                continue
            edits.append((anchor.end, anchor.end, f"\n{line_indent(text, anchor.start)}({rule.name} {wanted})"))
        changes.append(Change("flag", rule.name, wanted, rule.source, previous=present or "unset"))
    return edits, changes, skipped


def _split_lib_id(lib_id: str) -> tuple[str, str]:
    library, _, name = lib_id.partition(":")
    return (library, name) if name else ("", lib_id)


def process_sheet(
    path: Path,
    text: str,
    root: Node,
    rulesets: list[RuleSet],
    *,
    fill_empty: bool = True,
    allow_overwrite: bool = False,
    allow_flags: bool = False,
    include_cache: bool = False,
) -> tuple[str, list[InstanceResult]]:
    """``(new_text, results)`` for one sheet; ``new_text`` is ``text`` itself when nothing changed."""
    if root.head != "kicad_sch":
        raise SexpError(f"{path}: not a kicad_sch file (head is {root.head!r})")

    edits: list[Edit] = []
    results: list[InstanceResult] = []
    by_reference: dict[str, InstanceResult] = {}

    for sym in root.children("symbol"):
        lib_id = sym.child("lib_id").value(1) if sym.child("lib_id") else ""
        if not lib_id:
            continue
        library, name = _split_lib_id(lib_id)
        reference = property_value(sym, "Reference") or _instance_reference(sym)
        ctx = MatchContext(
            target="schematic",
            name=name,
            library=library,
            properties={p.key: p.value for p in properties(sym)},
            reference=reference,
            sheet=path.name,
            lib_id=lib_id,
        )
        e, changes, skipped = _process_symbol(
            text, sym, ctx, rulesets, fill_empty=fill_empty, allow_overwrite=allow_overwrite, allow_flags=allow_flags
        )
        edits.extend(e)
        if not (changes or skipped):
            continue
        # Multi-unit parts appear once per unit; report them as one component.
        key = reference or f"{lib_id}@{sym.start}"
        if key in by_reference:
            by_reference[key].units += 1
        else:
            by_reference[key] = InstanceResult(path, reference, lib_id, 1, changes, skipped)
            results.append(by_reference[key])

    cache = root.child("lib_symbols")
    if include_cache and cache is not None:
        for sym in cache.children("symbol"):
            lib_id = sym.value(1)
            if not lib_id:
                continue
            library, name = _split_lib_id(lib_id)
            ctx = MatchContext(
                target="schematic",
                name=name,
                library=library,
                properties={p.key: p.value for p in properties(sym)},
                sheet=path.name,
                lib_id=lib_id,
            )
            # Flags live on placed instances, not on the cached library copies.
            e, changes, skipped = _process_symbol(
                text,
                sym,
                ctx,
                rulesets,
                fill_empty=fill_empty,
                allow_overwrite=allow_overwrite,
                allow_flags=False,
                flags=False,
            )
            edits.extend(e)
            if changes or skipped:
                results.append(InstanceResult(path, "", lib_id, 1, changes, skipped, cached=True))

    return apply_edits(text, edits), results
