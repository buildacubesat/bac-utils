# SPDX-License-Identifier: MIT
"""The window's behaviour against a fake ``tkinter``: key handling, the busy guard, the counts.

Tk cannot open in the test environment; these tests stand a scripted
``Tk``/``Canvas`` in for it and drive the event handlers by hand.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from bac_store_product_cropper import gui
from bac_store_product_cropper.cli import plan_jobs
from bac_store_product_cropper.export import ExportOptions
from cropper_testkit import make_image


class FakeCanvas:
    instances: list[FakeCanvas] = []

    def __init__(self, root, **kwargs):
        self.items: dict[int, dict] = {}
        self.next_id = 1
        self.bindings: dict[str, object] = {}
        self.size = (kwargs.get("width"), kwargs.get("height"))
        FakeCanvas.instances.append(self)

    def pack(self):
        pass

    def _add(self, kind, **kw):
        self.items[self.next_id] = {"kind": kind, **kw}
        self.next_id += 1
        return self.next_id - 1

    def create_text(self, *args, **kw):
        return self._add("text", **kw)

    def create_image(self, *args, **kw):
        return self._add("image", **kw)

    def create_line(self, *args, **kw):
        return self._add("line", **kw)

    def delete(self, tag):
        if tag == "all":
            self.items.clear()
        else:
            self.items = {k: v for k, v in self.items.items() if v.get("tags") != tag}

    def itemconfigure(self, item, **kw):
        if item in self.items:
            self.items[item].update(kw)

    def tag_raise(self, item):
        pass

    def bind(self, seq, fn):
        self.bindings[seq] = fn

    def text_of(self, item):
        return self.items.get(item, {}).get("text", "")


class FakeTk:
    instances: list[FakeTk] = []

    def __init__(self):
        self.bindings: dict[str, object] = {}
        self.after_calls: list[tuple[int, object]] = []
        self.destroyed = False
        FakeTk.instances.append(self)

    def update_idletasks(self):
        pass

    def title(self, text):
        self.title_text = text

    def configure(self, **kw):
        pass

    def bind(self, seq, fn):
        self.bindings[seq] = fn

    def protocol(self, name, fn):
        self.bindings[name] = fn

    def after(self, ms, fn):
        self.after_calls.append((ms, fn))

    def destroy(self):
        self.destroyed = True

    def mainloop(self):
        pass

    def run_pending(self):
        """Run the queued ``after`` callbacks in order (Tk's own loop fires them later)."""
        while self.after_calls:
            _, fn = self.after_calls.pop(0)
            fn()


class FakePhoto:
    def __init__(self, image):
        self.size = image.size


class FakeEvent:
    def __init__(self, x=0, y=0, delta=0, num=None):
        self.x, self.y, self.delta, self.num = x, y, delta, num


@pytest.fixture
def fake_tk(monkeypatch):
    module = types.ModuleType("tkinter")
    module.Tk = FakeTk
    module.Canvas = FakeCanvas
    module.TclError = RuntimeError
    monkeypatch.setitem(sys.modules, "tkinter", module)
    image_tk = types.ModuleType("PIL.ImageTk")
    image_tk.PhotoImage = FakePhoto
    monkeypatch.setitem(sys.modules, "PIL.ImageTk", image_tk)
    import PIL

    monkeypatch.setattr(PIL, "ImageTk", image_tk, raising=False)
    FakeTk.instances.clear()
    FakeCanvas.instances.clear()
    return module


def start(photos: Path, **options):
    jobs = plan_jobs([photos], None, force=False)
    reports: list[tuple[str, str, str]] = []

    def report(kind, job, note):
        reports.append((kind, job.source.name, note))

    counts = gui.run(jobs, ExportOptions(**options), report=report)
    return jobs, FakeTk.instances[-1], counts, reports


def test_enter_saves_and_a_second_enter_during_the_pause_is_ignored(photos: Path, fake_tk):
    jobs, root, counts, reports = start(photos)
    confirm = root.bindings["<Return>"]
    confirm(FakeEvent())
    confirm(FakeEvent())  # the bug in 0.1.0: this saved the same crop under the next name
    assert [r[0] for r in reports] == ["done"]
    assert reports[0][1] == "square.tif"
    assert (photos / "out_webp" / "square.webp").exists()
    assert not (photos / "out_webp" / "tall.webp").exists()
    root.run_pending()  # the 800 ms pause ends, the next image loads
    confirm(FakeEvent())
    assert [r[1] for r in reports] == ["square.tif", "tall.png"]
    assert counts.saved == 2 and counts.remaining == 2


def test_skip_reset_pan_zoom_and_quit(photos: Path, fake_tk):
    jobs, root, counts, reports = start(photos, aspect=2.0)
    canvas = FakeCanvas.instances[-1]
    assert canvas.size == (900, 450)  # the preview has the crop's aspect, no stretching
    root.bindings["s"](FakeEvent())
    assert reports == [("skipped", "square.tif", "skipped by hand")]
    root.bindings["<Right>"](FakeEvent())  # busy during the 300 ms pause: ignored
    assert len(reports) == 1
    root.run_pending()
    app = _app_of(canvas)
    state = app.state
    assert (state.width, state.height) == (300, 600)  # tall.png
    assert (state.cw, state.ch) == (300, 150)
    canvas.bindings["<ButtonPress-1>"](FakeEvent(100, 100))
    canvas.bindings["<B1-Motion>"](FakeEvent(100, 50))  # drag up: the crop moves down the picture
    assert state.cy > 300
    root.bindings["<Button-4>"](FakeEvent(450, 225, num=4))  # one notch in
    assert state.cw == pytest.approx(285)
    assert canvas.text_of(app.zoom_id) == "105%"
    root.bindings["r"](FakeEvent())
    assert (state.cw, state.cy) == (300, 300)
    root.bindings["q"](FakeEvent())
    assert root.destroyed
    assert counts.skipped == 1 and counts.remaining == 3


def _app_of(canvas: FakeCanvas):
    """The ``_Cropper`` whose canvas this is – reached through the bound methods."""
    handler = canvas.bindings["<ButtonPress-1>"]
    return handler.__self__


def test_unreadable_image_is_failed_and_skipped_over(photos: Path, fake_tk):
    (photos / "square.tif").write_bytes(b"not an image")
    jobs, root, counts, reports = start(photos)
    assert reports[0][0] == "failed" and reports[0][1] == "square.tif"
    assert counts.failed == 1
    root.bindings["<Return>"](FakeEvent())
    assert reports[1] == ("done", "tall.png", reports[1][2])


def test_finishing_the_last_image_closes_the_window(photos: Path, fake_tk):
    jobs, root, counts, reports = start(photos, target_kb=0)
    for _ in range(4):
        root.bindings["<space>"](FakeEvent())
        root.run_pending()
    assert counts.saved == 4 and counts.remaining == 0
    assert root.destroyed
    assert all((photos / "out_webp" / f"{p.stem}.webp").exists() for p in photos.glob("*.*") if p.suffix != ".txt")


def test_unwritable_target_is_failed_not_fatal(photos: Path, fake_tk):
    (photos / "out_webp").write_text("a file where the folder should be", encoding="utf-8")
    jobs, root, counts, reports = start(photos)
    root.bindings["<Return>"](FakeEvent())
    assert reports[0][0] == "failed" and reports[0][1] == "square.tif"
    root.run_pending()
    app = _app_of(FakeCanvas.instances[-1])
    assert app.busy is False  # the next image is on screen and the window is alive
    root.bindings["WM_DELETE_WINDOW"]()
    assert root.destroyed
    assert counts.failed == 1 and counts.remaining == 3


def test_busy_guard_covers_reset_and_wheel(photos: Path, fake_tk):
    jobs, root, counts, reports = start(photos)
    app = _app_of(FakeCanvas.instances[-1])
    app.state.zoom(2)
    zoomed = app.state.cw
    root.bindings["<Return>"](FakeEvent())  # busy until run_pending
    root.bindings["r"](FakeEvent())
    root.bindings["<Button-4>"](FakeEvent(num=4))
    assert app.state.cw == zoomed


def test_existing_outputs_are_not_offered(photos: Path, fake_tk):
    make_image(photos / "out_webp" / "wide.webp", (10, 10))
    jobs, root, counts, reports = start(photos)
    assert counts.remaining == 3
    names = {j.source.name for j in jobs if j.status == "pending"}
    assert "wide.jpg" not in names
