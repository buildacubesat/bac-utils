# SPDX-License-Identifier: MIT
"""The build BOMs: the schematic's lines resolved against the catalogs and written per grade.

``kicad-cli sch export bom`` gives the lines (:func:`read_export`); :mod:`.catalog`
picks a row per line and grade; this module writes ``…-bom-dev.csv`` and
``…-bom-flight.csv`` (the purchase columns), ``…-bom-jlcpcb.csv`` (the dev
build in JLCPCB's assembly format) and ``…-bom-issues.csv`` (every line a
grade could not resolve, with the reason).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .catalog import BomLine, Catalog, Resolved, package_of, resolve

__all__ = ["RESOLVE_FIELDS", "RESOLVE_LABELS", "RESOLVE_GROUP_BY", "Summary", "read_export", "write_builds"]

# The second export, the one the resolver reads: fixed columns whatever [bom] says.
RESOLVE_FIELDS = "Reference,${QUANTITY},Value,Footprint,Manufacturer PN,${DNP}"
RESOLVE_LABELS = "Reference,Qty,Value,Footprint,MPN,DNP"
RESOLVE_GROUP_BY = "Value,Footprint,Manufacturer PN,${DNP}"

BUILD_COLUMNS = (
    "#", "Designator", "Qty", "Value", "Package", "Tolerance", "Rating", "Dielectric", "Height", "Manufacturer",
    "Manufacturer PN", "LCSC", "Digikey", "Catalog", "Status", "Lifecycle", "Verified", "Note", "DNP",
)  # fmt: skip
JLCPCB_COLUMNS = ("Comment", "Designator", "Footprint", "LCSC Part #")
ISSUE_COLUMNS = ("Designator", "Grade", "Kind", "Value", "Footprint", "MPN", "Reason")


@dataclass(frozen=True)
class Summary:
    lines: int
    resolved: dict[str, int]  # per grade
    issues: int  # lines without a row
    flagged: int  # resolved rows the catalog marks nrnd or unverified
    without_lcsc: int  # dev lines in the JLCPCB file without an LCSC number

    def note(self) -> str:
        parts = [f"{self.resolved[g]}/{self.lines} {g}" for g in self.resolved]
        text = f"{', '.join(parts)} resolved"
        if self.issues:
            text += f", {self.issues} issue{'s' if self.issues != 1 else ''}"
        if self.flagged:
            text += f", {self.flagged} flagged"
        if self.without_lcsc:
            text += f", {self.without_lcsc} without LCSC"
        return text


def read_export(path: Path) -> list[BomLine]:
    """The lines of the resolution export (:data:`RESOLVE_LABELS` as header)."""
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    lines = []
    for row in rows:
        refs = (row.get("Reference") or "").strip()
        if not refs:
            continue
        qty = (row.get("Qty") or "").strip()
        lines.append(
            BomLine(
                references=refs,
                quantity=int(qty) if qty.isdigit() else len(refs.replace(",", " ").split()),
                value=(row.get("Value") or "").strip(),
                footprint=(row.get("Footprint") or "").strip(),
                mpn=(row.get("MPN") or "").strip(),
                dnp=bool((row.get("DNP") or "").strip()),
            )
        )
    return lines


def _designators(line: BomLine) -> str:
    return ", ".join(line.references.replace(",", " ").split())


def _write(path: Path, header: tuple[str, ...], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def _build_row(n: int, r: Resolved) -> list[object]:
    line = r.line
    package = r.row["package"] if r.row and r.row.get("package") else package_of(line.footprint)
    note = r.note if r.row else r.reason
    return [
        n, _designators(line), line.quantity, line.value, package, r.tolerance, r.rating, r.dielectric, r.height,
        r.manufacturer, r.mpn, r.lcsc, r.digikey, r.catalog_id, r.status, r.lifecycle, r.verified, note,
        "DNP" if line.dnp else "",
    ]  # fmt: skip


def write_builds(catalog: Catalog, lines: list[BomLine], build: dict[str, Path], jlcpcb: Path, issues: Path) -> Summary:
    """Resolve every line in every grade of ``build`` and write the four files."""
    resolved: dict[str, list[Resolved]] = {grade: [resolve(catalog, line, grade) for line in lines] for grade in build}
    for grade, path in build.items():
        _write(path, BUILD_COLUMNS, [_build_row(n, r) for n, r in enumerate(resolved[grade], 1)])

    dev = resolved.get("dev", [])
    jlc_rows, without_lcsc = [], 0
    for r in dev:
        if r.line.dnp:
            continue
        if not r.lcsc:
            without_lcsc += 1
        comment = r.line.value if r.line.kind else (r.mpn or r.line.value)  # 4k7 for a passive, the MPN otherwise
        jlc_rows.append([comment, _designators(r.line).replace(", ", ","), r.line.footprint, r.lcsc])
    _write(jlcpcb, JLCPCB_COLUMNS, jlc_rows)

    issue_rows, unresolved, flagged = [], 0, 0
    for grade in build:
        for r in resolved[grade]:
            head = [_designators(r.line), grade]
            tail = [r.line.value, r.line.footprint, r.mpn]
            if r.row is None:
                issue_rows.append([*head, "unresolved", *tail, r.reason])
                unresolved += 1
            for flag in r.flags:
                detail = f"lifecycle {r.lifecycle}" if flag == "lifecycle" else "not confirmed against a datasheet"
                issue_rows.append([*head, flag, *tail, detail])
                flagged += 1
    _write(issues, ISSUE_COLUMNS, issue_rows)
    return Summary(
        lines=len(lines),
        resolved={g: sum(1 for r in resolved[g] if r.row is not None) for g in build},
        issues=unresolved,
        flagged=flagged,
        without_lcsc=without_lcsc,
    )
