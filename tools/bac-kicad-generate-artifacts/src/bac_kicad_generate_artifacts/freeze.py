# SPDX-License-Identifier: MIT
"""A frozen project: a copy of the KiCad project with one build's resolved parts written into it.

The thin schematic leaves the part choice to the catalogs. For a release, an
assembler or an archive, the copy ``<project>-frozen-<build>`` next to the
project folder carries the parts itself: every placed symbol and every board
footprint whose line the catalogs resolve gets ``Manufacturer PN``, ``LCSC``
and ``Digikey``; a part the ``Build`` field keeps out of the build gets
KiCad's DNP attribute; ``Value`` stays as the designer wrote it. The title
blocks record the build, the date, the catalog versions and the source commit
in their first two free comment slots, and ``FROZEN.md`` next to the project
files says the same with the lines that stayed unresolved.

Edits are span replacements on the copied files (:mod:`bac_common.sexp`), so
everything else in them is byte-identical to the source.
"""

from __future__ import annotations

import datetime as dt
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from bac_common import sexp
from bac_common.catalog import Catalog, Resolved
from bac_common.errors import ConfigError, ExternalToolError
from bac_common.sexp import Atom, Edit, Node, line_indent, quoted

__all__ = ["FIELDS", "Frozen", "freeze_project", "target_dir"]

FIELDS = ("Manufacturer PN", "LCSC", "Digikey")  # written in this order after the last property
# Folders and files a project copy does not need (the QR stage's list).
COPY_IGNORE = shutil.ignore_patterns("*-backups", ".git", "__pycache__", "fp-info-cache", "*.lck", "~*", "*.kicad_prl")


@dataclass
class Frozen:
    """What the freeze wrote."""

    target: Path
    build: str
    date: str
    commit: str
    versions: dict[str, str]
    symbols: int = 0  # placed symbol instances with the fields written
    footprints: int = 0  # board footprints with the fields written
    excluded: list[str] = field(default_factory=list)  # references the Build field keeps out of this build
    unresolved: list[tuple[str, str]] = field(default_factory=list)  # (designators, reason)
    flagged: list[tuple[str, str]] = field(default_factory=list)  # (designators, what the catalog says)
    unplaced: list[str] = field(default_factory=list)  # references resolved from the schematic but not on the board
    files: list[Path] = field(default_factory=list)  # the files edited
    titleblocks: int = 0  # title blocks that got the two comment lines
    without_titleblock: list[str] = field(default_factory=list)  # files whose title block could not take them

    def note(self) -> str:
        text = f"{self.symbols} symbols, {self.footprints} footprints"
        if self.excluded:
            text += f", {len(self.excluded)} DNP by Build"
        if self.unresolved:
            text += f", {len(self.unresolved)} unresolved"
        return text


def target_dir(kicad_dir: Path, stem: str, build: str) -> Path:
    """``<parent>/<stem>-frozen-<build>`` – a sibling of the project folder, so ``${KIPRJMOD}/..`` paths hold."""
    return kicad_dir.parent / f"{stem}-frozen-{build}"


def _reference(node: Node) -> str:
    for prop in node.children("property"):
        if prop.value(1) == "Reference":
            return prop.value(2)
    return ""


def _property(node: Node, key: str) -> Node | None:
    return next((p for p in node.children("property") if p.value(1) == key), None)


def _value_atom(prop: Node) -> Atom:
    return prop.atoms()[2]


def _last_property(node: Node) -> Node | None:
    props = node.children("property")
    return props[-1] if props else None


def _schematic_property(key: str, value: str, at: str, indent: str, unit: str) -> str:
    inner = indent + unit
    return "\n".join(
        [
            f"\n{indent}(property {quoted(key)} {quoted(value)}",
            f"{inner}(at {at})",
            f"{inner}(show_name no)",
            f"{inner}(do_not_autoplace no)",
            f"{inner}(hide yes)",
            f"{inner}(effects",
            f"{inner}{unit}(font",
            f"{inner}{unit}{unit}(size 1.27 1.27)",
            f"{inner}{unit})",
            f"{inner})",
            f"{indent})",
        ]
    )


def _footprint_property(key: str, value: str, at: str, layer: str, indent: str, unit: str) -> str:
    inner = indent + unit
    return "\n".join(
        [
            f"\n{indent}(property {quoted(key)} {quoted(value)}",
            f"{inner}(at {at})",
            f"{inner}(unlocked yes)",
            f"{inner}(layer {quoted(layer)})",
            f"{inner}(hide yes)",
            f"{inner}(uuid {quoted(str(uuid.uuid4()))})",
            f"{inner}(effects",
            f"{inner}{unit}(font",
            f"{inner}{unit}{unit}(size 1 1)",
            f"{inner}{unit}{unit}(thickness 0.15)",
            f"{inner}{unit})",
            f"{inner})",
            f"{indent})",
        ]
    )


def _at_text(text: str, node: Node) -> str:
    """The ``(at …)`` arguments of the node's Value property, else ``0 0 0``."""
    value = _property(node, "Value")
    at = value.child("at") if value else None
    if at is None:
        return "0 0 0"
    atoms = at.atoms()
    return " ".join(a.raw(text) for a in atoms[1:]) if len(atoms) > 1 else "0 0 0"


def _set_fields(
    text: str, node: Node, values: dict[str, str], edits: list[Edit], *, board: bool, layer: str = "F.Fab"
) -> bool:
    """Replace or add the property fields on one symbol or footprint node. Returns whether anything changes."""
    last = _last_property(node)
    if last is None:
        return False
    indent = line_indent(text, last.start)
    unit = sexp.indent_unit(indent)
    at = _at_text(text, node)
    changed = False
    additions = []
    for key, value in values.items():
        prop = _property(node, key)
        if prop is not None:
            atom = _value_atom(prop)
            if atom.value != value:
                edits.append((atom.start, atom.end, quoted(value)))
                changed = True
        else:
            additions.append(
                _footprint_property(key, value, at, layer, indent, unit)
                if board
                else _schematic_property(key, value, at, indent, unit)
            )
    if additions:
        edits.append((last.end, last.end, "".join(additions)))
        changed = True
    return changed


def _set_dnp_symbol(text: str, node: Node, edits: list[Edit]) -> bool:
    dnp = node.child("dnp")
    if dnp is not None:
        if dnp.value(1) == "yes":
            return False
        edits.append((dnp.start, dnp.end, "(dnp yes)"))
        return True
    anchor = node.child("in_pos_files") or node.child("on_board") or node.child("in_bom")
    if anchor is None:
        return False
    indent = line_indent(text, anchor.start)
    edits.append((anchor.end, anchor.end, f"\n{indent}(dnp yes)"))
    return True


def _set_dnp_footprint(text: str, node: Node, edits: list[Edit]) -> bool:
    attr = node.child("attr")
    if attr is not None:
        atoms = attr.atoms()[1:]
        if any(a.value == "dnp" for a in atoms):
            return False
        # KiCad writes dnp before allow_soldermask_bridges; keep its order so its next save changes nothing
        after = next((a for a in atoms if a.value == "allow_soldermask_bridges"), None)
        at = after.start - 1 if after is not None else attr.end - 1
        edits.append((at, at, " dnp"))
        return True
    last = _last_property(node)
    if last is None:
        return False
    indent = line_indent(text, last.start)
    edits.append((last.end, last.end, f"\n{indent}(attr dnp)"))
    return True


def _free_comments(block: Node) -> list[int]:
    used = {int(c.value(1)) for c in block.children("comment") if c.value(1).isdigit()}
    return [n for n in range(1, 10) if n not in used]


def _title_block_edits(text: str, root: Node, lines: tuple[str, str], edits: list[Edit]) -> bool:
    block = root.child("title_block")
    if block is None:
        return False
    free = _free_comments(block)
    if len(free) < 2:
        return False
    indent = line_indent(text, block.start) + sexp.indent_unit(line_indent(text, block.start))
    comments = block.children("comment")
    anchor = comments[-1] if comments else (block.children()[-1] if block.children() else None)
    if anchor is None:
        return False
    for n, line in zip(free[:2], lines, strict=True):
        edits.append((anchor.end, anchor.end, f"\n{indent}(comment {n} {quoted(line)})"))
    return True


def _by_reference(resolved: list[Resolved]) -> dict[str, Resolved]:
    out: dict[str, Resolved] = {}
    for r in resolved:
        for ref in r.line.reference_list:
            out[ref] = r
    return out


def _fields_for(r: Resolved) -> dict[str, str]:
    if r.row is None:
        return {}
    return {"Manufacturer PN": r.mpn, "LCSC": r.lcsc, "Digikey": r.digikey}


def freeze_project(
    kicad_dir: Path,
    target: Path,
    *,
    build: str,
    resolved: list[Resolved],
    catalog: Catalog,
    commit: str,
    tool: str,
    today: dt.date | None = None,
) -> Frozen:
    """Copy ``kicad_dir`` to ``target`` and write the resolved parts of ``build`` into the copy."""
    source, dest = kicad_dir.resolve(), target.resolve()
    if dest == source or source in dest.parents or dest in source.parents:
        raise ConfigError(
            f"{kicad_dir.name} is a frozen folder itself, or holds the target.", "Freeze the source project."
        )
    if target.exists():
        if any(target.glob("~*.lck")):
            raise ExternalToolError(f"{target.name} is open in KiCad.", "Close it, then run again.")
        shutil.rmtree(target)
    shutil.copytree(kicad_dir, target, ignore=COPY_IGNORE)
    date = (today or dt.date.today()).isoformat()
    frozen = Frozen(target, build, date, commit, dict(catalog.versions))
    by_ref = _by_reference(resolved)
    for r in resolved:
        designators = ", ".join(r.line.reference_list)
        if not r.line.fitted(build):
            frozen.excluded.extend(r.line.reference_list)
            continue  # not in this build: its resolution does not matter here
        if r.row is None:
            frozen.unresolved.append((designators, r.reason))
        for flag in r.flags:
            what = f"lifecycle {r.lifecycle}" if flag == "lifecycle" else "not confirmed against a datasheet"
            frozen.flagged.append((designators, what))
    excluded = set(frozen.excluded)
    versions = ", ".join(f"{k} {v}" for k, v in catalog.versions.items() if v) or "unversioned"
    lines = (
        f"Frozen {build} build {date} ({tool})",
        f"Catalogs {versions}; source {commit}",
    )

    placed: set[str] = set()
    for sch in sorted(target.glob("*.kicad_sch")):
        text, root = sexp.parse_file(sch)
        edits: list[Edit] = []
        for node in root.children("symbol"):
            ref = _reference(node)
            if not ref or ref.startswith("#"):
                continue
            if ref in excluded:  # not in this build: DNP, its fields as they are
                _set_dnp_symbol(text, node, edits)
                continue
            r = by_ref.get(ref)
            if r is not None and _set_fields(text, node, _fields_for(r), edits, board=False):
                frozen.symbols += 1
        if _title_block_edits(text, root, lines, edits):
            frozen.titleblocks += 1
        else:
            frozen.without_titleblock.append(sch.name)
        if edits:
            sch.write_text(sexp.apply_edits(text, edits), encoding="utf-8")
            frozen.files.append(sch)

    for pcb in sorted(target.glob("*.kicad_pcb")):
        text, root = sexp.parse_file(pcb)
        edits = []
        for node in root.children("footprint"):
            ref = _reference(node)
            if not ref:
                continue
            placed.add(ref)
            if ref in excluded:
                _set_dnp_footprint(text, node, edits)
                continue
            r = by_ref.get(ref)
            if r is not None and _set_fields(text, node, _fields_for(r), edits, board=True):
                frozen.footprints += 1
        if _title_block_edits(text, root, lines, edits):
            frozen.titleblocks += 1
        else:
            frozen.without_titleblock.append(pcb.name)
        if edits:
            pcb.write_text(sexp.apply_edits(text, edits), encoding="utf-8")
            frozen.files.append(pcb)
    if placed:
        frozen.unplaced = sorted(
            ref for ref, r in by_ref.items() if r.row is not None and ref not in placed and ref not in excluded
        )

    (target / "FROZEN.md").write_text(frozen_md(frozen, kicad_dir, tool), encoding="utf-8")
    return frozen


def frozen_md(frozen: Frozen, source: Path, tool: str) -> str:
    """The note next to the frozen project files."""
    versions = "\n".join(f"| {k} | {v or '–'} |" for k, v in frozen.versions.items()) or "| – | – |"
    where = "/".join(source.resolve().parts[-2:]) if len(source.resolve().parts) > 1 else source.name
    out = [
        f"# Frozen {frozen.build} build",
        "",
        f"A copy of `{where}/` with the {frozen.build} build's parts written into every placed symbol and board "
        f"footprint the catalogs resolve (`Manufacturer PN`, `LCSC`, `Digikey`); `Value` unchanged. "
        f"Generated by {tool} on {frozen.date}; do not edit, regenerate.",
        "",
        "| | |",
        "| :-- | :-- |",
        f"| Build | {frozen.build} |",
        f"| Date | {frozen.date} |",
        f"| Source | `{where}/` at {frozen.commit} |",
        f"| Symbol instances written | {frozen.symbols} |",
        f"| Footprints written | {frozen.footprints} |",
        "",
        "## Catalog versions",
        "",
        "| Catalog | Version |",
        "| :-- | :-- |",
        versions,
    ]
    if frozen.excluded:
        out += ["", f"## Not fitted in {frozen.build} (DNP by the Build field)", "", ", ".join(frozen.excluded)]
    if frozen.unresolved:
        out += ["", "## Unresolved", "", "| Designator | Reason |", "| :-- | :-- |"]
        out += [f"| {d} | {reason} |" for d, reason in frozen.unresolved]
    if frozen.flagged:
        out += ["", "## Flagged by the catalog", "", "| Designator | What |", "| :-- | :-- |"]
        out += [f"| {d} | {what} |" for d, what in frozen.flagged]
    if frozen.unplaced:
        out += ["", "## Resolved in the schematic but not on the board", "", ", ".join(frozen.unplaced)]
    if frozen.without_titleblock:
        out += [
            "",
            "## Title blocks without the two comment lines",
            "",
            "No title block or fewer than two free comment slots: " + ", ".join(frozen.without_titleblock),
        ]
    return "\n".join(out) + "\n"
