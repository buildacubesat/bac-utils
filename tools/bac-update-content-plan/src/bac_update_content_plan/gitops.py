# SPDX-License-Identifier: MIT
"""The few git operations the tool needs, on the ``git`` binary itself.

Every call is an argv list with ``-C repo``; failures become
:class:`~bac_common.errors.ExternalToolError` with git's last stderr line
as the detail. The repository is checked and put on the right branch
*before* the file is written, so a failed checkout never leaves a
regenerated file behind in the wrong state.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from bac_common.errors import ExternalToolError

__all__ = ["Repo"]


class Repo:
    def __init__(self, path: Path) -> None:
        self.path = path

    # -- plumbing --------------------------------------------------------------

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        if shutil.which("git") is None:
            raise ExternalToolError("git is not installed or not on PATH.")
        proc = subprocess.run(
            ["git", "-C", str(self.path), *args],
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        if check and proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).strip().splitlines()
            detail = tail[-1] if tail else f"exit {proc.returncode}"
            raise ExternalToolError(f"git {args[0]} failed in {self.path}", detail)
        return proc

    # -- checks ----------------------------------------------------------------

    def check(self) -> None:
        """The path must be an existing git work tree."""
        if not self.path.is_dir():
            raise ExternalToolError(f"Repository does not exist: {self.path}", "Check [output] repo in the config.")
        proc = self.run("rev-parse", "--is-inside-work-tree", check=False)
        if proc.returncode != 0 or proc.stdout.strip() != "true":
            raise ExternalToolError(f"Not a git work tree: {self.path}", "Check [output] repo in the config.")

    def current_branch(self) -> str | None:
        """The checked-out branch, or ``None`` on a detached HEAD."""
        proc = self.run("symbolic-ref", "--quiet", "--short", "HEAD", check=False)
        return proc.stdout.strip() or None

    def has_branch(self, branch: str) -> bool:
        return self.run("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0

    def show(self, branch: str, rel_file: str) -> str | None:
        """The file's content on ``branch``, or ``None`` when it does not exist there."""
        proc = self.run("show", f"{branch}:{rel_file}", check=False)
        return proc.stdout if proc.returncode == 0 else None

    def checkout(self, branch: str) -> None:
        self.run("checkout", "--quiet", branch)

    def has_staged(self, rel_file: str) -> bool:
        """Whether the index differs from HEAD for ``rel_file`` (a new file counts)."""
        proc = self.run("diff", "--cached", "--quiet", "--", rel_file, check=False)
        if proc.returncode not in (0, 1):
            tail = (proc.stderr or proc.stdout).strip().splitlines()
            raise ExternalToolError(f"git diff failed in {self.path}", tail[-1] if tail else f"exit {proc.returncode}")
        return proc.returncode == 1

    # -- changes ---------------------------------------------------------------

    def add(self, rel_file: str) -> None:
        self.run("add", "--", rel_file)

    def commit(self, message: str, rel_file: str) -> str:
        """Commit ``rel_file`` only – whatever else the user has staged stays staged – and return the short hash."""
        self.run("commit", "--quiet", "-m", message, "--", rel_file)
        return self.run("rev-parse", "--short", "HEAD").stdout.strip()

    def push(self, remote: str, branch: str) -> None:
        self.run("push", "--quiet", remote, branch)
