# SPDX-License-Identifier: MIT
"""The interactive prompts of ``edit`` (InquirerPy), kept apart so tests can replace them."""

from __future__ import annotations

from pathlib import Path

from .qr import FORMATS, LEVELS, QrOptions

__all__ = ["ask_text", "confirm", "pick_action", "pick_redirect", "qr_options"]

ACTIONS = (
    ("slug", "Change slug"),
    ("target", "Change destination URL"),
    ("qr", "Generate QR code"),
    ("cancel", "Cancel"),
)


def pick_redirect(redirects: list[tuple[str, str]]) -> int:
    """Fuzzy pick by slug only – matching on destinations made typing a slug pick the wrong entry."""
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice

    choices = [Choice(value=i, name=f"/{slug}") for i, (slug, _) in enumerate(redirects)]
    return inquirer.fuzzy(message="Redirect to edit:", choices=choices, max_height="70%").execute()


def pick_action(slug: str) -> str:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice

    choices = [Choice(value, name=name) for value, name in ACTIONS]
    return inquirer.select(message=f"/{slug}:", choices=choices, default="target").execute()


def ask_text(message: str, default: str) -> str:
    from InquirerPy import inquirer

    return inquirer.text(message=message, default=default).execute().strip()


def confirm(message: str) -> bool:
    from InquirerPy import inquirer

    return bool(inquirer.confirm(message=message, default=False).execute())


def qr_options() -> QrOptions:
    from InquirerPy import inquirer

    fmt = inquirer.select(message="Format:", choices=list(FORMATS), default="svg").execute()
    invert = inquirer.confirm(message="Invert (white on black)?", default=False).execute()
    alpha = inquirer.confirm(message="Transparent background?", default=False).execute()
    ec = inquirer.select(message="Error correction:", choices=list(LEVELS), default="M").execute()
    size = inquirer.number(message="Size in pixels:", default=1000, min_allowed=64).execute()
    output = inquirer.text(message="Output directory:", default="~").execute().strip()
    return QrOptions(fmt=fmt, invert=bool(invert), alpha=bool(alpha), ec=ec, size=int(size), output=Path(output))
