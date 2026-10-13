# SPDX-License-Identifier: MIT
"""Canned Forgejo API data and a fake fetcher for the bac-issue-print tests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bac_common.errors import ExternalToolError

FIXTURES = Path(__file__).parent / "fixtures"

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


def comment(n: int, kind: str = "comment") -> dict:
    return {
        "id": n,
        "type": kind,
        "user": {"login": f"user{n}"},
        "created_at": f"2026-08-31T{n % 24:02d}:00:00Z",
        "body": f"Comment {n}",
    }


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeServer:
    """Answers the endpoints from canned data; records every URL and token.

    ``timeline`` is served in pages of ``page_size`` with a ``Link`` header
    when it does not fit in one; the comments endpoint, like Forgejo's,
    returns everything whatever the query says.
    """

    def __init__(self) -> None:
        self.issue: dict = dict(ISSUE)
        self.comments: list[dict] = [comment(1), comment(2)]
        self.timeline: list[dict | None] | None = None  # None: the plain comments double as the timeline
        self.pull: dict = {"head": {"ref": "feature/x"}, "base": {"ref": "main"}}
        self.reviews: list[dict] = []
        self.review_comments: dict[int, list[dict]] = {}
        self.page_size: int = 50
        self.status: int | None = None
        self.urls: list[str] = []
        self.tokens: list[str | None] = []

    def __call__(self, url: str, token: str | None = None):
        self.urls.append(url)
        self.tokens.append(token)
        if self.status:
            raise ExternalToolError(f"HTTP {self.status} from codeberg.org", f"GET {url.split('?', 1)[0]} – hint")
        parsed = urlparse(url)
        path = parsed.path
        if path.endswith("/timeline"):
            return self._page(self.timeline if self.timeline is not None else list(self.comments), url)
        if path.endswith("/comments") and "/reviews/" in path:
            review_id = int(path.split("/reviews/")[1].split("/")[0])
            return list(self.review_comments.get(review_id, [])), {}
        if path.endswith("/comments"):
            return list(self.comments), {}
        if path.endswith("/reviews"):
            return self._page(self.reviews, url)
        if re.search(r"/pulls/\d+$", path):
            return dict(self.pull), {}
        return dict(self.issue), {}

    def _page(self, items: list, url: str):
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        page = int(q.get("page", ["1"])[0])
        limit = min(int(q.get("limit", [str(self.page_size)])[0]), self.page_size)
        chunk = items[(page - 1) * limit : page * limit]
        headers = {}
        if page * limit < len(items):
            headers["link"] = (
                f'<{parsed.scheme}://{parsed.netloc}{parsed.path}?limit={limit}&page={page + 1}>; rel="next"'
            )
        return chunk, headers
