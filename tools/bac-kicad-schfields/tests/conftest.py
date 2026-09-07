# SPDX-License-Identifier: MIT
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE_RULES = Path(__file__).resolve().parents[1] / "examples" / "rules"


@pytest.fixture(autouse=True)
def fixed_terminal(monkeypatch, tmp_path):
    monkeypatch.setenv("COLUMNS", "120")
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A writable copy of the two-sheet fixture project."""
    root = tmp_path / "project"
    root.mkdir()
    for f in FIXTURES.iterdir():
        shutil.copy(f, root / f.name)
    return root
