# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from bac_common import config as config_module


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("COLUMNS", "120")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config" / "bac")
