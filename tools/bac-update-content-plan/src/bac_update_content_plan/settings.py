# SPDX-License-Identifier: MIT
"""Configuration: ``~/.config/bac/bac-update-content-plan.toml`` plus the key path from ``.env``.

Everything specific to one project – the sheet, the range, the repository
and the file inside it – lives in the TOML written by ``--init``. The
service-account key is a secret and comes from ``BAC_GCP_CREDENTIALS``
(``.env`` or the environment); ``[credentials] file`` in the TOML is the
fallback for a machine where the key sits in a fixed place.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from bac_common import gsheets
from bac_common.config import expand, require_setup
from bac_common.errors import ConfigError

__all__ = ["TOOL", "Settings", "load_settings", "config_text", "DEFAULTS"]

TOOL = "bac-update-content-plan"

DEFAULTS = {
    "range": "'Content Plan'!A:E",
    "title": "Content Plan",
    "status_column": "Status",
    "file": "content/content-plan.md",
    "branch": "main",
    "remote": "origin",
}


@dataclass(frozen=True, slots=True)
class Settings:
    sheet_id: str
    a1_range: str
    title: str
    status_column: str
    repo: Path
    file: str
    branch: str
    remote: str
    credentials_file: str

    @property
    def target(self) -> Path:
        return self.repo / self.file

    @property
    def sheet_url(self) -> str:
        return gsheets.sheet_url(self.sheet_id)


def _table(config: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = config.get(name, {})
    if not isinstance(value, Mapping):
        raise ConfigError(f"[{name}] must be a table.", f"See `{TOOL} --init` for the shape.")
    return value


def _text(table: Mapping[str, object], key: str, default: str = "") -> str:
    value = table.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string.", f"See `{TOOL} --init` for the shape.")
    return value.strip() or default


def load_settings(config: Mapping[str, object]) -> Settings:
    """Validate the loaded TOML and resolve paths. Missing essentials point at ``--init``."""
    require_setup(TOOL, config, "sheet.id", "output.repo")
    sheet, output, credentials = _table(config, "sheet"), _table(config, "output"), _table(config, "credentials")
    file = _text(output, "file", DEFAULTS["file"])
    if Path(file).is_absolute() or ".." in Path(file).parts:
        raise ConfigError("output.file must be a relative path inside the repository.", f"Got {file!r}.")
    # An absent key means the default column; an explicit "" switches the filter off.
    status_column = sheet.get("status_column", DEFAULTS["status_column"])
    if not isinstance(status_column, str):
        raise ConfigError("status_column must be a string.", f"See `{TOOL} --init` for the shape.")
    return Settings(
        sheet_id=gsheets.spreadsheet_id(_text(sheet, "id")),
        a1_range=_text(sheet, "range", DEFAULTS["range"]),
        title=_text(sheet, "title", DEFAULTS["title"]),
        status_column=status_column.strip(),
        repo=expand(_text(output, "repo")),
        file=file,
        branch=_text(output, "branch", DEFAULTS["branch"]),
        remote=_text(output, "remote", DEFAULTS["remote"]),
        credentials_file=_text(credentials, "file"),
    )


def config_text(sheet_id: str, repo: str, file: str, branch: str) -> str:
    """The TOML ``--init`` writes, with the answers filled in."""
    return f"""# {TOOL}.toml
# Build a CubeSat – {TOOL} configuration. The service-account key is not
# in here: set {gsheets.CREDENTIALS_ENV} in a .env file (see .env.example) or
# name it under [credentials].

[sheet]
id = "{sheet_id}"                 # spreadsheet id (the part between /d/ and /edit in its URL)
range = "{DEFAULTS["range"]}"     # A1 range; the first row is the table header
title = "{DEFAULTS["title"]}"     # Markdown H1 above the table
status_column = "{DEFAULTS["status_column"]}"  # rows with an empty cell in this column are left out; "" keeps every row

[output]
repo = "{repo}"       # git work tree the file is written into
file = "{file}"       # relative to repo
branch = "{branch}"
remote = "{DEFAULTS["remote"]}"

[credentials]
file = ""   # service-account JSON key; {gsheets.CREDENTIALS_ENV} overrides this
"""
