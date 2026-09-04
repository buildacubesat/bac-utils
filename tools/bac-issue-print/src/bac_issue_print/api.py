# SPDX-License-Identifier: MIT
"""The two Forgejo/Gitea API calls the tool makes, on urllib.

``GET /api/v1/repos/{owner}/{repo}/issues/{n}`` and
``GET /api/v1/repos/{owner}/{repo}/issues/{n}/comments``. Comments are
paginated (``page``, ``limit``); the server caps ``limit`` – at 50 on
Codeberg, lower elsewhere – so the tool asks for 50 and keeps going until a
page comes back empty, which costs one extra request and never truncates
a thread on a server with a smaller cap. An optional
token is sent as ``Authorization: token …`` so private repositories work.
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from bac_common.errors import ExternalToolError

__all__ = ["Fetch", "fetch_json", "get_issue", "get_comments", "PAGE_SIZE"]

PAGE_SIZE = 50
TIMEOUT_S = 30
USER_AGENT = "bac-issue-print (+https://github.com/buildacubesat/bac-utils)"

# A fetcher takes a URL and returns the decoded JSON; tests substitute one.
Fetch = Callable[[str], Any]


def fetch_json(url: str, token: str | None = None) -> Any:
    """GET ``url`` and decode the JSON body. HTTP and network errors become :class:`ExternalToolError`."""
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    if token:
        request.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 – https API URL
            body = response.read()
    except urllib.error.HTTPError as exc:
        hint = {
            401: "The token is missing or invalid; set CODEBERG_TOKEN in your .env.",
            403: "The token lacks access to this repository.",
            404: "Check the repository key and the issue number.",
        }.get(exc.code, "The server did not accept the request.")
        raise ExternalToolError(f"HTTP {exc.code} from {_host(url)}", f"GET {_path(url)} – {hint}") from exc
    except urllib.error.URLError as exc:
        raise ExternalToolError(f"Could not reach {_host(url)}", str(exc.reason)) from exc
    except (OSError, http.client.HTTPException) as exc:  # timeouts, resets, truncated bodies
        raise ExternalToolError(f"Could not reach {_host(url)}", str(exc)) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ExternalToolError(f"Response from {_short(url)} is not JSON", str(exc)) from exc


def get_issue(fetch: Fetch, base: str) -> dict[str, Any]:
    """The issue object. ``base`` is ``…/repos/{owner}/{repo}/issues/{n}``."""
    data = fetch(base)
    if not isinstance(data, dict):
        raise ExternalToolError(f"Unexpected response for {_short(base)}", "Expected an issue object.")
    return data


def get_comments(fetch: Fetch, base: str, page_size: int = PAGE_SIZE) -> list[dict[str, Any]]:
    """Every comment on the issue, walking the pages until one comes back empty."""
    comments: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({"page": page, "limit": page_size})
        data = fetch(f"{base}/comments?{query}")
        if not isinstance(data, list):
            raise ExternalToolError(f"Unexpected response for {_short(base)}/comments", "Expected a list.")
        if not data:
            return comments
        comments.extend(c for c in data if isinstance(c, dict))
        page += 1


def _short(url: str) -> str:
    """The URL without its query string, for messages."""
    return url.split("?", 1)[0]


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc or url


def _path(url: str) -> str:
    return urllib.parse.urlsplit(url).path or url
