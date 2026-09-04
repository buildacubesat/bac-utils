# SPDX-License-Identifier: MIT
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Make csr_testkit importable under --import-mode=importlib.
sys.path.insert(0, str(Path(__file__).parent))

from csr_testkit import EPS_MD, TOOLS_MD  # noqa: E402


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "CubeSat-Resources"
    (root / "docs").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "docs" / "eps.md").write_text(EPS_MD, encoding="utf-8")
    (root / "docs" / "tools.md").write_text(TOOLS_MD, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
    return root
