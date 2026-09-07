# SPDX-License-Identifier: MIT
"""Loading, matching and merging of TOML field rules.

A rule file declares a ``target`` (``symbol``, ``footprint`` or
``schematic``), an optional file-level ``[match]`` block that selects which
items the file speaks to at all, and ``[[field]]`` entries (plus ``[[flag]]``
entries for schematics) that may narrow themselves further with ``when``
conditions. One directory of rule files serves every tool; each loads only
the targets it handles. Filename order is precedence order.

Lifted from ``bac_kicad_core.rules`` of bac-kicad-tools.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from bac_common.errors import ConfigError

__all__ = [
    "TARGETS",
    "FLAG_NAMES",
    "ALLOWED_AXES",
    "PROTECTED_FIELDS",
    "RuleError",
    "MatchContext",
    "FieldRule",
    "FlagRule",
    "RuleSet",
    "load_ruleset",
    "load_rules_dir",
    "rules_for",
    "flags_for",
]

TARGETS = ("symbol", "footprint", "schematic")

FLAG_NAMES = ("dnp", "in_bom", "on_board", "exclude_from_sim")

# Fields whose value lives in more than one place in the file format, so
# rewriting the property alone would desynchronise the document.
PROTECTED_FIELDS = {"schematic": {"Reference"}}

# Which [match] axes each target understands. Anything else is a config error
# rather than a silently ignored key.
ALLOWED_AXES = {
    "symbol": {"reference_prefixes", "libraries", "name_regex", "properties"},
    "footprint": {"libraries", "name_regex", "properties"},
    "schematic": {"lib_id_regex", "reference_regex", "sheet_regex", "name_regex", "properties"},
}


class RuleError(ConfigError):
    """A rule file is missing, malformed, or names things the target cannot have.

    Rules are inputs the user hands the tool, so this exits 2 like a usage error.
    """

    exit_code = 2


def _compile(expr: object, where: str) -> re.Pattern[str]:
    try:
        return re.compile(str(expr))
    except re.error as exc:
        raise RuleError(f"{where}: bad regex {expr!r}", str(exc)) from exc


def _compile_map(raw: object, where: str) -> dict[str, re.Pattern[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise RuleError(f"{where}: expected a table of property = regex pairs")
    return {str(k): _compile(v, where) for k, v in raw.items()}


@dataclass
class MatchContext:
    """What is known about the item currently under consideration."""

    target: str
    name: str = ""  # symbol/footprint name, or the name half of a lib_id
    library: str = ""  # library nickname or directory basename
    prefix: str = ""  # reference prefix, library symbols only
    properties: dict[str, str] = field(default_factory=dict)
    reference: str = ""  # schematic only, e.g. "R12"
    sheet: str = ""  # schematic only, sheet file name
    lib_id: str = ""  # schematic only, e.g. "BAC_Passives:R_0402_10k"


@dataclass
class _Conditions:
    """Entry-level narrowing, applied on top of the rule set's [match]."""

    when: dict[str, re.Pattern[str]] = field(default_factory=dict)
    when_name: re.Pattern[str] | None = None
    when_reference: re.Pattern[str] | None = None

    def matches(self, ctx: MatchContext) -> bool:
        if self.when_name is not None and not self.when_name.search(ctx.name):
            return False
        if self.when_reference is not None and not self.when_reference.search(ctx.reference):
            return False
        # A property the item does not carry can never match.
        return all(pattern.search(ctx.properties.get(key, "")) for key, pattern in self.when.items())


@dataclass
class FieldRule(_Conditions):
    name: str = ""
    value: str = ""
    hide: bool = True
    requires: list[str] = field(default_factory=list)
    layer: str = "F.Fab"  # footprints only
    size: float = 0.0  # 0 = the format default
    thickness: float = 0.0  # 0 = the format default
    overwrite: bool = False
    source: str = ""


@dataclass
class FlagRule(_Conditions):
    name: str = ""
    value: bool = True
    source: str = ""


@dataclass
class RuleSet:
    path: Path
    title: str
    target: str
    prefixes: list[str]
    libraries: list[str]
    name_patterns: list[re.Pattern[str]]
    property_patterns: dict[str, re.Pattern[str]]
    lib_id_patterns: list[re.Pattern[str]]
    reference_patterns: list[re.Pattern[str]]
    sheet_patterns: list[re.Pattern[str]]
    fields: list[FieldRule]
    flags: list[FlagRule]

    def applies_to(self, ctx: MatchContext) -> bool:
        if ctx.target != self.target:
            return False
        if self.prefixes and ctx.prefix not in self.prefixes:
            return False
        if self.libraries and ctx.library not in self.libraries:
            return False
        for patterns, subject in (
            (self.name_patterns, ctx.name),
            (self.lib_id_patterns, ctx.lib_id),
            (self.reference_patterns, ctx.reference),
            (self.sheet_patterns, ctx.sheet),
        ):
            if patterns and not any(p.search(subject) for p in patterns):
                return False
        return all(pattern.search(ctx.properties.get(key, "")) for key, pattern in self.property_patterns.items())


def _conditions(entry: dict, where: str, target: str) -> dict:
    if entry.get("when_reference") and target != "schematic":
        raise RuleError(f"{where}: when_reference only applies to target 'schematic' (library items have no reference)")
    return {
        "when": _compile_map(entry.get("when"), where),
        "when_name": _compile(entry["when_name"], where) if entry.get("when_name") else None,
        "when_reference": _compile(entry["when_reference"], where) if entry.get("when_reference") else None,
    }


def _number(entry: dict, key: str, where: str) -> float:
    raw = entry.get(key, 0.0)
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise RuleError(f"{where}: {key} must be a number, got {raw!r}")
    return float(raw)


def _string_list(raw: object, where: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RuleError(f"{where}: expected a list")
    return [str(x) for x in raw]


def load_ruleset(path: Path) -> RuleSet:
    """Load one rule file. Every structural problem is a :class:`RuleError` naming the file."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise RuleError(f"{path}: invalid TOML", str(exc)) from exc
    except OSError as exc:
        raise RuleError(f"Cannot read {path}", exc.strerror or str(exc)) from exc

    target = str(data.get("target", "symbol"))
    if target not in TARGETS:
        raise RuleError(f"{path}: target must be one of {', '.join(TARGETS)}, got {target!r}")

    match = data.get("match", {})
    if not isinstance(match, dict):
        raise RuleError(f"{path}: [match] must be a table")
    unknown = set(match) - ALLOWED_AXES[target]
    if unknown:
        raise RuleError(
            f"{path}: [match] key(s) {', '.join(sorted(unknown))} are not valid for target '{target}'.",
            "Valid axes: " + ", ".join(sorted(ALLOWED_AXES[target])) + ".",
        )

    protected = PROTECTED_FIELDS.get(target, set())
    fields: list[FieldRule] = []
    for entry in data.get("field", []):
        if not isinstance(entry, dict) or "name" not in entry:
            raise RuleError(f"{path}: a [[field]] entry is missing 'name'")
        name = str(entry["name"])
        if name in protected:
            raise RuleError(
                f"{path}: '{name}' cannot be written on a {target} target.",
                "Its value is stored in more than one place in the file; rewriting the property alone "
                "would desynchronise the document.",
            )
        where = f"{path} field {name!r}"
        fields.append(
            FieldRule(
                name=name,
                value=str(entry.get("value", "")),
                hide=bool(entry.get("hide", True)),
                requires=_string_list(entry.get("requires"), where + " requires"),
                layer=str(entry.get("layer", "F.Fab")),
                size=_number(entry, "size", where),
                thickness=_number(entry, "thickness", where),
                overwrite=bool(entry.get("overwrite", False)),
                source=path.name,
                **_conditions(entry, where, target),
            )
        )

    flags: list[FlagRule] = []
    for entry in data.get("flag", []):
        if not isinstance(entry, dict) or "name" not in entry:
            raise RuleError(f"{path}: a [[flag]] entry is missing 'name'")
        name = str(entry["name"])
        if target != "schematic":
            raise RuleError(f"{path}: [[flag]] is only supported for target 'schematic'")
        if name not in FLAG_NAMES:
            raise RuleError(
                f"{path}: unknown flag {name!r}.",
                "Known flags: " + ", ".join(FLAG_NAMES) + ". Custom fields go in [[field]].",
            )
        if "value" not in entry:
            raise RuleError(f"{path}: flag {name!r} is missing 'value' (true or false)")
        conditions = _conditions(entry, f"{path} flag {name!r}", target)
        flags.append(FlagRule(name=name, value=bool(entry["value"]), source=path.name, **conditions))

    def patterns(key: str) -> list[re.Pattern[str]]:
        return [_compile(p, f"{path} {key}") for p in _string_list(match.get(key), f"{path} {key}")]

    return RuleSet(
        path=path,
        title=str(data.get("title", path.stem)),
        target=target,
        prefixes=_string_list(match.get("reference_prefixes"), f"{path} reference_prefixes"),
        libraries=_string_list(match.get("libraries"), f"{path} libraries"),
        name_patterns=patterns("name_regex"),
        property_patterns=_compile_map(match.get("properties"), f"{path} [match.properties]"),
        lib_id_patterns=patterns("lib_id_regex"),
        reference_patterns=patterns("reference_regex"),
        sheet_patterns=patterns("sheet_regex"),
        fields=fields,
        flags=flags,
    )


def load_rules_dir(directory: Path, target: str | None = None) -> list[RuleSet]:
    """Every ``*.toml`` in ``directory``, sorted by filename; optionally only one target's."""
    directory = directory.expanduser()
    if not directory.is_dir():
        raise RuleError(f"Rules directory not found: {directory}")
    paths = sorted(p for p in directory.glob("*.toml") if p.is_file())
    if not paths:
        raise RuleError(f"No .toml rule files in {directory}")
    sets = [load_ruleset(p) for p in paths]
    if target is not None:
        sets = [rs for rs in sets if rs.target == target]
    return sets


def rules_for(rulesets: list[RuleSet], ctx: MatchContext) -> list[FieldRule]:
    """Matching field rules, one per field name, in file then declaration order.

    Entry-level ``when`` conditions are evaluated before de-duplication, so
    many entries may share a field name as long as at most one matches a
    given item. First match wins.
    """
    seen: set[str] = set()
    out: list[FieldRule] = []
    for rs in rulesets:
        if not rs.applies_to(ctx):
            continue
        for f in rs.fields:
            if f.name in seen or not f.matches(ctx):
                continue
            seen.add(f.name)
            out.append(f)
    return out


def flags_for(rulesets: list[RuleSet], ctx: MatchContext) -> list[FlagRule]:
    """Matching flag rules, one per flag name, same precedence as :func:`rules_for`."""
    seen: set[str] = set()
    out: list[FlagRule] = []
    for rs in rulesets:
        if not rs.applies_to(ctx):
            continue
        for f in rs.flags:
            if f.name in seen or not f.matches(ctx):
                continue
            seen.add(f.name)
            out.append(f)
    return out
