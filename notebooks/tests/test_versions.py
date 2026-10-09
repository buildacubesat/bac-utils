# SPDX-License-Identifier: MIT
"""Each notebook folder's pyproject.toml and README header carry the notebook's own TOOL_VERSION."""

import re
import tomllib
from pathlib import Path

import pytest

NOTEBOOKS = Path(__file__).resolve().parents[1]
FOLDERS = sorted(p for p in NOTEBOOKS.glob("bac-*") if (p / "pyproject.toml").is_file())


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda p: p.name)
def test_pyproject_version_follows_tool_version(folder):
    notebook = folder / (folder.name.replace("-", "_") + ".py")
    match = re.search(r'^\s*TOOL_VERSION = "([0-9.]+)"', notebook.read_text(encoding="utf-8"), re.M)
    assert match, f"no TOOL_VERSION in {notebook.name}"
    project = tomllib.loads((folder / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == match.group(1)


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda p: p.name)
def test_readme_header_follows_tool_version(folder):
    notebook = folder / (folder.name.replace("-", "_") + ".py")
    version = re.search(r'^\s*TOOL_VERSION = "([0-9.]+)"', notebook.read_text(encoding="utf-8"), re.M).group(1)
    header = (folder / "README.md").read_text(encoding="utf-8").splitlines()[0]
    match = re.fullmatch(rf"# {re.escape(folder.name)} v([0-9.]+)", header)
    assert match is None or match.group(1) == version, header  # the visualizer's header names no version
