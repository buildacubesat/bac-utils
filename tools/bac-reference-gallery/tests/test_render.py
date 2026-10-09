# SPDX-License-Identifier: MIT
"""The renderer's own logic with fakes for Playwright: shutdown on errors and Ctrl-C, the font gate."""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest
from bac_reference_gallery.render import FontGate, Renderer, short_error
from bac_reference_gallery.site import Board

from bac_common.errors import ExternalToolError


class Recorder:
    def __init__(self):
        self.calls: list[str] = []


class FakePage:
    def __init__(self, log: Recorder, fail_with: BaseException | None = None):
        self.log, self.fail_with = log, fail_with

    def goto(self, *args, **kwargs):
        if self.fail_with is not None:
            raise self.fail_with

    def close(self):
        self.log.calls.append("page.close")


class FakeContext:
    def __init__(self, log, fail_with=None):
        self.log, self.fail_with = log, fail_with

    def new_page(self):
        return FakePage(self.log, self.fail_with)


def renderer(fail_with=None) -> tuple[Renderer, Recorder]:
    log = Recorder()
    r = Renderer.__new__(Renderer)
    Renderer.__init__(r, browser=None, theme="light")  # type: ignore[arg-type]
    r._context = FakeContext(log, fail_with)
    r._chromium = type("C", (), {"close": lambda self: log.calls.append("chromium.close")})()
    r._pw = type("P", (), {"stop": lambda self: log.calls.append("pw.stop")})()
    return r, log


BOARD = Board("x", Path("/nowhere/x.html"))


@contextlib.contextmanager
def entered(r: Renderer):
    """The with-statement's exit half, without starting Playwright."""
    try:
        yield r
    except BaseException as exc:
        r.__exit__(type(exc), exc, None)
        raise
    r.__exit__(None, None, None)


def test_a_failing_page_is_closed_and_the_browser_shut_down():
    r, log = renderer(RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        with entered(r):
            r.render(BOARD, None, None)
    assert log.calls == ["page.close", "chromium.close", "pw.stop"]


def test_ctrl_c_skips_every_close_so_nothing_waits_on_a_dead_driver():
    r, log = renderer(KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        with entered(r):
            r.render(BOARD, None, None)
    assert log.calls == []


def test_ctrl_c_between_boards_skips_the_closes_too():
    r, log = renderer()
    with pytest.raises(KeyboardInterrupt):
        with entered(r):
            raise KeyboardInterrupt
    assert log.calls == []


def test_a_failing_close_does_not_hide_the_error_that_ended_the_run():
    r, log = renderer(RuntimeError("the real problem"))

    def bad_close():
        raise RuntimeError("close failed")

    r._chromium.close = bad_close
    with pytest.raises(RuntimeError, match="the real problem"):
        with entered(r):
            r.render(BOARD, None, None)
    assert log.calls == ["page.close", "pw.stop"]


def test_a_failing_close_after_a_clean_run_is_reported():
    r, log = renderer()

    def bad_close():
        raise RuntimeError("close failed")

    r._chromium.close = bad_close
    with pytest.raises(ExternalToolError, match="did not close cleanly"):
        with entered(r):
            pass
    assert log.calls == ["pw.stop"]


class FakeRoute:
    def __init__(self, fetch_error: Exception | None = None):
        self.fetch_error = fetch_error
        self.events: list[str] = []

    def fetch(self, timeout):
        self.events.append(f"fetch {timeout}")
        if self.fetch_error:
            raise self.fetch_error
        return "response"

    def fulfill(self, response):
        self.events.append(f"fulfill {response}")

    def abort(self):
        self.events.append("abort")


def test_the_font_gate_passes_fonts_through_while_the_host_answers():
    gate = FontGate(timeout_ms=1234)
    route = FakeRoute()
    gate(route)
    assert route.events == ["fetch 1234", "fulfill response"]
    assert not gate.unreachable


def test_the_font_gate_gives_up_after_the_first_timeout():
    gate = FontGate()
    first = FakeRoute(TimeoutError("Timeout 8000ms exceeded"))
    gate(first)
    assert first.events[-1] == "abort" and gate.unreachable
    later = FakeRoute()
    gate(later)
    assert later.events == ["abort"]  # no second wait


def test_short_error_keeps_the_first_line():
    assert short_error(RuntimeError("one\nCall log:\n  - two")) == "one"
    assert short_error(RuntimeError("")) == "RuntimeError"
    assert len(short_error(RuntimeError("x" * 400))) == 160
