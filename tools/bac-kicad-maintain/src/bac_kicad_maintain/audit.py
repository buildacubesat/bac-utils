# SPDX-License-Identifier: MIT
"""The library audit: what the central KiCad library holds, what uses it, and what is broken.

:func:`load_repository` reads the symbol library, the ``.pretty`` footprints,
the ``3d/`` model names and the design blocks under the library root, every
board and sheet under the repository root (projects, templates, generated
boards) with their lib tables, and the ``footprint`` column of the catalog
CSV files. :func:`audit` turns that into findings: unused footprints and
models, broken links, footprint fields that disagree with the symbols that
use them, symbols whose ``#unused`` prefix disagrees with their placements.
:func:`plan_renames` is what ``apply --audit`` performs – the ``#unused``
prefix on unused files and the references inside unused symbols and
footprints that follow.

The rule for "used" (decided 2026-10-29): a footprint is used when anything
live references it – a library symbol without the ``#unused`` prefix (its
default ``Footprint``), a placed symbol or a board footprint anywhere in the
repository, a design block, or a catalog row. ``ki_fp_filters`` patterns do
not count. A model is used when a used footprint, or a footprint embedded in
a board, points at it.
"""

from __future__ import annotations

import csv
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from bac_common.errors import BacError, UsageError
from bac_common.sexp import Node, SexpError, parse_file, quoted

from .maintain import SKIP_DIRS, Patches

__all__ = [
    "UNUSED_SYMBOL",
    "UNUSED_FILE",
    "LIB_VAR",
    "Finding",
    "Repository",
    "Report",
    "Rename",
    "load_repository",
    "audit",
    "plan_renames",
    "rel",
]

UNUSED_SYMBOL = "#unused "
UNUSED_FILE = "#unused-"
LIB_VAR = "BAC_LIB_DIR"
COMPARED_FIELDS = ("Datasheet", "Description")
STANDARD_FOOTPRINT_FIELDS = {"Reference", "Value", "Datasheet", "Description", "Footprint"}
SYMBOL_SUFFIX = ".kicad_sym"
FOOTPRINT_SUFFIX = ".kicad_mod"
MODEL_SUFFIXES = (".step", ".stp", ".wrl", ".wrz")
PROJECT_SUFFIX = ".kicad_pro"
_VAR_RE = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


class AuditError(BacError):
    """A library or project file the audit cannot read as expected."""


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Symbol:
    name: str
    properties: dict[str, str]
    node: Node

    @property
    def unused(self) -> bool:
        return self.name.startswith(UNUSED_SYMBOL)

    @property
    def footprint(self) -> str:
        return self.properties.get("Footprint", "")


@dataclass(slots=True)
class Footprint:
    name: str
    path: Path
    text: str
    root: Node
    properties: dict[str, str]
    models: list[str]

    @property
    def unused(self) -> bool:
        return self.name.startswith(UNUSED_FILE) or self.path.name.startswith(UNUSED_FILE)


@dataclass(slots=True)
class Document:
    """A board or sheet: where it is, which lib nicknames its own project's tables define."""

    path: Path
    root: Node
    kind: str  # "board", "sheet", "block"
    project: Path | None  # the folder with the .kicad_pro, None for a file outside any project
    own_footprint_libs: set[str]  # central-library nicknames in the project's fp-lib-table
    own_symbol_libs: set[str]
    missing_libs: list[tuple[str, str, str]]  # (table, nickname, uri) for entries pointing at nothing


@dataclass(slots=True)
class Repository:
    root: Path
    library: Path
    symbol_file: Path | None
    pretty: Path | None
    symbols: dict[str, Symbol]
    footprints: dict[str, Footprint]
    models: dict[str, Path]  # path relative to the library root, posix
    documents: list[Document]
    catalog_footprints: dict[str, list[str]]  # footprint reference -> catalog row ids
    catalogs: list[Path]
    footprint_libs: set[str] = field(default_factory=set)  # every nickname some project resolves to the .pretty
    symbol_libs: set[str] = field(default_factory=set)  # … to the symbol library
    symbol_text: str = ""
    symbol_root: Node | None = None


@dataclass(slots=True)
class Finding:
    kind: str
    subject: str
    detail: str
    where: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "subject": self.subject, "detail": self.detail, "where": self.where}


@dataclass(slots=True)
class Report:
    unused_footprints: list[Finding] = field(default_factory=list)
    unused_models: list[Finding] = field(default_factory=list)
    broken_links: list[Finding] = field(default_factory=list)
    field_mismatches: list[Finding] = field(default_factory=list)
    symbols: list[Finding] = field(default_factory=list)
    libraries: list[Finding] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def sections(self) -> list[tuple[str, list[Finding]]]:
        return [
            ("unused footprints", self.unused_footprints),
            ("unused models", self.unused_models),
            ("broken links", self.broken_links),
            ("field mismatches", self.field_mismatches),
            ("symbols", self.symbols),
            ("libraries", self.libraries),
        ]

    @property
    def total(self) -> int:
        return sum(len(items) for _, items in self.sections())


@dataclass(slots=True)
class Rename:
    """One file to move, with the edited content that goes to the new name."""

    path: Path
    new_path: Path
    text: str | None  # None: move the bytes unchanged (a model)
    original: str | None
    reason: str


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _properties(node: Node) -> dict[str, str]:
    out: dict[str, str] = {}
    for prop in node.children("property"):
        atoms = prop.atoms()
        if len(atoms) >= 3:
            out.setdefault(atoms[1].value, atoms[2].value)
    return out


def _walk_files(base: Path, suffixes: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    for directory, names, files in os.walk(base, followlinks=False):
        parent = Path(directory)
        names[:] = sorted(n for n in names if n not in SKIP_DIRS and not n.endswith("-backups"))
        for name in sorted(files):
            path = parent / name
            if path.suffix.lower() in suffixes and not path.is_symlink() and not name.startswith(("~", "_autosave")):
                found.append(path)
    return found


def _read_symbols(path: Path) -> tuple[str, Node, dict[str, Symbol]]:
    text, root = parse_file(path)
    if root.head != "kicad_symbol_lib":
        raise AuditError(f"{path}: not a symbol library (the file starts with ({root.head} …)).")
    symbols: dict[str, Symbol] = {}
    for node in root.children("symbol"):
        name = node.value(1)
        if not name:
            raise AuditError(f"{path}: a symbol has no name.")
        symbols[name] = Symbol(name, _properties(node), node)
    return text, root, symbols


def _read_footprint(path: Path) -> Footprint:
    text, root = parse_file(path)
    if root.head != "footprint":
        raise AuditError(f"{path}: not a footprint (the file starts with ({root.head} …)).")
    models = [m.value(1) for m in root.children("model") if m.value(1)]
    return Footprint(root.value(1), path, text, root, _properties(root), models)


def _expand(uri: str, library: Path) -> Path | None:
    """A lib-table or model path with ``${BAC_LIB_DIR}`` expanded; ``None`` when another variable is in it."""
    other = [m.group(1) for m in _VAR_RE.finditer(uri) if m.group(1) != LIB_VAR]
    if other:
        return None
    expanded = uri.replace("${" + LIB_VAR + "}", library.as_posix())
    return Path(expanded)


def _same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def _read_table(path: Path, library: Path, target: Path | None) -> tuple[set[str], list[tuple[str, str, str]]]:
    """Nicknames of a lib table that resolve to ``target``; ``(table, nickname, uri)`` for BAC paths that are gone."""
    central: set[str] = set()
    missing: list[tuple[str, str, str]] = []
    if not path.is_file():
        return central, missing
    try:
        _, root = parse_file(path)
    except SexpError as exc:
        raise AuditError(f"{path}: {exc.message}") from None
    for lib in root.children("lib"):
        name = lib.child("name")
        uri = lib.child("uri")
        if name is None or uri is None:
            continue
        nickname, where = name.value(1), uri.value(1)
        resolved = _expand(where, library)
        if resolved is None:
            continue  # another environment variable: not ours to check
        if not resolved.exists():
            if "${" + LIB_VAR + "}" in where:
                missing.append((path.name, nickname, where))
            continue
        if target is not None and _same(resolved, target):
            central.add(nickname)
    return central, missing


def _read_catalogs(paths: list[Path]) -> tuple[dict[str, list[str]], list[Path]]:
    refs: dict[str, list[str]] = defaultdict(list)
    files: list[Path] = []
    for folder in paths:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.csv")):
            try:
                with path.open(encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    if not reader.fieldnames or "footprint" not in reader.fieldnames:
                        continue
                    files.append(path)
                    for row in reader:
                        ref = (row.get("footprint") or "").strip()
                        if ref:
                            refs[ref].append(f"{path.name}:{row.get('id') or '?'}")
            except (OSError, csv.Error) as exc:
                raise AuditError(f"{path}: {exc}") from None
    return dict(refs), files


def load_repository(root: Path, library: Path, catalogs: list[Path]) -> Repository:
    """Read everything the audit looks at. ``library`` and ``catalogs`` are resolved against ``root`` when relative."""
    root = root.expanduser()
    if not root.is_dir():
        raise UsageError(f"Not a directory: {root}")
    library = library if library.is_absolute() else root / library
    if not library.is_dir():
        raise UsageError(
            f"No library folder at {library}.", "Set [audit] library to the folder with symbols/ and footprints/."
        )
    catalogs = [c if c.is_absolute() else root / c for c in catalogs]

    symbol_files = _walk_files(library, (SYMBOL_SUFFIX,))
    if len(symbol_files) > 1:
        raise UsageError(
            "More than one symbol library under " + str(library) + ".", ", ".join(p.name for p in symbol_files)
        )
    symbol_file = symbol_files[0] if symbol_files else None
    symbol_text, symbol_root, symbols = _read_symbols(symbol_file) if symbol_file else ("", None, {})

    pretties = sorted(
        {p.parent for p in _walk_files(library, (FOOTPRINT_SUFFIX,)) if p.parent.name.endswith(".pretty")}
    )
    if len(pretties) > 1:
        raise UsageError(
            "More than one .pretty folder under " + str(library) + ".", ", ".join(p.name for p in pretties)
        )
    pretty = pretties[0] if pretties else None
    footprints: dict[str, Footprint] = {}
    if pretty:
        for path in sorted(pretty.glob("*" + FOOTPRINT_SUFFIX)):
            fp = _read_footprint(path)
            footprints[path.stem] = fp

    models: dict[str, Path] = {}
    for path in _walk_files(library, MODEL_SUFFIXES):
        if ".pretty" in path.parts or ".kicad_blocks" in path.parts:
            continue
        models[path.relative_to(library).as_posix()] = path

    documents: list[Document] = []
    union_fp: set[str] = set()
    union_sym: set[str] = set()
    tables: dict[Path, tuple[set[str], set[str], list[tuple[str, str, str]]]] = {}
    projects = {p.parent for p in _walk_files(root, (PROJECT_SUFFIX,))}
    for project in sorted(projects):
        fp_central, fp_missing = _read_table(project / "fp-lib-table", library, pretty)
        sym_central, sym_missing = _read_table(project / "sym-lib-table", library, symbol_file)
        tables[project] = (fp_central, sym_central, fp_missing + sym_missing)
        union_fp |= fp_central
        union_sym |= sym_central
    for path in _walk_files(root, (".kicad_pcb", ".kicad_sch")):
        if path.suffix == ".kicad_sch" and path.parent.name.endswith(".kicad_block"):
            kind = "block"
        elif path.suffix == ".kicad_pcb":
            kind = "board"
        else:
            kind = "sheet"
        project = next((p for p in sorted(projects, key=lambda q: -len(q.parts)) if path.is_relative_to(p)), None)
        fp_libs, sym_libs, missing = tables[project] if project is not None else (set(), set(), [])
        try:
            _, node = parse_file(path)
        except SexpError as exc:
            raise AuditError(f"{path}: {exc.message}") from None
        documents.append(Document(path, node, kind, project, set(fp_libs), set(sym_libs), list(missing)))

    catalog_refs, catalog_files = _read_catalogs(catalogs)
    return Repository(
        root=root,
        library=library,
        symbol_file=symbol_file,
        pretty=pretty,
        symbols=symbols,
        footprints=footprints,
        models=models,
        documents=documents,
        catalog_footprints=catalog_refs,
        catalogs=catalog_files,
        footprint_libs=union_fp,
        symbol_libs=union_sym,
        symbol_text=symbol_text,
        symbol_root=symbol_root,
    )


# ---------------------------------------------------------------------------
# The audit
# ---------------------------------------------------------------------------


def _split(reference: str) -> tuple[str, str]:
    nickname, _, name = reference.partition(":")
    return (nickname, name) if name else ("", reference)


def rel(repo: Repository, path: Path) -> str:
    """``path`` relative to the repository root, as text."""
    try:
        return path.relative_to(repo.root).as_posix()
    except ValueError:
        return str(path)


def _model_key(repo: Repository, raw: str) -> str | None:
    """The model's path relative to the library root, or ``None`` for a path outside it."""
    expanded = _expand(raw, repo.library)
    if expanded is None:
        return None
    try:
        return expanded.resolve().relative_to(repo.library.resolve()).as_posix()
    except ValueError:
        return None


def audit(repo: Repository) -> Report:
    report = Report()
    fp_users: dict[str, list[str]] = defaultdict(list)  # footprint stem -> who uses it (live)
    fp_dead_users: dict[str, list[str]] = defaultdict(list)  # referenced only by #unused symbols
    sym_placed: dict[str, list[str]] = defaultdict(list)
    model_users: dict[str, list[str]] = defaultdict(list)
    central_fp_names = set(repo.footprints)
    seen_missing: set[tuple[Path, str, str]] = set()
    seen_foreign: set[tuple[Path, str, str]] = set()

    # Library symbols: their default footprint.
    for sym in sorted(repo.symbols.values(), key=lambda s: s.name):
        ref = sym.footprint
        if not ref:
            continue
        nickname, name = _split(ref)
        if nickname and not _is_central_fp(repo, nickname):
            continue
        if not nickname and name not in central_fp_names:
            continue
        if name not in central_fp_names:
            report.broken_links.append(Finding("symbol footprint", sym.name, _missing_fp(repo, ref, name), ""))
            continue
        (fp_dead_users if sym.unused else fp_users)[name].append(f"symbol {sym.name}")

    # Boards, sheets, design blocks. A nickname counts when any project's table resolves it to the central
    # library: the rule says "anywhere", and a board that uses a nickname its own table lacks is reported.
    for doc in repo.documents:
        where = rel(repo, doc.path)
        project = doc.project or doc.path.parent
        for table, nickname, uri in doc.missing_libs:
            key = (project, table, nickname)
            if key not in seen_missing:
                seen_missing.add(key)
                report.libraries.append(
                    Finding("library missing", nickname, f"{table} points at {uri}", rel(repo, project))
                )

        if doc.kind == "board":
            for fp in doc.root.children("footprint"):
                ref = fp.value(1)
                nickname, name = _split(ref)
                reference = _properties(fp).get("Reference", "?")
                if nickname in repo.footprint_libs or (not nickname and name in central_fp_names):
                    _foreign(repo, report, seen_foreign, doc, nickname, doc.own_footprint_libs, "fp-lib-table")
                    if name in central_fp_names:
                        fp_users[name].append(f"{where} {reference}")
                    else:
                        report.broken_links.append(
                            Finding("board footprint", f"{reference} {ref}", _missing_fp(repo, ref, name), where)
                        )
                for model in fp.children("model"):
                    key = _model_key(repo, model.value(1))
                    if key is None:
                        continue
                    if key in repo.models:
                        model_users[key].append(f"{where} {reference}")
                    else:
                        detail = _missing_model(repo, model.value(1), key)
                        report.broken_links.append(
                            Finding("board model", f"{reference} {model.value(1)}", detail, where)
                        )
            continue
        for sym in doc.root.children("symbol"):
            lib_id = sym.child("lib_id")
            ref = lib_id.value(1) if lib_id else ""
            props = _properties(sym)
            reference = props.get("Reference", "?")
            nickname, name = _split(ref)
            if nickname in repo.symbol_libs:
                _foreign(repo, report, seen_foreign, doc, nickname, doc.own_symbol_libs, "sym-lib-table")
                if name in repo.symbols:
                    sym_placed[name].append(f"{where} {reference}")
                else:
                    twin = UNUSED_SYMBOL + name
                    detail = (
                        f"the library has it as {twin!r}" if twin in repo.symbols else "no such symbol in the library"
                    )
                    report.broken_links.append(Finding("placed symbol", f"{reference} {ref}", detail, where))
            fp_ref = props.get("Footprint", "")
            if not fp_ref:
                continue
            fnick, fname = _split(fp_ref)
            if fnick in repo.footprint_libs or (not fnick and fname in central_fp_names):
                _foreign(repo, report, seen_foreign, doc, fnick, doc.own_footprint_libs, "fp-lib-table")
                if fname in central_fp_names:
                    fp_users[fname].append(f"{where} {reference}")
                else:
                    report.broken_links.append(
                        Finding("sheet footprint", f"{reference} {fp_ref}", _missing_fp(repo, fp_ref, fname), where)
                    )

    # Catalog rows.
    for ref, rows in sorted(repo.catalog_footprints.items()):
        nickname, name = _split(ref)
        if not _is_central_fp(repo, nickname):
            continue
        if name in central_fp_names:
            fp_users[name].extend(f"catalog {r}" for r in rows)
        else:
            report.broken_links.append(
                Finding("catalog footprint", ref, _missing_fp(repo, ref, name), ", ".join(rows[:3]))
            )

    # Footprints: usage, models, fields.
    for stem, fp in sorted(repo.footprints.items()):
        if fp.name != stem:
            report.libraries.append(
                Finding("footprint name", fp.path.name, f"the name inside the file is {fp.name!r}", "")
            )
        users = fp_users.get(stem, [])
        for raw in fp.models:
            key = _model_key(repo, raw)
            if key is None:
                continue
            if key not in repo.models:
                report.broken_links.append(Finding("footprint model", stem, _missing_model(repo, raw, key), ""))
            elif users:  # a footprint nothing uses keeps no model alive, prefixed or not
                model_users[key].append(f"footprint {stem}")
        if not users and not fp.unused:
            dead = fp_dead_users.get(stem, [])
            detail = "referenced by " + ", ".join(dead) + " only" if dead else "nothing references it"
            report.unused_footprints.append(Finding("unused footprint", stem, detail, ""))
        elif users and fp.unused:
            report.libraries.append(Finding("#unused footprint in use", stem, "used by " + ", ".join(users[:4]), ""))
        if fp.unused:
            continue  # a parked footprint's fields are nobody's concern until it comes back
        extra = sorted(set(fp.properties) - STANDARD_FOOTPRINT_FIELDS)
        if extra:
            report.field_mismatches.append(
                Finding("nonstandard field", stem, "footprint carries " + ", ".join(repr(e) for e in extra), "")
            )
        descr = fp.root.child("descr")
        description = fp.properties.get("Description", "")
        if descr is not None and descr.value(1) != description:
            detail = f"(descr …) {descr.value(1)!r} differs from the Description property {description!r}"
            report.field_mismatches.append(Finding("descr", stem, detail, ""))

    # Symbol fields against their footprint. Description is compared only where the footprint
    # belongs to one symbol: a generic footprint (R-0603 under every resistor) describes the package.
    live_by_fp: dict[str, int] = defaultdict(int)
    for sym in repo.symbols.values():
        if not sym.unused:
            live_by_fp[_split(sym.footprint)[1]] += 1
    for sym in sorted(repo.symbols.values(), key=lambda s: s.name):
        if sym.unused:
            continue
        nickname, name = _split(sym.footprint)
        if not sym.footprint or not _is_central_fp(repo, nickname) or name not in repo.footprints:
            continue
        fp = repo.footprints[name]
        for key in COMPARED_FIELDS:
            if key == "Description" and live_by_fp[name] > 1:
                continue
            mine, theirs = sym.properties.get(key, ""), fp.properties.get(key, "")
            if mine != theirs:
                report.field_mismatches.append(
                    Finding(key, name, f"symbol {sym.name!r}: {mine!r}; footprint: {theirs!r}", "")
                )

    # Models.
    for key in sorted(repo.models):
        if key not in model_users and not Path(key).name.startswith(UNUSED_FILE):
            report.unused_models.append(Finding("unused model", key, "no used footprint or board points at it", ""))

    # Symbols whose prefix disagrees with their placements.
    for sym in sorted(repo.symbols.values(), key=lambda s: s.name):
        placed = sym_placed.get(sym.name, [])
        if sym.unused and placed:
            report.symbols.append(Finding("#unused symbol placed", sym.name, "placed on " + ", ".join(placed[:4]), ""))
        elif not sym.unused and not placed:
            report.symbols.append(
                Finding("symbol not placed", sym.name, "no sheet, template or design block places it", "")
            )

    report.counts = {
        "symbols": len(repo.symbols),
        "symbols #unused": sum(s.unused for s in repo.symbols.values()),
        "footprints": len(repo.footprints),
        "footprints #unused": sum(f.unused for f in repo.footprints.values()),
        "models": len(repo.models),
        "boards": sum(d.kind == "board" for d in repo.documents),
        "sheets": sum(d.kind == "sheet" for d in repo.documents),
        "design blocks": sum(d.kind == "block" for d in repo.documents),
        "catalog files": len(repo.catalogs),
    }
    return report


def _missing_fp(repo: Repository, ref: str, name: str) -> str:
    """Why a footprint reference resolves to nothing, naming a ``#unused-`` twin when there is one."""
    if UNUSED_FILE + name in repo.footprints:
        return f"the library has it as {UNUSED_FILE + name!r}"
    if name.startswith(UNUSED_FILE) and name[len(UNUSED_FILE) :] in repo.footprints:
        return f"the library has it as {name[len(UNUSED_FILE) :]!r} (no longer prefixed)"
    return f"{ref!r} is not in the library"


def _foreign(
    repo: Repository,
    report: Report,
    seen: set[tuple[Path, str, str]],
    doc: Document,
    nickname: str,
    own: set[str],
    table: str,
) -> None:
    """A board or sheet that uses a central-library nickname its own project's table does not define."""
    if doc.project is None or nickname in own or (doc.project, table, nickname) in seen:
        return
    seen.add((doc.project, table, nickname))
    detail = f"used by {doc.path.name}; {table} does not define it"
    report.libraries.append(Finding("nickname not in table", nickname, detail, rel(repo, doc.project)))


def _is_central_fp(repo: Repository, nickname: str) -> bool:
    """Whether a nickname names the central footprint library in any project of the repository."""
    return bool(nickname) and nickname in repo.footprint_libs


def _missing_model(repo: Repository, raw: str, key: str) -> str:
    name = Path(key).name
    twin = (Path(key).parent / (UNUSED_FILE + name)).as_posix()
    if twin in repo.models:
        return f"the library has it as {Path(twin).name!r}"
    if name.startswith(UNUSED_FILE) and (Path(key).parent / name[len(UNUSED_FILE) :]).as_posix() in repo.models:
        return f"the library has it as {name[len(UNUSED_FILE) :]!r} (no longer prefixed)"
    return f"{raw} is not in the library"


# ---------------------------------------------------------------------------
# Renames for apply
# ---------------------------------------------------------------------------


def plan_renames(repo: Repository, report: Report) -> tuple[list[Rename], str | None]:
    """The files ``apply --audit`` moves and the symbol library text with the references that follow.

    Unused footprints get the ``#unused-`` prefix on the file and on the
    name inside it; unused models get it on the file, and the unused
    footprints that point at them follow; ``#unused`` symbols whose default
    footprint is renamed follow in the symbol library. Returns the renames
    and the new symbol-library text (``None`` when it does not change).
    """
    renames: list[Rename] = []
    fp_new: dict[str, str] = {}  # old stem -> new stem
    for finding in report.unused_footprints:
        if UNUSED_FILE + finding.subject in repo.footprints:
            report.libraries.append(
                Finding(
                    "twin",
                    finding.subject,
                    f"unused, but {UNUSED_FILE + finding.subject!r} exists too; merge by hand",
                    "",
                )
            )
            continue
        fp_new[finding.subject] = UNUSED_FILE + finding.subject
    model_new: dict[str, str] = {}  # key -> new key
    for finding in report.unused_models:
        path = Path(finding.subject)
        new_key = (path.parent / (UNUSED_FILE + path.name)).as_posix()
        if new_key in repo.models:
            report.libraries.append(
                Finding("twin", finding.subject, f"unused, but {Path(new_key).name!r} exists too; merge by hand", "")
            )
            continue
        model_new[finding.subject] = new_key

    for stem, fp in sorted(repo.footprints.items()):
        patches = Patches(fp.text)
        new_stem = fp_new.get(stem)
        if new_stem:
            patches.replace(fp.root.atoms()[1], quoted(new_stem))
        for model in fp.root.children("model"):
            key = _model_key(repo, model.value(1))
            if key in model_new:
                head, _, tail = model.value(1).rpartition("/")
                if tail != Path(key).name:  # a path spelled through "." or ".." – left alone, reported
                    report.libraries.append(Finding("model path", stem, f"{model.value(1)} is not renamed", ""))
                    continue
                patches.replace(model.atoms()[1], quoted(f"{head}/{UNUSED_FILE}{tail}"))
        if not patches.count:
            continue
        text = patches.render()
        new_path = fp.path.with_name((new_stem or stem) + FOOTPRINT_SUFFIX)
        reason = "unused footprint" if new_stem else "its model was renamed"
        renames.append(Rename(fp.path, new_path, text, fp.text, reason))

    for key, new_key in sorted(model_new.items()):
        path = repo.models[key]
        renames.append(Rename(path, repo.library / new_key, None, None, "unused model"))

    symbol_text: str | None = None
    if repo.symbol_root is not None:
        patches = Patches(repo.symbol_text)
        for sym in repo.symbols.values():
            if not sym.unused:
                continue  # a live symbol on a missing footprint is a broken link for a person, not a rename
            nickname, name = _split(sym.footprint)
            twin_only = name not in repo.footprints and UNUSED_FILE + name in repo.footprints
            if (name in fp_new or twin_only) and _is_central_fp(repo, nickname):
                prop = next(p for p in sym.node.children("property") if p.value(1) == "Footprint")
                patches.replace(prop.atoms()[2], quoted(f"{nickname}:{fp_new.get(name, UNUSED_FILE + name)}"))
        if patches.count:
            symbol_text = patches.render()
    return renames, symbol_text
