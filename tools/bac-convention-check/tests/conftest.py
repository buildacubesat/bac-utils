# SPDX-License-Identifier: MIT
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Every guide rule fires exactly once in this tree; see test_rules.py for the map.
DIRTY_FILES: dict[str, str] = {
    "README.md": "# demo\n\nIntro with an em dash — here.\nIt's ‘curly’ and “quoted”.\nA 100x100 mm board.\n"
    "Enjoy 🚀 the Bac project, buildacubesat says hi.\nStraße 12,059 CHF.\nSee github.com/buildacubesat/bac-hardware.\n"
    "The SPI master drives it.\nThe Internal Tools Design Language Guide said amber.\n",
    "src/demo/cli.py": "import argparse\n\ndef main():\n    pass\n",
    "src/demo/other.py": "# SPDX-License-Identifier: MIT\nAPI_KEY = 'sk-live-0123456789abcdef'\n",
    "Bac-notes.txt": "plain\n",
    "data/config-v1.2.yml": "a: 1\n",
    "pyproject.toml": '[project]\nname = "demo-tool"\nversion = "0.1.0"\nlicense = "MIT"\nrequires-python = ">=3.10"\n'
    'dependencies = ["rich<14", "pyyaml"]\n\n[project.scripts]\ndemo = "demo.main:run"\n\n'
    '[build-system]\nrequires = ["setuptools"]\nbuild-backend = "setuptools.build_meta"\n',
    "no-license/pyproject.toml": '[project]\nname = "bac-nolic"\nrequires-python = ">=3.11"\n\n'
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n',
}

CLEAN_FILES: dict[str, str] = {
    "README.md": "# bac-demo v0.1.0\n\nBuild a CubeSat – a demo. Costs 12'059 CHF – fine.\n\n## 1. Version history\n\n"
    "| Version | Date | Change |\n| :-- | :-- | :-- |\n| 0.1.0 | 2026-09-02 | Initial. |\n",
    "src/bac_demo/cli.py": "# SPDX-License-Identifier: MIT\nfrom bac_common import cli\n\n"
    'def main():\n    cli.make_parser("bac-demo", "0.1.0", "Demo.")\n',
    "pyproject.toml": '[project]\nname = "bac-demo"\nversion = "0.1.0"\nlicense = { text = "MIT" }\n'
    'requires-python = ">=3.11"\ndependencies = ["rich>=13.7"]\n\n[project.scripts]\n'
    'bac-demo = "bac_demo.cli:main"\n\n[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n',
    ".github/workflows/ci.yml": "name: CI\n",
    "image.bin": "\x00\x01binary — with an em dash that must not be scanned",
}


def write_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


@pytest.fixture
def dirty(tmp_path: Path) -> Path:
    return write_tree(tmp_path / "dirty", DIRTY_FILES)


@pytest.fixture
def clean(tmp_path: Path) -> Path:
    return write_tree(tmp_path / "clean", CLEAN_FILES)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    root = write_tree(tmp_path / "repo", CLEAN_FILES)
    (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (root / "ignored").mkdir()
    (root / "ignored" / "x.md").write_text("em dash — ignored by git\n", encoding="utf-8")
    (root / "untracked.md").write_text("em dash — untracked but not ignored\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    return root
