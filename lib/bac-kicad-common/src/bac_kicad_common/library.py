# SPDX-License-Identifier: MIT
"""Where things are in KiCad library files: suffixes, containers, names, prefixes."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from bac_common.errors import UsageError
from bac_common.sexp import Node, SexpError

__all__ = [
    "SYMBOL_SUFFIX",
    "FOOTPRINT_SUFFIX",
    "SCHEMATIC_SUFFIX",
    "LIBRARY_SUFFIXES",
    "REF_PREFIX_RE",
    "find_files",
    "library_name",
    "containers",
    "symbol_name",
    "reference_prefix",
]

SYMBOL_SUFFIX = ".kicad_sym"
FOOTPRINT_SUFFIX = ".kicad_mod"
SCHEMATIC_SUFFIX = ".kicad_sch"
LIBRARY_SUFFIXES = (SYMBOL_SUFFIX, FOOTPRINT_SUFFIX)

REF_PREFIX_RE = re.compile(r"^#?([A-Za-z]+)")


def find_files(roots: Iterable[Path], suffixes: tuple[str, ...] = LIBRARY_SUFFIXES) -> list[Path]:
    """Library files from files or directories (searched recursively), sorted and de-duplicated."""
    out: dict[Path, Path] = {}
    for root in roots:
        root = root.expanduser()
        if root.is_file():
            if root.suffix not in suffixes:
                raise UsageError(f"Not a KiCad library file: {root}", "Expected " + " or ".join(suffixes) + ".")
            out.setdefault(root.resolve(), root)
        elif root.is_dir():
            for suffix in suffixes:
                for path in sorted(root.rglob(f"*{suffix}")):
                    if path.is_file():
                        out.setdefault(path.resolve(), path)
        else:
            raise UsageError(f"No such file or directory: {root}")
    return [out[key] for key in sorted(out)]


def library_name(path: Path) -> str:
    """The library a file belongs to.

    Files inside a ``.kicad_symdir`` or ``.pretty`` directory belong to the
    library that directory names; a packed ``.kicad_sym`` outside one is a
    library of its own, named after the file.
    """
    parent = path.parent.name
    for suffix in (".kicad_symdir", ".pretty"):
        if parent.endswith(suffix):
            return parent[: -len(suffix)]
    if path.suffix == SYMBOL_SUFFIX:
        return path.stem
    return parent


def symbol_name(node: Node, fallback: str = "") -> str:
    return node.value(1) or fallback


def containers(path: Path, root: Node) -> tuple[str, list[tuple[Node, str]]]:
    """``(target, [(container, name), …])`` – the nodes that carry properties in this file.

    A symbol library holds one container per top-level symbol (sub-unit
    symbols nested inside carry no properties); a footprint file is one
    container.
    """
    if path.suffix == SYMBOL_SUFFIX:
        if root.head != "kicad_symbol_lib":
            raise SexpError(f"{path}: not a kicad_symbol_lib file (head is {root.head!r})")
        return "symbol", [(sym, symbol_name(sym, path.stem)) for sym in root.children("symbol")]
    if path.suffix == FOOTPRINT_SUFFIX:
        if root.head != "footprint":
            raise SexpError(f"{path}: not a footprint file (head is {root.head!r})")
        return "footprint", [(root, symbol_name(root, path.stem))]
    raise UsageError(f"{path}: unsupported extension {path.suffix!r}")


def reference_prefix(reference: str) -> str:
    """``R`` from ``R``, ``U`` from ``U12``, ``PWR`` from ``#PWR``; ``""`` when there is none."""
    m = REF_PREFIX_RE.match(reference)
    return m.group(1) if m else ""
