# SPDX-License-Identifier: MIT
"""Workspace-wide pytest fixtures.

Every test runs with the Rich consoles pinned wide and ``COLUMNS`` at 80, the same widths
``bac_common.testing.invoke`` uses: Rich output is captured unwrapped and untruncated whatever
terminal pytest runs in, while ``--help`` is still measured at the width a user sees.
"""

import pytest

from bac_common import testing, ui


@pytest.fixture(autouse=True)
def _fixed_terminal_widths(monkeypatch):
    monkeypatch.setenv("COLUMNS", str(testing.HELP_COLUMNS))
    monkeypatch.setattr(ui.console, "width", testing.RICH_COLUMNS)
    monkeypatch.setattr(ui.err_console, "width", testing.RICH_COLUMNS)
