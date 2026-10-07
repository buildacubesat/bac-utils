# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in ("BAC_SUITE_CONFIG", "BAC_DB_DSN", "BAC_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def files_config(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    path = tmp_path / "bac-suite.toml"
    path.write_text(f'[storage]\nbackend = "files"\ndata_dir = "{data}"\n', encoding="utf-8")
    return path
