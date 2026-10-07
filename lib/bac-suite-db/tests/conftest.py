# SPDX-License-Identifier: MIT
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from suite_testkit import StubEngine, write_suite_config  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """No suite config, DSN or data dir from the developer's machine leaks into a test."""
    for name in ("BAC_SUITE_CONFIG", "BAC_DB_DSN", "BAC_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def suite_config(tmp_path):
    """A postgres-backend config in tmp_path with its data directory; returns the TOML path."""
    return write_suite_config(tmp_path, backend="postgres")


@pytest.fixture
def files_config(tmp_path):
    return write_suite_config(tmp_path, backend="files")


@pytest.fixture
def stub_engine():
    return StubEngine()


@pytest.fixture
def fake_conn(monkeypatch):
    """Every ``db.connect`` in the test returns this one in-memory connection."""
    from bac_suite_db import db
    from bac_suite_db.testing import FakeConn

    conn = FakeConn()
    monkeypatch.setattr(db, "connect", lambda dsn: conn)
    return conn
