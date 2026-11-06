# SPDX-License-Identifier: MIT
"""The build BOMs: the schematic's lines resolved against the catalogs and written per grade.

``kicad-cli sch export bom`` gives the lines (:func:`read_export`);
:mod:`bac_common.catalog` picks a row per line and grade; this module writes
``…-bom-dev.csv`` and ``…-bom-flight.csv`` (the purchase columns),
``…-bom-jlcpcb.csv`` (the dev build in JLCPCB's assembly format) and
``…-bom-issues.csv`` (every line a grade could not resolve, with the reason).
Two symbol fields shape the lines: ``Build`` (``dev`` or ``flight``: the part
is fitted in that build only; absent: both) and ``Qty per footprint`` (how many
parts one placed footprint takes; the quantities are multiplied by it).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from bac_common.catalog import GRADES, BomLine, Catalog, Resolved, package_of, resolve
from bac_common.errors import UsageError

__all__ = [
    "RESOLVE_FIELDS",
    "RESOLVE_LABELS",
    "RESOLVE_GROUP_BY",
    "PER_FOOTPRINT",
    "Summary",
    "fold_per_footprint",
    "read_export",
    "write_builds",
]

PER_FOOTPRINT = "Qty per footprint"
BUILD = "Build"

# The second export, the one the resolver reads: fixed columns whatever [bom] says.
RESOLVE_FIELDS = f"Reference,${{QUANTITY}},Value,Footprint,Manufacturer PN,${{DNP}},{BUILD},{PER_FOOTPRINT}"
RESOLVE_LABELS = f"Reference,Qty,Value,Footprint,MPN,DNP,{BUILD},{PER_FOOTPRINT}"
RESOLVE_GROUP_BY = f"Value,Footprint,Manufacturer PN,${{DNP}},{BUILD},{PER_FOOTPRINT}"

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
    not_fitted: dict[str, int] | None = None  # per grade: lines the Build field keeps out of it

    def note(self) -> str:
        parts = []
        for g, n in self.resolved.items():
            skipped = (self.not_fitted or {}).get(g, 0)
            parts.append(f"{n}/{self.lines - skipped} {g}")
        text = f"{', '.join(parts)} resolved"
        skipped_total = sum((self.not_fitted or {}).values())
        if skipped_total:
            text += f", {skipped_total} not fitted"
        if self.issues:
            text += f", {self.issues} issue{'s' if self.issues != 1 else ''}"
        if self.flagged:
            text += f", {self.flagged} flagged"
        if self.without_lcsc:
            text += f", {self.without_lcsc} without LCSC"
        return text


def _first_reference(refs: str) -> str:
    return refs.replace(",", " ").split()[0]


def per_footprint_of(text: str, refs: str) -> int:
    """The ``Qty per footprint`` field as a count; empty is 1, anything else is a usage error naming the reference."""
    text = text.strip()
    if not text:
        return 1
    if not text.isdigit() or int(text) < 1:
        raise UsageError(
            f"{_first_reference(refs)}: {PER_FOOTPRINT} is {text!r}, not a count.",
            "The field says how many parts one placed footprint takes: a whole number of 1 or more.",
        )
    return int(text)


def build_of(text: str, refs: str) -> str:
    text = text.strip().lower()
    if text and text not in GRADES:
        raise UsageError(
            f"{_first_reference(refs)}: {BUILD} is {text!r}.", f"The field is one of {', '.join(GRADES)}, or empty."
        )
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
                build=build_of(row.get(BUILD) or "", refs),
                per_footprint=per_footprint_of(row.get(PER_FOOTPRINT) or "", refs),
            )
        )
    return lines


def fold_per_footprint(path: Path, fields: str) -> int:
    """Multiply the plain export's quantity column by its trailing ``Qty per footprint`` column and drop that column.

    ``fields`` is the field list the export was made with, *without* the appended
    column; it says where ``${QUANTITY}`` sits. Returns the number of lines whose
    quantity changed. A file without the trailing column is left alone.
    """
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return 0
    names = [f.strip() for f in fields.split(",") if f.strip()]
    if len(rows[0]) != len(names) + 1 or "${QUANTITY}" not in names:
        return 0  # no trailing column, or no quantity to multiply: the file stays as kicad-cli wrote it
    qty_index = names.index("${QUANTITY}")
    changed = 0
    out = [rows[0][:-1]]
    for row in rows[1:]:
        if len(row) != len(names) + 1:
            out.append(row)
            continue
        factor = per_footprint_of(row[-1], row[names.index("Reference")] if "Reference" in names else "?")
        row = row[:-1]
        if factor != 1 and row[qty_index].strip().isdigit():
            row[qty_index] = str(int(row[qty_index]) * factor)
            changed += 1
        out.append(row)
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(out)
    return changed


def _designators(line: BomLine) -> str:
    return ", ".join(line.reference_list)


def _write(path: Path, header: tuple[str, ...], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _build_row(n: int, r: Resolved) -> list[object]:
    line = r.line
    package = r.row["package"] if r.row and r.row.get("package") else package_of(line.footprint)
    note = r.note if r.row else r.reason
    dnp = "DNP" if line.dnp else ""
    if not line.fitted(r.grade):  # a line kept out of this build: listed as DNP, not resolved for it
        dnp, note = "DNP", f"{line.build} build only – not fitted in {r.grade}"
        r = Resolved(line, r.grade, None)
    return [
        n, _designators(line), line.quantity * line.per_footprint, line.value, package, r.tolerance, r.rating,
        r.dielectric, r.height, r.manufacturer, r.mpn, r.lcsc, r.digikey, r.catalog_id, r.status, r.lifecycle,
        r.verified, note, dnp,
    ]  # fmt: skip


def write_builds(catalog: Catalog, lines: list[BomLine], build: dict[str, Path], jlcpcb: Path, issues: Path) -> Summary:
    """Resolve every line in every grade of ``build`` and write the four files."""
    resolved: dict[str, list[Resolved]] = {grade: [resolve(catalog, line, grade) for line in lines] for grade in build}
    for grade, path in build.items():
        _write(path, BUILD_COLUMNS, [_build_row(n, r) for n, r in enumerate(resolved[grade], 1)])

    dev = resolved.get("dev", [])
    jlc_rows, without_lcsc = [], 0
    for r in dev:
        if r.line.dnp or not r.line.fitted("dev"):
            continue
        if not r.lcsc:
            without_lcsc += 1
        comment = r.line.value if r.line.kind else (r.mpn or r.line.value)  # 4k7 for a passive, the MPN otherwise
        jlc_rows.append([comment, ",".join(r.line.reference_list), r.line.footprint, r.lcsc])
    _write(jlcpcb, JLCPCB_COLUMNS, jlc_rows)

    issue_rows, unresolved, flagged = [], 0, 0
    for grade in build:
        for r in resolved[grade]:
            if not r.line.fitted(grade):
                continue
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
        resolved={g: sum(1 for r in resolved[g] if r.row is not None and r.line.fitted(g)) for g in build},
        issues=unresolved,
        flagged=flagged,
        without_lcsc=without_lcsc,
        not_fitted={g: sum(1 for line in lines if not line.fitted(g)) for g in build},
    )
