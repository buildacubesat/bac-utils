# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from bac_suite import __version__
from bac_suite.app import TOKENS_CSS, Tool, create_app, discover_tools, index_html


def test_tool_from_entry_validates_the_route():
    tool = Tool.from_entry({"label": "Pricing", "route": "/pricing", "notebook": "/x/notebook.py"})
    assert tool == Tool("Pricing", "/pricing", Path("/x/notebook.py"))
    with pytest.raises(ValueError):
        Tool.from_entry({"label": "Bad", "route": "pricing", "notebook": "n.py"})
    with pytest.raises(ValueError):
        Tool.from_entry({"label": "Bad", "route": "/", "notebook": "n.py"})


def test_discover_tools_sees_the_installed_pricing_notebook():
    tools = discover_tools()
    assert [t.route for t in tools] == ["/pricing"]
    assert tools[0].notebook.exists()


def test_index_html_links_every_tool_and_escapes():
    html = index_html([Tool("Pricing", "/pricing", Path("n.py")), Tool("A <b>", "/a?x=1&y=2", Path("m.py"))])
    assert '<a class="tool" href="/pricing">Pricing</a>' in html
    assert 'href="/a?x=1&amp;y=2">A &lt;b&gt;</a>' in html
    assert f"bac-suite v{__version__}" in html
    assert '<link rel="stylesheet" href="/tokens.css">' in html
    assert "prefers-reduced-motion" in html and "\u2014" not in html
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", html), "colours come from tokens.css"
    assert "fonts.googleapis.com" not in html  # tokens.css imports the fonts
    assert "No engines installed" in index_html([])


def _call(app, path):
    sent = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        sent.append(message)

    asyncio.run(app({"type": "http", "path": path}, receive, send))
    return sent


def test_create_app_serves_the_index_and_delegates_the_rest():
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["path"])

    tools = [Tool("Pricing", "/pricing", Path("n.py"))]
    app = create_app(tools, build=lambda t: inner)
    sent = _call(app, "/")
    assert sent[0]["status"] == 200
    assert b"Pricing" in sent[1]["body"]
    assert dict(sent[0]["headers"])[b"content-type"].startswith(b"text/html")
    _call(app, "/pricing")
    assert seen == ["/pricing"]


def test_tokens_css_is_the_gallery_file():
    gallery = Path(__file__).resolve().parents[3] / "tools" / "bac-reference-gallery" / "css" / "tokens.css"
    assert TOKENS_CSS.read_bytes() == gallery.read_bytes()


def test_create_app_serves_the_stylesheet():
    app = create_app([], build=lambda t: None)
    sent = _call(app, "/tokens.css")
    assert sent[0]["status"] == 200
    assert dict(sent[0]["headers"])[b"content-type"] == b"text/css; charset=utf-8"
    assert sent[1]["body"] == TOKENS_CSS.read_bytes()


def test_every_token_the_index_uses_is_defined():
    used = set(re.findall(r"var\((--[\w-]+)\)", index_html([])))
    defined = set(re.findall(r"(--[\w-]+)\s*:", TOKENS_CSS.read_text(encoding="utf-8")))
    assert used and used <= defined, used - defined
