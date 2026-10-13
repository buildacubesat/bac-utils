# SPDX-License-Identifier: MIT
"""Canned Forgejo API data and a fake fetcher for the bac-issue-print tests."""

from __future__ import annotations

from urllib.parse import urlparse

from bac_common.errors import ExternalToolError

ISSUE = {
    "number": 42,
    "title": "Watchdog resets the MCU",
    "state": "open",
    "created_at": "2026-08-30T10:11:12Z",
    "html_url": "https://codeberg.org/buildacubesat-project/bac-hardware/issues/42",
    "user": {"login": "mnu"},
    "labels": [{"name": "bug"}, {"name": "eps"}],
    "milestone": {"title": "R2"},
    "body": "The board resets every 4 s under load.\n\nSteps:\n1. power on\n2. wait",
}


def comment(n: int) -> dict:
    return {"user": {"login": f"user{n}"}, "created_at": f"2026-08-31T{n % 24:02d}:00:00Z", "body": f"Comment {n}"}


class FakeServer:
    """Answers the two endpoints from canned data; records every URL and token."""

    def __init__(self) -> None:
        self.issue: dict = dict(ISSUE)
        self.comments: list[dict] = [comment(1), comment(2)]
        self.status: int | None = None
        self.urls: list[str] = []
        self.tokens: list[str | None] = []

    def __call__(self, url: str, token: str | None = None):
        self.urls.append(url)
        self.tokens.append(token)
        if self.status:
            raise ExternalToolError(f"HTTP {self.status} from codeberg.org", f"GET {url.split('?', 1)[0]} – hint")
        parsed = urlparse(url)
        if parsed.path.endswith("/comments"):
            # Forgejo returns the whole thread whatever the query says; 0.1.0 relied on paging and hung.
            return list(self.comments)
        return self.issue
