# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "nets.txt"


@pytest.fixture(autouse=True)
def fixed_terminal(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")


@pytest.fixture
def example_text() -> str:
    return EXAMPLE.read_text(encoding="utf-8")
