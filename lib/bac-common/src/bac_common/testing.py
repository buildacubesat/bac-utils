# SPDX-License-Identifier: MIT
"""Test helpers so every tool can prove the guide's contract with three lines.

::

    from bac_common.testing import invoke, assert_standard_flags
    from bac_example.cli import main, TOOL, VERSION

    def test_contract():
        assert_standard_flags(main, TOOL, VERSION)

    def test_dry_run(tmp_path):
        result = invoke(main, ["--dry-run", str(tmp_path)])
        assert result.exit_code == 0
        assert "dry run" in result.stdout
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass

from . import ui
from .cli import MainFn, run

__all__ = ["Result", "invoke", "assert_standard_flags"]

HELP_MAX_LINES = 24


@dataclass(slots=True)
class Result:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


def invoke(main: MainFn, argv: Sequence[str]) -> Result:
    """Run ``main`` inside :func:`bac_common.cli.run`, capturing output and the exit code."""
    out, err = io.StringIO(), io.StringIO()
    # Rich consoles resolve sys.stdout/sys.stderr at print time, so the
    # redirects below capture them as long as no explicit file was set.
    with redirect_stdout(out), redirect_stderr(err):
        try:
            run(main, list(argv))
        except SystemExit as exc:
            code = exc.code
        else:  # pragma: no cover – run() always raises
            code = 0
    if code is None:
        code = 0
    elif not isinstance(code, int):
        code = 1
    return Result(code, out.getvalue(), err.getvalue())


def assert_standard_flags(main: MainFn, tool: str, version: str) -> None:
    """``-v`` prints ``tool vX.Y.Z`` and exits 0; ``--help`` fits on one screen and exits 0."""
    v = invoke(main, ["-v"])
    assert v.exit_code == 0, v.output
    assert v.stdout.strip() == f"{tool} {ui.display_version(version)}", v.stdout

    h = invoke(main, ["--help"])
    assert h.exit_code == 0, h.output
    lines = h.stdout.rstrip("\n").splitlines()
    assert len(lines) <= HELP_MAX_LINES, f"--help is {len(lines)} lines; the guide allows {HELP_MAX_LINES}"
    assert "--debug" not in h.stdout, "--debug must be hidden from --help"
