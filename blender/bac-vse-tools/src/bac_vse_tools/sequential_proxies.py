# SPDX-License-Identifier: MIT
"""Sequential Proxies: build the proxy of one movie strip at a time, waiting for each file to settle.

Blender's own Rebuild Proxy queues every selected strip into one job and
offers no per-strip progress or stop. This operator selects one strip,
triggers the build as a background job (``INVOKE_DEFAULT`` – the plain
Python call runs the synchronous path and blocks the interface for the
whole encode), and watches the proxy file until it exists, has changed
since the build was triggered, and has stayed unchanged for the stable
time; Blender exposes no status for the proxy job to Python, so the file is
the only signal. A timeout per strip bounds the wait whether the file has
appeared or not (the 1.x add-on timed out only while it was absent, and
counted a proxy left over from an earlier build as done).
"""

from __future__ import annotations

import os
import time

import bpy
from bpy.types import Operator, Panel

from . import _common
from ._logic import ProxyWait, proxy_artifact
from .settings import settings_of

__all__ = ["STATUS_PROP", "ProxyRun", "candidate_strips", "artifact_for", "BAC_OT_vse_sequential_proxies"]

STATUS_PROP = "bac_vse_proxy_status"


def candidate_strips(scene, scope: str) -> tuple[list, int]:
    """The movie strips the run covers, in timeline order, and how many were left out for sitting inside a meta.

    Top level only: Blender's Rebuild Proxy works on the open seqbase, so a
    movie inside a meta would be selected and never built. Two strips on the
    same file share one proxy, so the second is left out as well.
    """
    seqed = scene.sequence_editor
    if seqed is None:
        return [], 0
    inside_metas = sum(1 for s in _common.all_strips(seqed) if s.type == "MOVIE") - sum(
        1 for s in _common.strips(seqed) if s.type == "MOVIE"
    )
    movies = [s for s in _common.strips(seqed) if s.type == "MOVIE"]
    if scope == "SELECTED":
        movies = [s for s in movies if s.select]
    elif scope == "CURRENT":
        movies = [s for s in movies if s.frame_final_start >= scene.frame_current]
    movies.sort(key=lambda s: (s.frame_final_start, s.channel))
    seen: set[str] = set()
    unique = []
    for strip in movies:
        key = bpy.path.abspath(strip.filepath)
        if key not in seen:
            seen.add(key)
            unique.append(strip)
    return unique, inside_metas


def artifact_for(seqed, strip, size: int):
    """The proxy file Blender writes for ``strip`` at ``size`` percent, resolved like Blender does.

    Project storage with an empty directory means ``//BL_proxy`` beside the
    ``.blend`` file – or, for a file that was never saved, a ``BL_proxy``
    folder in the working directory, as ``bpy.path.abspath`` resolves it.
    """
    proxy = strip.proxy
    return proxy_artifact(
        bpy.path.abspath(strip.filepath),
        size,
        storage=seqed.proxy_storage,
        project_dir=bpy.path.abspath(seqed.proxy_dir or "//BL_proxy"),
        custom_dir=bpy.path.abspath(proxy.directory) if proxy is not None and proxy.directory else "",
        use_custom_dir=bool(proxy is not None and proxy.use_proxy_custom_directory),
    )


def _mtime(path) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


class ProxyRun:
    """The strips to build, the one in progress and its wait. ``tick(now)`` moves it forward.

    ``clock`` is what the wait is timed with; the build is triggered through
    ``trigger``, which the tests replace to check the wait without encoding.
    """

    def __init__(
        self,
        scene,
        strips: list,
        *,
        size: int,
        stable_time: float,
        timeout: float,
        skip_existing: bool = True,
        clock=time.time,
    ) -> None:
        self.scene = scene
        self.strips = list(strips)
        self.size = int(size)
        self.stable_time = float(stable_time)
        self.timeout = float(timeout)
        self.skip_existing = bool(skip_existing)
        self.clock = clock
        self.index = 0
        self.wait: ProxyWait | None = None
        self.artifact = None
        self.built = self.timed_out = self.skipped = 0
        self.outcomes: list[tuple[str, str]] = []
        """``(strip name, outcome)`` with outcome ``built`` | ``timeout`` | ``exists`` | ``skipped`` | ``failed``."""

    @property
    def total(self) -> int:
        return len(self.strips)

    @property
    def done(self) -> bool:
        return self.index >= len(self.strips)

    @property
    def current(self):
        return self.strips[self.index]

    def tick(self, now: float | None = None) -> str | None:
        """One timer tick: start the next build or check the running one. Returns what happened, if anything."""
        if self.done:
            return None
        if self.wait is None:
            return self._start()
        now = self.clock() if now is None else now
        state = self.wait.observe(now, _mtime(self.artifact))
        if state == "waiting":
            return None
        self._record("built" if state == "done" else "timeout")
        return state

    def _start(self) -> str:
        strip = self.current
        seqed = self.scene.sequence_editor
        strip.use_proxy = True
        proxy = strip.proxy
        if proxy.use_proxy_custom_file:
            self._record("skipped")
            return "skipped"
        self.artifact = artifact_for(seqed, strip, self.size)
        before = _mtime(self.artifact)
        if before is not None and self.skip_existing:
            self._record("exists")
            return "exists"
        setattr(proxy, f"build_{self.size}", True)  # the strip's other sizes stay as they were
        proxy.use_overwrite = True
        for other in _common.all_strips(seqed):
            other.select = False
        strip.select = True
        seqed.active_strip = strip
        try:
            self.trigger()
        except RuntimeError as exc:
            print(f"[bac-vse-tools] proxy build failed to start for {strip.name}: {exc}")
            self._record("failed")
            return "failed"
        # the clock starts after the call: in background mode the build runs inline and takes its time
        self.wait = ProxyWait(self.clock(), before, self.stable_time, self.timeout)
        return "started"

    def trigger(self) -> None:
        """Start Blender's proxy build for the selected strip as a background job."""
        bpy.ops.sequencer.rebuild_proxy("INVOKE_DEFAULT")

    def _record(self, outcome: str) -> None:
        self.outcomes.append((self.current.name, outcome))
        if outcome == "built":
            self.built += 1
        elif outcome == "timeout":
            self.timed_out += 1
        else:
            self.skipped += 1
        self.index += 1
        self.wait = None
        self.artifact = None

    def summary(self, cancelled: bool = False) -> str:
        head = "Cancelled" if cancelled else "Finished"
        return f"{head}: {self.built} built, {self.timed_out} timed out, {self.skipped} skipped"


class BAC_OT_vse_sequential_proxies(Operator):
    """Build the proxies of the movie strips one after the other, waiting for each file to settle"""

    bl_idname = "sequencer.bac_sequential_proxies"
    bl_label = "Sequential Proxy Build"
    bl_options = {"REGISTER"}

    _timer = None
    _run: ProxyRun | None = None

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.sequence_editor is not None

    _selection = None

    def execute(self, context):
        settings = settings_of(context)
        strips, inside_metas = candidate_strips(context.scene, settings.proxy_scope)
        if inside_metas:
            self.report({"INFO"}, f"{inside_metas} movie strip(s) inside meta strips left out")
        if not strips:
            self.report({"WARNING"}, "No movie strips to build proxies for.")
            return {"CANCELLED"}
        self._run = ProxyRun(
            context.scene,
            strips,
            size=int(settings.proxy_size),
            stable_time=settings.stable_time,
            timeout=settings.timeout_seconds,
            skip_existing=settings.skip_existing,
        )
        self._selection = _common.selection_snapshot(context.scene.sequence_editor)
        wm = context.window_manager
        wm.progress_begin(0, self._run.total)
        self._status(context, f"Proxies: 0/{self._run.total}")
        _common.start_timer(self, context, settings.check_interval)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        run = self._run
        if event.type == "ESC":
            self._finish(context, cancelled=True)
            return {"CANCELLED"}
        if event.type != "TIMER" or run is None:
            return {"PASS_THROUGH"}  # the editor stays usable while proxies build
        if run.done:
            self._finish(context)
            return {"FINISHED"}
        step = run.index + 1
        name = run.current.name
        happened = run.tick()
        if happened == "started":
            context.window_manager.progress_update(step)
            self._status(context, f"Proxy {step}/{run.total}: {name}")
        elif happened == "timeout":
            self.report({"WARNING"}, f"Timeout: {name}")
        elif happened == "exists":
            self.report({"INFO"}, f"{name}: proxy exists, left alone")
        elif happened == "skipped":
            self.report({"INFO"}, f"Skipped {name}: it uses a custom proxy file")
        elif happened == "failed":
            self.report({"WARNING"}, f"Could not start the proxy build for {name}")
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        """Blender ends the modal itself (file load, window closed): release the timer and the progress bar."""
        self._finish(context, cancelled=True)

    def _status(self, context, text: str) -> None:
        _common.set_status(context.window_manager, STATUS_PROP, text)
        _common.set_status_text(context, text)

    def _finish(self, context, cancelled: bool = False) -> None:
        _common.stop_timer(self, context)
        wm = context.window_manager
        wm.progress_end()
        if self._selection is not None and context.scene.sequence_editor is not None:
            _common.restore_selection(context.scene.sequence_editor, self._selection)
            self._selection = None
        text = self._run.summary(cancelled) if self._run else ("Cancelled" if cancelled else "Finished")
        _common.set_status(wm, STATUS_PROP, f"Proxies – {text}")
        _common.set_status_text(context, None)
        self.report({"INFO"}, text)


class BAC_PT_vse_sequential_proxies(Panel):
    bl_label = "Sequential Proxies"
    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"
    bl_category = _common.CATEGORY
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        settings = settings_of(context)
        col = layout.column(align=True)
        col.label(text="Build proxies one strip at a time")
        col.operator(BAC_OT_vse_sequential_proxies.bl_idname, icon="SEQUENCE")
        row = col.row(align=True)
        row.prop(settings, "proxy_scope")
        row.prop(settings, "proxy_size")
        col.prop(settings, "skip_existing")
        row = col.row(align=True)
        row.prop(settings, "stable_time")
        row.prop(settings, "check_interval")
        col.prop(settings, "timeout_seconds")
        _common.draw_status(col, context.window_manager, STATUS_PROP)
