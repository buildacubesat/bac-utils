# SPDX-License-Identifier: MIT
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make media_testkit importable under --import-mode=importlib.
sys.path.insert(0, str(Path(__file__).parent))

from media_testkit import make_image  # noqa: E402


@pytest.fixture(autouse=True)
def fixed_terminal(monkeypatch, tmp_path):
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    """A folder with a landscape jpg, a portrait png with alpha, a tiny square tif and a stray text file."""
    root = tmp_path / "photos"
    make_image(root / "wide.jpg", (600, 300))
    make_image(root / "tall.png", (200, 500), "RGBA", (0, 0, 255, 128))
    make_image(root / "small.tif", (40, 40))
    (root / "notes.txt").write_text("not an image", encoding="utf-8")
    return root
