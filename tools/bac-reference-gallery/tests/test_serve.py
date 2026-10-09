# SPDX-License-Identifier: MIT
from __future__ import annotations

import _thread
import http.client
import socket
import threading
import urllib.request
import webbrowser
from contextlib import contextmanager

import pytest
from bac_reference_gallery import cli, serve
from gallery_testkit import copy_gallery

from bac_common.testing import invoke


@contextmanager
def running(folder, port=0):
    server = serve.make_server(folder, port)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def get(server, path):
    conn = http.client.HTTPConnection(serve.HOST, server.server_address[1], timeout=5)
    try:
        conn.request("GET", path)  # sent as written: no client-side normalisation of ".."
        response = conn.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read()
    finally:
        conn.close()


@pytest.fixture
def gallery(tmp_path):
    return copy_gallery(tmp_path / "gallery")


def test_serves_the_pages_with_their_folder(gallery):
    with running(gallery) as server:
        status, kind, body = get(server, "/")
        assert status == 200 and kind.startswith("text/html") and b"examples/ops-vs-mission.html" in body
        assert get(server, "/css/tokens.css")[:2] == (200, "text/css")
        assert get(server, "/css/index.css")[0] == 200
        assert get(server, "/examples/product-sheet.html")[0] == 200
        assert get(server, "/assets/led-board.svg")[1] == "image/svg+xml"
        assert get(server, "/examples/missing.html")[0] == 404
        assert server.requests == 6


def test_stays_inside_the_gallery_folder(gallery):
    (gallery.parent / "secret.txt").write_text("outside")
    with running(gallery) as server:
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/css/../../secret.txt"):
            status, _, body = get(server, path)
            assert status == 404 and b"outside" not in body


def test_answers_on_the_loopback_address_only(gallery):
    with running(gallery) as server:
        assert server.server_address[0] == "127.0.0.1"
        assert server.url == f"http://127.0.0.1:{server.server_address[1]}/"


def test_a_taken_port_falls_back_to_a_free_one(gallery):
    with socket.socket() as busy:
        busy.bind((serve.HOST, 0))
        busy.listen()
        taken = busy.getsockname()[1]
        with running(gallery, taken) as server:
            assert server.server_address[1] != taken
            assert get(server, "/")[0] == 200


def test_no_caching_so_an_edited_page_shows_on_reload(gallery):
    with running(gallery) as server:
        conn = http.client.HTTPConnection(serve.HOST, server.server_address[1], timeout=5)
        conn.request("GET", "/index.html")
        response = conn.getresponse()
        response.read()
        conn.close()
        assert response.getheader("Cache-Control") == "no-store"


@pytest.fixture
def served(monkeypatch):
    """Real servers on free ports in place of the fixed one; the list holds every server made."""
    made = []
    real = serve.make_server

    def make(folder):
        made.append(real(folder, 0))
        return made[-1]

    monkeypatch.setattr(serve, "make_server", make)
    return made


def _port_answers(port):
    try:
        with socket.create_connection((serve.HOST, port), timeout=1):
            return True
    except OSError:
        return False


def test_cli_answers_before_the_browser_opens_and_stops_on_ctrl_c(monkeypatch, gallery, served):
    fetched = []

    def browser_that_fetches(url):
        # some launchers return only when the browser exits, so the page must load meanwhile
        with urllib.request.urlopen(url, timeout=5) as response:
            fetched.append(response.status)
        threading.Timer(0.2, _thread.interrupt_main).start()  # then Ctrl-C
        return True

    monkeypatch.setattr(webbrowser, "open", browser_that_fetches)
    r = invoke(cli._main, ["--serve", "--source", str(gallery)])
    assert r.exit_code == 0, r.stderr
    assert fetched == [200]
    assert "Opening it in the default browser" in r.stdout and "Serving until Ctrl-C" in r.stdout
    assert "Requests" in r.stdout and served[0].url in r.stdout
    assert served[0].requests == 1
    assert not _port_answers(served[0].server_address[1])  # closed


def test_cli_ctrl_c_while_the_browser_opens_exits_cleanly(monkeypatch, gallery, served):
    def interrupted(url):
        raise KeyboardInterrupt

    monkeypatch.setattr(webbrowser, "open", interrupted)
    r = invoke(cli._main, ["--serve", "--source", str(gallery)])
    assert r.exit_code == 0
    assert "Requests" in r.stdout and "Interrupted" not in r.stderr
    assert not _port_answers(served[0].server_address[1])


@pytest.mark.parametrize("fails", [False, True], ids=["returns-false", "raises"])
def test_cli_says_so_when_no_browser_starts(monkeypatch, gallery, served, fails):
    def no_browser(url):
        threading.Timer(0.3, _thread.interrupt_main).start()  # Ctrl-C once the server runs
        if fails:
            raise OSError("no launcher")
        return False

    monkeypatch.setattr(webbrowser, "open", no_browser)
    r = invoke(cli._main, ["--serve", "--source", str(gallery)])
    assert r.exit_code == 0
    assert "open the address yourself" in r.stdout


def test_a_dropped_connection_prints_no_traceback(gallery, capsys):
    with running(gallery) as server:
        try:
            raise BrokenPipeError(32, "Broken pipe")
        except BrokenPipeError:
            server.handle_error(None, ("127.0.0.1", 1))
    assert "Traceback" not in capsys.readouterr().err


def test_cli_dry_run_starts_no_server(monkeypatch, gallery):
    def refuse(folder):
        raise AssertionError("a dry run must not start the server")

    monkeypatch.setattr(serve, "make_server", refuse)
    monkeypatch.setattr(webbrowser, "open", refuse)
    r = invoke(cli._main, ["--serve", "--dry-run", "--source", str(gallery)])
    assert r.exit_code == 0
    assert "8765" in r.stdout and "dry run" in r.stdout


def test_cli_reports_a_server_that_does_not_start(monkeypatch, gallery):
    def fail(folder):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(serve, "make_server", fail)
    r = invoke(cli._main, ["--serve", "--source", str(gallery)])
    assert r.exit_code == 1
    assert "did not start" in r.stderr
    assert "Requests" in r.stdout  # the summary still prints


@pytest.mark.parametrize(
    "extra",
    [["--only", "ops-vs-mission"], ["--format", "png"], ["--theme", "dark"], ["--out-dir", "x"]],
)
def test_cli_serve_refuses_render_options(extra):
    r = invoke(cli._main, ["--serve", *extra])
    assert r.exit_code == 2
    assert extra[0] in r.stderr
