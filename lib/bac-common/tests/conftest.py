# SPDX-License-Identifier: MIT
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from bac_common import config as config_module

# Make demo_tool importable under --import-mode=importlib.
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path, monkeypatch):
    """Point ~/.config/bac at a temp dir and clear .env lookups for every test."""
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config" / "bac")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BAC_TEST_VALUE", raising=False)
    monkeypatch.setenv("COLUMNS", "80")
    return tmp_path / "config" / "bac"
