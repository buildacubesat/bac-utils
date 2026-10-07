# SPDX-License-Identifier: MIT
"""The Tk window: one image at a time, drag to pan, wheel to zoom, Enter to save.

Tk is imported inside :func:`run` so the package imports (and the pure
functions test) on a Python without Tk; the CLI reports the missing module
as an error with the package to install.

Keys: Enter / Space save and advance, S / → skip, R reset the crop,
Q / Esc quit. While an image is being saved or the next one loads, the
window is *busy* and keys are ignored – 0.1.0 accepted a second Enter
during its 800 ms pause and saved the same crop under the next file's name.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from bac_media_convert.batch import Job
from bac_media_convert.webp import load_oriented
from PIL import Image

from bac_common.errors import BacError, ExternalToolError

from .crop import CropState, preview_size, wheel_steps
from .export import ExportOptions, Saved, save_crop

__all__ = ["PREVIEW_PX", "Outcome", "Counts", "run"]

PREVIEW_PX = 900
BG, INK, MUTED = "#201E1C", "#EFEFED", "#A3A29C"
HELP = "Scroll: zoom · Drag: pan · Enter/Space: save & next · S/→: skip · R: reset · Q/Esc: quit"

Report = Callable[[str, Job, str], None]
"""``report(kind, job, note)`` with kind ``done`` | ``skipped`` | ``failed`` – the CLI prints the ✓/✗ lines."""


@dataclass(slots=True)
class Outcome:
    job: Job
    kind: str
    note: str = ""


@dataclass(slots=True)
class Counts:
    saved: int = 0
    skipped: int = 0
    failed: int = 0
    remaining: int = 0
    outcomes: list[Outcome] = field(default_factory=list)


def run(jobs: list[Job], options: ExportOptions, *, report: Report | None = None) -> Counts:
    """Open the window over ``jobs`` (those still ``pending``) and block until the last one or the user quits."""
    pending = [job for job in jobs if job.status == "pending"]
    counts = Counts(remaining=len(pending))
    if not pending:
        return counts
    try:
        import tkinter as tk

        from PIL import ImageTk
    except ImportError as exc:
        raise ExternalToolError(
            "Tk is not available in this Python.",
            "Install the python3-tk package (Debian/Ubuntu: apt install python3-tk) or a Python built with Tk.",
        ) from exc

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise ExternalToolError("Cannot open a window.", f"{exc} – is a display available?") from exc

    app = _Cropper(root, tk, ImageTk, pending, options, counts, report)
    app.start()
    root.mainloop()
    return counts


def _reason(exc: BaseException) -> str:
    return exc.message if isinstance(exc, BacError) else (str(exc).strip() or type(exc).__name__)


class _Cropper:
    def __init__(self, root, tk, image_tk, jobs: list[Job], options: ExportOptions, counts: Counts, report) -> None:
        self.root, self.tk, self.image_tk = root, tk, image_tk
        self.jobs, self.options, self.counts, self.report = jobs, options, counts, report
        self.index = 0
        self.busy = True
        self.state: CropState | None = None
        self.image = None
        self.photo = None
        self.drag_last: tuple[int, int] | None = None
        self.pw, self.ph = preview_size(options.aspect, PREVIEW_PX)

        root.title("bac-store-product-cropper")
        root.configure(bg=BG)
        self.canvas = tk.Canvas(root, width=self.pw, height=self.ph, bg=BG, highlightthickness=0)
        self.canvas.pack()
        font = ("Helvetica", 12)
        self.help_id = self.canvas.create_text(10, 10, anchor="nw", fill=MUTED, font=font, text=HELP)
        self.file_id = self.canvas.create_text(10, self.ph - 10, anchor="sw", fill=INK, font=font, text="")
        self.zoom_id = self.canvas.create_text(self.pw - 10, 10, anchor="ne", fill=INK, font=font, text="")
        self.toast_id = self.canvas.create_text(self.pw // 2, self.ph - 40, anchor="s", fill=INK, font=font, text="")

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _e: setattr(self, "drag_last", None))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            root.bind(seq, self.on_wheel)  # on the toplevel: Windows delivers wheel events to the focused widget
        for seq in ("<Return>", "<KP_Enter>", "<space>"):
            root.bind(seq, self.on_confirm)
        for seq in ("s", "S", "<Right>"):
            root.bind(seq, self.on_skip)
        for seq in ("r", "R"):
            root.bind(seq, self.on_reset)
        for seq in ("q", "Q", "<Escape>"):
            root.bind(seq, self.on_quit)
        root.protocol("WM_DELETE_WINDOW", self.on_quit)

    # -- flow ----------------------------------------------------------------------

    @property
    def job(self) -> Job:
        return self.jobs[self.index]

    def start(self) -> None:
        self.load_current()

    def load_current(self) -> None:
        if self.index >= len(self.jobs):
            self.finish()
            return
        job = self.job
        try:
            self.image = load_oriented(job.source)
        except (BacError, OSError) as exc:
            self.record("failed", _reason(exc))
            self.index += 1
            self.load_current()
            return
        self.state = CropState.initial(self.image.width, self.image.height, self.options.aspect)
        self.canvas.itemconfigure(self.file_id, text=f"{job.source.name}  ({self.index + 1}/{len(self.jobs)})")
        self.render()
        self.busy = False

    def record(self, kind: str, note: str = "") -> None:
        job = self.job
        job.status, job.note = kind, note
        self.counts.outcomes.append(Outcome(job, kind, note))
        self.counts.remaining -= 1
        if kind == "done":
            self.counts.saved += 1
        elif kind == "skipped":
            self.counts.skipped += 1
        else:
            self.counts.failed += 1
        if self.report:
            self.report(kind, job, note)

    def advance(self, delay_ms: int) -> None:
        self.index += 1
        self.root.after(delay_ms, self.load_current)

    def finish(self) -> None:
        self.busy = True
        self.canvas.delete("all")
        self.canvas.create_text(self.pw // 2, self.ph // 2, text="Done", fill=INK, font=("Helvetica", 24))
        self.root.after(1500, self.root.destroy)

    # -- drawing -------------------------------------------------------------------

    def render(self) -> None:
        assert self.state is not None and self.image is not None
        box = self.state.box()
        shown = self.image.crop(box).resize((self.pw, self.ph), Image.Resampling.BILINEAR)  # fast enough while dragging
        self.photo = self.image_tk.PhotoImage(shown)
        self.canvas.delete("img")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo, tags="img")
        self.canvas.delete("crosshair")
        cx, cy, arm, gap = self.pw // 2, self.ph // 2, 12, 4
        for x0, y0, x1, y1 in (
            (cx - arm, cy, cx - gap, cy),
            (cx + gap, cy, cx + arm, cy),
            (cx, cy - arm, cx, cy - gap),
            (cx, cy + gap, cx, cy + arm),
        ):
            self.canvas.create_line(x0, y0, x1, y1, fill=INK, width=1, tags="crosshair")
        self.canvas.itemconfigure(self.zoom_id, text=f"{self.state.zoom_percent}%")
        for item in (self.help_id, self.file_id, self.zoom_id, self.toast_id):
            self.canvas.tag_raise(item)

    def toast(self, text: str, ms: int = 1200) -> None:
        self.canvas.itemconfigure(self.toast_id, text=text)
        self.root.after(ms, lambda: self.canvas.itemconfigure(self.toast_id, text=""))

    # -- events --------------------------------------------------------------------

    def on_press(self, event) -> None:
        if not self.busy:
            self.drag_last = (event.x, event.y)

    def on_drag(self, event) -> None:
        if self.busy or self.drag_last is None or self.state is None:
            return
        lx, ly = self.drag_last
        self.state.pan(event.x - lx, event.y - ly, self.pw)
        self.drag_last = (event.x, event.y)
        self.render()

    def on_wheel(self, event) -> None:
        if self.busy or self.state is None:
            return
        steps = wheel_steps(getattr(event, "delta", 0), getattr(event, "num", None))
        if steps:
            u = min(0.5, max(-0.5, (event.x - self.pw / 2) / self.pw))
            v = min(0.5, max(-0.5, (event.y - self.ph / 2) / self.ph))
            self.state.zoom(steps, u, v)
            self.render()

    def on_confirm(self, _event=None) -> None:
        if self.busy or self.state is None or self.image is None:
            return
        self.busy = True
        job = self.job
        self.toast("Saving …", ms=60_000)
        self.root.update_idletasks()  # redraw only; key events stay queued behind the busy guard
        try:
            saved: Saved = save_crop(self.image, self.state.box(), job.target, self.options)
        except (BacError, OSError) as exc:  # an unwritable folder must not leave the window dead
            self.record("failed", _reason(exc))
            self.toast(f"Failed: {_reason(exc)}")
        else:
            self.record("done", f"{saved.width}×{saved.height} px, {saved.kb:.0f} kB at q{saved.quality}")
            self.toast(f"Saved {job.target.name} ({saved.kb:.0f} kB at q{saved.quality})")
        self.advance(800)

    def on_skip(self, _event=None) -> None:
        if self.busy:
            return
        self.busy = True
        self.record("skipped", "skipped by hand")
        self.toast("Skipped")
        self.advance(300)

    def on_reset(self, _event=None) -> None:
        if self.busy or self.state is None:
            return
        self.state.reset()
        self.render()

    def on_quit(self, _event=None) -> None:
        self.busy = True
        self.root.destroy()
