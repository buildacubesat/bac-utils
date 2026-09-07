# SPDX-License-Identifier: MIT
"""Step-log rendering of field changes, shared by the tools that apply rules."""

from __future__ import annotations

from bac_common import ui

from .props import VERBS, Change

__all__ = ["print_item", "print_changes"]


def print_item(kind: str, ident: str, extra: str = "") -> None:
    """The header line of one item: ``sym  BAC_Passives:R_0603 [R]``."""
    suffix = f" [dim]{ui.esc(extra)}[/]" if extra else ""
    ui.step(f"[dim]{ui.esc(kind):<5}[/]{ui.path(ident)}{suffix}")


def print_changes(changes: list[Change], skipped: list[tuple[str, str]]) -> None:
    """One indented line per change (``+ ~ ! *``) and per skipped rule (``·``)."""
    for c in changes:
        shown = ui.esc(c.value) if c.value else "[dim](empty placeholder)[/]"
        if c.kind in ("set", "flag"):
            shown = f"{ui.esc(c.previous or 'unset')} → {shown}"
        ui.step(f"    {VERBS[c.kind]} {ui.esc(c.key)} = {shown}   [dim]({ui.esc(c.source)})[/]")
    for name, reason in skipped:
        ui.step(f"    [dim]·[/] {ui.esc(name)} [dim]skipped: {ui.esc(reason)}[/]")
