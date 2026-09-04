# SPDX-License-Identifier: MIT
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from bac_issue_print import cli

from bac_common import config as config_module

# Make issue_testkit importable under --import-mode=importlib.
sys.path.insert(0, str(Path(__file__).parent))

from issue_testkit import FakeServer  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """No config file, no .env, no token, fixed width."""
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config" / "bac")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CODEBERG_TOKEN", raising=False)
    monkeypatch.setenv("COLUMNS", "80")
    return tmp_path


@pytest.fixture
def server(monkeypatch) -> FakeServer:
    """Route the CLI's fetches through a FakeServer so nothing touches the network."""
    fake = FakeServer()
    monkeypatch.setattr(cli, "fetch_json", fake)
    return fake
