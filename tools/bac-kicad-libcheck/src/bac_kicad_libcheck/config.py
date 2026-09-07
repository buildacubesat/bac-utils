# SPDX-License-Identifier: MIT
"""The project config: which schematic, board and libraries make up the library project.

Libraries are declared explicitly rather than read from ``sym-lib-table`` /
``fp-lib-table`` so the check has a fixed, reviewable scope that does not
drift when someone adds an unrelated library to their table. The file lives
next to the project (``bac-kicad-libcheck.toml``) because it describes the
project, not the user.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from bac_common.errors import ConfigError

TOOL = "bac-kicad-libcheck"
CONFIG_NAME = f"{TOOL}.toml"

DEFAULT_ERC_TYPES = ["lib_symbol_mismatch", "lib_symbol_issues"]
DEFAULT_DRC_TYPES = ["lib_footprint_mismatch", "lib_footprint_issues"]
DEFAULT_MODEL_EXTENSIONS = [".step", ".stp", ".wrl"]

CONFIG_TEMPLATE = f"""# {CONFIG_NAME}
# Build a CubeSat – library project verification. Paths are relative to this
# file. Nicknames must match the project's library tables: they are what
# appears in every lib_id.

[project]
schematic = "LibraryProject.kicad_sch"
board = "LibraryProject.kicad_pcb"

[[symbol_library]]
nickname = "bac"
path = "libs/bac.kicad_symdir"

[[footprint_library]]
nickname = "bac"
path = "libs/bac.pretty"

# ${{VAR}} in (model …) paths resolves here first, then in the environment;
# ${{KIPRJMOD}} is this directory.
[model_paths]
BAC_LIB_DIR = "."

[kicad]
cli = "kicad-cli"
# The ERC/DRC violation types that mean "placed item differs from its library
# copy". Check the note the run prints if these never appear in a report.
erc_types = [{", ".join(f'"{t}"' for t in DEFAULT_ERC_TYPES)}]
drc_types = [{", ".join(f'"{t}"' for t in DEFAULT_DRC_TYPES)}]

[models]
extensions = [{", ".join(f'"{e}"' for e in DEFAULT_MODEL_EXTENSIONS)}]
"""


@dataclass(slots=True)
class LibraryEntry:
    nickname: str
    path: Path


@dataclass
class Config:
    root: Path
    schematic: Path
    board: Path
    symbol_libraries: list[LibraryEntry]
    footprint_libraries: list[LibraryEntry]
    kicad_cli: str = "kicad-cli"
    erc_types: list[str] = field(default_factory=lambda: list(DEFAULT_ERC_TYPES))
    drc_types: list[str] = field(default_factory=lambda: list(DEFAULT_DRC_TYPES))
    model_vars: dict[str, str] = field(default_factory=dict)
    model_extensions: list[str] = field(default_factory=lambda: list(DEFAULT_MODEL_EXTENSIONS))


def _resolve(root: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else root / p


def load_config(path: Path) -> Config:
    if not path.is_file():
        raise ConfigError(
            f"Config file not found: {path}", f"Run `{TOOL} --init` in the project directory to create one."
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config file is not valid TOML: {path}", str(exc)) from exc
    root = path.resolve().parent

    project = data.get("project", {})
    if not isinstance(project, dict):
        raise ConfigError(f"{path}: [project] must be a table")
    for key in ("schematic", "board"):
        if not project.get(key):
            raise ConfigError(f"{path}: [project] is missing '{key}'")

    def entries(table_name: str) -> list[LibraryEntry]:
        out: list[LibraryEntry] = []
        for item in data.get(table_name, []):
            if not isinstance(item, dict) or not item.get("nickname") or not item.get("path"):
                raise ConfigError(f"{path}: every [[{table_name}]] needs 'nickname' and 'path'")
            out.append(LibraryEntry(str(item["nickname"]), _resolve(root, str(item["path"]))))
        return out

    symbol_libraries = entries("symbol_library")
    footprint_libraries = entries("footprint_library")
    if not symbol_libraries and not footprint_libraries:
        raise ConfigError(f"{path}: declare at least one [[symbol_library]] or [[footprint_library]]")

    kicad = data.get("kicad", {}) or {}
    models = data.get("models", {}) or {}
    model_paths = data.get("model_paths", {}) or {}
    return Config(
        root=root,
        schematic=_resolve(root, str(project["schematic"])),
        board=_resolve(root, str(project["board"])),
        symbol_libraries=symbol_libraries,
        footprint_libraries=footprint_libraries,
        kicad_cli=str(kicad.get("cli", "kicad-cli")),
        erc_types=[str(t) for t in kicad.get("erc_types", DEFAULT_ERC_TYPES)],
        drc_types=[str(t) for t in kicad.get("drc_types", DEFAULT_DRC_TYPES)],
        model_vars={str(k): str(v) for k, v in model_paths.items()},
        model_extensions=[str(e) for e in models.get("extensions", DEFAULT_MODEL_EXTENSIONS)],
    )
