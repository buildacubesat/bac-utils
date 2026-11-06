# SPDX-License-Identifier: MIT
"""Settings: ``~/.config/bac/bac-kicad-generate-artifacts.toml``, written by ``--init``.

Everything has a default, so the tool runs without a config file. The file
is where a project records what is specific to it: the output root, the
asset prefix and hardware repository name, author and organisation for the
STEP header, the BOM scheme and field list, the part catalogs, the iBOM plugin path and
the QR marker.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from bac_common import config as bac_config
from bac_common.errors import ConfigError

from . import TOOL_NAME

__all__ = ["Settings", "load_settings", "config_template", "find_ibom_script", "desktop_dir"]

BOM_SCHEMES = ("thin", "legacy")
# The plain export's columns per scheme: the thin schematic (the templates' BOM preset plus Build) and the
# 0.7-era field vocabulary of projects that carry their part data on the symbols.
BOM_FIELDS = {
    "thin": "Reference,${QUANTITY},Value,Footprint,Manufacturer PN,${DNP},Build,Datasheet",
    "legacy": (
        "${ITEM_NUMBER},Reference,${QUANTITY},Manufacturer,Manufacturer PN,Value,Package,Tolerance,"
        "R Rated Power,C Class,C D Rated Voltage,Notes,${DNP},Digikey URL"
    ),
}
BOM_LABELS = {
    "thin": "Reference,Qty,Value,Footprint,Manufacturer PN,DNP,Build,Datasheet",
    "legacy": (
        "#,Designator,Qty,Manufacturer,Manufacturer PN,Value,Package,Tolerance,R Rated Power,C Class,"
        "C D Rated Voltage,Notes,DNP,Digikey URL"
    ),
}
BOM_GROUP_BY = {
    "thin": "Value,Footprint,Manufacturer PN,${DNP},Build",
    "legacy": (
        "Value,Package,Manufacturer,Manufacturer PN,Tolerance,R Rated Power,C Class,C D Rated Voltage,Notes,${DNP},"
        "Digikey URL"
    ),
}
# Symbol fields only a legacy schematic carries; a thin-scheme run that meets them on a project gets a hint.
LEGACY_FIELDS = ("C Class", "R Rated Power", "C D Rated Voltage")

# Relative to the home directory: where KiCad's plugin manager installs plugins on Linux, Windows and macOS.
IBOM_GLOBS = (
    ".local/share/kicad/*/3rdparty/plugins/org_openscopeproject_InteractiveHtmlBom/generate_interactive_bom.py",
    "Documents/KiCad/*/3rdparty/plugins/org_openscopeproject_InteractiveHtmlBom/generate_interactive_bom.py",
    "Library/Application Support/kicad/*/3rdparty/plugins/org_openscopeproject_InteractiveHtmlBom/"
    "generate_interactive_bom.py",
)


@dataclass(frozen=True)
class Settings:
    output_root: Path | None = None  # None: the desktop
    prefix: str = "bac"
    hardware_root: str = "bac-hardware"
    author: str = ""
    organization: str = ""
    bom_scheme: str = "thin"
    bom_fields: str = ""  # empty: the scheme's columns
    bom_labels: str = ""
    bom_group_by: str = ""
    catalog_passives: Path | None = None  # folder with bac-passives-capacitors.csv and -resistors.csv
    catalog_ics: Path | None = None  # folder with bac-ics.csv
    catalog_other: Path | None = None  # folder with bac-other.csv (connectors, switches, LEDs – the ICs' columns)
    deprecations: tuple[str, ...] = ()  # keys the config still uses under an old name
    ibom_script: Path | None = None
    ibom_python: str | None = None
    qr_marker: str = "QR_MARKER"
    qr_text: str = ""
    timeout: float = 600.0
    source: Path | None = field(default=None, compare=False)

    def bom_columns(self, scheme: str) -> tuple[str, str, str]:
        """Fields, labels and grouping of the plain export: the config's when set, else ``scheme``'s."""
        return (
            self.bom_fields or BOM_FIELDS[scheme],
            self.bom_labels or BOM_LABELS[scheme],
            self.bom_group_by or BOM_GROUP_BY[scheme],
        )


def desktop_dir() -> Path:
    xdg = os.environ.get("XDG_DESKTOP_DIR")
    return Path(xdg).expanduser() if xdg else Path.home() / "Desktop"


def find_ibom_script() -> Path | None:
    """The InteractiveHtmlBom plugin script, where KiCad's plugin manager installs it; newest KiCad first."""
    for pattern in IBOM_GLOBS:
        hits = sorted(Path.home().glob(pattern), key=_version_key, reverse=True)
        if hits:
            return hits[0]
    return None


def _version_key(script: Path) -> tuple[int, ...]:
    """``…/kicad/10.0/3rdparty/plugins/<plugin>/script.py`` → ``(10, 0)``, so 10.0 sorts after 9.0."""
    version = script.parents[3].name
    return tuple(int(part) if part.isdigit() else -1 for part in version.split("."))


def _table(data: dict, name: str) -> dict:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] in the config must be a table.")
    return value


def _text(table: dict, key: str, default: str) -> str:
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"{key} in the config must be a string.")
    return value


def load_settings(config_path: str | os.PathLike[str] | None) -> Settings:
    data = bac_config.load_toml(TOOL_NAME, config_path)
    output, naming, meta = _table(data, "output"), _table(data, "naming"), _table(data, "metadata")
    bom, ibom, qr = _table(data, "bom"), _table(data, "ibom"), _table(data, "qr")
    catalog = _table(data, "catalog")
    root = _text(output, "root", "")
    passives, ics = _text(catalog, "passives", ""), _text(catalog, "ics", "")
    other, parts = _text(catalog, "other", ""), _text(catalog, "parts", "")
    deprecations = []
    if parts and not other:
        other = parts
        deprecations.append("parts in [catalog] is now other (the folder resources/catalog/other/ with bac-other.csv)")
    scheme = _text(bom, "scheme", "thin")
    if scheme not in BOM_SCHEMES:
        raise ConfigError(f"scheme in [bom] must be one of {', '.join(BOM_SCHEMES)}, not {scheme!r}.")
    script = _text(ibom, "script", "")
    timeout = output.get("timeout_s", 600)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ConfigError("timeout_s in [output] must be a positive number.")
    path = Path(config_path).expanduser() if config_path else bac_config.default_config_path(TOOL_NAME)
    return Settings(
        output_root=Path(root).expanduser() if root else None,
        prefix=_text(naming, "prefix", "bac").strip("-") or "bac",
        hardware_root=_text(naming, "hardware_root", "bac-hardware"),
        author=_text(meta, "author", ""),
        organization=_text(meta, "organization", ""),
        bom_scheme=scheme,
        bom_fields=_text(bom, "fields", ""),
        bom_labels=_text(bom, "labels", ""),
        bom_group_by=_text(bom, "group_by", ""),
        catalog_passives=Path(passives).expanduser() if passives else None,
        catalog_ics=Path(ics).expanduser() if ics else None,
        catalog_other=Path(other).expanduser() if other else None,
        deprecations=tuple(deprecations),
        ibom_script=Path(script).expanduser() if script else None,
        ibom_python=_text(ibom, "python", "") or None,
        qr_marker=_text(qr, "marker", "QR_MARKER") or "QR_MARKER",
        qr_text=_text(qr, "text", ""),
        timeout=float(timeout),
        source=path if path.exists() else None,
    )


def config_template(ibom_script: Path | None, today: date | None = None) -> str:
    """The file ``--init`` writes: every key with its default and a comment."""
    stamp = (today or date.today()).isoformat()
    ibom = ibom_script.as_posix() if ibom_script else ""  # forward slashes: a Windows path has backslashes TOML rejects
    return f'''# {TOOL_NAME} – written by --init on {stamp}. Every key is optional.

[output]
# Where the per-project folders go. Empty: $XDG_DESKTOP_DIR or ~/Desktop. --desktop overrides.
root = ""
# Per-command limit for kicad-cli and friends, in seconds.
timeout_s = 600

[naming]
# Artifacts are named <prefix>-<subsystem>-<name>-<vXrY>-<kind>.<ext>. The subsystem is
# the folder below hardware_root on the project's path; without one the prefix stands alone.
prefix = "bac"
hardware_root = "bac-hardware"

[metadata]
# Written into the STEP file header (FILE_NAME author and organisation) when the exporter left them empty.
author = ""
organization = ""

[bom]
# "thin": the schematic carries Value, Footprint and Manufacturer PN and the catalogs supply the rest
# (README §5). "legacy": the symbols carry Manufacturer, Package, Tolerance and the rating fields
# themselves; no catalog resolution. --bom-scheme overrides per run.
scheme = "thin"
# kicad-cli sch export bom --fields / --labels / --group-by. Empty: the scheme's columns.
# ${{...}} are KiCad's built-in fields.
fields = ""
labels = ""
group_by = ""

[catalog]
# The part catalogs the bom stage resolves the schematic against (README §5): the folder with
# bac-passives-capacitors.csv and bac-passives-resistors.csv, the folder with bac-ics.csv, and the
# folder with bac-other.csv (connectors, switches, LEDs, holders – the ICs' columns). Empty: the
# stage writes the plain export only.
passives = ""
ics = ""
other = ""

[ibom]
# The InteractiveHtmlBom plugin's generate_interactive_bom.py (--ibom runs it with a python that imports pcbnew).
script = "{ibom}"
# Python interpreter for the plugin. Empty: /usr/bin/python3, then python3 on PATH.
python = ""

[qr]
# Text of the gr_text_box items the QR stage replaces, and the default text to encode (--qr overrides).
marker = "QR_MARKER"
text = ""
'''
