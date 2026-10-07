# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from bac_suite import __version__
from bac_suite.app import Tool, create_app, discover_tools, index_html


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
    assert "light-dark(" in html and "prefers-reduced-motion" in html and "\u2014" not in html
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
