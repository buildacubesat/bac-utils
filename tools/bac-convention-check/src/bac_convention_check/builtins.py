# SPDX-License-Identifier: MIT
"""Analyses that need structure rather than a regex.

Each function takes the rule, the file index and the pre-selected files and
returns ``(hits, notes)``. Register new ones in :data:`BUILTINS` and refer to
them from a rule with ``kind = "builtin"`` and ``builtin = "<name>"``.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterator

from .engine import BuiltinFn, FileIndex, Hit
from .rules import Rule

# ---------------------------------------------------------------------------
# pyproject.toml conventions (BAC Project & Tooling Guide §2.1, §3.10)
# ---------------------------------------------------------------------------


def _pyprojects(index: FileIndex, files: list[str]) -> Iterator[tuple[str, dict]]:
    for rel in files:
        if rel.rsplit("/", 1)[-1] != "pyproject.toml":
            continue
        lines = index.lines(rel)
        if lines is None:
            continue
        try:
            data = tomllib.loads("\n".join(lines))
        except tomllib.TOMLDecodeError as exc:
            yield rel, {"__error__": str(exc)}
            continue
        yield rel, data


def _project_table(data: dict) -> dict | None:
    """The ``[project]`` table, or None for a workspace root that only ties members together."""
    project = data.get("project")
    return project if isinstance(project, dict) else None


def pyproject_license(rule: Rule, index: FileIndex, files: list[str]) -> tuple[list[Hit], list[str]]:
    hits: list[Hit] = []
    for rel, data in _pyprojects(index, files):
        if "__error__" in data:
            hits.append(Hit(rel, 0, f"not valid TOML: {data['__error__']}"))
            continue
        project = _project_table(data)
        if project is None:
            continue
        lic = project.get("license")
        value = lic.get("text") if isinstance(lic, dict) else lic
        if value is None:
            hits.append(Hit(rel, 0, 'no license field; add license = { text = "MIT" }'))
        elif str(value).strip().upper() != "MIT":
            hits.append(Hit(rel, 0, f"license is {value!r}; BAC software is MIT"))
    return hits, []


def pyproject_license_form(rule: Rule, index: FileIndex, files: list[str]) -> tuple[list[Hit], list[str]]:
    hits: list[Hit] = []
    for rel, data in _pyprojects(index, files):
        project = _project_table(data)
        if project is None or "__error__" in data:
            continue
        lic = project.get("license")
        if isinstance(lic, str):
            hits.append(Hit(rel, 0, f'license = "{lic}" – the guide uses the table form license = {{ text = "MIT" }}'))
    return hits, []


_PY_MIN_RE = re.compile(r">=\s*3\.(\d+)")


def pyproject_python(rule: Rule, index: FileIndex, files: list[str]) -> tuple[list[Hit], list[str]]:
    hits: list[Hit] = []
    for rel, data in _pyprojects(index, files):
        project = _project_table(data)
        if project is None or "__error__" in data:
            continue
        spec = str(project.get("requires-python", ""))
        m = _PY_MIN_RE.search(spec)
        if not spec:
            hits.append(Hit(rel, 0, 'no requires-python; the guide needs ">=3.11"'))
        elif not m or int(m.group(1)) < 11:
            hits.append(Hit(rel, 0, f"requires-python = {spec!r}; the guide needs >=3.11"))
    return hits, []


def pyproject_backend(rule: Rule, index: FileIndex, files: list[str]) -> tuple[list[Hit], list[str]]:
    hits: list[Hit] = []
    for rel, data in _pyprojects(index, files):
        project = _project_table(data)
        if project is None or "__error__" in data:
            continue
        backend = str(data.get("build-system", {}).get("build-backend", ""))
        if backend != "hatchling.build":
            hits.append(Hit(rel, 0, f"build backend is {backend or 'missing'!r}; the guide uses hatchling"))
    return hits, []


_UPPER_BOUND_RE = re.compile(r"(<=?|==|~=)\s*\d")
_ANY_BOUND_RE = re.compile(r"[<>=~!]")
_DEP_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def pyproject_pins(rule: Rule, index: FileIndex, files: list[str]) -> tuple[list[Hit], list[str]]:
    hits: list[Hit] = []
    for rel, data in _pyprojects(index, files):
        project = _project_table(data)
        if project is None or "__error__" in data:
            continue
        deps: list[str] = list(project.get("dependencies", []))
        for group in (project.get("optional-dependencies") or {}).values():
            deps.extend(group)
        for dep in deps:
            name = (_DEP_NAME_RE.match(dep) or [None, dep])[1]
            spec = dep[len(name) :] if dep.startswith(name) else dep
            if _UPPER_BOUND_RE.search(spec):
                hits.append(Hit(rel, 0, f"{dep}: upper bound or exact pin; the guide pins minimums only"))
            elif not _ANY_BOUND_RE.search(spec):
                hits.append(Hit(rel, 0, f"{dep}: no minimum version bound"))
    return hits, []


def pyproject_name(rule: Rule, index: FileIndex, files: list[str]) -> tuple[list[Hit], list[str]]:
    hits: list[Hit] = []
    for rel, data in _pyprojects(index, files):
        project = _project_table(data)
        if project is None or "__error__" in data:
            continue
        name = str(project.get("name", ""))
        if not name.startswith("bac-"):
            hits.append(Hit(rel, 0, f"project name {name!r} lacks the bac- prefix"))
        elif name != name.lower():
            hits.append(Hit(rel, 0, f"project name {name!r} is not lowercase"))
    return hits, []


_ENTRY_RE = re.compile(r"^bac_[a-z0-9_]+(\.[a-z0-9_]+)*\.cli:main$")


def pyproject_scripts(rule: Rule, index: FileIndex, files: list[str]) -> tuple[list[Hit], list[str]]:
    hits: list[Hit] = []
    for rel, data in _pyprojects(index, files):
        project = _project_table(data)
        if project is None or "__error__" in data:
            continue
        for script, target in (project.get("scripts") or {}).items():
            if not script.startswith("bac-"):
                hits.append(Hit(rel, 0, f"script {script!r} lacks the bac- prefix"))
            if not _ENTRY_RE.match(str(target)):
                hits.append(Hit(rel, 0, f"script {script} = {target!r}; the guide's shape is bac_toolname.cli:main"))
    return hits, []


# ---------------------------------------------------------------------------
# Firmware review heuristics (bac-software / bac-hardware)
# ---------------------------------------------------------------------------

_SOURCE_GLOBS = ("*.h", "*.c", "*.hpp", "*.cpp", "Kconfig*")


def prefix_inventory(rule: Rule, index: FileIndex, files: list[str]) -> tuple[list[Hit], list[str]]:
    """BAC_ versus ROCI_ identifier prefixes: an unsettled decision, reported as an inventory."""
    bac_re = re.compile(r"\bBAC_[A-Z0-9_]+")
    roci_re = re.compile(r"\bROCI_[A-Z0-9_]+")
    bac = 0
    roci_hits: list[Hit] = []
    for rel in index.select(_SOURCE_GLOBS):
        if rel not in files:
            continue
        lines = index.lines(rel)
        if lines is None:
            continue
        for no, line in enumerate(lines, start=1):
            bac += len(bac_re.findall(line))
            if roci_re.search(line):
                roci_hits.append(Hit(rel, no, line.strip()))
    notes = [f"BAC_ prefixed occurrences: {bac}", f"ROCI_ prefixed occurrences: {len(roci_hits)}"]
    if bac and roci_hits:
        notes.append("both prefixes are in use; the decision is still accumulating precedent")
        return roci_hits, notes
    return [], notes


_TRANSCEIVER_RE = re.compile(r"\b(TCAN[0-9]{3,4}|TJA10[0-9]{2}|MCP254[0-9]FD|ISO10[0-9]{2}|SN65HVD[0-9]{3})\b", re.I)


def transceiver_families(rule: Rule, index: FileIndex, files: list[str]) -> tuple[list[Hit], list[str]]:
    """More than one CAN transceiver family named means at least one reference is stale."""
    hits: list[Hit] = []
    families: set[str] = set()
    for rel in files:
        lines = index.lines(rel)
        if lines is None:
            continue
        for no, line in enumerate(lines, start=1):
            found = _TRANSCEIVER_RE.findall(line)
            if found:
                families.update(f.upper() for f in found)
                hits.append(Hit(rel, no, line.strip()))
    if not families:
        return [], []
    notes = [f"transceiver parts named: {' '.join(sorted(families))}"]
    if len(families) > 1:
        notes.append("more than one family present; at least one is likely stale")
        return hits, notes
    return [], notes


_PART_RE = re.compile(
    r"\b(ADS[0-9]{4}|INA[0-9]{3}|TMP[0-9]{4}|BNO[0-9]{3}|MCP[0-9]{4,6}|TPS[0-9A-Z]{5,7}|STM32F4[0-9]{2}|TCAN[0-9]{3,4})\b",
    re.I,
)
_DOC_GLOBS = ("*.md", "*.rst", "*.txt")
_HW_GLOBS = ("*.dts", "*.dtsi", "*.overlay", "Kconfig*", "*.conf", "*.c", "*.h", "*.repl")


def orphan_parts(rule: Rule, index: FileIndex, files: list[str]) -> tuple[list[Hit], list[str]]:
    """Parts named in documentation but absent from devicetree, Kconfig and sources."""
    selected = set(files)
    first_seen: dict[str, Hit] = {}
    in_hw: set[str] = set()
    for rel in index.select(_DOC_GLOBS):
        if rel not in selected:
            continue
        lines = index.lines(rel)
        if lines is None:
            continue
        for no, line in enumerate(lines, start=1):
            for part in _PART_RE.findall(line):
                first_seen.setdefault(part.upper(), Hit(rel, no, f"{part.upper()}: {line.strip()}"))
    for rel in index.select(_HW_GLOBS):
        if rel not in selected:
            continue
        lines = index.lines(rel)
        if lines is None:
            continue
        for line in lines:
            in_hw.update(p.upper() for p in _PART_RE.findall(line))
    orphans = sorted(set(first_seen) - in_hw)
    if not orphans:
        return [], []
    notes = [
        "named in documentation but absent from devicetree, Kconfig and sources",
        "expect false positives for parts named as alternatives or comparisons",
    ]
    return [first_seen[p] for p in orphans], notes


BUILTINS: dict[str, BuiltinFn] = {
    "pyproject_license": pyproject_license,
    "pyproject_license_form": pyproject_license_form,
    "pyproject_python": pyproject_python,
    "pyproject_backend": pyproject_backend,
    "pyproject_pins": pyproject_pins,
    "pyproject_name": pyproject_name,
    "pyproject_scripts": pyproject_scripts,
    "prefix_inventory": prefix_inventory,
    "transceiver_families": transceiver_families,
    "orphan_parts": orphan_parts,
}
