# SPDX-License-Identifier: MIT
"""Bulk Import: every video and audio file of a folder, one after the other, at the end of the timeline.

The modal operator advances a :class:`BulkImportRun` by one file per timer
tick, so the interface keeps redrawing and the status line moves. Videos go
through Blender's own ``movie_strip_add`` operator with explicit arguments:
it is the one path that keeps audio and video in sync (it retimes a clip
whose frame rate differs from the scene's and offsets the audio by the
stream's start), which the data API does not. Audio-only files use
``strips.new_sound``.

Autosave is opt-in and writes *copies* into a folder of the user's choice.
The open file itself is never saved by this tool – the 1.x add-on saved it
after every clip, which made undo meaningless once a run had started.
"""

from __future__ import annotations

import traceback
from pathlib import Path

import bpy
from bpy.types import Operator, Panel

from . import _common
from ._logic import autosave_name, fps_settings, list_media, media_kind, min_frames
from .settings import settings_of

__all__ = ["STATUS_PROP", "BulkImportRun", "BAC_OT_vse_bulk_import", "BAC_PT_vse_bulk_import"]

STATUS_PROP = "bac_vse_bulk_status"
CHANNEL = 1
"""Blender's Add Movie puts the sound strip on this channel and the movie on the one above; audio-only files go here."""


class BulkImportRun:
    """One import job: the files, the position in them and the counts. ``step()`` imports the next file."""

    def __init__(
        self,
        scene,
        files: list[Path],
        *,
        min_length: float,
        retries: int,
        match_fps: bool,
        autosave_dir: Path | None,
    ) -> None:
        self.scene = scene
        self.files = list(files)
        self.min_length = float(min_length)
        self.retries = max(0, int(retries))
        self.match_fps = bool(match_fps)
        self.autosave_dir = autosave_dir
        self.index = 0
        self.imported = self.skipped = self.failed = 0
        self.outcomes: list[tuple[str, str, str]] = []
        """``(file name, kind, note)`` with kind ``imported`` | ``short`` | ``failed``."""
        self.autosave_failures = 0
        self.fps_changed: tuple[int, float] | None = None
        """``(fps, fps_base)`` when the first clip set the scene's frame rate."""
        self._first_into_empty = _common.last_end_frame(scene) < scene.frame_start

    @property
    def total(self) -> int:
        return len(self.files)

    @property
    def done(self) -> bool:
        return self.index >= len(self.files)

    @property
    def current(self) -> Path:
        return self.files[self.index]

    def step(self) -> tuple[str, str]:
        """Import the current file (with retries), autosave, advance. Returns ``(kind, note)``."""
        path = self.current
        kind, note = "failed", ""
        for attempt in range(1, self.retries + 2):
            try:
                kind, note = self._import_one(path)
                break
            except Exception as exc:  # noqa: BLE001 – a broken file must not end the run
                note = f"{type(exc).__name__}: {exc}".splitlines()[0]
                print(f"[bac-vse-tools] {path.name}: attempt {attempt} failed – {note}")
                traceback.print_exc()
        if kind == "imported":
            self.imported += 1
        elif kind == "short":
            self.skipped += 1
        else:
            self.failed += 1
        self.outcomes.append((path.name, kind, note))
        self.index += 1
        if self.autosave_dir is not None:
            self._autosave()
        return kind, note

    # -- the import itself ------------------------------------------------------

    def _import_one(self, path: Path) -> tuple[str, str]:
        scene = self.scene
        seqed = _common.ensure_sequence_editor(scene)
        coll = _common.strips(seqed)
        start = _common.last_end_frame(scene) + 1
        kind = media_kind(path)
        if kind == "video":
            created = self._add_movie(path, start)
            movie = next(s for s in created if s.type == "MOVIE")
            if self._first_into_empty and self.match_fps and abs(movie.fps - _common.scene_fps(scene)) > 0.01:
                # The operator retimed the clip to the old scene rate; set the rate first and add it again.
                fps, base = fps_settings(movie.fps)
                _remove_strips(coll, created)
                scene.render.fps, scene.render.fps_base = fps, base
                self.fps_changed = (fps, base)
                created = self._add_movie(path, start)
                movie = next(s for s in created if s.type == "MOVIE")
            measure = movie
        else:
            sound = coll.new_sound(path.stem, str(path), CHANNEL, start)
            if sound.frame_final_duration <= 1:
                _remove_sound(coll, sound)  # Blender makes a one-frame stub for a file it cannot decode
                raise RuntimeError("Blender could not read the audio file")
            measure = sound
            created = [sound]
        self._first_into_empty = False
        limit = min_frames(self.min_length, _common.scene_fps(scene))
        if limit and measure.frame_final_duration < limit:
            _remove_strips(coll, created)
            return "short", f"shorter than {self.min_length:g} s"
        return "imported", f"{measure.frame_final_duration} frames at {start}"

    def _add_movie(self, path: Path, start: int) -> list:
        """Blender's Add Movie with the sound track, at ``start`` on the default channel. Returns the new strips."""
        seqed = self.scene.sequence_editor
        before = {s.name for s in _common.all_strips(seqed)}
        bpy.ops.sequencer.movie_strip_add(**movie_add_arguments(path, start))  # raises on an unreadable file
        created = [s for s in _common.all_strips(seqed) if s.name not in before]
        if not any(s.type == "MOVIE" for s in created):
            raise RuntimeError("Blender added no movie strip")
        return created

    def _autosave(self) -> None:
        target = self.autosave_dir / autosave_name(bpy.data.filepath, self.index, self.total)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=str(target), copy=True)
        except Exception:  # noqa: BLE001 – an autosave failure must not end the run
            self.autosave_failures += 1
            print(f"[bac-vse-tools] autosave failed: {target}")
            traceback.print_exc()

    def summary(self, cancelled: bool = False) -> str:
        head = "Cancelled" if cancelled else "Finished"
        text = f"{head}: {self.imported} imported, {self.skipped} too short, {self.failed} failed"
        if self.autosave_failures:
            text += f", {self.autosave_failures} autosave failures"
        return text


def movie_add_arguments(path: Path, start: int) -> dict:
    """The keyword arguments for ``sequencer.movie_strip_add``, limited to the ones this Blender knows.

    ``adjust_playback_rate`` keeps a clip at its own speed in a scene with
    another frame rate, ``set_view_transform=False`` stops the operator from
    switching the scene's colour management, and ``use_framerate`` stays off
    because the run sets the scene rate itself in the ``(fps, fps_base)``
    form Blender's UI expects.
    """
    wanted = {
        "filepath": str(path),
        "frame_start": int(start),
        "channel": CHANNEL,
        "sound": True,
        "fit_method": "FIT",
        "adjust_playback_rate": True,
        "use_framerate": False,
        "set_view_transform": False,
    }
    known = bpy.ops.sequencer.movie_strip_add.get_rna_type().properties.keys()
    return {key: value for key, value in wanted.items() if key in known}


def _remove_strips(coll, created) -> None:
    for strip in created:
        if strip.type == "SOUND":
            _remove_sound(coll, strip)
        else:
            coll.remove(strip)


def _remove_sound(coll, strip) -> None:
    """Remove a sound strip and the sound datablock it brought along when nothing else uses it."""
    sound = strip.sound
    coll.remove(strip)
    if sound is not None and sound.users == 0:
        bpy.data.sounds.remove(sound)


def prepare_run(context) -> tuple[BulkImportRun | None, str | None]:
    """Build the run from the scene's settings; the second value is the error to report instead."""
    settings = settings_of(context)
    if not settings.import_dir:
        return None, "Choose a folder first."
    folder = Path(bpy.path.abspath(settings.import_dir))
    if not folder.is_dir():
        return None, f"Folder not found: {folder}"
    files = list_media(folder)
    if not files:
        return None, "No video or audio files in that folder."
    autosave_dir = None
    if settings.autosave:
        if not settings.autosave_dir:
            return None, "Autosave is on but no autosave folder is set."
        autosave_dir = Path(bpy.path.abspath(settings.autosave_dir))
    run = BulkImportRun(
        context.scene,
        files,
        min_length=settings.min_length,
        retries=settings.retries_per_file,
        match_fps=settings.match_fps,
        autosave_dir=autosave_dir,
    )
    return run, None


class BAC_OT_vse_bulk_import(Operator):
    """Import every video and audio file of the folder, one after the other, at the end of the timeline"""

    bl_idname = "sequencer.bac_bulk_import"
    bl_label = "Bulk Import"
    bl_options = {"UNDO"}  # no REGISTER: a redo from Adjust Last Operation would start a second import

    _timer = None
    _run: BulkImportRun | None = None

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def invoke(self, context, event):
        run, error = prepare_run(context)
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        self._run = run
        if run.autosave_dir is not None:
            message = f"Import {run.total} file(s) and write a copy into '{run.autosave_dir.name}' after each one?"
            return context.window_manager.invoke_confirm(
                self, event, title="Bulk Import with Autosave", message=message, confirm_text="Import", icon="INFO"
            )
        return self.execute(context)

    def execute(self, context):
        if self._run is None:  # called directly, without invoke
            run, error = prepare_run(context)
            if error:
                self.report({"ERROR"}, error)
                return {"CANCELLED"}
            self._run = run
        settings = settings_of(context)
        wm = context.window_manager
        wm.progress_begin(0, self._run.total)
        self._status(context, f"Bulk Import: 0/{self._run.total}")
        _common.start_timer(self, context, settings.pause_seconds)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        run = self._run
        if event.type == "ESC":
            self._finish(context, cancelled=True)
            return {"CANCELLED"}
        if event.type != "TIMER" or run is None:
            return {"PASS_THROUGH"}  # clicks, keys and scrubbing keep working during the run
        if run.done:
            self._finish(context)
            return {"FINISHED"}
        step = run.index + 1
        self._status(context, f"Bulk Import {step}/{run.total}: {run.current.name}")
        context.window_manager.progress_update(step)
        kind, note = run.step()
        if kind != "imported":
            level = "INFO" if kind == "short" else "WARNING"
            self.report({level}, f"Skipped {run.outcomes[-1][0]} ({note})")
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
        run = self._run
        text = run.summary(cancelled) if run else ("Cancelled" if cancelled else "Finished")
        if run and run.fps_changed:
            fps, base = run.fps_changed
            text += f"; scene frame rate set to {fps / base:g} fps"
        _common.set_status(wm, STATUS_PROP, f"Bulk Import – {text}")
        _common.set_status_text(context, None)
        self.report({"INFO"}, text)


class BAC_PT_vse_bulk_import(Panel):
    bl_label = "Bulk Import"
    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"
    bl_category = _common.CATEGORY
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        settings = settings_of(context)
        col = layout.column(align=True)
        col.label(text="Video and audio import at the end of the timeline")
        col.operator(BAC_OT_vse_bulk_import.bl_idname, icon="IMPORT")
        col.prop(settings, "import_dir")
        row = col.row(align=True)
        row.prop(settings, "pause_seconds")
        row.prop(settings, "retries_per_file")
        col.prop(settings, "min_length")
        col.prop(settings, "match_fps")
        col.prop(settings, "autosave")
        sub = col.row(align=True)
        sub.enabled = settings.autosave
        sub.prop(settings, "autosave_dir")
        _common.draw_status(col, context.window_manager, STATUS_PROP)
