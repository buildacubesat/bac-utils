# SPDX-License-Identifier: MIT
"""The Forgejo/Gitea API calls the tool makes, on urllib.

For an issue: ``GET …/issues/{n}`` and ``GET …/issues/{n}/timeline``. For
a pull request also ``GET …/pulls/{n}``, ``GET …/pulls/{n}/reviews`` and
``GET …/pulls/{n}/reviews/{id}/comments`` for each review that has line
comments. ``--comments-only`` uses ``GET …/issues/{n}/comments`` instead
of the timeline. Lists that the server pages are walked through the
``Link: <…>; rel="next"`` header, which is what Forgejo documents; the
per-issue comments endpoint is not paged at all (0.1.0 walked it by page
number and never met an empty page). An optional token is sent as
``Authorization: token …`` so private repositories work.
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from bac_common.errors import ExternalToolError

__all__ = [
    "Fetch",
    "Page",
    "fetch_json",
    "next_link",
    "get_issue",
    "get_comments",
    "get_timeline",
    "get_pull",
    "get_reviews",
    "get_review_comments",
]

TIMEOUT_S = 30
PAGE_LIMIT = 50  # Codeberg's cap; the Link header walks the rest
USER_AGENT = "bac-issue-print (+https://github.com/buildacubesat/bac-utils)"

Page = tuple[Any, Mapping[str, str]]
# A fetcher takes a URL and returns the decoded JSON plus the response headers; tests substitute one.
Fetch = Callable[[str], Page]

_LINK_RE = re.compile(r'<([^>]+)>\s*;\s*rel="?next"?')


def fetch_json(url: str, token: str | None = None) -> Page:
    """GET ``url``: the decoded JSON body and the headers. HTTP and network errors become :class:`ExternalToolError`."""
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    if token:
        request.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 – https API URL
            body = response.read()
            headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        hint = {
            401: "The token is missing or invalid; set CODEBERG_TOKEN in your .env.",
            403: "The token lacks access to this repository, or the rate limit is reached.",
            404: "Check the repository key and the issue number.",
        }.get(exc.code, "The server did not accept the request.")
        raise ExternalToolError(f"HTTP {exc.code} from {_host(url)}", f"GET {_path(url)} – {hint}") from exc
    except urllib.error.URLError as exc:
        raise ExternalToolError(f"Could not reach {_host(url)}", str(exc.reason)) from exc
    except (OSError, http.client.HTTPException) as exc:  # timeouts, resets, truncated bodies
        raise ExternalToolError(f"Could not reach {_host(url)}", str(exc)) from exc
    try:
        return json.loads(body), headers
    except json.JSONDecodeError as exc:
        raise ExternalToolError(f"Response from {_short(url)} is not JSON", str(exc)) from exc


def next_link(headers: Mapping[str, str]) -> str | None:
    """The ``rel="next"`` URL of a ``Link`` header, or ``None`` on the last page."""
    for key, value in headers.items():
        if key.lower() == "link":
            for part in value.split(","):
                m = _LINK_RE.search(part)
                if m:
                    return m.group(1)
    return None


def get_issue(fetch: Fetch, base: str) -> dict[str, Any]:
    """The issue object. ``base`` is ``…/repos/{owner}/{repo}/issues/{n}``."""
    data, _ = fetch(base)
    if not isinstance(data, dict):
        raise ExternalToolError(f"Unexpected response for {_short(base)}", "Expected an issue object.")
    return data


def get_comments(fetch: Fetch, base: str) -> list[dict[str, Any]]:
    """Every plain comment on the issue: one request, the endpoint is not paginated."""
    return _list(fetch, f"{base}/comments", paged=False)


def get_timeline(fetch: Fetch, base: str) -> list[dict[str, Any] | None]:
    """Every timeline entry, pages followed through the Link header.

    ``None`` entries are kept so the caller can count them.
    """
    return _list(fetch, f"{base}/timeline", paged=True, keep_null=True)


def get_pull(fetch: Fetch, pulls_base: str) -> dict[str, Any]:
    """The pull request object. ``pulls_base`` is ``…/repos/{owner}/{repo}/pulls/{n}``."""
    data, _ = fetch(pulls_base)
    if not isinstance(data, dict):
        raise ExternalToolError(f"Unexpected response for {_short(pulls_base)}", "Expected a pull request object.")
    return data


def get_reviews(fetch: Fetch, pulls_base: str) -> list[dict[str, Any]]:
    """The pull request's reviews (state, summary, comment count), pages followed."""
    return _list(fetch, f"{pulls_base}/reviews", paged=True)


def get_review_comments(fetch: Fetch, pulls_base: str, review_id: int) -> list[dict[str, Any]]:
    """The line comments of one review."""
    return _list(fetch, f"{pulls_base}/reviews/{review_id}/comments", paged=False)


def _list(fetch: Fetch, url: str, *, paged: bool, keep_null: bool = False) -> list:
    """A JSON list from ``url``; with ``paged`` the ``Link`` header's next pages are appended."""
    items: list = []
    target: str | None = f"{url}?limit={PAGE_LIMIT}" if paged else url
    seen: set[str] = set()
    while target and target not in seen:
        seen.add(target)
        data, headers = fetch(target)
        if not isinstance(data, list):
            raise ExternalToolError(f"Unexpected response for {_short(url)}", "Expected a list.")
        items.extend(item for item in data if isinstance(item, dict) or (keep_null and item is None))
        target = next_link(headers) if paged else None
    return items


def _short(url: str) -> str:
    """The URL without its query string, for messages."""
    return url.split("?", 1)[0]


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc or url


def _path(url: str) -> str:
    return urllib.parse.urlsplit(url).path or url
