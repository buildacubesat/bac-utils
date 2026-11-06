# SPDX-License-Identifier: MIT
"""The catalog check: the part catalogs as data, and the README tables generated from them.

``check ROOT --catalog`` reads the catalog folders of ``[audit] catalogs``
(each recognised by the CSV files it holds) and reports what
:func:`bac_common.catalog.check` finds – vocabularies, ids, values against
packages, slot shapes – plus every ICs-shaped README whose generated sections
(3 Slots, 4 Catalog) no longer match its CSV. ``apply ROOT --catalog``
regenerates those sections, with ``.bak`` copies and one confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bac_common.catalog import (
    IC_FILE,
    OTHER_FILE,
    OTHER_FILE_OLD,
    PASSIVE_FILES,
    Catalog,
    Finding,
    check,
    load_catalog,
    regenerate_readme,
)
from bac_common.errors import ConfigError

__all__ = ["CatalogReport", "ReadmePlan", "inspect"]


@dataclass(frozen=True)
class ReadmePlan:
    """An ICs-shaped README whose generated sections differ from its CSV."""

    path: Path
    original: str
    text: str


@dataclass
class CatalogReport:
    root: Path
    folders: dict[str, Path] = field(default_factory=dict)  # collection -> folder
    catalog: Catalog = field(default_factory=Catalog)
    findings: list[Finding] = field(default_factory=list)
    readmes: list[ReadmePlan] = field(default_factory=list)  # stale READMEs, apply rewrites them
    plain: list[Path] = field(default_factory=list)  # ICs-shaped folders whose README has no generated sections
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.findings) + len(self.readmes)


def _classify(root: Path, folders: list[Path]) -> dict[str, Path]:
    """Which configured folder holds which collection, by the files in it."""
    out: dict[str, Path] = {}
    for folder in folders:
        path = folder if folder.is_absolute() else root / folder
        if not path.is_dir():
            continue
        if all((path / name).is_file() for name in PASSIVE_FILES):
            out.setdefault("passives", path)
        elif (path / IC_FILE).is_file():
            out.setdefault("ics", path)
        elif (path / OTHER_FILE).is_file() or (path / OTHER_FILE_OLD).is_file():
            out.setdefault("other", path)
    return out


def inspect(root: Path, folders: list[Path]) -> CatalogReport:
    """Read the catalogs under ``root`` and compare their READMEs with the CSVs."""
    report = CatalogReport(root)
    report.folders = _classify(root, folders)
    if not report.folders:
        raise ConfigError(
            "No catalog folder found.",
            f"catalogs in [audit] names {', '.join(str(f) for f in folders) or 'nothing'}; "
            f"a folder holds {PASSIVE_FILES[0]} and {PASSIVE_FILES[1]}, {IC_FILE} or {OTHER_FILE}.",
        )
    report.catalog = load_catalog(
        report.folders.get("passives"), report.folders.get("ics"), report.folders.get("other")
    )
    report.findings = check(report.catalog)
    for name, rows in (("ics", report.catalog.ics), ("other", report.catalog.other)):
        folder = report.folders.get(name)
        if folder is None:
            continue
        readme = folder / "README.md"
        if not readme.is_file():
            report.notes.append(f"{name}: no README.md")
            continue
        original = readme.read_text(encoding="utf-8")
        text = regenerate_readme(original, rows)
        if text is None:
            report.plain.append(readme)
        elif text != original:
            report.readmes.append(ReadmePlan(readme, original, text))
    return report
