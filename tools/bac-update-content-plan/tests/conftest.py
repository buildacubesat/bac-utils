# SPDX-License-Identifier: MIT
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from bac_common import config as config_module

# Make contentplan_testkit importable under --import-mode=importlib.
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No test may see the developer's own config, key or docs repository."""
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("BAC_GCP_CREDENTIALS", raising=False)
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config" / "bac")
    monkeypatch.chdir(tmp_path)
