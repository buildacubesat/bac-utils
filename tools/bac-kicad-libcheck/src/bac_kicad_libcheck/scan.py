# SPDX-License-Identifier: MIT
"""Enumerate the library inventory, scan project usage, resolve 3D model paths."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from bac_common.sexp import Node, SexpError, parse_file
from bac_kicad_common.props import property_value

from .config import Config, LibraryEntry

__all__ = ["Usage", "ModelRef", "Scan", "build_scan", "counts", "resolve_model_path"]

VAR_RE = re.compile(r"\$\{([^}]+)\}")


@dataclass(slots=True)
class Usage:
    lib_id: str
    reference: str
    sheet: str


@dataclass(slots=True)
class ModelRef:
    lib_id: str
    raw: str
    resolved: Path | None
    exists: bool
    note: str = ""


@dataclass
class Scan:
    symbol_inventory: set[str] = field(default_factory=set)
    footprint_inventory: set[str] = field(default_factory=set)
    symbol_usage: list[Usage] = field(default_factory=list)
    footprint_usage: list[Usage] = field(default_factory=list)
    models: list[ModelRef] = field(default_factory=list)
    footprints_without_model: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _read(path: Path, warnings: list[str]) -> Node | None:
    try:
        return parse_file(path)[1]
    except SexpError as exc:
        warnings.append(exc.message)
        return None


def symbol_inventory(entry: LibraryEntry, warnings: list[str]) -> set[str]:
    """``nickname:name`` for every symbol in a ``.kicad_symdir`` directory or packed ``.kicad_sym``."""
    out: set[str] = set()
    if not entry.path.exists():
        warnings.append(f"symbol library not found: {entry.path}")
        return out
    files = sorted(entry.path.glob("*.kicad_sym")) if entry.path.is_dir() else [entry.path]
    for f in files:
        root = _read(f, warnings)
        if root is None:
            continue
        if root.head != "kicad_symbol_lib":
            warnings.append(f"{f}: not a kicad_symbol_lib file")
            continue
        for sym in root.children("symbol"):
            if sym.value(1):
                out.add(f"{entry.nickname}:{sym.value(1)}")
    return out


def footprint_inventory(entry: LibraryEntry, warnings: list[str]) -> set[str]:
    """``nickname:name`` for every ``.kicad_mod`` in a ``.pretty`` directory."""
    if not entry.path.is_dir():
        warnings.append(f"footprint library not found: {entry.path}")
        return set()
    return {f"{entry.nickname}:{f.stem}" for f in sorted(entry.path.glob("*.kicad_mod"))}


def scan_schematic(path: Path, warnings: list[str]) -> list[Usage]:
    """Placed symbol instances across the sheet hierarchy, de-duplicated on (lib_id, reference, sheet).

    Instances are direct ``symbol`` children of the sheet root; the cached
    definitions inside ``lib_symbols`` are nested one level deeper and never
    picked up. Multi-unit parts appear once per unit, hence the de-duplication.
    """
    seen_files: set[Path] = set()
    seen: set[tuple[str, str, str]] = set()
    out: list[Usage] = []

    def walk(sch: Path) -> None:
        sch = sch.resolve()
        if sch in seen_files:
            return
        seen_files.add(sch)
        if not sch.exists():
            warnings.append(f"schematic sheet not found: {sch}")
            return
        root = _read(sch, warnings)
        if root is None:
            return
        for sym in root.children("symbol"):
            lib_id_node = sym.child("lib_id")
            lib_id = lib_id_node.value(1) if lib_id_node else ""
            if not lib_id:
                continue
            key = (lib_id, property_value(sym, "Reference"), sch.name)
            if key not in seen:
                seen.add(key)
                out.append(Usage(lib_id, key[1], sch.name))
        for sheet in root.children("sheet"):
            sheetfile = property_value(sheet, "Sheetfile") or property_value(sheet, "Sheet file")
            if sheetfile:
                walk(sch.parent / sheetfile)

    walk(path)
    return out


def scan_board(path: Path, warnings: list[str]) -> list[Usage]:
    if not path.exists():
        warnings.append(f"board not found: {path}")
        return []
    root = _read(path, warnings)
    if root is None:
        return []
    out: list[Usage] = []
    for fp in root.children("footprint"):
        lib_id = fp.value(1)
        if lib_id:
            out.append(Usage(lib_id, property_value(fp, "Reference"), path.name))
    return out


def resolve_model_path(raw: str, cfg: Config) -> tuple[Path | None, str]:
    """Expand ``${VAR}`` against ``[model_paths]``, then the environment; ``${KIPRJMOD}`` is the project root."""
    unresolved: list[str] = []

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if name == "KIPRJMOD":
            return str(cfg.root)
        if name in cfg.model_vars:
            return cfg.model_vars[name]
        if name in os.environ:
            return os.environ[name]
        unresolved.append(name)
        return m.group(0)

    expanded = VAR_RE.sub(repl, raw)
    if unresolved:
        return None, f"unresolved path variable ${{{unresolved[0]}}}"
    p = Path(expanded.replace("\\", "/")).expanduser()
    if not p.is_absolute():
        p = cfg.root / p
    return p, ""


def scan_models(footprint_files: list[tuple[str, Path]], cfg: Config) -> tuple[list[ModelRef], list[str]]:
    """Every ``(model …)`` reference in the library footprints, resolved and checked."""
    refs: list[ModelRef] = []
    without: list[str] = []
    for lib_id, path in footprint_files:
        try:
            _, root = parse_file(path)
        except SexpError:
            continue
        models = root.children("model")
        if not models:
            without.append(lib_id)
            continue
        for model in models:
            raw = model.value(1)
            if not raw:
                continue
            resolved, note = resolve_model_path(raw, cfg)
            if resolved is None:
                refs.append(ModelRef(lib_id, raw, None, False, note))
            elif resolved.exists():
                refs.append(ModelRef(lib_id, raw, resolved, True))
            else:
                # KiCad accepts a .step reference backed by a .wrl file and vice versa;
                # say so when a sibling exists, since that is a common slip.
                sibling = next(
                    (resolved.with_suffix(e) for e in cfg.model_extensions if resolved.with_suffix(e).exists()), None
                )
                refs.append(ModelRef(lib_id, raw, resolved, False, f"but {sibling.name} exists" if sibling else ""))
    return refs, without


def build_scan(cfg: Config) -> Scan:
    scan = Scan()
    for entry in cfg.symbol_libraries:
        scan.symbol_inventory |= symbol_inventory(entry, scan.warnings)
    for entry in cfg.footprint_libraries:
        scan.footprint_inventory |= footprint_inventory(entry, scan.warnings)
    scan.symbol_usage = scan_schematic(cfg.schematic, scan.warnings)
    scan.footprint_usage = scan_board(cfg.board, scan.warnings)
    footprint_files = [
        (f"{entry.nickname}:{f.stem}", f)
        for entry in cfg.footprint_libraries
        if entry.path.is_dir()
        for f in sorted(entry.path.glob("*.kicad_mod"))
    ]
    scan.models, scan.footprints_without_model = scan_models(footprint_files, cfg)
    return scan


def counts(usages: list[Usage]) -> dict[str, list[Usage]]:
    out: dict[str, list[Usage]] = defaultdict(list)
    for u in usages:
        out[u.lib_id].append(u)
    return out
