# SPDX-License-Identifier: MIT
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))  # maintain_testkit


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No developer config, a fixed terminal width, a scratch working directory."""
    monkeypatch.setenv("COLUMNS", "120")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr("bac_common.config.CONFIG_DIR", tmp_path / "home" / ".config" / "bac")
    monkeypatch.chdir(tmp_path)
