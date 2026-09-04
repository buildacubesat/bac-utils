# SPDX-License-Identifier: MIT
"""Canned Forgejo API data and a fake fetcher for the bac-issue-print tests."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

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
        self.cap: int | None = None  # a server-side page-size cap below what the client asks for
        self.urls: list[str] = []
        self.tokens: list[str | None] = []

    def __call__(self, url: str, token: str | None = None):
        self.urls.append(url)
        self.tokens.append(token)
        if self.status:
            raise ExternalToolError(f"HTTP {self.status} from codeberg.org", f"GET {url.split('?', 1)[0]} – hint")
        parsed = urlparse(url)
        if parsed.path.endswith("/comments"):
            q = parse_qs(parsed.query)
            page, limit = int(q["page"][0]), int(q["limit"][0])
            if self.cap:
                limit = min(limit, self.cap)
            return self.comments[(page - 1) * limit : page * limit]
        return self.issue
