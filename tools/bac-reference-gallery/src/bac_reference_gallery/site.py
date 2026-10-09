# SPDX-License-Identifier: MIT
"""Where the gallery pages are and which boards they hold.

An installed tool carries the pages inside the package (``pages/``, put there
by the wheel build); a checkout reads them from the tool folder. ``--source``
points at any other copy, such as a gallery adapted for another project.
A board is one page under ``examples/``; the order is the order of the
index page's links, so the numbering on the boards and the renders agree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bac_common.errors import ConfigError, UsageError

PACKAGED = Path(__file__).resolve().parent / "pages"
CHECKOUT = Path(__file__).resolve().parents[2]
_LINK_RE = re.compile(r"""href=["']examples/([A-Za-z0-9_-]+)\.html["']""")


@dataclass(frozen=True)
class Board:
    name: str
    path: Path


def is_site(folder: Path) -> bool:
    return (folder / "index.html").is_file() and (folder / "examples").is_dir()


def find_site(source: Path | None = None) -> Path:
    """The gallery folder: ``source`` when given, else the packaged pages, else the checkout."""
    if source is not None:
        folder = source.expanduser()
        if not is_site(folder):
            raise UsageError(
                f"Not a gallery folder: {folder}",
                "A gallery folder holds index.html and an examples/ folder.",
            )
        return folder.resolve()
    for folder in (PACKAGED, CHECKOUT):
        if is_site(folder):
            return folder
    raise ConfigError(
        "The gallery pages were not found.",
        "Reinstall the tool, or pass the gallery folder with --source.",
    )


def boards(site: Path) -> list[Board]:
    """Every page under ``examples/``, in the index page's link order; unlinked pages follow by name."""
    pages = {p.stem: p for p in sorted((site / "examples").glob("*.html"))}
    order: list[str] = []
    index = (site / "index.html").read_text(encoding="utf-8")
    for name in _LINK_RE.findall(index):
        if name in pages and name not in order:
            order.append(name)
    order += [name for name in pages if name not in order]
    return [Board(name, pages[name]) for name in order]


def select(all_boards: list[Board], only: list[str] | None) -> list[Board]:
    """The boards named by ``--only`` (in gallery order), or all of them."""
    if not only:
        return all_boards
    known = {b.name for b in all_boards}
    unknown = [name for name in only if name not in known]
    if unknown:
        raise UsageError(
            f"Unknown board: {', '.join(unknown)}",
            "List the boards with -l.",
        )
    wanted = set(only)
    return [b for b in all_boards if b.name in wanted]
