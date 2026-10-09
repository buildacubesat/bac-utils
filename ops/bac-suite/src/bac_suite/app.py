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


# The shared stylesheet: a copy of tools/bac-reference-gallery/css/tokens.css, kept identical by a test.
TOKENS_CSS = Path(__file__).resolve().parent / "static" / "tokens.css"

_INDEX_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Build a CubeSat – Operations</title>
<link rel="stylesheet" href="/tokens.css">
<style>
body {{ font-family: var(--font-body); background: var(--bg); color: var(--text);
  max-width: 640px; margin: 12vh auto; padding: 0 24px; line-height: 1.6; }}
h1 {{ font-family: var(--font-display); font-weight: var(--fw-bold); font-size: 1.4rem; color: var(--text-strong); }}
h1 b {{ background: var(--bac-yellow); color: var(--warm-950); padding: 0 .3em; border-radius: 3px; }}
p {{ color: var(--text-muted); font-size: .9rem; }}
a.tool {{ display: block; background: var(--surface-card); border: 1px solid var(--border);
  border-radius: var(--radius-sm); padding: 14px 18px; margin: 10px 0; color: var(--text); text-decoration: none;
  font-weight: 500; transition: border-color var(--dur-fast) var(--ease-standard); }}
a.tool:hover {{ border-color: var(--bac-yellow); }}
a.tool:focus-visible {{ outline: 3px solid var(--focus-ring); outline-offset: 2px; }}
@media (prefers-reduced-motion: reduce) {{ a.tool {{ transition: none; }} }}
footer {{ font-size: .8rem; color: var(--text-muted); margin-top: 32px; }}
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
    """The ASGI app: ``/`` serves the index and ``/tokens.css`` its stylesheet; every other path goes to marimo.

    ``build`` turns the tools into marimo's ASGI app and is replaceable so the
    index can be tested without marimo serving anything.
    """
    pages = {
        "": (b"text/html; charset=utf-8", index_html(tools).encode("utf-8")),
        "/": (b"text/html; charset=utf-8", index_html(tools).encode("utf-8")),
        "/tokens.css": (b"text/css; charset=utf-8", TOKENS_CSS.read_bytes()),
    }
    inner = (build or _marimo_app)(tools)

    async def app(scope: dict, receive: Callable, send: Callable) -> None:
        page = pages.get(scope.get("path")) if scope["type"] == "http" else None
        if page is not None:
            kind, body = page
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", kind), (b"content-length", str(len(body)).encode())],
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
