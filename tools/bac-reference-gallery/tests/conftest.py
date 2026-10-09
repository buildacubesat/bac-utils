# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No test reads a .env or a browser override from the machine, and none leaks one to the next.

    python-dotenv writes to os.environ directly, so the environment is restored by hand.
    """
    from bac_reference_gallery import cli

    saved = dict(os.environ)
    real_load_env = cli.load_env
    monkeypatch.setattr(cli, "load_env", lambda env_file=None: real_load_env(env_file) if env_file else None)
    monkeypatch.chdir(tmp_path)
    os.environ.pop("BAC_CHROMIUM_PATH", None)
    yield
    os.environ.clear()
    os.environ.update(saved)
