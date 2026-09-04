# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def fixed_terminal(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
