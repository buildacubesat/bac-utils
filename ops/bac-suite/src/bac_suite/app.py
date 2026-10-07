# SPDX-License-Identifier: MIT
"""The ASGI application: an index page plus one marimo app per registered notebook."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from . import __version__

__all__ = ["Tool", "discover_tools", "index_html", "create_app"]


@dataclass(frozen=True, slots=True)
class Tool:
    label: str
    route: str
    notebook: Path

    @classmethod
    def from_entry(cls, obj: Any) -> Tool:
        """An entry point resolves to ``{"label", "route", "notebook"}`` (see ``bac_pricing.APP``)."""
        route = str(obj["route"])
        if not route.startswith("/") or route == "/":
            raise ValueError(f"route must start with '/' and not be the root: {route}")
        return cls(label=str(obj["label"]), route=route, notebook=Path(obj["notebook"]))


def discover_tools() -> list[Tool]:
    """Every installed engine's notebook, in entry-point name order."""
    tools: list[Tool] = []
    for ep in sorted(entry_points(group="bac_suite.apps"), key=lambda e: e.name):
        tools.append(Tool.from_entry(ep.load()))
    return tools


# Token values copied from the BAC Identity Guide; the shared tokens.css (reference gallery) is authoritative.
_INDEX_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Build a CubeSat – Operations</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,600;6..12,800" rel="stylesheet">
<style>
:root {{ color-scheme: light dark;
  --text: light-dark(#3F3F3F, #efefed); --bg: light-dark(#efefed, #201e1c);
  --muted: light-dark(#6A6A66, #A3A29C); --card: light-dark(#F6F6F4, #2a2826);
  --line: light-dark(#CFCFCA, #4A4844); --yellow: #F7D400; --focus: #4A8FD9; }}
body {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; background: var(--bg); color: var(--text);
  max-width: 640px; margin: 12vh auto; padding: 0 24px; line-height: 1.6; }}
h1 {{ font-family: 'Nunito Sans', system-ui, sans-serif; font-weight: 800; font-size: 1.4rem; }}
h1 b {{ background: var(--yellow); color: #2A2600; padding: 0 .3em; border-radius: 3px; }}
p {{ color: var(--muted); font-size: .9rem; }}
a.tool {{ display: block; background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  padding: 14px 18px; margin: 10px 0; color: var(--text); text-decoration: none; font-weight: 500;
  transition: border-color 120ms cubic-bezier(.2, 0, .1, 1); }}
a.tool:hover {{ border-color: var(--yellow); }}
a.tool:focus-visible {{ outline: 3px solid var(--focus); outline-offset: 2px; }}
@media (prefers-reduced-motion: reduce) {{ a.tool {{ transition: none; }} }}
footer {{ font-size: .8rem; color: var(--muted); margin-top: 32px; }}
</style></head><body>
<h1><b>Build a CubeSat</b> · Operations</h1>
<p>Orchestrated mode: every engine reads the same store. Each one also runs standalone through its own command.</p>
{links}
<footer>bac-suite v{version}</footer>
</body></html>"""


def index_html(tools: list[Tool]) -> str:
    links = "\n".join(f'<a class="tool" href="{escape(t.route)}">{escape(t.label)}</a>' for t in tools) or (
        "<p>No engines installed. Install bac-pricing (or another engine) next to bac-suite.</p>"
    )
    return _INDEX_TEMPLATE.format(links=links, version=__version__)


def create_app(tools: list[Tool], build: Callable[[list[Tool]], Any] | None = None) -> Callable:
    """The ASGI app: ``/`` serves the index, every other path goes to marimo's app.

    ``build`` turns the tools into marimo's ASGI app and is replaceable so the
    index can be tested without marimo serving anything.
    """
    body = index_html(tools).encode("utf-8")
    inner = (build or _marimo_app)(tools)

    async def app(scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] == "http" and scope.get("path") in ("", "/"):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"text/html; charset=utf-8"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await inner(scope, receive, send)

    return app


def _marimo_app(tools: list[Tool]) -> Any:
    import marimo

    builder = marimo.create_asgi_app()
    for tool in tools:
        builder = builder.with_app(path=tool.route, root=str(tool.notebook))
    return builder.build()
