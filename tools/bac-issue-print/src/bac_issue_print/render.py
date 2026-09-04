# SPDX-License-Identifier: MIT
"""Markdown rendering of an issue and its comments.

One H1 per issue, a short metadata list, the body, then a ``Comments``
section with one H3 per comment. A missing body prints nothing – the API
returns ``null`` for an empty description, and the old shell script printed
the word ``null``.
"""

from __future__ import annotations

from typing import Any

__all__ = ["render"]


def render(issue: dict[str, Any], comments: list[dict[str, Any]], slug: str) -> str:
    """The Markdown document. ``slug`` is ``owner/repo``."""
    number = issue.get("number", "?")
    lines: list[str] = [f"# {_text(issue.get('title')) or 'Untitled'} ({slug} #{number})", ""]

    labels = [label for label in issue.get("labels") or [] if isinstance(label, dict)]
    milestone = issue.get("milestone")
    meta = [
        ("Author", _login(issue.get("user"))),
        ("State", _text(issue.get("state"))),
        ("Created", _text(issue.get("created_at"))),
        ("Labels", ", ".join(_text(label.get("name")) for label in labels)),
        ("Milestone", _text(milestone.get("title")) if isinstance(milestone, dict) else ""),
        ("URL", _text(issue.get("html_url"))),
    ]
    lines.extend(f"- {key}: {value}" for key, value in meta if value)
    lines.append("")

    body = _text(issue.get("body")).strip()
    if body:
        lines.extend([body, ""])

    lines.extend(["## Comments", ""])
    if not comments:
        lines.append("_No comments._")
    for index, comment in enumerate(comments):
        if index:
            lines.extend(["---", ""])
        lines.append(f"### {_login(comment.get('user'))} – {_text(comment.get('created_at'))}")
        lines.append("")
        text = _text(comment.get("body")).strip()
        if text:
            lines.extend([text, ""])
    return "\n".join(lines).rstrip("\n") + "\n"


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _login(user: object) -> str:
    if isinstance(user, dict):
        return _text(user.get("login")) or _text(user.get("username")) or "unknown"
    return "unknown"
