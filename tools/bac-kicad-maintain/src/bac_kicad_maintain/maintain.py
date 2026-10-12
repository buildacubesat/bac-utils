# SPDX-License-Identifier: MIT
"""The operations: text, courtyard, via and label normalisation, the library rename, the statistics.

Everything works on :mod:`bac_common.sexp` trees and produces span edits,
so the file comes back with KiCad's own formatting and only the intended
tokens changed. :func:`transform` plans one file and returns the new text,
the counts and – for ``stats`` – the size statistics; :func:`discover`
finds the files a command works on.
"""

from __future__ import annotations

import fnmatch
import os
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from bac_common.errors import BacError, UsageError
from bac_common.sexp import Atom, Edit, Node, SexpError, apply_edits, fmt_number, indent_unit, parse, quoted

from .config import Settings, number

__all__ = [
    "BOARD_SUFFIX",
    "SCHEMATIC_SUFFIX",
    "LABEL_HEADS",
    "TEXT_HEADS",
    "Patches",
    "transform",
    "inspect_stats",
    "discover",
    "suffixes_for",
]

BOARD_SUFFIX = ".kicad_pcb"
SCHEMATIC_SUFFIX = ".kicad_sch"
BOARD_HEADS = {"kicad_pcb"}
LABEL_HEADS = {"label", "global_label", "hierarchical_label"}
TEXT_HEADS = {"gr_text", "fp_text", "gr_text_box", "fp_text_box", "property"}
SHAPE_HEADS = {p + s for p in ("gr_", "fp_") for s in ("line", "rect", "circle", "arc", "poly", "curve")}
COURTYARD_LAYERS = {"F.CrtYd", "B.CrtYd"}
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules"}


class MaintainError(BacError):
    """A file the operations cannot handle, or a plan that contradicts itself."""


def _one(node: Node, head: str) -> Node | None:
    """The only child ``head``, ``None`` when there is none; two are an error."""
    matches = node.children(head)
    if len(matches) > 1:
        raise MaintainError(f"Duplicate ({head} …) inside ({node.head} …).")
    return matches[0] if matches else None


def _fmt(value: object) -> str:
    return fmt_number(float(number(value)))


# ---------------------------------------------------------------------------
# Span edits
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Patches:
    """Collects span replacements and insertions for one file and renders them."""

    text: str
    edits: dict[tuple[int, int], str] = field(default_factory=dict)
    insertions: dict[int, list[str]] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.edits) + sum(len(parts) for parts in self.insertions.values())

    def replace(self, item: Atom | Node, value: str) -> None:
        if self.text[item.start : item.end] == value:
            return
        key = (item.start, item.end)
        if key in self.edits and self.edits[key] != value:
            raise MaintainError("Two operations want to change the same token differently.")
        self.edits[key] = value

    def remove(self, item: Atom | Node) -> None:
        """Take a token or list out together with the whitespace that separated it.

        A list alone on its line (KiCad's one-child-per-line layout) goes
        with its line; a token inside a line goes with the space before it,
        so ``(justify left top mirror)`` becomes ``(justify mirror)`` and a
        diff shows only the intended change.
        """
        start, end = item.start, item.end
        line_start = self.text.rfind("\n", 0, start) + 1
        newline = self.text.find("\n", end)
        line_end = len(self.text) if newline < 0 else newline + 1
        alone = line_start > 0 and not self.text[line_start:start].strip() and not self.text[end:line_end].strip()
        if alone:
            self._edit(line_start, line_end, "")
            return
        while start > 0 and self.text[start - 1] in " \t":
            start -= 1
        if start == item.start or self.text[start - 1] == "(":
            start = item.start
            while end < len(self.text) and self.text[end] in " \t":
                end += 1
        self._edit(start, end, "")

    def _edit(self, start: int, end: int, value: str) -> None:
        key = (start, end)
        if key in self.edits and self.edits[key] != value:
            raise MaintainError("Two operations want to change the same token differently.")
        self.edits[key] = value

    def append(self, node: Node, text: str) -> None:
        """Insert ``text`` as the last item of ``node``.

        When the closing parenthesis sits on its own line the item gets a
        line of its own, indented one level deeper than the parenthesis;
        otherwise it follows the last item after a space.
        """
        close = node.end - 1
        line_start = self.text.rfind("\n", 0, close) + 1
        indent = self.text[line_start:close]
        if line_start > 0 and not indent.strip():
            eol = "\r\n" if self.text[line_start - 2 : line_start] == "\r\n" else "\n"
            self.insertions.setdefault(line_start, []).append(f"{indent}{indent_unit(indent)}{text}{eol}")
        else:
            self.insertions.setdefault(close, []).append(" " + text)

    def scalar(self, node: Node, head: str, values: Iterable[object]) -> None:
        """Set ``(head v1 v2 …)`` inside ``node``: edit the numbers that differ, add the list when missing."""
        values = list(values)
        child = _one(node, head)
        if child is None:
            self.append(node, f"({head} {' '.join(_fmt(v) for v in values)})")
            return
        atoms = child.atoms()[1:]
        if len(atoms) != len(values) or child.children():
            raise MaintainError(f"Unexpected ({head} …) shape: {self.text[child.start : child.end]}")
        for atom, target in zip(atoms, values, strict=True):
            try:
                current = number(atom.value)
            except BacError:
                raise MaintainError(f"({head} …) holds a non-number: {self.text[child.start : child.end]}") from None
            if current != number(target):
                self.replace(atom, _fmt(target))

    def render(self) -> str:
        edits: list[Edit] = [(start, end, value) for (start, end), value in self.edits.items()]
        edits += [(pos, pos, "".join(parts)) for pos, parts in self.insertions.items()]
        return apply_edits(self.text, edits)


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------


def _layer(node: Node) -> str:
    layer = _one(node, "layer")
    return layer.value(1) if layer else ""


def board_items(root: Node) -> Iterator[Node]:
    """The board's items with footprints flattened; dimension and zone internals stay out."""
    for item in root.children():
        if item.head == "footprint":
            yield from item.children()
        else:
            yield item


def normalize_text(item: Node, patches: Patches, settings: Settings) -> bool:
    """Font size, stroke, centring and keep-upright on one text item. True when something changed."""
    before = patches.count
    effects = _one(item, "effects")
    if effects is None:
        return False
    font = _one(effects, "font")
    size = (settings.text_height, settings.text_width)
    if font is None:
        patches.append(
            effects, f"(font (size {_fmt(size[0])} {_fmt(size[1])}) (thickness {_fmt(settings.text_thickness)}))"
        )
    else:
        patches.scalar(font, "size", size)
        patches.scalar(font, "thickness", [settings.text_thickness])
    if settings.text_center:
        justify = _one(effects, "justify")
        if justify:
            doomed = [a for a in justify.atoms()[1:] if a.value in {"left", "right", "top", "bottom"}]
            if doomed and len(doomed) == len(justify.atoms()) - 1 and not justify.children():
                patches.remove(justify)  # nothing would be left but (justify)
            else:
                for atom in doomed:
                    patches.remove(atom)
            # mirror and any attribute KiCad adds later stay.
    if settings.text_keep_upright:
        for atom in item.atoms():
            if not atom.quoted and atom.value == "unlocked":
                patches.remove(atom)
        for unlocked in item.children("unlocked"):
            patches.remove(unlocked)
        # Board text has no serialised keep-upright flag; its rotation stays as it is.
    changed = patches.count != before
    if changed:
        for cache in item.children("render_cache"):
            patches.remove(cache)
    return changed


def normalize_courtyard(item: Node, patches: Patches, settings: Settings) -> bool:
    if item.head not in SHAPE_HEADS or _layer(item) not in COURTYARD_LAYERS:
        return False
    before = patches.count
    stroke = _one(item, "stroke")
    legacy = _one(item, "width")
    if stroke:
        patches.scalar(stroke, "width", [settings.courtyard_width])
    if legacy:
        patches.scalar(item, "width", [settings.courtyard_width])
    if not stroke and not legacy:
        raise MaintainError(f"A courtyard {item.head} has neither (stroke …) nor (width …).")
    return patches.count != before


def net_table(root: Node) -> dict[str, str]:
    nets = {"0": ""}
    for node in root.children("net"):
        atoms = node.atoms()[1:]
        if len(atoms) == 2:
            nets[atoms[0].value] = atoms[1].value
    return nets


def via_net(item: Node, nets: dict[str, str]) -> str | None:
    """The via's net name: ``""`` when unconnected, ``None`` when the reference cannot be resolved."""
    node = _one(item, "net")
    atoms = node.atoms()[1:] if node else []
    if len(atoms) == 1:
        return atoms[0].value if atoms[0].quoted else nets.get(atoms[0].value)
    if len(atoms) == 2:
        return atoms[1].value
    return None


def via_type(item: Node) -> str:
    return next((a.value for a in item.atoms()[1:] if a.value in {"blind", "micro"}), "through")


def normalize_via(item: Node, patches: Patches, settings: Settings, nets: dict[str, str], counts: Counter) -> None:
    name = via_net(item, nets)
    if name is None:
        counts["vias skipped, unknown net"] += 1
        return
    if not name:
        counts["vias skipped, unconnected"] += 1
        return
    if any(fnmatch.fnmatchcase(name, pattern) for pattern in settings.preserve_nets):
        counts["vias kept, preserved net"] += 1
        return
    if via_type(item) not in settings.via_types or _one(item, "padstack"):
        counts["vias skipped, type or padstack"] += 1
        return
    if _one(item, "size") is None or _one(item, "drill") is None:
        raise MaintainError("A via has no size or no drill.")
    before = patches.count
    patches.scalar(item, "size", [settings.via_diameter])
    patches.scalar(item, "drill", [settings.via_drill])
    if patches.count != before:
        counts["vias"] += 1


# ---------------------------------------------------------------------------
# Schematics
# ---------------------------------------------------------------------------


def normalize_labels(root: Node, patches: Patches, size: Decimal, counts: Counter) -> None:
    """Top-level electrical labels only; notes, fields, sheet pins and the cache stay."""
    for item in root.children():
        if item.head not in LABEL_HEADS:
            continue
        before = patches.count
        effects = _one(item, "effects")
        if effects is None:
            patches.append(item, f"(effects (font (size {_fmt(size)} {_fmt(size)})))")
        else:
            font = _one(effects, "font")
            if font is None:
                patches.append(effects, f"(font (size {_fmt(size)} {_fmt(size)}))")
            else:
                patches.scalar(font, "size", [size, size])
        if patches.count != before:
            counts["labels"] += 1


def migrate_library(root: Node, patches: Patches, old: str, new: str, counts: Counter) -> None:
    """Rename the library part of ``lib_id`` values and of the cached symbol IDs; nothing else."""
    prefix = old + ":"
    cache = _one(root, "lib_symbols")
    if cache:
        renamed = []
        for symbol in cache.children("symbol"):
            name = symbol.value(1)
            if not name:
                raise MaintainError("A cached symbol has no identifier.")
            renamed.append(new + name[len(old) :] if name.startswith(prefix) else name)
        duplicates = sorted(name for name, count in Counter(renamed).items() if count > 1)
        if duplicates:
            raise MaintainError(
                "The rename would give two cached symbols the same ID: " + ", ".join(duplicates) + ".",
                "Resolve the cached definitions in lib_symbols first; nothing was written.",
            )
        for symbol in cache.children("symbol"):
            atom = symbol.atoms()[1]
            if atom.value.startswith(prefix):
                patches.replace(atom, quoted(new + atom.value[len(old) :]))
                counts["cached symbols"] += 1
    for symbol in root.children("symbol"):
        lib_id = _one(symbol, "lib_id")
        atoms = lib_id.atoms()[1:] if lib_id else []
        if len(atoms) != 1:
            raise MaintainError("A placed symbol has no single lib_id.")
        if atoms[0].value.startswith(prefix):
            patches.replace(atoms[0], quoted(new + atoms[0].value[len(old) :]))
            counts["symbol references"] += 1


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def inspect_stats(root: Node) -> dict[str, dict[str, int]]:
    """Text sizes by layer and via sizes by type and net (boards), label sizes (schematics)."""
    if root.head == "kicad_sch":
        sizes: Counter = Counter()
        for item in root.children():
            if item.head not in LABEL_HEADS:
                continue
            effects = _one(item, "effects")
            font = _one(effects, "font") if effects else None
            size = _one(font, "size") if font else None
            dims = " × ".join(a.value for a in size.atoms()[1:]) + " mm" if size else "default size"
            sizes[f"{item.head}: {dims}"] += 1
        return {"labels": dict(sorted(sizes.items()))}
    text: Counter = Counter()
    vias: Counter = Counter()
    nets = net_table(root)
    for item in board_items(root):
        if item.head in TEXT_HEADS and _one(item, "effects"):
            font = _one(_one(item, "effects"), "font")
            size = _one(font, "size") if font else None
            thick = _one(font, "thickness") if font else None
            dims = " × ".join(a.value for a in size.atoms()[1:]) + " mm" if size else "default size"
            width = thick.value(1) + " mm" if thick and thick.value(1) else "default stroke"
            text[f"{_layer(item) or '(no layer)'}: {dims} / {width}"] += 1
        if item.head == "via":
            size, drill = _one(item, "size"), _one(item, "drill")
            diameter = size.value(1) if size and size.value(1) else "?"
            hole = drill.value(1) if drill and drill.value(1) else "?"
            name = via_net(item, nets)
            vias[f"{diameter}/{hole} mm, {via_type(item)}, net {name or '(unconnected or unknown)'}"] += 1
    return {"text": dict(sorted(text.items())), "vias": dict(sorted(vias.items()))}


# ---------------------------------------------------------------------------
# One file
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Outcome:
    text: str
    counts: dict[str, int]
    stats: dict[str, dict[str, int]]


def transform(
    text: str,
    root: Node,
    settings: Settings,
    command: str,
    selected: set[str],
    *,
    old: str | None = None,
    new: str | None = None,
    where: str = "",
) -> Outcome:
    """Plan every edit the command makes to one file and render the result.

    ``root`` is ``text`` parsed (:func:`bac_common.sexp.parse_file` gives
    both). ``command`` is ``check``, ``apply``, ``stats`` or
    ``rename-library``; ``selected`` names the operations. The rendered text
    is parsed again so that a broken edit is caught before anything is
    written.
    """
    patches, counts = Patches(text), Counter()
    if command == "stats":
        if root.head not in BOARD_HEADS | {"kicad_sch"}:
            raise MaintainError(f"Not a board or schematic: the file starts with ({root.head} …).")
        return Outcome(text, {}, inspect_stats(root))
    if command == "rename-library":
        if root.head != "kicad_sch":
            raise MaintainError(f"Not a schematic: the file starts with ({root.head} …).")
        assert old is not None and new is not None
        migrate_library(root, patches, old, new, counts)
    elif root.head == "kicad_sch":
        if "labels" not in selected:
            raise MaintainError("A schematic needs --labels; the other operations are for boards.")
        normalize_labels(root, patches, settings.label_size_mm, counts)
    else:
        if root.head not in BOARD_HEADS:
            raise MaintainError(f"Not a board: the file starts with ({root.head} …).")
        nets = net_table(root)
        for item in board_items(root):
            if "text" in selected and item.head in TEXT_HEADS:
                if not settings.text_layers or _layer(item) in settings.text_layers:
                    if normalize_text(item, patches, settings):
                        counts["text items"] += 1
            if "courtyards" in selected and normalize_courtyard(item, patches, settings):
                counts["courtyard lines"] += 1
            if "vias" in selected and item.head == "via":
                normalize_via(item, patches, settings, nets, counts)
    result = patches.render()
    try:
        parse(result, where=where)
    except SexpError as exc:  # pragma: no cover – an edit that breaks the file is a bug here
        raise MaintainError("The planned edits do not parse; nothing was written.", str(exc)) from exc
    return Outcome(result, dict(counts), {})


# ---------------------------------------------------------------------------
# Finding files
# ---------------------------------------------------------------------------


def suffixes_for(command: str, selected: set[str]) -> set[str]:
    """Which file types a command touches: boards for the PCB operations, schematics for labels and the rename."""
    out: set[str] = set()
    if command == "rename-library" or "labels" in selected:
        out.add(SCHEMATIC_SUFFIX)
    if command != "rename-library" and selected & {"text", "courtyards", "vias"}:
        out.add(BOARD_SUFFIX)
    return out


def discover(paths: Iterable[Path], suffixes: set[str], excludes: Iterable[str]) -> list[Path]:
    """Files from paths and directories (searched recursively), sorted and de-duplicated.

    Symlinks are not followed; version-control folders and KiCad's
    ``-backups`` folders are skipped (a ``.bak`` has no KiCad suffix).
    ``excludes`` are glob patterns matched against the path relative to the
    directory given and against the file name. No file at all is an error:
    a run that scans the wrong folder must not pass.
    """
    excludes = list(excludes)
    found: dict[Path, Path] = {}
    for given in paths:
        base = Path(given).expanduser()
        if base.is_symlink():
            raise UsageError(f"Symlinks are not followed: {base}")
        if base.is_file():
            if base.suffix.lower() not in suffixes:
                raise UsageError(
                    f"Not a file this command works on: {base}", "Expected " + " or ".join(sorted(suffixes)) + "."
                )
            if not any(fnmatch.fnmatchcase(base.name, p) for p in excludes):
                found.setdefault(base.resolve(), base)
        elif base.is_dir():
            found.update(_walk(base, suffixes, excludes))
        else:
            raise UsageError(f"No such file or directory: {base}")
    if not found:
        raise UsageError(
            "No " + " or ".join(sorted(suffixes)) + " files found.",
            "Check the paths, the --exclude patterns and which operations are selected.",
        )
    return [found[key] for key in sorted(found)]


def _walk(base: Path, suffixes: set[str], excludes: list[str]) -> dict[Path, Path]:
    def on_error(error: OSError) -> None:
        raise UsageError(f"Cannot scan {error.filename}", error.strerror or str(error))

    found: dict[Path, Path] = {}
    for directory, names, files in os.walk(base, onerror=on_error, followlinks=False):
        parent = Path(directory)
        names[:] = sorted(
            n
            for n in names
            if n not in SKIP_DIRS
            and not n.endswith("-backups")
            and not (parent / n).is_symlink()
            and not any(fnmatch.fnmatchcase((parent / n).relative_to(base).as_posix(), p) for p in excludes)
        )
        for name in sorted(files):
            path = parent / name
            if path.suffix.lower() not in suffixes or path.is_symlink():
                continue
            rel = path.relative_to(base).as_posix()
            if any(fnmatch.fnmatchcase(rel, p) or fnmatch.fnmatchcase(name, p) for p in excludes):
                continue
            found.setdefault(path.resolve(), path)
    return found
