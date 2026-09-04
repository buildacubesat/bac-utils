# SPDX-License-Identifier: MIT
"""Scanning engine: one file walk, one text cache, every rule applied to it.

The engine never depends on an external search program, so results are the
same on every machine. Files come from ``git ls-files`` when the root is a
git checkout (so ``.gitignore`` is honoured, untracked files included),
otherwise from a directory walk with a fixed exclude list. A file is text if
its first 8 KiB contain no NUL byte.

A line may opt out of specific rules with an inline marker anywhere on it::

    parser = re.compile("[–—:-]")  # convention-check: allow A1

``allow all`` silences every rule for that line. File-wide and rule-wide
exclusions belong in the project config (see :mod:`bac_convention_check.cli`).
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .rules import Rule

MAX_FILE_BYTES = 5 * 1024 * 1024
SNIFF_BYTES = 8192

DEFAULT_EXCLUDE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "dist",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
        ".idea",
        ".vscode",
    }
)
DEFAULT_EXCLUDE_FILES = ("*.lock", "*.pyc", "*.min.js", "*.min.css", "*.map", ".DS_Store")

ALLOW_RE = re.compile(r"convention-check:\s*allow\s+(all|[A-Za-z0-9_]+(?:\s*,\s*[A-Za-z0-9_]+)*)", re.I)


@dataclass(slots=True)
class Hit:
    path: str
    line: int  # 0 for file-level findings
    text: str


@dataclass(slots=True)
class RuleResult:
    rule: Rule
    hits: list[Hit] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def count(self) -> int:
        return len(self.hits)


# ---------------------------------------------------------------------------
# Glob matching (Python 3.11 has no PurePath.full_match)
# ---------------------------------------------------------------------------


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def path_matches(rel: str, pattern: str) -> bool:
    """A pattern without ``/`` matches the file name; one with ``/`` matches the whole relative path."""
    if "/" not in pattern:
        return fnmatch.fnmatchcase(PurePosixPath(rel).name, pattern)
    regex = _GLOB_CACHE.get(pattern)
    if regex is None:
        regex = _GLOB_CACHE[pattern] = _glob_to_regex(pattern)
    return bool(regex.match(rel))


def any_match(rel: str, patterns: Iterable[str]) -> bool:
    return any(path_matches(rel, p) for p in patterns)


# ---------------------------------------------------------------------------
# File index
# ---------------------------------------------------------------------------


def _is_excluded_by_default(rel: str) -> bool:
    parts = PurePosixPath(rel).parts
    for part in parts[:-1]:
        if part in DEFAULT_EXCLUDE_DIRS or part.startswith("build"):
            return True
    return any(fnmatch.fnmatchcase(parts[-1], g) for g in DEFAULT_EXCLUDE_FILES)


def enumerate_files(root: Path, *, use_git: bool = True) -> tuple[list[str], str]:
    """Repo-relative posix paths of regular files, and a label for how they were found."""
    if use_git and (root / ".git").exists():
        try:
            out = subprocess.run(
                ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                check=True,
                capture_output=True,
            ).stdout
        except (FileNotFoundError, subprocess.CalledProcessError):
            out = None
        if out is not None:
            rels = [p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p]
            files = sorted(r for r in set(rels) if (root / r).is_file() and not _is_excluded_by_default(r))
            return files, "git ls-files"
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if _is_excluded_by_default(rel):
            continue
        files.append(rel)
    return sorted(files), "directory walk"


class FileIndex:
    """All scannable files under ``root`` with lazily read, cached text."""

    def __init__(self, root: Path, files: list[str]):
        self.root = root
        self.files = files
        self._lines: dict[str, list[str] | None] = {}

    def lines(self, rel: str) -> list[str] | None:
        """Lines of a text file, or None for binary or oversized files."""
        if rel in self._lines:
            return self._lines[rel]
        path = self.root / rel
        try:
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                self._lines[rel] = None
                return None
            with path.open("rb") as f:
                head = f.read(SNIFF_BYTES)
                if b"\0" in head:
                    self._lines[rel] = None
                    return None
                data = head + f.read()
        except OSError:
            self._lines[rel] = None
            return None
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        self._lines[rel] = lines
        return lines

    def select(self, include: Iterable[str], exclude: Iterable[str] = ()) -> list[str]:
        """Files matching any include glob (all files when none) and no exclude glob."""
        inc = list(include)
        exc = list(exclude)
        return [rel for rel in self.files if (not inc or any_match(rel, inc)) and not any_match(rel, exc)]


# ---------------------------------------------------------------------------
# Running rules
# ---------------------------------------------------------------------------


def _allowed(line: str, rule_id: str) -> bool:
    m = ALLOW_RE.search(line)
    if not m:
        return False
    spec = m.group(1)
    if spec.lower() == "all":
        return True
    return rule_id.lower() in {s.strip().lower() for s in spec.split(",")}


def run_regex(rule: Rule, index: FileIndex, files: list[str]) -> list[Hit]:
    pattern = rule.compiled()
    assert pattern is not None
    drop = rule.compiled_drop()
    keep = rule.compiled_keep()
    hits: list[Hit] = []
    for rel in files:
        lines = index.lines(rel)
        if lines is None:
            continue
        for no, line in enumerate(lines, start=1):
            if not pattern.search(line):
                continue
            if drop and drop.search(line):
                continue
            if keep and not keep.search(line):
                continue
            if _allowed(line, rule.id):
                continue
            hits.append(Hit(rel, no, line.strip()))
    return hits


def run_require(rule: Rule, index: FileIndex, files: list[str]) -> list[Hit]:
    pattern = rule.compiled()
    assert pattern is not None
    hits: list[Hit] = []
    for rel in files:
        lines = index.lines(rel)
        if lines is None:
            continue
        scope = lines[: rule.head_lines] if rule.head_lines else lines
        if not any(pattern.search(line) for line in scope):
            hits.append(Hit(rel, 0, rule.note or rule.title))
    return hits


def run_path(rule: Rule, index: FileIndex, files: list[str]) -> list[Hit]:
    pattern = rule.compiled()
    assert pattern is not None
    return [Hit(rel, 0, rule.note or rule.title) for rel in files if pattern.search(rel)]


BuiltinFn = Callable[[Rule, FileIndex, list[str]], tuple[list[Hit], list[str]]]


def run_rules(
    rules: list[Rule],
    index: FileIndex,
    *,
    excludes: dict[str, list[str]] | None = None,
    builtins: dict[str, BuiltinFn] | None = None,
) -> list[RuleResult]:
    """Apply every rule; a failing rule reports an error instead of aborting the run.

    ``excludes`` maps a rule id (or ``"*"`` for all) to path globs that rule
    must skip – the project config's escape hatch for documented exceptions.
    """
    excludes = excludes or {}
    builtins = builtins or {}
    results: list[RuleResult] = []
    for rule in rules:
        extra = [*excludes.get("*", []), *excludes.get(rule.id, [])]
        files = index.select(rule.include, [*rule.exclude, *extra])
        result = RuleResult(rule)
        try:
            if rule.kind == "regex":
                result.hits = run_regex(rule, index, files)
            elif rule.kind == "require":
                result.hits = run_require(rule, index, files)
            elif rule.kind == "path":
                result.hits = run_path(rule, index, files)
            else:
                fn = builtins.get(rule.builtin or "")
                if fn is None:
                    result.error = f"unknown builtin {rule.builtin!r}"
                else:
                    result.hits, result.notes = fn(rule, index, files)
        except Exception as exc:  # noqa: BLE001 – one broken rule must not hide the others
            result.error = f"{type(exc).__name__}: {exc}"
        results.append(result)
    return results
