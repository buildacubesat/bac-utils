# SPDX-License-Identifier: MIT
"""The gallery over HTTP on this computer, for looking at it in a browser.

A browser that runs in a sandbox – a Flatpak or a Snap – receives a local
file through a portal that passes the one file and not the folder around it,
so ``index.html`` opened from disk loses its stylesheets and its previews.
Served from ``127.0.0.1`` every relative path resolves, in any browser, and
the copy inside an installed tool (a hidden folder) becomes reachable too.
The server answers on the loopback address only.
"""

from __future__ import annotations

import errno
import functools
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8765


class _Handler(SimpleHTTPRequestHandler):
    """Static files from the gallery folder; no access log, no caching."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 – the stdlib's name
        pass

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        self.server.count_request()  # type: ignore[attr-defined]

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")  # an edited page shows on reload
        super().end_headers()


class GalleryServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second server take a port another program
    # listens on, so the fallback below would never see the conflict.
    allow_reuse_address = os.name != "nt"

    def __init__(self, address: tuple[str, int], handler) -> None:
        self._lock = threading.Lock()
        self.requests = 0
        super().__init__(address, handler)

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.server_address[1]}/"

    def count_request(self) -> None:
        with self._lock:
            self.requests += 1

    def handle_error(self, request, client_address) -> None:
        if isinstance(sys.exc_info()[1], ConnectionError):
            return  # the browser dropped the connection: a reload, a preview cut short
        super().handle_error(request, client_address)


def make_server(folder: Path, port: int = PORT) -> GalleryServer:
    """A server for ``folder`` on ``port``, or on a free port when that one is taken or refused."""
    handler = functools.partial(_Handler, directory=str(folder))
    try:
        return GalleryServer((HOST, port), handler)
    except OSError as exc:
        if port == 0 or exc.errno not in (errno.EADDRINUSE, errno.EACCES):
            raise
        return GalleryServer((HOST, 0), handler)
