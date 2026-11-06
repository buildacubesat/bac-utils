# SPDX-License-Identifier: MIT
"""The part catalogs: loading, checking, the resolution of BOM lines, the generated README tables.

Three collections, all CSV, all kept outside bac-utils (BAC's are in
``bac-hardware/resources/catalog/``): the *passives* – one row per value,
package and grade, dev and flight rows sharing value and package –, the *ICs* –
rows grouped in a ``slot`` (one function in one footprint) with the
``reference`` part fitted on the board, ``drop-in`` alternatives and a
``flight`` candidate – and the *other* parts (connectors, switches, LEDs,
holders, spacers, crystals, discretes) in the ICs' shape. A BOM line from the
schematic names a passive by value and footprint and anything else by its
manufacturer part number; :func:`resolve` finds the row for a dev build and
the row for a flight build, and says why when it cannot.

``bac-kicad-generate-artifacts`` resolves BOMs and freezes projects with this
module; ``bac-kicad-maintain`` checks the catalogs (:func:`check`) and
regenerates the slot tables of an ICs-shaped README (:func:`regenerate_readme`).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError

__all__ = [
    "BomLine",
    "Catalog",
    "Finding",
    "Resolved",
    "check",
    "load_catalog",
    "package_of",
    "parse_value",
    "readme_version",
    "regenerate_readme",
    "resolve",
]

PASSIVE_FILES = ("bac-passives-capacitors.csv", "bac-passives-resistors.csv")
IC_FILE = "bac-ics.csv"
OTHER_FILE = "bac-other.csv"  # the ICs' columns
OTHER_FILE_OLD = "bac-parts.csv"  # the name before 2026-11 (resources/parts/)
PASSIVE_COLUMNS = ("id", "grade", "value", "package", "manufacturer", "mpn", "role", "status", "lcsc", "digikey")
IC_COLUMNS = ("id", "slot", "role", "compat", "manufacturer", "mpn", "qualification", "lcsc", "digikey")
GRADES = ("dev", "flight")
# the qualification grades that let a reference IC stay in a flight build; `accepted` is a decision
# for a part with no qualified variant (a connector, a spacer)
QUALIFIED = ("aec-q100", "aec-q101", "aec-q102", "aec-q200", "enhanced-product", "space", "accepted")
# roles a passive line resolves to, in order of preference
ROLE_ORDER = ("default", "shunt", "jumper", "alternative")

# The controlled vocabularies of the catalogs' READMEs (column reference sections).
PASSIVE_ROLES = ROLE_ORDER
PASSIVE_STATUS = ("active", "conditional", "proposal", "sourcing-open")
PASSIVE_QUALIFICATION = ("commercial", "aec-q200", "accepted")
IC_ROLES = ("reference", "flight", "alternative")
IC_COMPAT = ("reference", "drop-in", "drop-in-behavior", "footprint-only", "different-footprint")
IC_QUALIFICATION = ("commercial", "industrial", *QUALIFIED)
IC_LIFECYCLE = ("active", "nrnd", "obsolete")

_PACKAGES = ("0201", "0306", "0402", "0603", "0612", "0805", "1206", "1210", "1411", "2010", "2512", "2917")
# metric codes (R_0603_1608Metric, CP_EIA-3528-21) to the imperial ones the catalogs use
_METRIC = {
    "0603": "0201", "0816": "0306", "1005": "0402", "1608": "0603", "1632": "0612", "2012": "0805",
    "3216": "1206", "3225": "1210", "3528": "1411", "5025": "2010", "6332": "2512", "7343": "2917",
}  # fmt: skip
_PACKAGE_RE = re.compile(r"(?<![0-9])(" + "|".join(_PACKAGES) + r")(?![0-9])")
_METRIC_RE = re.compile(r"(?<![0-9])(" + "|".join(_METRIC) + r")(?![0-9])")
_SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}
_VALUE_RE = re.compile(r"^\s*([0-9]*)([.,]?)([0-9]*)\s*([pnuµμmkKMGRrΩ]?)\s*([0-9]*)\s*([FfΩRr]|ohm|Ohm)?\s*$")
_VERSION_ROW = re.compile(r"^\|\s*v?(\d+\.\d+(?:\.\d+)?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", re.M)
_LCSC_RE = re.compile(r"^C\d+$")


@dataclass(frozen=True)
class BomLine:
    """One grouped line of the schematic's BOM as kicad-cli exports it."""

    references: str  # "R1, R2"
    quantity: int
    value: str
    footprint: str
    mpn: str  # the Manufacturer PN field; empty on most passives
    dnp: bool = False
    build: str = ""  # the Build field: "dev", "flight", or "" for both
    per_footprint: int = 1  # the Qty per footprint field: parts one placed footprint takes

    @property
    def kind(self) -> str:
        """``c`` or ``r`` from the first reference's prefix, else ``""``."""
        first = re.split(r"[,\s]+", self.references.strip())[0].upper()
        return first[0].lower() if first[:1] in ("C", "R") and first[1:2].isdigit() else ""

    @property
    def reference_list(self) -> list[str]:
        return self.references.replace(",", " ").split()

    def fitted(self, grade: str) -> bool:
        """Whether the line belongs to ``grade``'s build: no ``Build`` field, or the matching one."""
        return not self.build or self.build == grade


@dataclass(frozen=True)
class Resolved:
    """A BOM line with the catalog row chosen for one grade, or the reason there is none."""

    line: BomLine
    grade: str
    row: dict[str, str] | None
    note: str = ""  # what is text by nature: a condition, a difference to check, the next-revision candidate
    reason: str = ""  # why there is no row (the issues list)

    @property
    def status(self) -> str:
        """The catalog's own word for the row (``active``, ``conditional``, …); ``unresolved`` without a row."""
        return (self.row.get("status") or "active") if self.row else "unresolved"

    @property
    def lifecycle(self) -> str:
        return self.row.get("lifecycle", "") if self.row else ""

    @property
    def verified(self) -> str:
        return self.row.get("verified", "") if self.row else ""

    @property
    def tolerance(self) -> str:
        """``1 %`` from the catalog's fraction (``0.01``)."""
        return _percent(self.row.get("tolerance", "")) if self.row else ""

    @property
    def rating(self) -> str:
        """What limits the part: a resistor's power, a capacitor's voltage, an IC's temperature range."""
        if not self.row:
            return ""
        r = self.row
        if r.get("_kind") == "r":
            return _unit(r.get("power_w", ""), "W")
        if r.get("_kind") == "c":
            return _unit(r.get("voltage_v", ""), "V")
        lo, hi = r.get("temp_min_c", ""), r.get("temp_max_c", "")
        return f"{lo} to {hi} °C" if lo and hi else ""

    @property
    def dielectric(self) -> str:
        return self.row.get("dielectric", "") if self.row else ""

    @property
    def height(self) -> str:
        """Maximum height in mm, where the catalog states one (capacitors)."""
        return self.row.get("height_max_mm", "") if self.row else ""

    @property
    def flags(self) -> list[str]:
        """What the issues list reports about a resolved row (ICs README §2.3 rules 4 and 5)."""
        out = []
        if self.lifecycle not in ("", "active"):
            out.append("lifecycle")
        if self.verified == "false":
            out.append("unverified")
        return out

    @property
    def manufacturer(self) -> str:
        return self.row["manufacturer"] if self.row else ""

    @property
    def mpn(self) -> str:
        return self.row["mpn"] if self.row else self.line.mpn

    @property
    def lcsc(self) -> str:
        return self.row.get("lcsc", "") if self.row else ""

    @property
    def digikey(self) -> str:
        return self.row.get("digikey", "") if self.row else ""

    @property
    def catalog_id(self) -> str:
        return self.row["id"] if self.row else ""


def _number(text: str) -> str:
    """``0.100`` → ``0.1``, ``1.0`` → ``1``; anything that is not a number stays as it is."""
    try:
        value = float(text)
    except ValueError:
        return text
    return f"{value:g}"


def _unit(text: str, unit: str) -> str:
    return f"{_number(text)} {unit}" if text else ""


def _percent(text: str) -> str:
    try:
        return f"{float(text) * 100:g} %"
    except ValueError:
        return text


@dataclass
class Catalog:
    passives: list[dict[str, str]] = field(default_factory=list)
    ics: list[dict[str, str]] = field(default_factory=list)
    other: list[dict[str, str]] = field(default_factory=list)  # connectors and such, resolved like ICs
    source: dict[str, Path] = field(default_factory=dict)  # file name -> path
    versions: dict[str, str] = field(default_factory=dict)  # collection ("passives", "ics", "other") -> README version

    @property
    def empty(self) -> bool:
        return not self.passives and not self.ics and not self.other

    @property
    def by_mpn(self) -> list[dict[str, str]]:
        """Every row a manufacturer part number can name: the ICs, then the other parts."""
        return self.ics + self.other

    def ic_by_mpn(self, mpn: str) -> dict[str, str] | None:
        key = mpn.strip().casefold()
        return next((r for r in self.by_mpn if r["mpn"].strip().casefold() == key), None) if key else None

    def slot(self, name: str) -> list[dict[str, str]]:
        return [r for r in self.by_mpn if r["slot"] == name]

    def counts(self) -> str:
        """``15 passives, 14 ICs, 6 other`` for a dim line."""
        parts = [f"{len(self.passives)} passives", f"{len(self.ics)} ICs"]
        if self.other:
            parts.append(f"{len(self.other)} other")
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _read(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:  # a catalog re-saved by a spreadsheet may carry a marker
        reader = csv.DictReader(fh)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise ConfigError(f"{path.name} lacks the column(s) {', '.join(missing)}.", f"In {path.parent}.")
        return [{k: (v or "").strip() for k, v in row.items() if k} for row in reader]


def readme_version(folder: Path) -> str:
    """The newest version in the version history of ``folder/README.md``; empty without one."""
    readme = folder / "README.md"
    if not readme.is_file():
        return ""
    versions = _VERSION_ROW.findall(readme.read_text(encoding="utf-8"))
    if not versions:
        return ""
    return max((v for v, _ in versions), key=lambda v: tuple(int(x) for x in v.split(".")))


def load_catalog(passives_dir: Path | None, ics_dir: Path | None, other_dir: Path | None = None) -> Catalog:
    """The collections from their folders; a folder may be absent, a file in a given folder may not."""
    catalog = Catalog()
    if passives_dir is not None:
        folder = passives_dir.expanduser()
        for name in PASSIVE_FILES:
            path = folder / name
            if not path.is_file():
                raise ConfigError(f"Passives catalog file missing: {path}", "Check passives in [catalog].")
            rows = _read(path, PASSIVE_COLUMNS)
            kind = "c" if "capacitor" in name else "r"
            for row in rows:
                row["_kind"] = kind
                row["_value"] = parse_value(row["value"], kind)
            catalog.passives.extend(rows)
            catalog.source[name] = path
        catalog.versions["passives"] = readme_version(folder)
    if ics_dir is not None:
        folder = ics_dir.expanduser()
        path = folder / IC_FILE
        if not path.is_file():
            raise ConfigError(f"IC catalog file missing: {path}", "Check ics in [catalog].")
        catalog.ics = _read(path, IC_COLUMNS)
        catalog.source[IC_FILE] = path
        catalog.versions["ics"] = readme_version(folder)
    if other_dir is not None:
        folder = other_dir.expanduser()
        path = folder / OTHER_FILE
        if not path.is_file():
            hint = "Check other in [catalog]."
            if (folder / OTHER_FILE_OLD).is_file():
                hint = f"The folder holds {OTHER_FILE_OLD}; rename it to {OTHER_FILE} (resources/catalog/other/)."
            raise ConfigError(f"Other-parts catalog file missing: {path}", hint)
        catalog.other = _read(path, IC_COLUMNS)
        catalog.source[OTHER_FILE] = path
        catalog.versions["other"] = readme_version(folder)
    return catalog


# ---------------------------------------------------------------------------
# Values and packages
# ---------------------------------------------------------------------------


def parse_value(text: str, kind: str) -> float | None:
    """A capacitor or resistor value as a number: ``4k7``, ``4.7k``, ``100nF``, ``0.1u``, ``2u2``, ``0R``, ``60R4``.

    ``kind`` is ``c`` or ``r`` (the unit of a bare number: farad, ohm – the number is the same).
    Returns ``None`` for anything that is not a value.
    """
    if not text:
        return None
    match = _VALUE_RE.match(text.replace("Ω", "R").replace("ohm", "R").replace("Ohm", "R"))
    if not match:
        return None
    whole, point, frac, prefix, tail, _unit = match.groups()
    if not whole and not frac and not tail:
        return None
    if prefix in ("R", "r"):  # 60R4 = 60.4 Ω, 0R = 0 Ω
        prefix, scale = "", 1.0
    elif prefix:
        scale = _SI[prefix]
    else:
        scale = 1.0
    if tail:  # 4k7, 2u2: the prefix stands for the decimal point
        if point or frac:
            return None
        number = float(f"{whole or '0'}.{tail}")
    else:
        number = float(f"{whole or '0'}.{frac or '0'}")
    return number * scale


def package_of(footprint: str) -> str:
    """The imperial package code in a footprint name: ``Resistor_SMD:R_0603_1608Metric`` → ``0603``."""
    name = footprint.split(":", 1)[-1]
    match = _PACKAGE_RE.search(name)
    if match:
        return match.group(1)
    metric = _METRIC_RE.search(name)  # a tantalum: CP_EIA-3528-21_Kemet-B
    return _METRIC[metric.group(1)] if metric else ""


def _same_value(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    if a == 0 or b == 0:
        return a == b
    return abs(a - b) <= 1e-3 * max(abs(a), abs(b))


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _passive_candidates(catalog: Catalog, line: BomLine, grade: str) -> list[dict[str, str]]:
    kind, value, package = line.kind, parse_value(line.value, line.kind), package_of(line.footprint)
    rows = [
        r
        for r in catalog.passives
        if r["_kind"] == kind
        and r["grade"] == grade
        and r["package"] == package
        and r["status"] != "proposal"  # not released
        and _same_value(r["_value"], value)
    ]
    rows.sort(key=lambda r: (ROLE_ORDER.index(r["role"]) if r["role"] in ROLE_ORDER else 9, r["status"] != "active"))
    return rows


def _resolve_passive(catalog: Catalog, line: BomLine, grade: str) -> Resolved:
    if line.mpn:
        key = line.mpn.casefold()
        exact = next(
            (
                r
                for r in catalog.passives
                if r["mpn"].casefold() == key and r["grade"] == grade and r["status"] != "proposal"
            ),
            None,
        )
        if exact is not None:
            return Resolved(line, grade, exact, _passive_note(exact))
    if parse_value(line.value, line.kind) is None:
        return Resolved(line, grade, None, reason=f"value {line.value!r} is not a value the catalog can match")
    if not package_of(line.footprint):
        return Resolved(line, grade, None, reason=f"no package code in the footprint {line.footprint!r}")
    rows = _passive_candidates(catalog, line, grade)
    if not rows:
        if line.mpn and catalog.ic_by_mpn(line.mpn) is not None:  # an NTC, a network: an R or C the ICs file knows
            return _resolve_ic(catalog, line, grade)
        other = _passive_candidates(catalog, line, "flight" if grade == "dev" else "dev")
        why = f"no {grade} row" + (" (the other grade has one)" if other else "") + " in the passives catalog"
        return Resolved(line, grade, None, reason=why)
    row = rows[0]
    return Resolved(line, grade, row, _passive_note(row))


def _passive_note(row: dict[str, str]) -> str:
    notes = []
    if row["role"] == "alternative":
        notes.append("alternative row")
    if row["status"] == "conditional" and row.get("notes"):
        notes.append(row["notes"])
    return "; ".join(notes)


def _ic(line: BomLine, grade: str, row: dict[str, str], note: str = "") -> Resolved:
    """An IC row for the BOM – unless the catalog retired it (ICs README §2.3 rule 5: not designed in)."""
    if row.get("lifecycle") == "obsolete":
        return Resolved(line, grade, None, reason=f"{row['mpn']} is obsolete in the catalog")
    return Resolved(line, grade, row, note)


def _resolve_ic(catalog: Catalog, line: BomLine, grade: str) -> Resolved:
    row = catalog.ic_by_mpn(line.mpn)
    if row is None:
        which = "IC or other-parts" if catalog.other else "IC"
        return Resolved(line, grade, None, reason=f"{line.mpn} is not in the {which} catalog")
    if grade == "dev":
        return _ic(line, grade, row, f"{row['role']} row" if row["role"] != "reference" else "")
    if row["role"] == "flight":  # the board already carries the flight part
        return _ic(line, grade, row)
    slot = catalog.slot(row["slot"]) if row["slot"] else [row]
    flight = next((r for r in slot if r["role"] == "flight"), None)
    if row["qualification"] in QUALIFIED:  # ICs README §2.3 rule 3: a qualified part stays
        also = f" (flight row {flight['mpn']} available)" if flight is not None else ""
        return _ic(line, "flight", row, f"{row['qualification']} {row['role']} stays{also}")
    if flight is None:
        if row.get("lifecycle") == "obsolete":
            return _ic(line, "flight", row)
        return Resolved(line, "flight", None, reason=f"no flight candidate in slot {row['slot'] or line.mpn}")
    if flight["compat"] in ("reference", "drop-in"):
        return _ic(line, "flight", flight)
    if flight["compat"] == "drop-in-behavior":
        return _ic(line, "flight", flight, f"check: {flight.get('difference', '') or 'behavior differs'}")
    # footprint-only or different-footprint: the board has to change first
    return _ic(line, "flight", row, f"{flight['mpn']} needs a new footprint ({flight['compat']}) – next board revision")


def resolve(catalog: Catalog, line: BomLine, grade: str) -> Resolved:
    """The catalog row for ``line`` in ``grade``; a line the catalog does not cover passes through unchanged."""
    if grade not in GRADES:
        raise ValueError(grade)
    if line.kind in ("c", "r") and catalog.passives:
        return _resolve_passive(catalog, line, grade)
    if line.mpn and catalog.by_mpn:
        return _resolve_ic(catalog, line, grade)
    if line.kind in ("c", "r"):
        reason = "no passives catalog configured"
    elif line.mpn:
        reason = "no IC or other-parts catalog configured"
    else:
        reason = "no Manufacturer PN on the symbol, and not a resistor or capacitor"
    return Resolved(line, grade, None, reason=reason)


# ---------------------------------------------------------------------------
# Checking the catalogs themselves
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One thing wrong with a catalog row: the file, the row's id, what."""

    file: str
    row: str
    detail: str


def _check_vocabulary(out: list[Finding], name: str, rows: list[dict[str, str]], column: str, allowed: tuple) -> None:
    for r in rows:
        if column in r and r[column] not in allowed:
            out.append(Finding(name, r["id"], f"{column} {r[column]!r} is not one of {', '.join(allowed)}"))


def _check_common(out: list[Finding], name: str, rows: list[dict[str, str]]) -> None:
    seen: dict[str, int] = {}
    for r in rows:
        if not r["id"]:
            out.append(Finding(name, "?", "a row without id"))
            continue
        seen[r["id"]] = seen.get(r["id"], 0) + 1
        if not r["mpn"]:
            out.append(Finding(name, r["id"], "no mpn"))
        if r.get("lcsc") and not _LCSC_RE.match(r["lcsc"]):
            out.append(Finding(name, r["id"], f"lcsc {r['lcsc']!r} is not a C-number"))
        if r.get("checked") and not re.match(r"^\d{4}-\d{2}-\d{2}$", r["checked"]):
            out.append(Finding(name, r["id"], f"checked {r['checked']!r} is not YYYY-MM-DD"))
    for key, n in seen.items():
        if n > 1:
            out.append(Finding(name, key, f"id used {n} times"))


def _check_passives(out: list[Finding], name: str, rows: list[dict[str, str]]) -> None:
    _check_common(out, name, rows)
    _check_vocabulary(out, name, rows, "grade", GRADES)
    _check_vocabulary(out, name, rows, "role", PASSIVE_ROLES)
    _check_vocabulary(out, name, rows, "status", PASSIVE_STATUS)
    _check_vocabulary(out, name, rows, "qualification", PASSIVE_QUALIFICATION)
    number_column = "value_f" if rows and "value_f" in rows[0] else "value_ohm"
    for r in rows:
        if r["_value"] is None:
            out.append(Finding(name, r["id"], f"value {r['value']!r} does not parse"))
        elif r.get(number_column):
            try:
                stated = float(r[number_column])
            except ValueError:
                out.append(Finding(name, r["id"], f"{number_column} {r[number_column]!r} is not a number"))
            else:
                if not _same_value(stated, r["_value"]):
                    out.append(Finding(name, r["id"], f"value {r['value']!r} and {number_column} {stated:g} disagree"))
        if r["package"] not in _PACKAGES:
            out.append(Finding(name, r["id"], f"package {r['package']!r} is not an imperial code"))
        elif r.get("footprint") and package_of(r["footprint"]) and package_of(r["footprint"]) != r["package"]:
            out.append(Finding(name, r["id"], f"footprint {r['footprint']!r} is not a {r['package']} footprint"))
    # the resolver's view: one default per value, package and grade
    defaults: dict[tuple, list[str]] = {}
    for r in rows:
        if r["role"] == "default" and r["status"] == "active":
            defaults.setdefault((r["_kind"], r["_value"], r["package"], r["grade"]), []).append(r["id"])
    for key, ids in defaults.items():
        if len(ids) > 1:
            out.append(
                Finding(
                    name, ids[0], f"{len(ids)} active default rows for {key[1]:g} {key[2]} {key[3]}: {', '.join(ids)}"
                )
            )


def _check_ics(out: list[Finding], name: str, rows: list[dict[str, str]]) -> None:
    _check_common(out, name, rows)
    _check_vocabulary(out, name, rows, "role", IC_ROLES)
    _check_vocabulary(out, name, rows, "compat", IC_COMPAT)
    _check_vocabulary(out, name, rows, "qualification", IC_QUALIFICATION)
    _check_vocabulary(out, name, rows, "lifecycle", IC_LIFECYCLE)
    _check_vocabulary(out, name, rows, "verified", ("true", "false"))
    slots: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        if not r["slot"]:
            out.append(Finding(name, r["id"], "no slot"))
            continue
        slots.setdefault(r["slot"], []).append(r)
        if r["role"] == "reference" and r["compat"] != "reference":
            out.append(Finding(name, r["id"], f"a reference row with compat {r['compat']!r}"))
        if r["role"] != "reference" and r["compat"] == "reference":
            out.append(Finding(name, r["id"], f"compat reference on a {r['role']} row"))
        if r["id"] and r["slot"] and not r["id"].startswith(r["slot"] + "."):
            out.append(Finding(name, r["id"], f"id does not start with the slot {r['slot']!r}"))
    for slot, group in slots.items():
        refs = [r for r in group if r["role"] == "reference"]
        if len(refs) != 1:
            out.append(Finding(name, slot, f"{len(refs)} reference rows in the slot (one expected)"))
        flights = [r for r in group if r["role"] == "flight"]
        if len(flights) > 1:
            out.append(Finding(name, slot, f"{len(flights)} flight rows in the slot (at most one)"))


def check(catalog: Catalog) -> list[Finding]:
    """What is wrong with the catalogs as data: vocabularies, ids, values against packages, slot shapes."""
    out: list[Finding] = []
    for name in PASSIVE_FILES:
        if name in catalog.source:
            kind = "c" if "capacitor" in name else "r"
            _check_passives(out, name, [r for r in catalog.passives if r["_kind"] == kind])
    if IC_FILE in catalog.source:
        _check_ics(out, IC_FILE, catalog.ics)
    if OTHER_FILE in catalog.source:
        _check_ics(out, OTHER_FILE, catalog.other)
    mpns: dict[str, list[tuple[str, str]]] = {}
    slots: dict[str, set[str]] = {}
    for name, rows in ((IC_FILE, catalog.ics), (OTHER_FILE, catalog.other)):
        for r in rows:
            if r["mpn"]:
                mpns.setdefault(r["mpn"].casefold(), []).append((name, r["id"]))
            if r["slot"]:
                slots.setdefault(r["slot"], set()).add(name)
    for hits in mpns.values():
        if len(hits) > 1:
            out.append(Finding(hits[0][0], hits[0][1], f"mpn shared by {', '.join(i for _, i in hits)}"))
    for slot, files in slots.items():
        if len(files) > 1:
            out.append(Finding(" and ".join(sorted(files)), slot, "slot name used in both files"))
    return out


# ---------------------------------------------------------------------------
# The generated sections of an ICs-shaped README
# ---------------------------------------------------------------------------

SLOTS_HEADING = "## 3. Slots"
CATALOG_HEADING = "## 4. Catalog"
COLUMNS_HEADING = "## 5. Column reference"


def _qualification(r: dict[str, str]) -> str:
    return r["qualification"] + (f" G{r['aec_grade']}" if r.get("aec_grade") else "")


def _temperature(r: dict[str, str]) -> str:
    lo, hi = r.get("temp_min_c", ""), r.get("temp_max_c", "")
    return f"{lo} to {hi}" if lo and hi else ""


def _flags(r: dict[str, str]) -> str:
    out = [r["lifecycle"]] if r.get("lifecycle") not in ("active", "", None) else []
    if r.get("verified") != "true":
        out.append("unverified")
    return ", ".join(out)


def _slot_order(rows: list[dict[str, str]]) -> list[str]:
    order: list[str] = []
    for r in rows:
        if r["slot"] not in order:
            order.append(r["slot"])
    return order


def slots_section(rows: list[dict[str, str]]) -> str:
    out = [SLOTS_HEADING, "", "| Slot | Function | Reference | Flight | Used on |", "| --- | --- | --- | --- | --- |"]
    for slot in _slot_order(rows):
        group = [r for r in rows if r["slot"] == slot]
        ref = next((r for r in group if r["role"] == "reference"), group[0])
        flight = next((r for r in group if r["role"] == "flight"), None)
        if flight:
            text = f"`{flight['mpn']}` ({flight['compat']})"
        elif ref["qualification"] == "accepted":
            text = "reference accepted"
        elif ref["qualification"] in QUALIFIED:
            text = "reference is qualified"
        else:
            text = "none found"
        used = ", ".join(u.strip() for u in ref.get("used_on", "").split(";") if u.strip())
        out.append(f"| `{slot}` | {ref.get('function', '')} | `{ref['mpn']}` | {text} | {used} |")
    return "\n".join(out)


def catalog_section(rows: list[dict[str, str]], intro: str) -> str:
    out = [CATALOG_HEADING, "", intro]
    for slot in _slot_order(rows):
        group = sorted(
            (r for r in rows if r["slot"] == slot), key=lambda r: {"reference": 0, "flight": 1}.get(r["role"], 2)
        )
        out += [
            "",
            f"### `{slot}` – {group[0].get('function', '')}",
            "",
            "| Role | Compat | MPN | Mfr. | Pkg | Qual. | Temp | LCSC | Flags | Difference |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in group:
            pkg = r.get("package_code") or r.get("package", "")
            out.append(
                f"| {r['role']} | {r['compat']} | `{r['mpn']}` | {r['manufacturer']} | {pkg} | {_qualification(r)} | "
                f"{_temperature(r)} | {r.get('lcsc', '')} | {_flags(r)} | {r.get('difference', '')} |"
            )
    return "\n".join(out)


def regenerate_readme(text: str, rows: list[dict[str, str]]) -> str | None:
    """``text`` with its slots and catalog sections rebuilt from ``rows``; ``None`` without the three headings."""
    try:
        s3, s4, s5 = text.index(SLOTS_HEADING), text.index(CATALOG_HEADING), text.index(COLUMNS_HEADING)
    except ValueError:
        return None
    if not s3 < s4 < s5:
        return None
    lines = text[s4:s5].split("\n")
    intro = lines[2] if len(lines) > 2 else ""
    return text[:s3] + slots_section(rows) + "\n\n" + catalog_section(rows, intro) + "\n\n" + text[s5:]
