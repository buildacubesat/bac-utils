# SPDX-License-Identifier: MIT
"""The timeline, turned into entries the renderer prints.

Forgejo's timeline mixes comments with events – reviews, pushes, references
from other issues, title changes, review requests, labels – each a
comment object whose ``type`` says what it is and whose other fields vary
with the type. :func:`build_entries` reads what each type carries and
produces one :class:`Entry` per item with a one-line heading, an optional
body and, for reviews, the line comments the reviews API supplies. Types
this module does not know are kept as their raw name so nothing is lost
silently; a literal ``null`` in the array (Forgejo emits one for an entry
it cannot serialise) is counted and skipped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Entry", "LineComment", "build_entries", "REVIEW_STATES"]

REVIEW_STATES = {
    "APPROVED": "approved",
    "REQUEST_CHANGES": "requested changes",
    "COMMENT": "reviewed",
    "PENDING": "started a review",
    "REQUEST_REVIEW": "requested a review",
}

# Timeline types that carry nothing worth a line beyond the fact itself.
_PLAIN_VERBS = {
    "close": "closed this",
    "reopen": "reopened this",
    "merge_pull": "merged this",
    "lock": "locked this",
    "unlock": "unlocked this",
    "pin": "pinned this",
    "unpin": "unpinned this",
    "delete_branch": "deleted the branch",
    "start_tracking": "started time tracking",
    "stop_tracking": "stopped time tracking",
    "cancel_tracking": "cancelled time tracking",
    "pull_scheduled_merge": "scheduled the merge",
    "pull_cancel_scheduled_merge": "cancelled the scheduled merge",
    "dismiss_review": "dismissed a review",
    "change_target_branch": "changed the target branch",
}


@dataclass(slots=True)
class LineComment:
    path: str
    line: str  # "line 42", "old line 7" or "" when the comment is no longer attached to a line
    user: str
    body: str


@dataclass(slots=True)
class Entry:
    kind: str  # the timeline type, or "comment"
    user: str
    when: str
    verb: str  # "commented", "approved", "pushed 3 commits", …
    body: str = ""
    lines: list[LineComment] = field(default_factory=list)
    link: str = ""  # a URL the heading points at, where one exists (a referencing comment)


def build_entries(
    timeline: list[dict[str, Any] | None],
    reviews: dict[int, dict[str, Any]] | None = None,
    review_comments: dict[int, list[dict[str, Any]]] | None = None,
) -> tuple[list[Entry], int]:
    """Entries in timeline order, and how many ``null`` items the server sent."""
    reviews = reviews or {}
    review_comments = review_comments or {}
    entries: list[Entry] = []
    skipped = 0
    for item in timeline:
        if item is None:
            skipped += 1
            continue
        entry = _entry(item, reviews, review_comments)
        if entry is not None:
            entries.append(entry)
    return entries, skipped


def _entry(item: dict[str, Any], reviews: dict, review_comments: dict) -> Entry | None:
    kind = _text(item.get("type")) or "comment"
    user = _login(item.get("user"))
    when = _text(item.get("created_at"))
    body = _text(item.get("body")).strip()

    if kind == "comment":
        return Entry(kind, user, when, "commented", body)

    if kind == "review":
        review_id = item.get("review_id") or 0
        review = reviews.get(review_id, {})
        verb = REVIEW_STATES.get(_text(review.get("state")).upper(), "reviewed")
        lines = [_line_comment(c) for c in review_comments.get(review_id, []) if isinstance(c, dict)]
        if not body and not lines and verb in ("reviewed", "started a review"):
            return None  # an empty review shell – Forgejo writes one per inline comment batch
        return Entry(kind, user, when, verb, body, lines)

    if kind == "pull_push":
        try:
            push = json.loads(body) if body else {}
        except json.JSONDecodeError:
            push = {}
        shas = [str(s)[:7] for s in push.get("commit_ids", []) if isinstance(s, str)]
        count = len(shas)
        verb = (
            "force-pushed" if push.get("is_force_push") else "pushed"
        ) + f" {count} commit{'s' if count != 1 else ''}"
        return Entry(kind, user, when, verb, ", ".join(shas))

    if kind in ("issue_ref", "pull_ref", "comment_ref"):
        ref = item.get("ref_issue") if isinstance(item.get("ref_issue"), dict) else {}
        what = "pull request" if kind == "pull_ref" or "/pulls/" in _text(ref.get("html_url")) else "issue"
        number = ref.get("number")
        title = _text(ref.get("title"))
        verb = f"referenced this from {what} #{number}" if number else "referenced this"
        if title:
            verb += f" – {title}"
        comment = item.get("ref_comment") if isinstance(item.get("ref_comment"), dict) else {}
        excerpt = _text(comment.get("body")).strip()
        link = _text(comment.get("html_url")) or _text(ref.get("html_url"))
        return Entry(kind, user, when, verb, _quote(excerpt), link=link)

    if kind == "commit_ref":
        return Entry(kind, user, when, "referenced this from a commit", body)

    if kind == "change_title":
        return Entry(
            kind, user, when, "changed the title", f"{_text(item.get('old_title'))} → {_text(item.get('new_title'))}"
        )

    if kind == "review_request":
        removed = _login(item.get("removed_assignee")) if item.get("removed_assignee") else ""
        if removed and removed != "unknown":
            return Entry(kind, user, when, f"removed the review request for {removed}")
        who = _login(item.get("assignee")) if item.get("assignee") else _login(item.get("assignee_team"))
        return Entry(kind, user, when, f"requested a review from {who}")

    if kind == "label":
        label = item.get("label") if isinstance(item.get("label"), dict) else {}
        name = _text(label.get("name")) or "a label"
        verb = f"added the label {name}" if body == "1" else f"removed the label {name}"
        return Entry(kind, user, when, verb)

    if kind == "assignees":
        if item.get("removed_assignee"):
            return Entry(kind, user, when, f"unassigned {_login(item.get('assignee'))}")
        return Entry(kind, user, when, f"assigned {_login(item.get('assignee'))}")

    if kind == "milestone":
        new = item.get("milestone") if isinstance(item.get("milestone"), dict) else {}
        old = item.get("old_milestone") if isinstance(item.get("old_milestone"), dict) else {}
        if new:
            return Entry(kind, user, when, f"set the milestone to {_text(new.get('title'))}")
        return Entry(kind, user, when, f"removed the milestone {_text(old.get('title'))}".rstrip())

    if kind in _PLAIN_VERBS:
        return Entry(kind, user, when, _PLAIN_VERBS[kind], body)

    return Entry(kind, user, when, kind.replace("_", " "), body)


def _line_comment(comment: dict[str, Any]) -> LineComment:
    position = comment.get("position")
    original = comment.get("original_position")
    if isinstance(position, int) and position > 0:
        line = f"line {position}"
    elif isinstance(position, int) and position < 0:
        line = f"old line {-position}"
    elif isinstance(original, int) and original:
        line = f"line {abs(original)} (outdated)"
    else:
        line = ""
    return LineComment(
        _text(comment.get("path")), line, _login(comment.get("user")), _text(comment.get("body")).strip()
    )


def _quote(text: str, limit: int = 400) -> str:
    """The first lines of a referencing comment as a block quote."""
    if not text:
        return ""
    short = text if len(text) <= limit else text[:limit].rstrip() + " …"
    return "\n".join(f"> {line}" if line else ">" for line in short.splitlines())


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _login(user: object) -> str:
    if isinstance(user, dict):
        return _text(user.get("login")) or _text(user.get("username")) or _text(user.get("name")) or "unknown"
    return "unknown"
