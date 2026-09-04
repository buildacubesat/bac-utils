# SPDX-License-Identifier: MIT
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest
from bac_issue_print import api

from bac_common.errors import ExternalToolError


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_fetch_json_sends_token_and_decodes(monkeypatch):
    seen = {}

    def urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["accept"] = request.get_header("Accept")
        return _Response(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert api.fetch_json("https://x.y/api/v1/z", "tok") == {"ok": True}
    assert seen == {"url": "https://x.y/api/v1/z", "auth": "token tok", "accept": "application/json"}

    assert api.fetch_json("https://x.y/api/v1/z") == {"ok": True}
    assert seen["auth"] is None


@pytest.mark.parametrize(("status", "hint"), [(401, "token"), (404, "issue number"), (500, "did not accept")])
def test_fetch_json_maps_http_errors(monkeypatch, status, hint):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, status, "nope", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(ExternalToolError) as info:
        api.fetch_json("https://x.y/api/v1/z?page=1")
    assert info.value.message == f"HTTP {status} from x.y"
    assert info.value.detail is not None and info.value.detail.startswith("GET /api/v1/z – ")
    assert hint in info.value.detail


def test_fetch_json_network_and_body_errors(monkeypatch):
    def down(request, timeout):
        raise urllib.error.URLError("name or service not known")

    monkeypatch.setattr(urllib.request, "urlopen", down)
    with pytest.raises(ExternalToolError, match="Could not reach"):
        api.fetch_json("https://x.y/z")

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: _Response(b"<html>"))
    with pytest.raises(ExternalToolError, match="not JSON"):
        api.fetch_json("https://x.y/z")

    def slow(request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", slow)
    with pytest.raises(ExternalToolError, match="Could not reach x.y"):
        api.fetch_json("https://x.y/z")


def test_get_comments_stops_on_empty_page():
    pages = {1: [{"body": "a"}] * 3, 2: [{"body": "b"}] * 2}
    calls = []

    def fetch(url):
        calls.append(url)
        page = int(url.rsplit("page=", 1)[1].split("&")[0])
        return pages.get(page, [])

    got = api.get_comments(fetch, "https://x.y/issues/1", page_size=3)
    assert len(got) == 5 and len(calls) == 3
    assert api.get_comments(lambda url: [], "https://x.y/issues/1") == []


def test_unexpected_shapes():
    with pytest.raises(ExternalToolError, match="Unexpected response") as info:
        api.get_issue(lambda url: [], "https://x.y/issues/1")
    assert info.value.detail == "Expected an issue object."
    with pytest.raises(ExternalToolError, match="Unexpected response") as info:
        api.get_comments(lambda url: {}, "https://x.y/issues/1")
    assert info.value.detail == "Expected a list."
