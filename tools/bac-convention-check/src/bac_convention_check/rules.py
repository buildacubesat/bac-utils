# SPDX-License-Identifier: MIT
"""Rule model and rule-set loading.

A rule set is a TOML file with a ``[[rules]]`` array. Two sets ship with the
tool: ``guide`` (the BAC Project & Tooling Guide and Interface Design Guide
conventions) and ``firmware`` (review heuristics for the flight software
and hardware repositories, owned by those projects). Extra sets are loaded
by path.

Rule kinds:

``regex``
    One hit per matching line in every text file the ``include`` globs
    select. ``drop`` is a second regex; matching lines are discarded
    (``grep -v``). ``keep`` is a third; only lines matching it survive.
``require``
    One hit per selected file in which ``pattern`` does not occur (within
    the first ``head_lines`` lines when set). For "every X must contain Y".
``path``
    One hit per selected file whose repo-relative path matches ``pattern``.
``builtin``
    A named Python analysis from :mod:`bac_convention_check.builtins`, for
    checks that need structure (parsing pyproject.toml, comparing sets of
    part numbers across file classes).
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Literal

from bac_common.errors import ConfigError

Severity = Literal["blocking", "advisory"]
Kind = Literal["regex", "require", "path", "builtin"]

BUNDLED_SETS = ("guide", "firmware")


@dataclass(slots=True)
class Rule:
    id: str
    title: str
    severity: Severity
    kind: Kind
    pattern: str | None = None
    ignore_case: bool = False
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    drop: str | None = None
    keep: str | None = None
    head_lines: int | None = None
    builtin: str | None = None
    note: str | None = None
    rule_set: str = ""

    def compiled(self) -> re.Pattern[str] | None:
        if self.pattern is None:
            return None
        return re.compile(self.pattern, re.IGNORECASE if self.ignore_case else 0)

    def compiled_drop(self) -> re.Pattern[str] | None:
        return re.compile(self.drop, re.IGNORECASE) if self.drop else None

    def compiled_keep(self) -> re.Pattern[str] | None:
        return re.compile(self.keep, re.IGNORECASE) if self.keep else None


def bundled_set_path(name: str) -> Path:
    """Path of a rule set shipped inside the package."""
    return Path(str(resources.files("bac_convention_check").joinpath("rules", f"{name}.toml")))


def resolve_set(spec: str, relative_to: Path | None = None) -> Path:
    """``guide`` → bundled file; anything else is a path (relative to ``relative_to`` or cwd)."""
    if spec in BUNDLED_SETS:
        return bundled_set_path(spec)
    path = Path(spec).expanduser()
    if not path.is_absolute() and relative_to is not None:
        path = relative_to / path
    if not path.exists():
        raise ConfigError(
            f"Rule set not found: {spec}", f"Bundled sets are {', '.join(BUNDLED_SETS)}; anything else must be a path."
        )
    return path


def load_rule_set(path: Path, name: str | None = None) -> list[Rule]:
    """Parse one rule-set file, validating every rule up front so a bad regex fails before any scan."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Rule set is not valid TOML: {path}", str(exc)) from exc
    set_name = name or path.stem
    rules: list[Rule] = []
    seen: set[str] = set()
    for i, raw in enumerate(data.get("rules", []), start=1):
        rule = _rule_from_dict(raw, set_name, f"{path}: rule #{i}")
        if rule.id in seen:
            raise ConfigError(f"{path}: duplicate rule id {rule.id}")
        seen.add(rule.id)
        rules.append(rule)
    if not rules:
        raise ConfigError(f"Rule set defines no rules: {path}")
    return rules


def _rule_from_dict(raw: dict, set_name: str, where: str) -> Rule:
    missing = [k for k in ("id", "title", "severity", "kind") if k not in raw]
    if missing:
        raise ConfigError(f"{where}: missing {', '.join(missing)}")
    if raw["severity"] not in ("blocking", "advisory"):
        raise ConfigError(f"{where}: severity must be blocking or advisory, got {raw['severity']!r}")
    if raw["kind"] not in ("regex", "require", "path", "builtin"):
        raise ConfigError(f"{where}: kind must be regex, require, path or builtin, got {raw['kind']!r}")
    rule = Rule(
        id=str(raw["id"]),
        title=str(raw["title"]),
        severity=raw["severity"],
        kind=raw["kind"],
        pattern=raw.get("pattern"),
        ignore_case=bool(raw.get("ignore_case", False)),
        include=list(raw.get("include", [])),
        exclude=list(raw.get("exclude", [])),
        drop=raw.get("drop"),
        keep=raw.get("keep"),
        head_lines=raw.get("head_lines"),
        builtin=raw.get("builtin"),
        note=raw.get("note"),
        rule_set=set_name,
    )
    if rule.kind in ("regex", "require", "path") and not rule.pattern:
        raise ConfigError(f"{where}: kind {rule.kind} needs a pattern")
    if rule.kind == "require" and not rule.include:
        raise ConfigError(f"{where}: kind require needs include globs")
    if rule.kind == "builtin" and not rule.builtin:
        raise ConfigError(f"{where}: kind builtin needs a builtin name")
    for label, value in (("pattern", rule.pattern), ("drop", rule.drop), ("keep", rule.keep)):
        if value:
            try:
                re.compile(value)
            except re.error as exc:
                raise ConfigError(f"{where}: invalid {label} regex: {exc}") from exc
    return rule


def load_rules(specs: list[str], relative_to: Path | None = None) -> list[Rule]:
    """Load several sets in order; ids must be unique across them."""
    rules: list[Rule] = []
    ids: dict[str, str] = {}
    for spec in specs:
        path = resolve_set(spec, relative_to)
        for rule in load_rule_set(path, spec if spec in BUNDLED_SETS else None):
            if rule.id in ids:
                raise ConfigError(f"Rule id {rule.id} is defined in both {ids[rule.id]} and {rule.rule_set}.")
            ids[rule.id] = rule.rule_set
            rules.append(rule)
    return rules
