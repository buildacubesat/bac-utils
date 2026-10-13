# SPDX-License-Identifier: MIT
"""Markdown rendering of an issue and its timeline.

One H1 per issue, a short metadata list, the body, then a ``Timeline``
section with one H3 per entry – ``user verb – date`` – followed by the
entry's text, and for a review its line comments under the file path. In
``--comments-only`` mode the section is ``Comments`` and the headings are
``user – date``, the 0.1 shape. A missing body prints nothing – the API
returns ``null`` for an empty description, and the old shell script
printed the word ``null``.
"""

from __future__ import annotations

from typing import Any

from .timeline import Entry

__all__ = ["render", "render_comments"]


def render(issue: dict[str, Any], entries: list[Entry], slug: str, pull: dict[str, Any] | None = None) -> str:
    """The Markdown document with the timeline. ``slug`` is ``owner/repo``."""
    lines = _head(issue, slug, pull)
    lines.extend(["## Timeline", ""])
    if not entries:
        lines.append("_Nothing happened after the description._")
    for index, entry in enumerate(entries):
        if index:
            lines.extend(["---", ""])
        heading = f"### {entry.user} {entry.verb} – {entry.when}"
        lines.extend([heading, ""])
        if entry.link:
            lines.extend([entry.link, ""])
        if entry.body:
            lines.extend([entry.body, ""])
        for comment in entry.lines:
            where = f"`{comment.path}`" + (f" {comment.line}" if comment.line else "")
            by = f" – {comment.user}" if comment.user != entry.user else ""
            lines.extend([f"**{where}**{by}", ""])
            if comment.body:
                lines.extend([comment.body, ""])
    return "\n".join(lines).rstrip("\n") + "\n"


def render_comments(issue: dict[str, Any], comments: list[dict[str, Any]], slug: str) -> str:
    """The 0.1 document: the issue and its plain comments only."""
    lines = _head(issue, slug, None)
    lines.extend(["## Comments", ""])
    if not comments:
        lines.append("_No comments._")
    for index, comment in enumerate(comments):
        if index:
            lines.extend(["---", ""])
        lines.extend([f"### {_login(comment.get('user'))} – {_text(comment.get('created_at'))}", ""])
        text = _text(comment.get("body")).strip()
        if text:
            lines.extend([text, ""])
    return "\n".join(lines).rstrip("\n") + "\n"


def _head(issue: dict[str, Any], slug: str, pull: dict[str, Any] | None) -> list[str]:
    number = issue.get("number", "?")
    lines: list[str] = [f"# {_text(issue.get('title')) or 'Untitled'} ({slug} #{number})", ""]

    labels = [label for label in issue.get("labels") or [] if isinstance(label, dict)]
    milestone = issue.get("milestone")
    pr = issue.get("pull_request") if isinstance(issue.get("pull_request"), dict) else None
    meta = [
        ("Author", _login(issue.get("user"))),
        ("State", _state(issue, pr)),
        ("Created", _text(issue.get("created_at"))),
        ("Branch", _branches(pull)),
        ("Labels", ", ".join(_text(label.get("name")) for label in labels)),
        ("Milestone", _text(milestone.get("title")) if isinstance(milestone, dict) else ""),
        ("URL", _text(issue.get("html_url"))),
    ]
    lines.extend(f"- {key}: {value}" for key, value in meta if value)
    lines.append("")

    body = _text(issue.get("body")).strip()
    if body:
        lines.extend([body, ""])
    return lines


def _state(issue: dict[str, Any], pr: dict[str, Any] | None) -> str:
    state = _text(issue.get("state"))
    if pr is None:
        return state
    if pr.get("merged"):
        return f"pull request, merged {_text(pr.get('merged_at'))[:10]}".rstrip()
    draft = " (draft)" if pr.get("draft") else ""
    return f"pull request, {state}{draft}"


def _branches(pull: dict[str, Any] | None) -> str:
    if not pull:
        return ""
    head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
    base = pull.get("base") if isinstance(pull.get("base"), dict) else {}
    if not head.get("ref") and not base.get("ref"):
        return ""
    return f"{_text(head.get('ref'))} → {_text(base.get('ref'))}"


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _login(user: object) -> str:
    if isinstance(user, dict):
        return _text(user.get("login")) or _text(user.get("username")) or "unknown"
    return "unknown"
