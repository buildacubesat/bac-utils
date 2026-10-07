# SPDX-License-Identifier: MIT
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from pricing_testkit import FIXTURES, write_files_config  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in ("BAC_SUITE_CONFIG", "BAC_DB_DSN", "BAC_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def data_dir(tmp_path) -> Path:
    """A writable copy of the fixture files."""
    target = tmp_path / "data"
    target.mkdir()
    for f in FIXTURES.iterdir():
        (target / f.name).write_bytes(f.read_bytes())
    return target


@pytest.fixture
def files_settings(tmp_path, data_dir):
    from bac_suite_db import config

    path = write_files_config(tmp_path, data_dir)
    return config.load_settings(path)


@pytest.fixture
def fake_conn(monkeypatch):
    from bac_suite_db import db
    from bac_suite_db.testing import FakeConn

    conn = FakeConn()
    monkeypatch.setattr(db, "connect", lambda dsn: conn)
    return conn
