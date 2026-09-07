# SPDX-License-Identifier: MIT
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bac_common import config as config_module

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE_RULES = Path(__file__).resolve().parents[1] / "examples" / "rules"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config" / "bac")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "120")
    return tmp_path


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """A writable copy of the four fixtures laid out as a .kicad_symdir and a .pretty."""
    root = tmp_path / "libs"
    symdir = root / "bac.kicad_symdir"
    pretty = root / "bac.pretty"
    symdir.mkdir(parents=True)
    pretty.mkdir()
    for f in FIXTURES.iterdir():
        shutil.copy(f, symdir / f.name if f.suffix == ".kicad_sym" else pretty / f.name)
    return root
