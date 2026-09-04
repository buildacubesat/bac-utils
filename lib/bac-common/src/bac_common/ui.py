# SPDX-License-Identifier: MIT
"""Terminal presentation, following the BAC Interface Design Guide §10.

Literal colour values here are copies of the canonical BAC tokens and are
not authoritative; if they disagree with the Identity Guide, update this file.

Markup: every function accepts Rich markup in its message. Values that come
from outside the tool – file names, LLM output, user input – must pass
through :func:`esc` (or :func:`path`, which escapes for you) so that a
stray ``[/]`` cannot break or restyle the output.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from typing import Literal

from rich import box
from rich.console import Console
from rich.markup import escape as esc
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.table import Table

GREEN = "#84C45A"
RED = "#CE6C63"
YELLOW = "#F7D400"

PROJECT = "Build a CubeSat"

console = Console()
err_console = Console(stderr=True)

__all__ = [
    "GREEN",
    "RED",
    "YELLOW",
    "PROJECT",
    "console",
    "err_console",
    "esc",
    "ok",
    "fail",
    "warn",
    "step",
    "dim",
    "path",
    "fields",
    "error",
    "header",
    "opening",
    "rule",
    "summary",
    "table",
    "spinner",
    "make_progress",
    "display_version",
]


# ---------------------------------------------------------------------------
# Step log
# ---------------------------------------------------------------------------


def ok(message: str) -> None:
    """One successful step: ``✓ message``."""
    console.print(f"  [{GREEN}]✓[/] {message}")


def fail(message: str) -> None:
    """One failed step: ``✗ message``. Stays visible; never dimmed."""
    console.print(f"  [{RED}]✗[/] {message}")


def warn(message: str) -> None:
    """One warning: ``! message``."""
    console.print(f"  [{YELLOW}]![/] {message}")


def step(message: str) -> None:
    """A neutral step line without a glyph."""
    console.print(f"  {message}")


def dim(message: str) -> None:
    """A muted step line, for routine detail that need not stand out."""
    console.print(f"  [dim]{message}[/]")


def path(value: str | object) -> str:
    """Render a path or identifier in the guide's cyan, escaped for markup."""
    return f"[cyan]{esc(str(value))}[/]"


def fields(pairs: Iterable[tuple[str, object]], indent: int = 4) -> None:
    """Aligned label/value rows for a few key facts. Values are escaped.

    Use for 2–6 pairs where a table would be heavier than the data deserves.
    """
    rows = [(label, "" if value is None else str(value)) for label, value in pairs]
    if not rows:
        return
    width = max(len(label) for label, _ in rows)
    pad = " " * indent
    for label, value in rows:
        console.print(f"{pad}[bold]{esc(label).ljust(width)}[/]  {esc(value)}")


def error(message: str, detail: str | None = None) -> None:
    """Canonical error rendering on stderr: ``ERROR message`` plus an indented next step."""
    err_console.print(f"[{RED}]ERROR[/] {message}")
    if detail:
        err_console.print(f"      {detail}")


# ---------------------------------------------------------------------------
# Panels, headers, rules
# ---------------------------------------------------------------------------


def display_version(version: str) -> str:
    """``0.1.0`` and ``v0.1.0`` both become ``v0.1.0``."""
    version = version.strip()
    return version if version.startswith("v") else f"v{version}"


def header(tool: str, version: str) -> str:
    """The canonical branded header line: ``Build a CubeSat – tool v0.1.0``."""
    return f"{PROJECT} – {tool} {display_version(version)}"


def opening(tool: str, version: str, description: str) -> None:
    """Opening run summary. Shown once, at the start of a run."""
    console.print(
        Panel(
            f"[bold]{esc(tool)}[/bold]  [dim]{display_version(version)}[/dim]\n{description}",
            box=box.SIMPLE,
            border_style="dim",
        )
    )


def rule(label: str) -> None:
    """Section divider with a short label. No decorative banners."""
    console.print(Rule(label, style="dim"))


def summary(rows: Sequence[tuple[str, int | str]], dry_run: bool = False) -> None:
    """Final result block: numbers only, values right-aligned.

    Always call it, even on partial failure. With ``dry_run`` the guide's
    label is appended.
    """
    lines: list[str] = []
    if rows:
        label_width = max(len(label) for label, _ in rows)
        value_width = max(len(str(value)) for _, value in rows)
        for label, value in rows:
            lines.append(f"  {esc(label).ljust(label_width)}  :  {esc(str(value)).rjust(value_width)}")
    if dry_run:
        lines.append("  [dim](dry run – no changes made)[/dim]")
    console.print(Panel("\n".join(lines), box=box.SIMPLE, border_style="dim"))


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

Justify = Literal["left", "right", "center"]


def table(
    title: str | None,
    columns: Sequence[tuple[str, int] | tuple[str, int, Justify]],
    rows: Iterable[Sequence[str]],
    *,
    secondary: bool = False,
) -> None:
    """Rule-based table: heavy header rule, no outer border, cells never wrap.

    ``columns`` are ``(header, ratio)`` or ``(header, ratio, justify)``.
    ``ratio`` controls how spare width is shared; ``0`` makes the column
    exactly as wide as its content. Numeric columns should pass ``"right"``.
    ``secondary`` switches to ``box.SIMPLE`` for inline or minor tables.
    Cell values are printed as given; escape untrusted text with :func:`esc`.
    """
    t = Table(
        title=title,
        box=box.SIMPLE if secondary else box.HEAVY_HEAD,
        show_edge=False,
        title_justify="left",
        expand=True,
    )
    for column in columns:
        header_text, ratio = column[0], column[1]
        justify: Justify = column[2] if len(column) > 2 else "left"  # type: ignore[misc]
        t.add_column(header_text, overflow="ellipsis", no_wrap=True, ratio=ratio or None, justify=justify)
    for r in rows:
        t.add_row(*r)
    console.print(t)


# ---------------------------------------------------------------------------
# Liveness
# ---------------------------------------------------------------------------


@contextmanager
def spinner(message: str) -> Iterator[None]:
    """Indeterminate liveness for silent operations longer than ~1 s."""
    with console.status(f"[dim]{message}[/]", spinner="dots"):
        yield


Status = Literal["count", "percent", "elapsed"]


def make_progress(status: Status = "count") -> Progress:
    """Determinate progress: task name, bar, and exactly one right-aligned status.

    ``status`` picks that one: ``x/n``, percentage, or elapsed time. The bar
    collapses when finished so the scroll buffer stays clean.
    """
    status_column = {
        "count": MofNCompleteColumn(),
        "percent": TaskProgressColumn(),
        "elapsed": TimeElapsedColumn(),
    }[status]
    return Progress(
        TextColumn("[dim]{task.description}[/]"),
        BarColumn(bar_width=30, complete_style=YELLOW, finished_style=YELLOW),
        status_column,
        console=console,
        transient=True,
    )
