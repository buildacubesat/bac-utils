# SPDX-License-Identifier: MIT
"""Settings: ``~/.config/bac/bac-kicad-generate-artifacts.toml``, written by ``--init``.

Everything has a default, so the tool runs without a config file. The file
is where a project records what is specific to it: the output root, the
asset prefix and hardware repository name, author and organisation for the
STEP header, the BOM field list, the iBOM plugin path and the QR marker.
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

BOM_FIELDS = (
    "${ITEM_NUMBER},Reference,${QUANTITY},Manufacturer,Manufacturer PN,Value,Package,Tolerance,"
    "R Rated Power,C Class,C D Rated Voltage,Notes,${DNP},Alternative parts,Digikey URL"
)
BOM_LABELS = (
    "#,Designator,Qty,Manufacturer,Manufacturer PN,Value,Package,Tolerance,R Rated Power,C Class,"
    "C D Rated Voltage,Notes,DNP,Alternative parts,Digikey URL"
)
BOM_GROUP_BY = (
    "Value,Package,Manufacturer,Manufacturer PN,Tolerance,R Rated Power,C Class,C D Rated Voltage,Notes,${DNP},"
    "Alternative parts,Digikey URL"
)

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
    bom_fields: str = BOM_FIELDS
    bom_labels: str = BOM_LABELS
    bom_group_by: str = BOM_GROUP_BY
    ibom_script: Path | None = None
    ibom_python: str | None = None
    qr_marker: str = "QR_MARKER"
    qr_text: str = ""
    timeout: float = 600.0
    source: Path | None = field(default=None, compare=False)


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
    root = _text(output, "root", "")
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
        bom_fields=_text(bom, "fields", BOM_FIELDS),
        bom_labels=_text(bom, "labels", BOM_LABELS),
        bom_group_by=_text(bom, "group_by", BOM_GROUP_BY),
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
# kicad-cli sch export bom --fields / --labels / --group-by. ${{...}} are KiCad's built-in fields.
fields = "{BOM_FIELDS}"
labels = "{BOM_LABELS}"
group_by = "{BOM_GROUP_BY}"

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
