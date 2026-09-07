# SPDX-License-Identifier: MIT
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def fixed_terminal(monkeypatch, tmp_path):
    monkeypatch.setenv("COLUMNS", "120")
    monkeypatch.chdir(tmp_path)
    # The fixture's R-0603 model points at ${KICAD8_3DMODEL_DIR}; keep the
    # host's KiCad installation from resolving it.
    monkeypatch.delenv("KICAD8_3DMODEL_DIR", raising=False)


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    """A writable copy of the fixture library project, cwd inside it."""
    root = tmp_path / "project"
    shutil.copytree(FIXTURES / "project", root)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def no_kicad_cli(monkeypatch):
    monkeypatch.setattr("bac_kicad_libcheck.kicadcli.shutil.which", lambda name: None)


@pytest.fixture
def fake_kicad_cli(monkeypatch):
    """A kicad-cli stand-in that writes the JSON report the test supplies.

    Returns a setter: ``fake({"violations": [...]}, {"sheets": [...]})`` for
    the DRC and ERC payloads; the calls made are collected in ``fake.calls``.
    """
    import json
    import subprocess

    from bac_kicad_libcheck import kicadcli

    state: dict[str, dict] = {"erc": {"sheets": []}, "drc": {"violations": []}}
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        kind = "erc" if "erc" in cmd else "drc"
        out = Path(cmd[cmd.index("-o") + 1])
        out.write_text(json.dumps(state[kind]), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(kicadcli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(kicadcli.subprocess, "run", fake_run)

    def setter(erc: dict | None = None, drc: dict | None = None) -> None:
        if erc is not None:
            state["erc"] = erc
        if drc is not None:
            state["drc"] = drc

    setter.calls = calls  # type: ignore[attr-defined]
    return setter
