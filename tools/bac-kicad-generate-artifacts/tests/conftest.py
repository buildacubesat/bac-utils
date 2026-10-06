# SPDX-License-Identifier: MIT
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bac_kicad_generate_artifacts import cli
from genart_testkit import DSW, PANEL, SYNTH, TOOLS, FakeRunner  # noqa: E402


@pytest.fixture(autouse=True)
def fixed_terminal(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setattr("bac_kicad_generate_artifacts.stages.WEBP_METHOD", 0)  # the slow encoder is not under test


@pytest.fixture
def no_config(monkeypatch, tmp_path):
    """No ~/.config/bac file and a desktop inside tmp_path, whatever the machine has."""
    monkeypatch.setattr("bac_common.config.CONFIG_DIR", tmp_path / "config")
    monkeypatch.setenv("XDG_DESKTOP_DIR", str(tmp_path / "Desktop"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path


@pytest.fixture
def fake(monkeypatch, no_config):
    """The CLI with kicad-cli and the rasteriser replaced by :class:`FakeRunner`; returns the runner used."""
    holder: dict[str, FakeRunner] = {}

    def make_runner(*, dry_run: bool = False, timeout: float = 600.0) -> FakeRunner:
        r = holder.get("runner") or FakeRunner()
        r.dry_run = dry_run
        holder["runner"] = r
        return r

    monkeypatch.setattr(cli, "find_tools", lambda: TOOLS)
    monkeypatch.setattr(cli, "Runner", make_runner)
    holder["runner"] = FakeRunner()
    return holder["runner"]


@pytest.fixture
def synth(tmp_path) -> Path:
    """A writable copy of the synthetic project (the tool must never touch the fixture itself)."""
    dst = tmp_path / "hw" / "eps" / "bac-synth-v2" / "kicad10"
    shutil.copytree(SYNTH, dst)
    return dst


@pytest.fixture
def panel(tmp_path) -> Path:
    dst = tmp_path / "hw" / "eps" / "bac-synth-panel-v1" / "kicad10"
    shutil.copytree(PANEL, dst)
    return dst


@pytest.fixture
def dsw(tmp_path) -> Path:
    dst = tmp_path / "hw" / "inhibit" / "deployment-switch" / "kicad10"
    shutil.copytree(DSW, dst)
    return dst
