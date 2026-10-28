# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from bac_common import config as config_module

# page_testkit is importable under --import-mode=importlib
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No test sees the developer's config, environment or Pages clone; .env loads are undone."""
    saved = dict(os.environ)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("BAC_PAGE_REPO", raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config" / "bac")
    monkeypatch.setattr("bac_page.cli.LEGACY_ENV", tmp_path / "legacy" / ".env")
    monkeypatch.chdir(tmp_path)
    yield
    os.environ.clear()
    os.environ.update(saved)
