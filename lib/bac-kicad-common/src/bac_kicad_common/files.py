# SPDX-License-Identifier: MIT
"""Writing edited files back: backups, confirmation, the dry-run gate."""

from __future__ import annotations

import shutil
from pathlib import Path

from bac_common import ui
from bac_common.errors import BacError, UserAbort

__all__ = ["BACKUP_SUFFIX", "write_back", "confirm"]

BACKUP_SUFFIX = ".bak"


def write_back(path: Path, text: str, *, backup: bool = True) -> Path | None:
    """Write ``text`` over ``path``; with ``backup`` the previous content is kept as ``<name>.bak``.

    Returns the backup path, or ``None`` when none was made. The backup is
    made first, so a failed write never loses the original.
    """
    saved: Path | None = None
    try:
        if backup:
            saved = path.with_name(path.name + BACKUP_SUFFIX)
            shutil.copy2(path, saved)
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write(text)  # newline="" keeps the file's own line endings
    except OSError as exc:
        raise BacError(f"Cannot write {path}", exc.strerror or str(exc)) from exc
    return saved


def confirm(question: str, *, yes: bool = False) -> None:
    """Ask ``question [y/N]`` on the terminal; raise :class:`UserAbort` unless answered yes.

    ``yes`` (the ``--yes`` flag) skips the prompt. Without a terminal to ask
    on, the answer is no: a script that means it passes ``--yes``.
    """
    if yes:
        return
    try:
        answer = ui.console.input(f"  {question} [y/N] ")
    except EOFError:
        answer = ""
    if answer.strip().lower() not in ("y", "yes"):
        raise UserAbort("Aborted – nothing written.")
