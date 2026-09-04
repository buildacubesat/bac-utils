# SPDX-License-Identifier: MIT
"""Error taxonomy shared by BAC tools.

Every expected failure is a :class:`BacError` carrying an exit code. The
boundary in :func:`bac_common.cli.run` converts it to a formatted stderr
message and ``SystemExit``; tracebacks are shown only with ``--debug``.
Tools subclass :class:`BacError` for their own categories and keep the exit
codes of the BAC Project & Tooling Guide §3.8: 0 success, 1 runtime error,
2 bad arguments.
"""

from __future__ import annotations


class BacError(Exception):
    """Base class for all expected tool errors.

    ``detail`` is an optional second line shown indented under the message,
    typically the actionable next step ("Run `tool --init`.").
    """

    exit_code: int = 1

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __str__(self) -> str:
        return self.message


class ConfigError(BacError):
    """Missing or invalid configuration: config file, env vars, paths, credentials."""


class UsageError(BacError):
    """Bad arguments discovered after argparse has finished (exit code 2)."""

    exit_code = 2


class ExternalToolError(BacError):
    """A required external program is missing or failed (kicad-cli, ffmpeg, git)."""


class UserAbort(BacError):
    """The user explicitly cancelled. A clean exit, so the exit code is 0."""

    exit_code = 0

    def __init__(self, message: str = "Aborted.", detail: str | None = None) -> None:
        super().__init__(message, detail)


class SkipItem(Exception):
    """Skip the current item of a batch and continue.

    Deliberately not a :class:`BacError`: skipping one item is normal control
    flow that a per-item loop catches.
    """
